"""
Deterministic content deduplication and hashing utilities.
"""

import hashlib
import re
from typing import List, Dict, Any, TypeVar, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.schemas import EvidenceItem

T = TypeVar("T")


def compute_content_hash(text: str) -> str:
    """Computes SHA-256 hash of normalized text for exact/near-duplicate detection."""
    normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def calculate_text_similarity(text1: str, text2: str) -> float:
    """
    Calculates token-level Jaccard similarity between two text strings [0.0 - 1.0].
    """
    if not text1 or not text2:
        return 0.0
    t1 = set(re.sub(r"[^\w\s]", "", text1.lower()).split())
    t2 = set(re.sub(r"[^\w\s]", "", text2.lower()).split())
    if not t1 or not t2:
        return 0.0
    intersection = len(t1.intersection(t2))
    union = len(t1.union(t2))
    return intersection / union if union > 0 else 0.0


def deduplicate_evidence(
    items: List[Any],
    similarity_threshold: float = 0.75,
) -> List[Any]:
    """
    Deduplicates EvidenceItem objects using multi-signal heuristics:
      1. Exact content hash filtering.
      2. High token similarity collapsing across duplicate or mirror claims.
      3. Preserving distinct claims even when sourced from the same URL or domain.

    Args:
        items: List of EvidenceItem instances.
        similarity_threshold: Threshold above which two items are deemed duplicates.

    Returns:
        Deduplicated list of EvidenceItem instances.
    """
    seen_hashes = set()
    unique_items = []

    for item in items:
        # 1. Exact content hash check
        h = getattr(item, "content_hash", None)
        if not h:
            h = compute_content_hash(f"{getattr(item, 'claim', '')} {getattr(item, 'supporting_text', '')}")
            if hasattr(item, "content_hash"):
                item.content_hash = h

        if h in seen_hashes:
            continue

        # 2. Semantic/lexical similarity check against already accepted items
        is_duplicate = False
        item_text = f"{getattr(item, 'claim', '')} {getattr(item, 'supporting_text', '')}"
        item_url = getattr(item, "source_url", "")

        for idx, existing in enumerate(unique_items):
            existing_text = f"{getattr(existing, 'claim', '')} {getattr(existing, 'supporting_text', '')}"
            existing_url = getattr(existing, "source_url", "")

            sim = calculate_text_similarity(item_text, existing_text)

            if sim >= similarity_threshold:
                is_duplicate = True
                # Keep the one with higher relevance or higher confidence
                if getattr(item, "relevance_score", 0.0) > getattr(existing, "relevance_score", 0.0):
                    unique_items[idx] = item
                break

        if not is_duplicate:
            seen_hashes.add(h)
            unique_items.append(item)

    return unique_items


def deduplicate_articles(items: List[Dict[str, Any]], hash_key: str = "content_hash") -> List[Dict[str, Any]]:
    """Filters duplicate dictionaries from a list based on content hash (legacy support)."""
    seen_hashes = set()
    deduped = []
    for item in items:
        h = item.get(hash_key)
        if not h and "content" in item:
            h = compute_content_hash(item["content"])
            item[hash_key] = h
        if h and h not in seen_hashes:
            seen_hashes.add(h)
            deduped.append(item)
    return deduped
