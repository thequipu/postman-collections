"""HuggingFace datasets — real-world content with substantial text for Neuro memory."""

import logging

logger = logging.getLogger(__name__)


def load_ag_news(max_items: int = 2000) -> list[dict]:
    """AG News — real news articles (business, sci/tech, sports, world).
    120K items available. Each item is 200-500 chars — substantial content."""
    from datasets import load_dataset
    try:
        ds = load_dataset("fancyzhx/ag_news", split=f"train[:{max_items}]")
        label_map = {0: "world", 1: "sports", 2: "finance", 3: "technology"}
        items = []
        for row in ds:
            text = row.get("text", "")
            if text and len(text) > 50:
                items.append({
                    "content": text.replace("\\", " "),
                    "domain": label_map.get(row.get("label", 3), "general"),
                    "source": "huggingface/ag_news",
                })
        logger.info("Loaded %d AG News items", len(items))
        return items
    except Exception as e:
        logger.warning("Failed to load ag_news: %s", e)
        return []


def load_squad_contexts(max_items: int = 2000) -> list[dict]:
    """SQuAD — Wikipedia reading comprehension paragraphs.
    87K items available. Each context is 300-2000 chars — rich factual content."""
    from datasets import load_dataset
    try:
        ds = load_dataset("rajpurkar/squad", split=f"train[:{max_items}]")
        seen_contexts = set()
        items = []
        for row in ds:
            ctx = row.get("context", "")
            title = row.get("title", "")
            # Deduplicate — SQuAD has multiple questions per context
            ctx_key = ctx[:100]
            if ctx_key in seen_contexts:
                continue
            seen_contexts.add(ctx_key)
            if ctx and len(ctx) > 100:
                items.append({
                    "content": ctx,
                    "title": title,
                    "domain": "general",
                    "source": "huggingface/squad",
                })
        logger.info("Loaded %d SQuAD context items (deduplicated)", len(items))
        return items
    except Exception as e:
        logger.warning("Failed to load squad: %s", e)
        return []


def load_sciq(max_items: int = 2000) -> list[dict]:
    """SciQ — science exam questions with supporting paragraphs.
    11K items available. Each support paragraph is 200-800 chars — factual science content."""
    from datasets import load_dataset
    try:
        ds = load_dataset("allenai/sciq", split=f"train[:{max_items}]")
        items = []
        for row in ds:
            support = row.get("support", "")
            question = row.get("question", "")
            answer = row.get("correct_answer", "")
            if support and len(support) > 50:
                # Combine question + answer + support for rich content
                content = f"{question} Answer: {answer}. {support}"
                items.append({
                    "content": content,
                    "domain": "science",
                    "source": "huggingface/sciq",
                })
        logger.info("Loaded %d SciQ items", len(items))
        return items
    except Exception as e:
        logger.warning("Failed to load sciq: %s", e)
        return []
