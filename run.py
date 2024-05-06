import feedparser
from openai import OpenAI
import os
import json
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import re


def load_config(config_path="config.json"):
    """Load the configuration from a JSON file."""
    with open(config_path, "r") as config_file:
        config = json.load(config_file)
    return config


# Example usage within your script
config = load_config()
rss_urls = config["rss_urls"]
interest_tags = config["interest_tags"]
# Adjust this regex pattern to match your ID format if necessary
id_pattern = re.compile(
    r"^\d+:\s"
)

MYKEY = os.environ.get("OPENAI_API_KEY")
GPT_MODEL = "gpt-4"  # Update this with your preferred model
RET_LANGUAGE = "中文"  # Update this with your preferred language
BSIZE = 20

# Path to save the summaries and logs
daily_base_path = "daily"
log_path = "log.txt"


def fetch_article_content(url):
    """Fetches the full article content from the given URL."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        # This is a simplified example. You'll need to adjust the selector based on the actual HTML structure of the webpage.
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


def filter_new_articles(articles, log_path):
    """Filters out articles that have already been logged."""
    if not os.path.exists(log_path):
        return articles  # If no log exists, all articles are new
    with open(log_path, "r") as log_file:
        logged_titles = [json.loads(line)["title"] for line in log_file]
    new_articles = [
        article for article in articles if article["title"] not in logged_titles
    ]
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
                model=GPT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a smart assistant that filters article titles based on the user's interest tags.",
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


def generate_summary_and_log(articles, summary_path, log_path):
    """Generates summaries for the given articles and logs the titles."""
    client = OpenAI(api_key=MYKEY)
    summaries = []

    with open(
        log_path, "a", encoding="utf-8"
    ) as log_file:  # Ensure file is opened with UTF-8 encoding
        for article in articles:
            # Use ensure_ascii=False to write non-ASCII characters directly
            log_entry = json.dumps(
                {"title": article["title"], "date": datetime.now().isoformat()},
                ensure_ascii=False,
            )
            log_file.write(log_entry + "\n")

            # Fetch full article content if 'summary' is not sufficient
            article_content = (
                fetch_article_content(article["link"])
                if "查看全文" in article["summary"]
                else article["summary"]
            )

            try:
                response = client.chat.completions.create(
                    model=GPT_MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a smart assistant that summarizes articles. Your summary will be only written in {RET_LANGUAGE}.",
                        },
                        {
                            "role": "user",
                            "content": "Exclude any references to author publicity and promotion and the summary should be straightforward within 50 to 200 characters in {RET_LANGUAGE}. Summarize the following:"
                            + article_content,
                        },
                    ],
                    temperature=0.7,
                )
                summary_text = response.choices[0].message.content.strip()
            except Exception as e:
                print(f"An error occurred while summarizing the article: {e}")
                summary_text = article_content  # Fallback to original content if the API call fails

            summaries.append(
                f"### {article['title']}\n\n- **链接**: [{article['link']}]({article['link']})\n- **摘要**: {summary_text}\n\n"
            )

    summary_content = "\n".join(summaries)
    with open(summary_path, "w") as summary_file:
        summary_file.write(summary_content)

    return summary_content


def main():
    articles = fetch_rss_articles(rss_urls)
    new_articles = filter_new_articles(articles, log_path)
    if not new_articles:
        print("No new articles found.")
        return
    interested_articles = filter_by_interest(new_articles, interest_tags)
    num_articles = len(interested_articles)
    if num_articles > 20:
        print(
            "Too many articles ({num_articles}) matched the interest tags. Please narrow down the interest tags."
        )
        # interested_articles = interested_articles[:10]
    if not interested_articles:
        print("No articles matched the interest tags.")
        return
    today = datetime.now().strftime("%Y-%m-%d")

    os.makedirs(daily_base_path, exist_ok=True)
    summary_path = f"{daily_base_path}/{today}.md"
    summary_content = generate_summary_and_log(
        interested_articles, summary_path, log_path
    )
    print(f"Daily summary generated and saved to {summary_path}")


if __name__ == "__main__":
    main()
