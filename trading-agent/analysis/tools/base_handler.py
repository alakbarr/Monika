from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class DisaggregatedToolResult:
    """
    Disaggregated tool execution result.
    - content: Concise, synthesized text block returned directly to LLM context (saving tokens).
    - details: Exhaustive raw data payload retained for audit logging, UI, and state persistence.
    """
    content: str
    details: Dict[str, Any] = field(default_factory=dict)


class ToolHandler(ABC):
    """Abstract base handler for an individual agent tool.
    
    Adheres to robust agent execution standards:
    - Single responsibility per tool handler
    - Explicit name, aliases, category, and parallel safety metadata
    - Self-registering decorator support
    - Streaming progress callback (on_update) support
    - Content/details disaggregation support
    """
    name: str = ""
    aliases: List[str] = []
    category: str = "GENERAL"
    description: str = ""
    parallel_safe: bool = True  # Whether this tool can be run in parallel with others
    protected: bool = False  # Whether this tool is protected against unprivileged invocation

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}

    @abstractmethod
    async def execute(
        self,
        args: Dict[str, Any],
        session: AsyncSession,
        executor: Optional[Any] = None,
        **kwargs: Any
    ) -> Any:
        """
        Execute the tool logic and return result payload.
        May return str, dict, or DisaggregatedToolResult(content=..., details=...).
        """
        pass
