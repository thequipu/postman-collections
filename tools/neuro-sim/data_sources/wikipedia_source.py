"""Wikipedia random article summaries via REST API."""

import logging
import time

import requests

logger = logging.getLogger(__name__)

WIKI_RANDOM_URL = "https://en.wikipedia.org/api/rest_v1/page/random/summary"


def load_random_articles(count: int = 200) -> list[dict]:
    """Fetch random Wikipedia article summaries."""
    items = []
    failures = 0
    for i in range(count):
        try:
            resp = requests.get(WIKI_RANDOM_URL, timeout=10,
                                headers={"User-Agent": "NeuroSim/1.0 (quipu.test)"})
            if resp.ok:
                data = resp.json()
                extract = data.get("extract", "")
                if extract and len(extract) > 30:
                    items.append({
                        "content": extract,
                        "title": data.get("title", ""),
                        "domain": "general",
                        "source": "wikipedia/random",
                    })
            else:
                failures += 1
        except Exception:
            failures += 1
        # Rate-limit: ~100ms between requests
        if i < count - 1:
            time.sleep(0.1)
    logger.info("Loaded %d Wikipedia articles (%d failures)", len(items), failures)
    return items
