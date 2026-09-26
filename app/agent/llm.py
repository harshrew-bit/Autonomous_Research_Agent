"""
LLM provider abstraction supporting structured output generation, retries, and multi-provider backends.
"""

from abc import ABC, abstractmethod
import json
import os
from typing import Type, TypeVar, Optional, Dict, Any, List
from pydantic import BaseModel, ValidationError

from app.utils.logging import get_logger

logger = get_logger("llm_provider")

T = TypeVar("T", bound=BaseModel)


class LLMProvider(ABC):
    """Abstract base class for LLM providers supporting structured output generation."""

    @abstractmethod
    async def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        system_instruction: Optional[str] = None,
        retry_limit: int = 2,
    ) -> T:
        """
        Generates a structured Pydantic object from prompt using the LLM.

        Args:
            prompt: User prompt or objective description.
            response_schema: Pydantic model class defining the expected output structure.
            system_instruction: Optional system prompt or role guidance.
            retry_limit: Number of recovery retries if LLM output fails schema validation.

        Returns:
            Validated instance of response_schema.
        """
        pass

    @abstractmethod
    async def synthesize_research_report(
        self,
        research_question: str,
        goal_analysis: Optional[Any],
        evidence: List[Any],
        sources: List[Dict[str, Any]],
    ) -> Any:
        """
        Synthesizes a structured ResearchReport from gathered evidence items.

        Args:
            research_question: User's original research prompt.
            goal_analysis: Structured goal analysis breakdown.
            evidence: List of relevant, deduplicated EvidenceItem instances.
            sources: List of source metadata dictionaries.

        Returns:
            Structured ResearchReport instance.
        """
        pass


class GeminiProvider(LLMProvider):
    """Google Gemini LLM provider implementation using official google-genai SDK."""

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        self._client = None

    def _get_client(self):
        if not self._client:
            if not self.api_key:
                raise ValueError("GEMINI_API_KEY environment variable is not set.")
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    async def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        system_instruction: Optional[str] = None,
        retry_limit: int = 2,
    ) -> T:
        from google.genai import types
        client = self._get_client()

        current_prompt = prompt
        last_error = None

        for attempt in range(retry_limit + 1):
            try:
                config = types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=response_schema,
                    system_instruction=system_instruction,
                    temperature=0.2,
                )

                response = client.models.generate_content(
                    model=self.model_name,
                    contents=current_prompt,
                    config=config,
                )

                raw_text = response.text
                if not raw_text:
                    raise ValueError("Received empty response from Gemini model.")

                # Validate JSON against schema
                if isinstance(raw_text, str):
                    parsed_json = json.loads(raw_text)
                    return response_schema.model_validate(parsed_json)
                elif isinstance(raw_text, response_schema):
                    return raw_text

            except (json.JSONDecodeError, ValidationError, ValueError) as e:
                last_error = e
                logger.warning(
                    f"Structured generation attempt {attempt + 1}/{retry_limit + 1} failed for {response_schema.__name__}: {e}"
                )
                if attempt < retry_limit:
                    current_prompt = (
                        f"{prompt}\n\n"
                        f"[SYSTEM RECOVERY NOTICE]: Your previous response failed schema validation with error: {e}.\n"
                        f"Please produce strictly valid JSON conforming exactly to the required schema: {response_schema.model_json_schema()}."
                    )

        raise RuntimeError(
            f"Failed to generate valid {response_schema.__name__} after {retry_limit + 1} attempts. Last error: {last_error}"
        )

    async def synthesize_research_report(
        self,
        research_question: str,
        goal_analysis: Optional[Any],
        evidence: List[Any],
        sources: List[Dict[str, Any]],
    ) -> Any:
        from app.models.schemas import ResearchReport
        evidence_text = "\n\n".join(
            f"Source URL: {getattr(e, 'source_url', '')}\n"
            f"Title: {getattr(e, 'source_title', '')}\n"
            f"Claim: {getattr(e, 'claim', '')}\n"
            f"Supporting Text: {getattr(e, 'supporting_text', '')}\n"
            f"Relevance: {getattr(e, 'relevance_score', 1.0)}"
            for e in evidence
        )
        sources_text = "\n".join(
            f"- {s.get('title', 'Unknown')}: {s.get('url', '')}"
            for s in sources
        )
        prompt = (
            f"Synthesize a rigorous, objective final Research Report answering this research question:\n"
            f"\"{research_question}\"\n\n"
            f"Gathered Evidence Items ({len(evidence)} total):\n{evidence_text or 'No direct evidence chunks gathered.'}\n\n"
            f"Identified Sources ({len(sources)} total):\n{sources_text or 'None.'}\n\n"
            "Requirements:\n"
            "1. Ground all key findings strictly in the provided evidence. Cite supporting source URLs.\n"
            "2. Avoid fabricating facts, metrics, or citations.\n"
            "3. If evidence is sparse, clearly explain the empirical limitations in the limitations field.\n"
            "4. Provide practical, supported actionable insights."
        )
        system_instruction = (
            "You are an expert autonomous research synthesis analyst. Your job is to produce a high-fidelity, "
            "factually grounded research report using only retrieved evidence."
        )
        return await self.generate_structured(prompt, ResearchReport, system_instruction=system_instruction)


class MockLLMProvider(LLMProvider):
    """Deterministic mock provider for unit testing without live API keys."""

    def __init__(self, mock_responses: Optional[Dict[str, BaseModel]] = None):
        self.mock_responses = mock_responses or {}

    def register_mock_response(self, schema_name: str, response: BaseModel):
        self.mock_responses[schema_name] = response

    async def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        system_instruction: Optional[str] = None,
        retry_limit: int = 2,
    ) -> T:
        schema_name = response_schema.__name__
        if schema_name in self.mock_responses:
            mock_obj = self.mock_responses[schema_name]
            if isinstance(mock_obj, response_schema):
                return mock_obj

        # Default fallback mock generation based on schema
        logger.info(f"[MockLLMProvider] Generating default mock object for {schema_name}")
        return self._generate_default_mock(response_schema, prompt)

    def _generate_default_mock(self, schema: Type[T], prompt: str) -> T:
        from app.models.schemas import GoalAnalysis, Plan, Task, TaskStatus

        if schema == GoalAnalysis:
            return GoalAnalysis(
                objective=f"Analyze goal: {prompt}",
                topic="Software Engineering & AI",
                constraints=["Comprehensive synthesis"],
                time_range="Recent",
                output_requirements=["Structured analysis"],
                success_criteria=["Complete report"],
            ) # type: ignore
        elif schema == Plan:
            is_replan = "replan" in prompt.lower() or "revised" in prompt.lower()
            topic = "Agentic AI"
            if 'User Query:\n"' in prompt:
                try:
                    topic = prompt.split('User Query:\n"')[1].split('"')[0].strip()
                except Exception:
                    pass
            elif 'Original Query: "' in prompt:
                try:
                    topic = prompt.split('Original Query: "')[1].split('"')[0].strip()
                except Exception:
                    pass
            elif len(prompt) < 100:
                topic = prompt.strip()

            if is_replan:
                tasks = [
                    Task(
                        id="task_replan_1",
                        description=f"Search alternative broader sources for {topic}",
                        objective="Gather broadened search results",
                        expected_output="Expanded search URLs",
                        suggested_tool="web_search",
                        tool_input={"query": f"{topic} alternative perspectives"},
                    ),
                    Task(
                        id="task_replan_2",
                        description=f"Extract page content from expanded sources on {topic}",
                        objective="Fetch new evidence chunks",
                        expected_output="Detailed text excerpts",
                        suggested_tool="page_fetcher",
                    ),
                ]
                rationale = f"Adaptive recovery plan broadening search keywords for '{topic}' after initial strategy failure."
            else:
                tasks = [
                    Task(
                        id="task_1",
                        description=f"Search authoritative sources regarding {topic}",
                        objective="Gather candidate research links",
                        expected_output="Candidate search results",
                        suggested_tool="web_search",
                        tool_input={"query": f"{topic} latest developments"},
                    ),
                    Task(
                        id="task_2",
                        description=f"Extract detailed content from top discovered source for {topic}",
                        objective="Extract structured evidence from web page",
                        expected_output="Cleaned text content",
                        suggested_tool="page_fetcher",
                    ),
                ]
                rationale = f"Dynamic execution plan combining external search and deep content extraction for '{topic}'."

            return Plan(
                query=prompt,
                rationale=rationale,
                tasks=tasks,
            ) # type: ignore
        elif schema.__name__ == "ResearchReport":
            from app.models.schemas import ResearchReport, KeyFinding, SourceCitation
            topic = "Autonomous Research"
            if 'research question:\n"' in prompt:
                try:
                    topic = prompt.split('research question:\n"')[1].split('"')[0].strip()
                except Exception:
                    pass
            elif len(prompt) < 100:
                topic = prompt.strip()

            findings = [
                KeyFinding(
                    claim=f"Autonomous tool orchestration significantly improves research fidelity for {topic}.",
                    explanation=(
                        f"Empirical observations confirm that proactive goal decomposition paired with dynamic tool invocation "
                        f"allows autonomous agents to navigate complex information landscapes related to {topic}."
                    ),
                    supporting_source_urls=["https://example.com/research-1"],
                ),
                KeyFinding(
                    claim="Multi-signal deduplication and relevance filtering prevent hallucinated citations.",
                    explanation=(
                        "Filtering low-relevance content blocks and clustering near-duplicate extracts eliminates redundant claims "
                        "and establishes strict source attribution for all synthesized findings."
                    ),
                    supporting_source_urls=["https://example.com/research-2"],
                ),
            ]
            citations = [
                SourceCitation(
                    url="https://example.com/research-1",
                    title=f"Architectural Paradigms in {topic}",
                    domain="example.com",
                    relevant_excerpts_count=2,
                ),
                SourceCitation(
                    url="https://example.com/research-2",
                    title="Evaluation and Deduplication Frameworks",
                    domain="example.com",
                    relevant_excerpts_count=1,
                ),
            ]
            return ResearchReport(
                research_question=topic,
                topic=topic,
                executive_summary=(
                    f"This report presents an evidence-backed synthesis of {topic}. "
                    "Through systematic web exploration, selective content extraction, and multi-signal deduplication, "
                    "the autonomous agent isolated key principles governing adaptive reasoning and empirical validation."
                ),
                key_findings=findings,
                important_evidence=[],
                sources=citations,
                actionable_insights=[
                    f"Adopt structured Pydantic schemas across all tool interfaces when researching {topic}.",
                    "Implement lexical and content-hash deduplication before passing external observations to the synthesis layer.",
                ],
                limitations=[
                    "Findings are bounded by the accessible public sources retrieved during the execution session.",
                    "Live dynamic pages with client-side JavaScript execution may require headless browser rendering for deeper retrieval.",
                ],
            ) # type: ignore

        raise ValueError(f"No mock generator implemented for schema {schema.__name__}")

    async def synthesize_research_report(
        self,
        research_question: str,
        goal_analysis: Optional[Any],
        evidence: List[Any],
        sources: List[Dict[str, Any]],
    ) -> Any:
        from app.models.schemas import ResearchReport, KeyFinding, SourceCitation
        # Extract unique sources from evidence
        seen_urls = {}
        for ev in evidence:
            url = getattr(ev, "source_url", "")
            title = getattr(ev, "source_title", "External Source")
            domain = getattr(ev, "source_domain", None)
            if not domain and "/" in url:
                domain = url.split("/")[2]
            if url:
                if url not in seen_urls:
                    seen_urls[url] = {"url": url, "title": title, "domain": domain or "web", "count": 0}
                seen_urls[url]["count"] += 1

        citations = [
            SourceCitation(
                url=data["url"],
                title=data["title"],
                domain=data["domain"],
                relevant_excerpts_count=data["count"],
            )
            for data in seen_urls.values()
        ]
        if not citations and sources:
            citations = [
                SourceCitation(
                    url=s.get("url", "https://example.com"),
                    title=s.get("title", "Discovered Source"),
                    domain=s.get("source", "web"),
                    relevant_excerpts_count=1,
                )
                for s in sources[:3]
            ]
        if not citations:
            citations = [
                SourceCitation(
                    url="https://example.com",
                    title="Reference Overview",
                    domain="example.com",
                    relevant_excerpts_count=1,
                )
            ]

        findings = []
        for i, ev in enumerate(evidence[:4]):
            findings.append(
                KeyFinding(
                    claim=getattr(ev, "claim", f"Simulated observation on '{research_question}'"),
                    explanation=getattr(ev, "supporting_text", f"Mock context excerpt extracted for '{research_question}'"),
                    supporting_source_urls=[getattr(ev, "source_url", "https://example.com")],
                )
            )

        if not findings:
            findings = [
                KeyFinding(
                    claim=f"Deterministic mock pipeline validated for query '{research_question}'.",
                    explanation=f"Demonstration run executed using mock providers to verify goal decomposition and tool orchestration.",
                    supporting_source_urls=[c.url for c in citations[:1]],
                )
            ]

        topic_str = research_question.strip()

        return ResearchReport(
            research_question=research_question,
            topic=topic_str,
            executive_summary=(
                f"This report presents a simulated synthesis for '{research_question}' generated in mock/demo execution mode. "
                f"The analysis is deterministically grounded in {len(evidence)} mock evidence items extracted from test sources. "
                "In production mode with live Gemini and Tavily API credentials, real-world web sources are retrieved, verified, and synthesized."
            ),
            key_findings=findings,
            important_evidence=evidence[:5],
            sources=citations,
            actionable_insights=[
                f"Execute with live SEARCH_PROVIDER=tavily and LLM_PROVIDER=gemini to conduct real-world research on '{research_question}'.",
                "Maintain strict evidence schema validation and multi-signal deduplication to ensure traceability in production runs.",
            ],
            limitations=[
                "SIMULATED EVALUATION: Report was generated using MockLLMProvider and MockSearchProvider for offline assessment demonstration.",
                "No live external HTTP requests were dispatched to real-world knowledge repositories.",
                "Empirical validity and real-world domain findings require live execution with authenticated provider API keys.",
            ],
        )


def get_llm_provider(provider_type: Optional[str] = None) -> LLMProvider:
    """Factory function returning configured LLMProvider instance."""
    provider = (provider_type or os.getenv("LLM_PROVIDER", "gemini")).lower()

    if provider == "gemini":
        return GeminiProvider()
    elif provider == "mock":
        return MockLLMProvider()
    else:
        raise ValueError(f"Unsupported LLM_PROVIDER: '{provider}'. Supported options: 'gemini', 'mock'.")
