# ==============================================================================
# File: analysis/tools/base_handler.py
# ==============================================================================

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession


class ToolHandler(ABC):
    """Abstract base handler for an individual agent tool.
    
    Adheres to robust agent execution standards:
    - Single responsibility per tool handler
    - Explicit name, aliases, category, and parallel safety metadata
    - Self-registering decorator support
    """
    name: str = ""
    aliases: List[str] = []
    category: str = "GENERAL"
    description: str = ""
    parallel_safe: bool = True  # Whether this tool can be run in parallel with others

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}

    @abstractmethod
    async def execute(
        self,
        args: Dict[str, Any],
        session: AsyncSession,
        executor: Optional[Any] = None,
        **kwargs
    ) -> Any:
        """Execute the tool logic and return the result payload (dict, str, or JSON-serializable)."""
        pass
