import feedparser
from openai import OpenAI
import os
import json
import time
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import re
import shelve
import xxhash
import ollama


def load_config(config_path="config.json"):
    """Load the configuration from a JSON file."""
    with open(config_path, "r") as config_file:
        config = json.load(config_file)
    return config


try:
    config = load_config()
    rss_urls = config["rss_urls"]
    interest_tags = config["interest_tags"]
    # LLM_MODEL = "llama3"
    LLM_MODEL = "qwen:7b"
    BSIZE = 5
    daily_base_path = "ollama_daily"
    db_path = "ollama_history_titles"
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


def fetch_rss_articles(urls):
    """Fetches articles from the given RSS feed URLs."""
    articles = []
    for url in urls:
        feed = feedparser.parse(url)
        for index, entry in enumerate(feed.entries):
            articles.append(
                {
                    "id": index,
                    "title": entry.title,
                    "link": entry.link,
                    "summary": entry.summary,
                }
            )
    return articles


def hash_title(title):
    """Hashes the title using the xxHash algorithm."""
    return xxhash.xxh64(title).hexdigest()


def store_hashed_titles(articles, db_path="hashed_titles.db"):
    """store hashed titles in a shelve database"""
    with shelve.open(db_path) as db:
        for article in articles:
            hashed_title = hash_title(article["title"])
            db[hashed_title] = article["title"]


def filter_new_articles(articles, db_path="hashed_titles.db"):
    """Filters out articles that have already been logged."""
    new_articles = []
    with shelve.open(db_path) as db:
        for article in articles:
            hashed_title = hash_title(article["title"])
            if hashed_title not in db:
                new_articles.append(article)
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
    """Filters articles based on the user's interest tags."""

    def chunked_iterable(iterable, size):
        for i in range(0, len(iterable), size):
            yield iterable[i : i + size]

    interested_articles = []

    # Prepare a mapping of title IDs to articles
    title_id_map = {f"{article['id']}": article for article in articles}

    for titles_chunk in chunked_iterable(list(title_id_map.keys()), BSIZE):
        prompt_titles = [f"{id}: {title_id_map[id]['title']}" for id in titles_chunk]
        print(f"Titles: {prompt_titles}")
        messages = [
            {
                "role": "user",
                "content": (
                    "Please filter the news titles based on interest tags: {}\n\n"
                    "Here are titles: \n{}\n\n"
                    "Please return unordered list of titles"
                ).format(interest_tags, "\n".join(prompt_titles)),
            }
        ]

        try:
            response = ollama.chat(
                model=LLM_MODEL,
                messages=messages,
            )
            interested_ids_text = response["message"]["content"].strip()
            print(f"Interested IDs text: {interested_ids_text}")
        except Exception as e:
            print(f"An error occurred: {e}")
            continue

        interested_ids = extract_ids_from_response(interested_ids_text)
        print(f"Interested IDs: {interested_ids}")

        interested_articles.extend(
            title_id_map[id] for id in interested_ids if id in title_id_map
        )

    interested_articles = list(
        {article["id"]: article for article in interested_articles}.values()
    )

    return interested_articles


def generate_summary(articles, summary_path, interest_tags):
    """Generates summaries for the given articles and logs the titles."""
    last_time = time.time()
    summaries = []

    for i, article in enumerate(articles):
        article_content = (
            fetch_article_content(article["link"])
            if "查看全文" in article["summary"]
            else article["summary"]
        )

        messages = [
            {
                "role": "user",
                "content": (
                    f"请排除掉与兴趣标签无关的新闻：{interest_tags}\n"
                    f"并且排除任何作者宣传和推广的引用\n"
                    f"摘要应该简洁明了，长度在50到200个字符之间\n"
                    f"请对以下内容进行总结：{article_content}"
                ),
            }
        ]

        try:
            response = ollama.chat(
                model=LLM_MODEL,
                messages=messages,
            )
            summary_text = response["message"]["content"].strip()
        except Exception as e:
            print(f"An error occurred while summarizing the article: {e}")
            summary_text = (
                article_content  # Fallback to original content if the API call fails
            )

        summaries.append(
            f"### {article['title']}\n\n- **链接**: [{article['link']}]({article['link']})\n- **摘要**: {summary_text}\n\n"
        )
        if (i + 1) % BSIZE == 0:
            print(f"Processed {i + 1}/{len(articles)} articles.")
            print(f"Each article took {(time.time() - last_time)/BSIZE:.1f} seconds.")
            last_time = time.time()
            summary_content = "\n".join(summaries)
            with open(summary_path, "a") as summary_file:
                summary_file.write(summary_content)
            summaries = []
    summary_content = "\n".join(summaries)
    with open(summary_path, "a") as summary_file:
        summary_file.write(summary_content)


def main():
    articles = fetch_rss_articles(rss_urls)
    new_articles = filter_new_articles(articles, db_path)
    if not new_articles:
        print("No new articles found.")
        return
    store_hashed_titles(articles, db_path)

    # prefilter not working for now
    # interested_articles = filter_by_interest(new_articles, interest_tags)

    interested_articles = new_articles
    # num_articles = len(interested_articles)
    # if num_articles > 100:
    #     print(f"Too many articles ({num_articles}) matched the interest tags.")
    #     try:
    #         num_to_process = int(input("Enter the number of articles to process: "))
    #         if 0 < num_to_process <= num_articles:
    #             interested_articles = interested_articles[:num_to_process]
    #         else:
    #             print(f"Please enter a number between 1 and {num_articles}.")
    #     except ValueError:
    #         print("Please enter a valid number. Program exited, please run again.")
    #         return
    # elif num_articles == 0:
    #     print("No articles matched the interest tags.")
    #     return
    # else:
    #     print(f"{num_articles} articles matched the interest tags.")

    today = datetime.now().strftime("%Y-%m-%d")
    os.makedirs(daily_base_path, exist_ok=True)

    summary_path = f"{daily_base_path}/{today}.md"
    generate_summary(interested_articles, summary_path, interest_tags)
    print(f"Daily summary generated and saved to {summary_path}")


if __name__ == "__main__":
    main()
