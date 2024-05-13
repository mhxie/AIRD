import feedparser
from openai import OpenAI
import openai
import random
import os
import json
import time
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import re
import shelve
import xxhash
import threading
from queue import Queue


def load_config(config_path="config.json"):
    """Load the configuration from a JSON file."""
    with open(config_path, "r") as config_file:
        config = json.load(config_file)
    return config


try:
    config = load_config()
    rss_urls = config["rss_urls"]
    interest_tags = config["interest_tags"]
    FILTER_MODEL = config["filter_model"]
    SUMMARY_MODEL = config["summary_model"]
    RET_LANGUAGE = config["language"]
    BSIZE = config["batch_size"]
    PSIZE = config["process_size"]
    MAX_TOKENS = config["max_tokens"]
    MYKEY = config["api_key"]
    daily_base_path = config["daily_base_path"]
    db_path = config["db_path"]
except KeyError:
    print("Configuration file is missing required fields.")
    exit(1)
# Adjust this regex pattern to match your ID format if necessary
id_pattern = re.compile(r"^\d+:\s")


def fetch_article_content(url):
    """Fetches the full article content from the given URL."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        article_text = soup.get_text(strip=True)
        return article_text
    except Exception as e:
        print(f"An error occurred while fetching the article content: {e}")
        return ""


def find_the_first_image(description):
    """Finds the first image URL in the feed entry description."""
    img_urls = re.findall(r'<img src="(.*?)"', description)
    if img_urls:
        return img_urls[0]
    return None


def clean_html_content(html_content):
    """Removes unnecessary HTML elements from the content."""
    soup = BeautifulSoup(html_content, "lxml")

    for script_or_style in soup(["script", "style"]):
        script_or_style.decompose()

    text = soup.get_text()

    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = "\n".join(chunk for chunk in chunks if chunk)
    return text


def fetch_rss_articles(urls):
    """Fetches articles from the given RSS feed URLs."""
    articles = []
    count = 0
    for url in urls:
        print(f"Fetching articles from {url}...")
        feed = feedparser.parse(url)
        if feed.bozo:
            print(f"Error fetching articles from {url}: {feed.bozo_exception}")
            continue

        for entry in feed.entries:
            article = {
                "id": count,
                "title": entry.title,
                "link": entry.link,
                "published": entry.get("published", ""),
                "updated": entry.get("updated", ""),
                "content": "",
                "image": "",
            }

            # If 'content' is an array, merge all elements into a single string
            if hasattr(entry, "content") and isinstance(entry.content, list):
                content_merged = "".join([item.value for item in entry.content])
                article["content"] = content_merged
            elif hasattr(entry, "description"):
                article["content"] = entry.description

            # Clean the HTML content
            article["content"] = clean_html_content(article["content"])
            # Extracting the first image from the content
            article["image"] = find_the_first_image(article["content"])

            articles.append(article)
            count += 1
    return articles


def hash_title(title):
    """Hashes the title using the xxHash algorithm."""
    return xxhash.xxh64(title).hexdigest()


def store_hashed_titles(articles, db_path="hashed_titles"):
    """store hashed titles in a shelve database"""
    with shelve.open(db_path) as db:
        for article in articles:
            hashed_title = hash_title(article["title"])
            db[hashed_title] = article["title"]


def filter_new_articles(articles, db_path="hashed_titles"):
    """Filters out articles that have already been logged."""
    new_articles = []
    with shelve.open(db_path) as db:
        for article in articles:
            hashed_title = hash_title(article["title"])
            if hashed_title not in db:
                new_articles.append(article)
    print(f"Removed {len(articles) - len(new_articles)} old articles.")
    return new_articles


def extract_ids_from_response(response_text):
    """
    Extracts IDs from the response text, filtering out any preamble or non-ID lines.
    """
    lines = response_text.split("\n")
    ids = []
    for line in lines:
        match = id_pattern.match(line)
        if match:
            # Extract the ID part before the colon (:)
            id_only = line.split(":", 1)[0].strip()
            ids.append(id_only)
    return ids


def filter_by_interest(articles, interest_tags):
    """Filters articles based on the user's interest tags. s"""

    def chunked_iterable(iterable, size):
        for i in range(0, len(iterable), size):
            yield iterable[i : i + size]

    client = OpenAI(api_key=MYKEY)
    interested_articles = []

    # Prepare a mapping of title IDs to articles
    title_id_map = {f"{article['id']}": article for article in articles}

    for titles_chunk in chunked_iterable(list(title_id_map.keys()), BSIZE):
        prompt_titles = [f"{id}: {title_id_map[id]['title']}" for id in titles_chunk]
        print(f"Titles: {prompt_titles}")
        prompt = "Filter titles by interest tags: {}\n\nTitles:\n{}\n".format(
            interest_tags, "\n".join(prompt_titles)
        )

        try:
            response = client.chat.completions.create(
                model=FILTER_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a smart assistant that filters article titles "
                            "based on the user's interest tags. Specifically, you should exclude "
                            "titles that are advertisements, including promotions, sales, "
                            "sponsored content, and any other form of paid content."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )
            interested_ids_text = response.choices[0].message.content.strip()
        except Exception as e:
            print(f"An error occurred: {e}")
            continue

        interested_ids = extract_ids_from_response(interested_ids_text)
        print(f"Interested IDs: {interested_ids}")

        # Continue with filtering articles based on the extracted interested IDs
        interested_articles.extend(
            title_id_map[id] for id in interested_ids if id in title_id_map
        )

    # Ensure uniqueness in case of overlapping interest matches
    interested_articles = list(
        {article["id"]: article for article in interested_articles}.values()
    )

    return interested_articles


def process_batch(tid, batch, summary_queue):
    """Processes a batch of articles and generates summaries."""
    client = OpenAI(api_key=MYKEY)
    summaries = []
    skipped_count = 0

    print(f"T-{tid}: started processing a new batch...")
    start_t = time.time()
    for article in batch:
        article_content = (
            fetch_article_content(article["link"])
            if "查看全文" in article["content"]
            else article["content"]
        )
        if len(article_content) < 200:
            summary = (
                f"### {article['title']}\n\n"
                f"- **链接**: [{article['link']}]({article['link']})\n"
                f"- **短文**: {article_content}\n"
            )
            if article["image"]:
                summary += f"- **图片**: ![]({article['image']})\n\n"
            summaries.append(summary)
            skipped_count += 1
            continue
        prompt_message = (
            "Exclude any references to author publicity and promotion and "
            "the summary should be straightforward within 50 to 200 characters "
            f"in {RET_LANGUAGE}."
        )

        attempt = 0
        while attempt < 3:
            try:
                response = client.chat.completions.create(
                    model=SUMMARY_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": prompt_message,
                        },
                        {
                            "role": "user",
                            "content": article_content,
                        },
                    ],
                    temperature=0.7,
                )
                summary_text = response.choices[0].message.content.strip()
                break
            except openai.BadRequestError:
                print(
                    f"T-{tid}: Bad request error, skipping the article and using the original content."
                )
                summary_text = article_content[:200]
                print(f"The malfunctioning prompt: {prompt_message}")
                skipped_count += 1
                break
            except openai.RateLimitError:
                time2sleep = random.randint(1, 10)
                print(
                    f"T-{tid}: Rate limit exceeded, waiting {time2sleep} seconds to retry..."
                )
                time.sleep(time2sleep)
                attempt += 1
            except Exception as e:
                print(
                    f"An error occurred while summarizing the article: {e}, using the original content."
                )
                summary_text = "Failed to summarize the article."
                skipped_count += 1
                break

        summary = (
            f"### {article['title']}\n\n"
            f"- **链接**: [{article['link']}]({article['link']})\n"
            f"- **摘要**: {summary_text}\n"
        )
        if article["image"]:
            summary += f"- **图片**: ![]({article['image']})\n\n"
        summaries.append(summary)
    print(
        f"T-{tid}: {len(batch)} articles (skipped: {skipped_count}) summarized in {time.time() - start_t:.2f} seconds."
    )
    summary_queue.put(summaries)


def generate_summary(articles, summary_path):
    """Generates summaries for the given articles and logs the titles."""
    summary_queue = Queue()
    threads = []

    tid = 0
    for i in range(0, len(articles), PSIZE):
        batch = articles[i : i + PSIZE]
        thread = threading.Thread(
            target=process_batch,
            args=(tid, batch, summary_queue),
        )
        threads.append(thread)
        thread.start()
        tid += 1

    for thread in threads:
        thread.join()

    summaries = []
    while not summary_queue.empty():
        summaries.extend(summary_queue.get())

    summary_content = "\n".join(summaries)
    with open(summary_path, "a") as summary_file:
        summary_file.write(summary_content)

    return summary_content


def main():
    articles = fetch_rss_articles(rss_urls)
    new_articles = filter_new_articles(articles, db_path)
    if not new_articles:
        print("No new articles found.")
        return
    store_hashed_titles(articles, db_path)

    interested_articles = filter_by_interest(new_articles, interest_tags)
    num_articles = len(interested_articles)
    if num_articles > 100:
        print(f"Too many articles ({num_articles}) matched the interest tags.")
        try:
            num_to_process = int(input("Enter the number of articles to process: "))
            if 0 < num_to_process <= num_articles:
                interested_articles = interested_articles[:num_to_process]
            else:
                print(f"Please enter a number between 1 and {num_articles}.")
        except ValueError:
            print("Please enter a valid number. Program exited, please run again.")
            return
    elif num_articles == 0:
        print("No articles matched the interest tags.")
        return
    else:
        print(f"{num_articles} articles matched the interest tags.")

    assert len(interested_articles) / PSIZE <= 16, "We only support 16 threads at most."
    today = datetime.now().strftime("%Y-%m-%d")
    os.makedirs(daily_base_path, exist_ok=True)

    summary_path = f"{daily_base_path}/{today}.md"
    summary_content = generate_summary(interested_articles, summary_path)
    print(f"Daily summary generated and saved to {summary_path}")


if __name__ == "__main__":
    main()
