"""
Deterministic content deduplication and hashing utilities.
"""

import hashlib
import re
from typing import List, Dict, Any, TypeVar

T = TypeVar("T")


def compute_content_hash(text: str) -> str:
    """Computes SHA-256 hash of normalized text for exact/near-duplicate detection."""
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def deduplicate_articles(items: List[Dict[str, Any]], hash_key: str = "content_hash") -> List[Dict[str, Any]]:
    """Filters duplicate dictionaries from a list based on content hash."""
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
