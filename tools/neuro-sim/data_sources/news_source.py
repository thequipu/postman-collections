"""RSS news feeds — BBC technology, health, business, science."""

import logging

import feedparser

logger = logging.getLogger(__name__)

RSS_FEEDS = [
    ("https://feeds.bbci.co.uk/news/technology/rss.xml", "technology"),
    ("https://feeds.bbci.co.uk/news/health/rss.xml", "healthcare"),
    ("https://feeds.bbci.co.uk/news/business/rss.xml", "finance"),
    ("https://feeds.bbci.co.uk/news/science_and_environment/rss.xml", "science"),
]


def load_rss_news(items_per_feed: int = 50) -> list[dict]:
    """Pull headlines + summaries from public RSS feeds."""
    items = []
    for url, domain in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:items_per_feed]:
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                if title:
                    items.append({
                        "content": f"{title}. {summary}".strip(),
                        "domain": domain,
                        "source": f"rss/{domain}",
                    })
        except Exception as e:
            logger.warning("Failed to parse RSS %s: %s", url, e)
    logger.info("Loaded %d RSS news items", len(items))
    return items
