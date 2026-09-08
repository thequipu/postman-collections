"""Memory evaluation benchmark datasets from HuggingFace.

Sources:
  - LMEB (KaLM-Embedding/LMEB): 103 corpus files — dialogue, episodic, semantic, procedural
  - MemoryAgentBench (ai-hyz/MemoryAgentBench): multi-turn conflict resolution, retrieval
  - SciQ, SQuAD, AG News: science, factual, news content
"""

import json
import logging
import random

logger = logging.getLogger(__name__)


# ---- LMEB: Long-Term Memory Evaluation Benchmark ----
# Corpus files contain rich text across 4 memory types:
#   Dialogue (conversations), Episodic (events), Semantic (facts), Procedural (how-to)

LMEB_TASKS = [
    # Dialogue — conversations and memory across sessions
    ("Dialogue/LoCoMo/corpus.jsonl", "dialogue"),
    ("Dialogue/LongMemEval/corpus.jsonl", "dialogue"),
    ("Dialogue/REALTALK/corpus.jsonl", "dialogue"),
    ("Dialogue/TMD/corpus.jsonl", "dialogue"),
    ("Dialogue/ConvoMem/preference_evidence/corpus.jsonl", "dialogue"),
    ("Dialogue/ConvoMem/changing_evidence/corpus.jsonl", "dialogue"),
    ("Dialogue/ConvoMem/user_evidence/corpus.jsonl", "dialogue"),
    ("Dialogue/MemBench/knowledge_updating/corpus.jsonl", "dialogue"),
    ("Dialogue/MemBench/multi_hop/corpus.jsonl", "dialogue"),
    ("Dialogue/MemBench/preference/corpus.jsonl", "dialogue"),
    ("Dialogue/MemBench/single_hop/corpus.jsonl", "dialogue"),
    # Episodic — temporal event memory
    ("Episodic/EPBench/default_claude_long/corpus.jsonl", "episodic"),
    ("Episodic/EPBench/default_claude_short/corpus.jsonl", "episodic"),
    ("Episodic/EPBench/world_news_claude_long/corpus.jsonl", "episodic"),
    ("Episodic/EPBench/sci_fi_claude_long/corpus.jsonl", "episodic"),
    ("Episodic/KnowMeBench/event_driven/corpus.jsonl", "episodic"),
    ("Episodic/KnowMeBench/psychological_depth/corpus.jsonl", "episodic"),
    # Semantic — factual knowledge retrieval
    ("Semantic/SciFact/corpus.jsonl", "semantic"),
    ("Semantic/Covid-QA/corpus.jsonl", "semantic"),
    ("Semantic/QASPER/corpus.jsonl", "semantic"),
    ("Semantic/PeerQA/corpus.jsonl", "semantic"),
    ("Semantic/NovelQA/corpus.jsonl", "semantic"),
    ("Semantic/LooGLE/LongDepQA/corpus.jsonl", "semantic"),
    ("Semantic/LooGLE/ShortDepQA/corpus.jsonl", "semantic"),
    ("Semantic/ESG-Reports/corpus.jsonl", "semantic"),
    ("Semantic/MLDR/corpus.jsonl", "semantic"),
    # Procedural — task/tool memory
    ("Procedural/ToolBench/corpus.jsonl", "procedural"),
    ("Procedural/Proced_mem_bench/corpus.jsonl", "procedural"),
]


def load_lmeb() -> list[dict]:
    """Load corpus entries from LMEB benchmark — rich, diverse memory content."""
    from huggingface_hub import hf_hub_download

    items = []
    for file_path, domain in LMEB_TASKS:
        try:
            local_path = hf_hub_download(
                "KaLM-Embedding/LMEB", file_path, repo_type="dataset"
            )
            count = 0
            with open(local_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    text = row.get("text", "")
                    title = row.get("title", "")
                    if text and len(text) > 30:
                        content = f"{title}. {text}" if title else text
                        items.append({
                            "content": content[:2000],  # Cap very long entries
                            "domain": domain,
                            "source": f"lmeb/{file_path.split('/')[0]}/{file_path.split('/')[1]}",
                        })
                        count += 1
            logger.info("LMEB %s: %d items", file_path.split("/")[1], count)
        except Exception as e:
            logger.warning("Failed to load LMEB %s: %s", file_path, str(e)[:100])

    logger.info("LMEB total: %d items", len(items))
    return items


# ---- MemoryAgentBench: Multi-turn Memory Conflict Resolution ----

def load_memory_agent_bench() -> list[dict]:
    """Load MemoryAgentBench — context documents with memory conflicts and retrieval tasks."""
    from datasets import load_dataset

    items = []
    domain_map = {
        "Accurate_Retrieval": "semantic",
        "Conflict_Resolution": "episodic",
        "Long_Range_Understanding": "episodic",
        "Test_Time_Learning": "dialogue",
    }

    for split_name, domain in domain_map.items():
        try:
            ds = load_dataset("ai-hyz/MemoryAgentBench", split=split_name)
            for row in ds:
                context = row.get("context", "")
                if context and len(context) > 50:
                    # Split long contexts into 500-char chunks for realistic ingestion
                    for i in range(0, len(context), 500):
                        chunk = context[i:i + 500]
                        if len(chunk) > 30:
                            items.append({
                                "content": chunk,
                                "domain": domain,
                                "source": f"memoryagentbench/{split_name}",
                            })
            logger.info("MemoryAgentBench/%s: loaded", split_name)
        except Exception as e:
            logger.warning("Failed MemoryAgentBench/%s: %s", split_name, str(e)[:100])

    logger.info("MemoryAgentBench total: %d items", len(items))
    return items


# ---- AG News: Real news articles (business, tech, sports, world) ----

def load_ag_news() -> list[dict]:
    """Full AG News dataset — 120K real news articles."""
    from datasets import load_dataset
    try:
        ds = load_dataset("fancyzhx/ag_news", split="train")
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
        logger.info("AG News: %d items", len(items))
        return items
    except Exception as e:
        logger.warning("Failed AG News: %s", e)
        return []


# ---- SQuAD: Wikipedia reading comprehension paragraphs ----

def load_squad_contexts() -> list[dict]:
    """Full SQuAD dataset — deduplicated Wikipedia paragraphs."""
    from datasets import load_dataset
    try:
        ds = load_dataset("rajpurkar/squad", split="train")
        seen = set()
        items = []
        for row in ds:
            ctx = row.get("context", "")
            key = ctx[:100]
            if key in seen:
                continue
            seen.add(key)
            if ctx and len(ctx) > 100:
                items.append({
                    "content": ctx,
                    "title": row.get("title", ""),
                    "domain": "general",
                    "source": "huggingface/squad",
                })
        logger.info("SQuAD: %d unique contexts", len(items))
        return items
    except Exception as e:
        logger.warning("Failed SQuAD: %s", e)
        return []


# ---- SciQ: Science exam Q&A with explanations ----

def load_sciq() -> list[dict]:
    """Full SciQ dataset — science questions with supporting paragraphs."""
    from datasets import load_dataset
    try:
        ds = load_dataset("allenai/sciq", split="train")
        items = []
        for row in ds:
            support = row.get("support", "")
            question = row.get("question", "")
            answer = row.get("correct_answer", "")
            if support and len(support) > 50:
                content = f"{question} Answer: {answer}. {support}"
                items.append({
                    "content": content,
                    "domain": "science",
                    "source": "huggingface/sciq",
                })
        logger.info("SciQ: %d items", len(items))
        return items
    except Exception as e:
        logger.warning("Failed SciQ: %s", e)
        return []
