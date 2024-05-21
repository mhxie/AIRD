# AIRD: Your Personal AI RSS Daily

AIRD (AI RSS Daily) is your personal assistant for staying up-to-date with the latest content from your favorite RSS feeds. Tailored specifically for those who want to optimize their information intake, AIRD filters and summarizes articles based on your interests, making sure you only spend time on content that matters most to you.

## Features

- **Interest-Based Filtering**: Specify your interest tags to get articles that are most relevant to you. AIRD uses these tags to filter RSS feed content, ensuring you only see articles that match your specified interests.
- **Efficient Local Deduplication**: AIRD implements an advanced deduplication algorithm that runs locally. This means you won't be bothered by the same article more than once, even if you run AIRD frequently throughout the day.
- **Summarization**: Get concise summaries of articles instead of reading the full text. AIRD utilizes state-of-the-art AI to provide you with the gist of each article, saving you time.
- **Customizable Output**: Choose how you want to view your summarized content. AIRD supports output in both plain text and Markdown, making it easy to read or share your daily digest in your preferred format.
- **Secure and Private**: Your RSS feed subscriptions and interest tags are stored locally on your device. AIRD values your privacy and ensures that your data never leaves your computer.

## Getting Started

### Prerequisites

Before you start using AIRD, make sure you have the following installed on your machine:
- Python 3.6 or later
- Required Python packages: `feedparser`, `requests`, `beautifulsoup4`, `openai`, and `xxhash`.

### Installation

1. Clone the AIRD repository to your local machine:

```bash
git clone https://github.com/your-github/aird.git
```

2. Navigate to the AIRD directory:

```bash
cd aird
```

3. Install the required Python packages:

```bash
pip install -r requirements.txt
```

### Configuration

To tailor AIRD to your preferences, edit the `config.json` file. Here's a quick overview of key settings:

- **filter_model**: GPT model version for interest filter.
- **summary_model**: GPT model version for article summarization.
- **language**: Summary language, e.g. set to "中文" for Chinese.
- **batch_size**: Number of articles to be filtered per batch.
- **process_size**: Number of articles to be summarized per batch.
- **max_tokens**: Max number of tokens for each summary.
- **api_key**: Your OpenAI API key.
- **daily_base_path**: Directory for saving daily summaries.
- **db_path**: Database file path for deduplication.
- **rss_urls**: Active RSS feed URLs.
- **interest_tags**: Your interest tags for article filtering.
- **noise_tags**: Tags for articles to remove in article filtering.


### Running AIRD

To start AIRD, simply run the following command in your terminal:

```bash
python run.py
```


## Future Works

AIRD is committed to continuous improvement and expansion. Here's a shortlist of planned enhancements:

- [x] **Better Link Reader**: Improving the mechanism for fetching and interpreting article content from various RSS feeds.
- [ ] **Enhanced Configuration System**: Moving away from hardcoded configurations to a more dynamic and user-friendly setup process.
- [x] **Higher Concurrency**: Implementing more concurrent processing to handle multiple feeds and operations simultaneously, enhancing efficiency.
- [ ] **GitHub Actions Support**: Integrating with GitHub Actions for automated runs, making AIRD more accessible and easier to deploy.
- [ ] **Auto Tagging and Categorization**: Developing AI-driven features to automatically tag and categorize articles, refining content relevance.
- [ ] **Performance Optimization**: Continual efforts to optimize code and processes for faster execution and lower resource consumption.
- [x] **Batch Processing**: Adding the ability to process tasks in batches for increased efficiency and scalability, reducing cost significantly.

## Contributing

Contributions to AIRD are welcome! If you have suggestions for improvements or new features, feel free to open an issue or submit a pull request.

## License

AIRD is released under the MIT License. See the LICENSE file for more details.

---

Enjoy your personalized AI-powered RSS digest with AIRD – Your gateway to efficient and focused content consumption!