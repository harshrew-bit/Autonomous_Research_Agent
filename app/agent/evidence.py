"""
Evidence extraction, relevance scoring, and aggregation pipeline for the autonomous research agent.
Converts raw fetched pages and search results into structured, traceable, deduplicated EvidenceItem sets.
"""

from typing import List, Dict, Any, Optional, Tuple
import re
from urllib.parse import urlparse

from app.models.schemas import EvidenceItem, FetchedPage, SearchResultItem
from app.utils.deduplication import compute_content_hash, deduplicate_evidence
from app.utils.logging import get_logger, TraceLogger

logger = get_logger("evidence")

# Common web boilerplate to reject during evidence extraction
BOILERPLATE_PATTERNS = [
    r"cookie policy",
    r"terms of service",
    r"privacy policy",
    r"all rights reserved",
    r"sign in to your account",
    r"subscribe to our newsletter",
    r"click here to",
    r"javascript is disabled",
    r"enable javascript",
    r"404 not found",
    r"page not found",
    r"access denied",
]


def extract_domain(url: str) -> str:
    """Extracts clean hostname/domain from a URL."""
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower() or "unknown"
    except Exception:
        return "unknown"


def calculate_relevance_score(text: str, query: str, topic: Optional[str] = None) -> float:
    """
    Computes a deterministic relevance score [0.0 - 1.0] based on lexical and topical overlap.

    Args:
        text: Candidate text excerpt or claim.
        query: User's original research question.
        topic: Identified core research topic or domain.

    Returns:
        Float score between 0.0 and 1.0.
    """
    if not text or not text.strip():
        return 0.0

    # Build reference keywords from query and topic
    ref_terms = f"{query} {topic or ''}".lower()
    # Filter stopwords and short punctuation
    words = re.findall(r"\b[a-z]{3,}\b", ref_terms)
    stopwords = {
        "the", "and", "for", "with", "this", "that", "from", "what", "which",
        "about", "how", "are", "can", "will", "all", "our", "your", "into",
        "recent", "advances", "research", "investigate", "study", "analysis"
    }
    keywords = {w for w in words if w not in stopwords}

    if not keywords:
        return 0.5  # Neutral fallback if no specific keywords exist

    text_lower = text.lower()
    text_words = set(re.findall(r"\b[a-z]{3,}\b", text_lower))

    # Keyword match count
    matched = keywords.intersection(text_words)
    if not matched:
        return 0.0

    keyword_coverage = len(matched) / len(keywords)

    # Keyword density in candidate text
    total_text_words = len(re.findall(r"\b\w+\b", text_lower))
    density = (len(matched) / max(total_text_words, 1)) * 5.0

    # Base match boost: matching distinct domain keywords provides strong baseline relevance
    base_match_boost = 0.25 + (0.1 * min(len(matched) - 1, 2))

    # Boost if topic phrase appears directly in text
    topic_phrase_boost = 0.2 if (topic and topic.lower() in text_lower) else 0.0
    query_phrase_boost = 0.2 if (len(query) < 40 and query.lower() in text_lower) else 0.0

    raw_score = (0.3 * keyword_coverage) + (0.2 * min(density, 1.0)) + base_match_boost + topic_phrase_boost + query_phrase_boost
    return round(min(max(raw_score, 0.0), 1.0), 3)


def classify_evidence_type(text: str) -> str:
    """Classifies the empirical nature of the evidence excerpt."""
    lower = text.lower()
    if re.search(r"\b\d+(\.\d+)?%\b|\b\d+ (percent|fold|times|increase|decrease)\b", lower):
        return "statistical"
    elif any(term in lower for term in ("benchmark", "accuracy", "latency", "f1-score", "precision", "recall")):
        return "benchmark"
    elif any(term in lower for term in ("architecture", "framework", "orchestration", "pipeline", "component")):
        return "architectural"
    elif any(term in lower for term in ("theory", "conjecture", "hypothesis", "fundamental", "paradigm")):
        return "theoretical"
    else:
        return "empirical"


def extract_candidate_evidence_from_text(
    content: str,
    source_url: str,
    source_title: str,
    query: str,
    topic: Optional[str] = None,
    min_paragraph_length: int = 60,
    max_paragraph_length: int = 1500,
) -> List[EvidenceItem]:
    """
    Extracts structured EvidenceItem candidates from raw cleaned page text.

    Args:
        content: Extracted body text from page.
        source_url: Source page URL.
        source_title: Source page title.
        query: Research query.
        topic: Optional core topic.
        min_paragraph_length: Minimum char length for a viable text block.
        max_paragraph_length: Maximum char length for a single evidence chunk.

    Returns:
        List of structured EvidenceItem candidates.
    """
    if not content or len(content.strip()) < min_paragraph_length:
        return []

    domain = extract_domain(source_url)
    paragraphs = re.split(r"\n\s*\n|\n(?=[A-Z0-9])", content)
    candidates: List[EvidenceItem] = []

    for para in paragraphs:
        cleaned = re.sub(r"\s+", " ", para.strip())
        if len(cleaned) < min_paragraph_length:
            continue

        # Truncate overly long single blocks
        if len(cleaned) > max_paragraph_length:
            cleaned = cleaned[:max_paragraph_length].rsplit(".", 1)[0] + "."

        # Check for boilerplate phrases
        if any(re.search(pat, cleaned, re.IGNORECASE) for pat in BOILERPLATE_PATTERNS):
            continue

        # Extract primary claim (first 1-2 sentences)
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned) if len(s.strip()) > 20]
        if not sentences:
            continue

        claim = sentences[0]
        if len(claim) < 35 and len(sentences) > 1:
            claim = f"{sentences[0]} {sentences[1]}"

        supporting_text = cleaned
        relevance = calculate_relevance_score(supporting_text, query, topic)
        ev_type = classify_evidence_type(supporting_text)
        content_hash = compute_content_hash(f"{claim} {supporting_text}")

        item = EvidenceItem(
            source_url=source_url,
            source_title=source_title or f"Document from {domain}",
            source_domain=domain,
            claim=claim,
            supporting_text=supporting_text,
            relevance_score=relevance,
            content_hash=content_hash,
            evidence_type=ev_type,
            extraction_reason=f"Topical excerpt relevant to '{query}' (score: {relevance})",
            confidence=0.9 if relevance >= 0.5 else 0.7,
        )
        candidates.append(item)

    return candidates


def filter_relevant_evidence(
    items: List[EvidenceItem],
    min_relevance: float = 0.35,
) -> Tuple[List[EvidenceItem], List[EvidenceItem]]:
    """
    Separates candidate evidence into relevant and irrelevant partitions.

    Args:
        items: List of candidate EvidenceItem instances.
        min_relevance: Cutoff threshold for acceptance.

    Returns:
        Tuple of (accepted_relevant_items, rejected_irrelevant_items).
    """
    accepted = []
    rejected = []
    for item in items:
        if item.relevance_score >= min_relevance:
            accepted.append(item)
        else:
            rejected.append(item)

    # Sort accepted items in descending order of relevance
    accepted.sort(key=lambda x: x.relevance_score, reverse=True)
    return accepted, rejected


async def process_evidence_pipeline(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    LangGraph node: Ingests fetched pages and search results, extracts candidate evidence,
    applies relevance filtering, deduplicates multi-signal items, and updates state.

    Workflow:
      raw pages / search snippets
            ↓
      candidate evidence extraction
            ↓
      relevance filtering
            ↓
      multi-signal deduplication
            ↓
      final structured evidence set
    """
    query = state.get("query", "")
    goal_analysis = state.get("goal_analysis")
    topic = getattr(goal_analysis, "topic", "") if goal_analysis else ""

    fetched_pages: List[FetchedPage] = state.get("fetched_pages", [])
    search_results: List[SearchResultItem] = state.get("search_results", [])

    TraceLogger.print_pipeline_stage(
        "EVIDENCE PROCESSING",
        "Extracting, relevance-filtering, and deduplicating candidate evidence",
    )

    candidates: List[EvidenceItem] = []

    # 1. Extract from all successfully fetched pages
    for page in fetched_pages:
        if page.success and page.content:
            page_candidates = extract_candidate_evidence_from_text(
                content=page.content,
                source_url=page.final_url or page.url,
                source_title=page.title or f"Page from {extract_domain(page.url)}",
                query=query,
                topic=topic,
            )
            candidates.extend(page_candidates)

    # 2. Extract from search result snippets as secondary/supplementary evidence
    for res in search_results:
        if res.snippet and len(res.snippet.strip()) >= 50:
            snippet_candidates = extract_candidate_evidence_from_text(
                content=res.snippet,
                source_url=res.url,
                source_title=res.title or res.source or "Search Result",
                query=query,
                topic=topic,
                min_paragraph_length=40,
            )
            candidates.extend(snippet_candidates)

    candidate_count = len(candidates)

    # 3. Relevance filtering
    relevant_items, rejected_items = filter_relevant_evidence(candidates, min_relevance=0.30)
    relevant_count = len(relevant_items)

    # 4. Multi-signal deduplication
    final_evidence: List[EvidenceItem] = deduplicate_evidence(relevant_items, similarity_threshold=0.75)
    deduped_count = len(final_evidence)
    duplicates_removed = relevant_count - deduped_count

    stats = {
        "candidates": candidate_count,
        "relevant": relevant_count,
        "duplicates_removed": duplicates_removed,
        "final": deduped_count,
    }

    logger.info(
        f"[evidence_pipeline] Ingested {candidate_count} candidates -> "
        f"{relevant_count} relevant -> {duplicates_removed} duplicates removed -> "
        f"{deduped_count} final evidence items."
    )

    TraceLogger.print_tool_success(
        "evidence_pipeline",
        f"Processed {candidate_count} candidates -> {deduped_count} verified evidence items ({duplicates_removed} duplicates removed)"
    )

    return {
        "evidence_items": final_evidence,
        "evidence_stats": stats,
        # Convert to legacy dict format for backwards compatibility with any state listeners
        "evidence": [item.model_dump() for item in final_evidence],
    }
