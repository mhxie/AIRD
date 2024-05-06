# AIRD: Your Personal AI RSS Daily

## Prerequisites
You need to have python3 installed on your system.
```
pip3 install -r requirements.txt
```

## Configuration

```
vi config.json
```

Your config.json should look like this:
```json
{
    "rss_urls": [
        "https://example.com/rss",
    ],
    "interest_tags": [
        "AI",
    ]
}

```

## Execution

```
python3 run.py
```

## Read
Your new daily will be saved under `daily_base_path` folder.

## Future Work
- Support efficient deduplication
- Better link reader
- Better configuration system (instead of hardcoding)
- Higher concurrency
- Support github actions
- Auto tagging and categorization
- Performance optimization