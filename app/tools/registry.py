"""
Tool registry and safe dispatcher preventing arbitrary execution and validating parameters.
"""

from typing import Dict, Any, Callable, Type, List, Optional
import inspect
from pydantic import BaseModel, Field, ValidationError

from app.tools.web_search import web_search
from app.tools.page_fetcher import fetch_page
from app.utils.logging import get_logger

logger = get_logger("tool_registry")


class WebSearchInput(BaseModel):
    """Validated input parameters for web_search tool."""
    query: str = Field(description="Search terms or query string")
    max_results: int = Field(default=5, ge=1, le=20, description="Number of results to retrieve (1-20)")


class PageFetcherInput(BaseModel):
    """Validated input parameters for page_fetcher tool."""
    url: str = Field(description="Target web page URL to fetch and parse")
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0, description="HTTP request timeout in seconds")
    max_size_bytes: int = Field(default=2_000_000, le=10_000_000, description="Max allowed response size in bytes")


class ToolDefinition:
    """Descriptor for a registered, safe tool."""
    def __init__(
        self,
        name: str,
        func: Callable,
        input_schema: Type[BaseModel],
        description: str,
    ):
        self.name = name
        self.func = func
        self.input_schema = input_schema
        self.description = description


class ToolRegistry:
    """Registry maintaining authorized tools and enforcing schema validation before execution."""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        func: Callable,
        input_schema: Type[BaseModel],
        description: str,
    ) -> None:
        """Registers a safe tool with its validation schema."""
        self._tools[name] = ToolDefinition(
            name=name,
            func=func,
            input_schema=input_schema,
            description=description,
        )
        logger.debug(f"Registered tool: '{name}'")

    def list_tools(self) -> List[str]:
        """Returns names of all authorized tools."""
        return list(self._tools.keys())

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Returns tool definition if registered."""
        return self._tools.get(name)

    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Validates arguments against the tool's Pydantic schema and invokes the tool.

        Raises:
            ValueError: If tool_name is unknown or if arguments fail validation.
        """
        tool_def = self._tools.get(tool_name)
        if not tool_def:
            allowed = ", ".join(f"'{t}'" for t in self._tools.keys())
            raise ValueError(
                f"Unauthorized or unknown tool: '{tool_name}'. Allowed registered tools: [{allowed}]."
            )

        # Validate arguments using Pydantic schema
        try:
            validated = tool_def.input_schema.model_validate(arguments or {})
        except ValidationError as e:
            raise ValueError(
                f"Invalid arguments for tool '{tool_name}': {e.errors()}"
            )

        # Execute callable
        kwargs = validated.model_dump()
        if inspect.iscoroutinefunction(tool_def.func):
            return await tool_def.func(**kwargs)
        else:
            return tool_def.func(**kwargs)


# Global default tool registry
TOOL_REGISTRY = ToolRegistry()
TOOL_REGISTRY.register(
    name="web_search",
    func=web_search,
    input_schema=WebSearchInput,
    description="Search the web for relevant sources, facts, and documents.",
)
TOOL_REGISTRY.register(
    name="page_fetcher",
    func=fetch_page,
    input_schema=PageFetcherInput,
    description="Fetch and extract readable text from a specific public URL.",
)
