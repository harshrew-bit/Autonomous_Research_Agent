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


class GeminiProvider(LLMProvider):
    """Google Gemini LLM provider implementation using official google-genai SDK."""

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
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
            tasks = [
                Task(
                    id="task_1",
                    description=f"Search information for {prompt}",
                    objective="Gather raw sources",
                    expected_output="Search result links",
                    suggested_tool="web_search",
                ),
                Task(
                    id="task_2",
                    description="Extract page content from top sources",
                    objective="Fetch detailed content",
                    expected_output="Extracted text chunks",
                    suggested_tool="page_fetcher",
                ),
                Task(
                    id="task_3",
                    description="Evaluate relevance and synthesize findings",
                    objective="Produce final report",
                    expected_output="Structured summary report",
                    suggested_tool="report_writer",
                ),
            ]
            return Plan(
                query=prompt,
                rationale="Mock execution plan with search, fetch, and report steps",
                tasks=tasks,
            ) # type: ignore

        raise ValueError(f"No mock generator implemented for schema {schema.__name__}")


def get_llm_provider(provider_type: Optional[str] = None) -> LLMProvider:
    """Factory function returning configured LLMProvider instance."""
    provider = (provider_type or os.getenv("LLM_PROVIDER", "gemini")).lower()

    if provider == "gemini":
        return GeminiProvider()
    elif provider == "mock":
        return MockLLMProvider()
    else:
        raise ValueError(f"Unsupported LLM_PROVIDER: '{provider}'. Supported options: 'gemini', 'mock'.")
