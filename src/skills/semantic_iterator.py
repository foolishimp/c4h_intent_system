"""
Enhanced semantic iterator with fast/slow extraction modes.
Path: src/skills/semantic_iterator.py
"""

from typing import List, Dict, Any, Optional, Iterator, Union, Tuple
from enum import Enum
import structlog
import json
from dataclasses import dataclass
from src.skills.semantic_extract import SemanticExtract, ExtractResult
from src.skills.shared.types import ExtractConfig
from src.agents.base import BaseAgent, LLMProvider, AgentResponse

logger = structlog.get_logger()

class ExtractionMode(str, Enum):
    """Available extraction modes"""
    FAST = "fast"      # Direct extraction from structured data
    SLOW = "slow"      # Sequential item-by-item extraction

@dataclass
class ExtractionState:
    """Tracks extraction state"""
    current_mode: ExtractionMode
    attempted_modes: List[ExtractionMode]
    items: List[Any]
    position: int = 0
    raw_response: str = ""
    error: Optional[str] = None
    content: Any = None
    config: Optional[ExtractConfig] = None

class ItemIterator:
    """Iterator over extracted items"""
    
    def __init__(self, state: ExtractionState, agent: 'SemanticIterator'):
        self._state = state
        self._agent = agent
        logger.debug("iterator.initialized",
                    mode=state.current_mode,
                    items_count=len(state.items),
                    position=state.position)

    @staticmethod
    def _generate_ordinal(n: int) -> str:
        """Generate ordinal string for a number"""
        if 10 <= n % 100 <= 20:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
        return f"{n}{suffix}"

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
                    logger.info("fast_extract.completed",
                              total_items=len(self._state.items))
                    raise StopIteration()
                
                item = self._state.items[self._state.position]
                self._state.position += 1
                return item
            else:
                return self._get_slow_item()

        except Exception as e:
            if isinstance(e, StopIteration):
                raise
            logger.error("iterator.error", error=str(e))
            raise StopIteration()

    def _get_slow_item(self) -> Any:
        """Get next item using slow extraction"""
        try:
            ordinal = self._generate_ordinal(self._state.position + 1)
            
            result = self._agent.process({
                "content": self._state.content,
                "instruction": self._state.config.instruction,
                "format": self._state.config.format,
                "position": self._state.position,
                "ordinal": ordinal,
                "mode": "slow"
            })
            
            if not result.success:
                raise StopIteration

            if result.data.get("response") == "NO_MORE_ITEMS":
                logger.info("slow_extract.completed", 
                          position=self._state.position,
                          total_items_processed=self._state.position)
                raise StopIteration

            item = result.data.get("item")
            if item:
                self._state.position += 1
                return item
            
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
        
        logger.info("iterator.configured",
                   modes=[m.value for m in self.modes],
                   allow_fallback=allow_fallback)
    
    def _get_agent_name(self) -> str:
        return "semantic_iterator"

    def _format_request(self, context: Dict[str, Any]) -> str:
        """Format request using config templates"""
        mode = context.get("mode", "fast")
        content = context.get("content", "")
        instruction = context.get("instruction", "")
        fmt = context.get("format", "json")
        
        if mode == "slow":
            ordinal = context.get("ordinal", "next")
            template = self._get_prompt("slow_extract")
            return template.format(
                instruction=instruction,
                format=fmt,
                content=content,
                ordinal=ordinal
            )
        else:
            template = self._get_prompt("fast_extract")
            return template.format(
                instruction=instruction,
                format=fmt,
                content=content
            )

    def _process_llm_response(self, content: str, result: AgentResponse) -> Dict[str, Any]:
        """Process LLM response with detailed logging"""
        try:
            if not content:
                logger.warning("empty_content_received")
                return {"items": []}

            logger.info("llm_response.received",
                    content_length=len(content),
                    response_type=type(content).__name__)
            
            logger.debug("llm_response.content",
                        content_preview=str(content)[:500])

            try:
                parsed = json.loads(content)
                logger.info("json_parse.success", 
                        parsed_type=type(parsed).__name__,
                        is_list=isinstance(parsed, list),
                        is_dict=isinstance(parsed, dict))
                
                if isinstance(parsed, list):
                    return {"items": parsed}
                elif isinstance(parsed, dict):
                    return {"item": parsed}
                
            except json.JSONDecodeError as e:
                logger.warning("json_parse.failed", error=str(e))
                return {"items": []}

        except Exception as e:
            logger.error("response_processing.failed", error=str(e))
            return {"items": []}

    def process(self, context: Dict[str, Any]) -> AgentResponse:
        """Process extraction request"""
        try:
            mode = context.get("mode", "fast")
            result = super().process(context)
            
            if not result.success:
                return result

            content = result.data.get("raw_content", "")
            processed_data = self._process_llm_response(content, result)
            
            if mode == "slow" and "NO_MORE_ITEMS" in str(content).upper():
                return AgentResponse(
                    success=True,
                    data={"response": "NO_MORE_ITEMS"},
                    raw_response=result.raw_response
                )

            return AgentResponse(
                success=True,
                data=processed_data,
                raw_response=result.raw_response
            )

        except Exception as e:
            logger.error("process.failed", error=str(e))
            return AgentResponse(
                success=False,
                data={},
                error=str(e)
            )

    def iter_extract(self, content: Any, config: ExtractConfig) -> 'ItemIterator':
        """Create iterator for extracted items with enhanced logging"""
        try:
            logger.info("extraction.starting",
                    mode=self.modes[0].value,
                    content_length=len(str(content)) if content else 0,
                    instruction_length=len(config.instruction) if config.instruction else 0)

            state = ExtractionState(
                current_mode=self.modes[0],
                attempted_modes=[self.modes[0]],
                items=[],
                position=0,
                content=content,
                config=config
            )
            
            if state.current_mode == ExtractionMode.FAST:
                logger.info("fast_extraction.request",
                        instruction_preview=config.instruction[:100],
                        format=config.format)
                
                result = self.process({
                    "content": content,
                    "instruction": config.instruction,
                    "format": config.format,
                    "mode": "fast"
                })
                
                logger.info("fast_extraction.response",
                        success=result.success,
                        has_items=bool(result.data.get("items")),
                        items_count=len(result.data.get("items", [])),
                        error=result.error)

                if result.success:
                    state.items = result.data.get("items", [])
                elif self.allow_fallback and ExtractionMode.SLOW in self.modes:
                    logger.info("extraction.fallback_to_slow")
                    state.current_mode = ExtractionMode.SLOW
                    state.attempted_modes.append(ExtractionMode.SLOW)
            
            return ItemIterator(state, self)
                
        except Exception as e:
            logger.error("iterator.creation_failed", error=str(e))
            return ItemIterator(
                ExtractionState(
                    current_mode=ExtractionMode.FAST,
                    attempted_modes=[],
                    items=[],
                    content=content,
                    config=config
                ),
                self
            )