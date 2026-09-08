"""DataPool — downloads real data from internet, caches locally, serves to users.

Data sources:
  - LMEB (KaLM-Embedding/LMEB) — 27 corpus files: dialogue, episodic, semantic, procedural
  - MemoryAgentBench (ai-hyz/MemoryAgentBench) — multi-turn memory conflicts
  - AG News (fancyzhx/ag_news) — 120K real news articles
  - SQuAD (rajpurkar/squad) — Wikipedia paragraphs
  - SciQ (allenai/sciq) — science Q&A with explanations
  - Wikipedia API — random article summaries
  - BBC RSS — live news feeds
"""

import json
import logging
import random
from pathlib import Path

logger = logging.getLogger(__name__)


class DataPool:
    """Downloads from HuggingFace benchmarks + Wikipedia + RSS, caches to disk,
    serves random-sized unique slices to each simulated user."""

    def __init__(self, cache_dir: str = "./cache",
                 enable_huggingface: bool = True,
                 enable_wikipedia: bool = True,
                 enable_rss: bool = True,
                 hf_items: int = 0,  # 0 = load full dataset
                 wiki_items: int = 200,
                 rss_items: int = 200,
                 min_items_per_user: int = 100,
                 max_items_per_user: int = 500):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.enable_hf = enable_huggingface
        self.enable_wiki = enable_wikipedia
        self.enable_rss = enable_rss
        self.hf_items = hf_items
        self.wiki_items = wiki_items
        self.rss_items = rss_items
        self.min_items_per_user = min_items_per_user
        self.max_items_per_user = max_items_per_user
        self.pool: list[dict] = []

    def setup(self):
        """Download (or load from cache) all data sources. Call once at startup."""
        if self.enable_hf:
            # Memory evaluation benchmarks
            self._load_cached("lmeb", "data_sources.memory_benchmarks", "load_lmeb")
            self._load_cached("memoryagentbench", "data_sources.memory_benchmarks", "load_memory_agent_bench")
            # General knowledge datasets
            self._load_cached("ag_news", "data_sources.memory_benchmarks", "load_ag_news")
            self._load_cached("squad_contexts", "data_sources.memory_benchmarks", "load_squad_contexts")
            self._load_cached("sciq", "data_sources.memory_benchmarks", "load_sciq")

        if self.enable_wiki:
            self._load_wikipedia()

        if self.enable_rss:
            self._load_rss()

        # Shuffle so users get varied domains
        random.shuffle(self.pool)
        logger.info("DataPool ready: %d items (%.1f MB)",
                    len(self.pool),
                    sum(len(i["content"]) for i in self.pool) / 1024 / 1024)
        if len(self.pool) == 0:
            raise RuntimeError(
                "DataPool has 0 items — check network connectivity and data source config"
            )

    # ---- Cache helpers ----

    def _cache_path(self, name: str) -> Path:
        return self.cache_dir / f"{name}.json"

    def _cached(self, name: str) -> bool:
        p = self._cache_path(name)
        return p.exists() and p.stat().st_size > 10

    def _save_cache(self, name: str, items: list[dict]):
        with open(self._cache_path(name), "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False)
        logger.info("Cached %d items as %s (%.1f MB)",
                    len(items), name,
                    sum(len(i["content"]) for i in items) / 1024 / 1024)

    def _load_cache(self, name: str) -> list[dict]:
        with open(self._cache_path(name), "r", encoding="utf-8") as f:
            return json.load(f)

    # ---- Generic cache-through loader ----

    def _load_cached(self, cache_name: str, module_path: str, func_name: str):
        """Load from cache, or import and call the loader function."""
        if not self._cached(cache_name):
            import importlib
            mod = importlib.import_module(module_path)
            loader = getattr(mod, func_name)
            items = loader()
            if items:
                self._save_cache(cache_name, items)
        if self._cached(cache_name):
            self.pool.extend(self._load_cache(cache_name))

    def _load_wikipedia(self):
        name = "wiki_random"
        if not self._cached(name):
            from data_sources.wikipedia_source import load_random_articles
            items = load_random_articles(self.wiki_items)
            if items:
                self._save_cache(name, items)
        if self._cached(name):
            self.pool.extend(self._load_cache(name))

    def _load_rss(self):
        name = "rss_news"
        if not self._cached(name):
            from data_sources.news_source import load_rss_news
            items = load_rss_news(self.rss_items // 4)
            if items:
                self._save_cache(name, items)
        if self._cached(name):
            self.pool.extend(self._load_cache(name))

    # ---- Serving ----

    def get_items_for_user(self, user_index: int, count: int = 0) -> list[dict]:
        """Get a unique data slice for a specific user.

        If count=0, assigns a random number of items between
        min_items_per_user and max_items_per_user (seeded by user_index
        for reproducibility).
        """
        if count <= 0:
            rng = random.Random(user_index)
            count = rng.randint(self.min_items_per_user, self.max_items_per_user)

        start = (user_index * self.max_items_per_user) % len(self.pool)
        items = self.pool[start:start + count]
        if len(items) < count:
            items += self.pool[:count - len(items)]
        return items

    def get_random_query(self, user_data: list[dict]) -> str:
        """Generate a recall query from a user's assigned data."""
        item = random.choice(user_data)
        words = item["content"].split()
        query_words = random.sample(words, min(5, len(words)))
        return " ".join(query_words)

    def __len__(self):
        return len(self.pool)
