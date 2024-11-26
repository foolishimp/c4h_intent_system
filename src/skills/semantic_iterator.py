"""
Enhanced semantic iterator with fast/slow extraction modes.
Path: src/skills/semantic_iterator.py
"""

from typing import List, Dict, Any, Optional, Iterator
import structlog
from dataclasses import dataclass
from enum import Enum
import json
from .shared.types import ExtractConfig
from src.agents.base import BaseAgent, LLMProvider, AgentResponse

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
        logger.debug("iterator.initialized",
                    mode=state.current_mode,
                    items_count=len(state.items))

    @property
    def state(self) -> ExtractionState:
        """Access to iterator state"""
        return self._state

    def __iter__(self):
        return self

    def __next__(self) -> Any:
        """Get next item using current mode"""
        try:
            if self._state.current_mode == ExtractionMode.FAST:
                if self._state.position >= len(self._state.items):
                    raise StopIteration()
                
                item = self._state.items[self._state.position]
                self._state.position += 1
                return item
            else:
                return self._get_slow_item()

        except Exception as e:
            logger.error("iterator.error", error=str(e))
            raise StopIteration()

    def _get_slow_item(self) -> Any:
        """Get next item using slow extraction"""
        try:
            request = {
                "content": self._state.raw_response,
                "position": self._state.position,
                "format": self._state.format,
                "instruction": self._state.instruction,
                "mode": "slow"
            }

            result = self._agent.process(request)
            
            if not result.success:
                raise StopIteration

            if result.data.get("response") == "NO_MORE_ITEMS":
                raise StopIteration

            item = result.data.get("item")
            if item:
                self._state.position += 1
                return item
            else:
                raise StopIteration

        except Exception as e:
            logger.error("slow_extract.failed", error=str(e))
            raise StopIteration

class SemanticIterator(BaseAgent):
    """Agent for iterative semantic extraction"""
    
    def __init__(self, 
                 provider: LLMProvider,
                 model: str,
                 temperature: float = 0,
                 config: Optional[Dict[str, Any]] = None,
                 extraction_modes: Optional[List[str]] = None):
        """Initialize with standard agent configuration"""
        super().__init__(
            provider=provider,
            model=model,
            temperature=temperature,
            config=config
        )
        
        self.modes = [ExtractionMode(m) for m in (extraction_modes or ["fast", "slow"])]
        
    def _get_agent_name(self) -> str:
        return "semantic_iterator"

    def _get_system_message(self) -> str:
        """Get system message from config"""
        return self._get_prompt('system')

    def _format_request(self, context: Dict[str, Any]) -> str:
        """Format request using config templates"""
        mode = context.get("mode", "fast")
        content = context.get("content", "")
        instruction = context.get("instruction", "")
        fmt = context.get("format", "json")
        position = context.get("position", 0)

        # Get appropriate prompt template from config
        prompt_key = 'fast_extract' if mode == "fast" else 'slow_extract'
        template = self._get_prompt(prompt_key)

        # Format the template with context
        return template.format(
            instruction=instruction,
            format=fmt,
            content=content,
            ordinal=f"{position + 1}th" if position > 2 else ["1st", "2nd", "3rd"][position]
        )

    def process(self, context: Dict[str, Any]) -> AgentResponse:
        """Process extraction request"""
        try:
            mode = context.get("mode", "fast")
            result = super().process(context)
            
            if not result.success:
                return result

            # Process the raw response into standardized format
            content = result.data.get("raw_content", "")
            raw_response = result.data.get("raw_output")
            
            processed_data = self._process_llm_response(content, raw_response)
            
            # Create properly structured response
            if mode == "slow" and "response" in processed_data:
                return AgentResponse(
                    success=True,
                    data={"response": processed_data["response"]},
                    raw_response=raw_response
                )
            elif "items" in processed_data:
                return AgentResponse(
                    success=True,
                    data={"items": processed_data["items"]},
                    raw_response=raw_response
                )
            elif "item" in processed_data:
                return AgentResponse(
                    success=True,
                    data={"item": processed_data["item"]},
                    raw_response=raw_response
                )
            
            return AgentResponse(
                success=False,
                data={},
                error="Invalid response format"
            )

        except Exception as e:
            logger.error("process.failed", error=str(e))
            return AgentResponse(
                success=False,
                data={},
                error=str(e)
            )

    def _process_llm_response(self, content: str, raw_response: Any) -> Dict[str, Any]:
        """Process LLM response ensuring proper JSON structure"""
        try:
            if isinstance(content, str):
                # Try to parse JSON response
                items = json.loads(content)
                if isinstance(items, list):
                    return {"items": items}
                elif isinstance(items, dict):
                    if items.get("status") == "NO_MORE_ITEMS":
                        return {"response": "NO_MORE_ITEMS"}
                    return {"item": items}
            
            logger.error("invalid_response_format", content=content[:100])
            return {"items": []}
            
        except json.JSONDecodeError as e:
            logger.error("json_parse_error", error=str(e), content=content[:100])
            return {"items": []}

    def iter_extract(self, content: Any, config: ExtractConfig) -> ItemIterator:
        """Create iterator for extracted items"""
        try:
            state = ExtractionState(
                current_mode=self.modes[0],
                attempted_modes=[self.modes[0]],
                items=[],
                position=0,
                raw_response=content,
                format=config.format,
                instruction=config.instruction
            )
            
            if state.current_mode == ExtractionMode.FAST:
                result = self.process({
                    "content": content,
                    "format": config.format,
                    "instruction": config.instruction,
                    "mode": "fast"
                })
                
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
                    raw_response=content,
                    format=config.format,
                    instruction=config.instruction
                ),
                self
            )