"""
Enhanced semantic iterator with fast/slow extraction modes.
Path: src/skills/semantic_iterator.py
"""

from typing import List, Dict, Any, Optional, Iterator, Union
import structlog
import json
import asyncio
from dataclasses import dataclass
from enum import Enum
from .shared.types import ExtractConfig
from src.agents.base import BaseAgent, LLMProvider, AgentResponse, LLMConfigError

logger = structlog.get_logger()

class ExtractionMode(str, Enum):
    """Available extraction modes"""
    FAST = "fast"  # Direct extraction from structured data
    SLOW = "slow"  # Sequential item-by-item extraction

@dataclass
class ExtractionState:
    """Tracks extraction state"""
    current_mode: ExtractionMode
    attempted_modes: List[ExtractionMode]
    items: List[Any]
    position: int = 0
    raw_response: str = ""
    error: Optional[str] = None
    format: str = "json"
    instruction: str = ""

class ItemIterator:
    """Iterator over extracted items"""
    
    def __init__(self, state: ExtractionState, agent: 'SemanticIterator'):
        self._state = state
        self._agent = agent
        self._loop = None
        logger.debug("iterator.initialized",
                    mode=state.current_mode,
                    items_count=len(state.items))

    @property
    def state(self) -> ExtractionState:
        """Access to iterator state"""
        return self._state

    def _ensure_loop(self):
        """Infrastructure concern: Ensure async event loop"""
        try:
            self._loop = asyncio.get_event_loop()
        except RuntimeError:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

    def __iter__(self):
        return self

    def __next__(self) -> Any:
        """Progress through items with mode-specific handling"""
        try:
            self._ensure_loop()
            result = self._loop.run_until_complete(self._get_next())
            return result
        except StopAsyncIteration:
            raise StopIteration()

    async def _get_next(self) -> Any:
        """Get next item using current mode"""
        try:
            if self._state.current_mode == ExtractionMode.FAST:
                if self._state.position >= len(self._state.items):
                    # Try fallback to slow mode if configured
                    if (self._agent.allow_fallback and 
                        ExtractionMode.SLOW not in self._state.attempted_modes):
                        logger.info("extraction.fallback_to_slow")
                        self._state.current_mode = ExtractionMode.SLOW
                        self._state.attempted_modes.append(ExtractionMode.SLOW)
                        return await self._get_next()
                    raise StopAsyncIteration()
                
                item = self._state.items[self._state.position]
                self._state.position += 1
                return item
            else:
                return await self._get_slow_item()

        except Exception as e:
            logger.error("iterator.error", error=str(e))
            raise StopAsyncIteration()

    async def _get_slow_item(self) -> Any:
        """Get next item using slow extraction"""
        try:
            # Create extraction request
            request = {
                "content": self._state.raw_response,
                "position": self._state.position,
                "format": self._state.format,
                "instruction": self._state.instruction,
                "mode": "slow"
            }

            # Use agent's process method
            result = await self._agent.process(request)
            
            if not result.success:
                raise StopAsyncIteration

            # Handle NO_MORE_ITEMS signal
            if isinstance(result.data.get("response"), str):
                if "NO_MORE_ITEMS" in result.data["response"].upper():
                    raise StopAsyncIteration

            # Extract and validate item
            item = result.data.get("item")
            if item:
                self._state.position += 1
                return item
            else:
                raise StopAsyncIteration

        except Exception as e:
            logger.error("slow_extract.failed", error=str(e))
            raise StopAsyncIteration

class SemanticIterator(BaseAgent):
    """Agent for iterative semantic extraction"""
    
    def __init__(self, 
                 provider: LLMProvider,
                 model: str,
                 temperature: float = 0,
                 config: Optional[Dict[str, Any]] = None,
                 extraction_modes: Optional[List[str]] = None,
                 allow_fallback: bool = True):
        """Initialize with standard agent configuration"""
        super().__init__(
            provider=provider,
            model=model,
            temperature=temperature,
            config=config
        )
        
        self.modes = [ExtractionMode(m) for m in (extraction_modes or ["fast", "slow"])]
        self.allow_fallback = allow_fallback

    def _get_agent_name(self) -> str:
        """Required by BaseAgent"""
        return "semantic_iterator"

    @staticmethod
    def _generate_ordinal(n: int) -> str:
        """Generate ordinal string (1st, 2nd, 3rd, etc.)"""
        if 10 <= n % 100 <= 20:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
        return f"{n}{suffix}"

    def _format_request(self, context: Dict[str, Any]) -> str:
        """Format LLM request based on mode"""
        mode = context.get("mode", "fast")
        content = context.get("content", "")
        position = context.get("position", 0)
        fmt = context.get("format", "json")
        instruction = context.get("instruction", "")

        if mode == "slow":
            # Calculate ordinal for precise item extraction
            ordinal = self._generate_ordinal(position + 1)
            
            prompt = self._get_prompt('slow_extract')
            if not prompt:
                raise LLMConfigError("Missing slow_extract prompt configuration")
                
            return prompt.format(
                ordinal=ordinal,
                content=content,
                format=fmt,
                instruction=instruction
            )
        else:
            prompt = self._get_prompt('fast_extract')
            if not prompt:
                raise LLMConfigError("Missing fast_extract prompt configuration")
                
            return prompt.format(
                content=content,
                format=fmt,
                instruction=instruction
            )

    async def process(self, context: Dict[str, Any]) -> AgentResponse:
        """Process extraction request through BaseAgent"""
        try:
            result = await super().process(context)
            
            if not result.success:
                return result

            # Handle slow mode responses
            if context.get("mode") == "slow":
                response = result.data.get("response", "").strip()
                
                # Check for end of items
                if "NO_MORE_ITEMS" in response.upper():
                    return AgentResponse(
                        success=True,
                        data={"response": "NO_MORE_ITEMS"},
                        raw_response=result.raw_response
                    )
                    
                # Try to parse single item
                try:
                    if response.startswith("[") and response.endswith("]"):
                        # Handle case where LLM returns array with single item
                        items = json.loads(response)
                        item = items[0] if items else None
                    else:
                        item = json.loads(response)
                        
                    return AgentResponse(
                        success=True,
                        data={"item": item},
                        raw_response=result.raw_response
                    )
                except json.JSONDecodeError:
                    return AgentResponse(
                        success=False,
                        data={},
                        error=f"Failed to parse item at position {context.get('position')}"
                    )

            # Handle fast mode responses
            else:
                try:
                    response = result.data.get("response", "[]")
                    items = json.loads(response if isinstance(response, str) else "[]")
                    if not isinstance(items, list):
                        items = [items] if items else []
                        
                    return AgentResponse(
                        success=True,
                        data={"items": items},
                        raw_response=result.raw_response
                    )
                except json.JSONDecodeError:
                    return AgentResponse(
                        success=False,
                        data={"items": []},
                        error="Failed to parse items list"
                    )

        except Exception as e:
            logger.error("process.failed", error=str(e))
            return AgentResponse(
                success=False,
                data={},
                error=str(e)
            )

    def iter_extract(self, content: Any, config: ExtractConfig) -> ItemIterator:
        """Create iterator for extracted items"""
        try:
            # Start with fast extraction if available
            state = ExtractionState(
                current_mode=self.modes[0],
                attempted_modes=[self.modes[0]],
                items=[],
                position=0,
                raw_response=content,
                format=config.format,
                instruction=config.instruction
            )
            
            # If starting with fast mode, try immediate extraction
            if state.current_mode == ExtractionMode.FAST:
                self._ensure_loop()
                result = self._loop.run_until_complete(self.process({
                    "content": content,
                    "format": config.format,
                    "instruction": config.instruction,
                    "mode": "fast"
                }))
                
                if result.success and result.data.get("items"):
                    state.items = result.data["items"]
            
            return ItemIterator(state, self)
            
        except Exception as e:
            logger.error("iterator.creation_failed", error=str(e))
            return ItemIterator(
                ExtractionState(
                    current_mode=ExtractionMode.FAST,
                    attempted_modes=[],
                    items=[],
                    position=0,
                    raw_response=content,
                    format=config.format,
                    instruction=config.instruction
                ),
                self
            )

    def _ensure_loop(self):
        """Ensure we have an event loop"""
        try:
            self._loop = asyncio.get_event_loop()
        except RuntimeError:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)