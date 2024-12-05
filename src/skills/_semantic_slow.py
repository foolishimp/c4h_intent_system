"""
Slow extraction mode with lazy LLM calls.
Path: src/skills/_semantic_slow.py
"""

from typing import Dict, Any, Optional
import structlog
from agents.base import BaseAgent, LLMProvider, AgentResponse
from skills.shared.types import ExtractConfig
import json

logger = structlog.get_logger()

class SlowItemIterator:
    """Iterator for slow extraction results with lazy LLM calls"""
    def __init__(self, extractor: 'SlowExtractor', content: Any, config: ExtractConfig):
        self._extractor = extractor
        self._content = content
        self._config = config
        self._position = 0
        self._exhausted = False
        self._has_items = False
        self._current_item = None
        self._max_attempts = 10  # Safety limit
        logger.debug("slow_iterator.initialized", 
                    content_type=type(content).__name__,
                    max_attempts=self._max_attempts)

    def __iter__(self):
        return self

    def __next__(self):
        """Synchronous next implementation"""
        if self._exhausted or self._position >= self._max_attempts:
            raise StopIteration

        try:
            # Run extraction synchronously
            result = self._extractor.process({
                'content': self._content,
                'config': self._config,
                'position': self._position
            })

            if not result.success:
                logger.warning("slow_extraction.failed", 
                             error=result.error,
                             position=self._position)
                self._exhausted = True
                raise StopIteration

            response = result.data.get('response', '')
            
            # Check for completion marker
            if 'NO_MORE_ITEMS' in str(response):
                logger.debug("slow_extraction.complete",
                           position=self._position)
                self._exhausted = True
                raise StopIteration

            # Parse response
            try:
                if isinstance(response, str):
                    item = json.loads(response)
                else:
                    item = response
            except json.JSONDecodeError as e:
                logger.error("slow_extraction.parse_error", 
                           error=str(e),
                           position=self._position)
                self._exhausted = True
                raise StopIteration

            self._position += 1
            self._has_items = True
            return item

        except Exception as e:
            logger.error("slow_iteration.failed", 
                        error=str(e), 
                        position=self._position)
            self._exhausted = True
            raise StopIteration

    def has_items(self) -> bool:
        return self._has_items

class SlowExtractor(BaseAgent):
    """Implements slow extraction mode using iterative LLM queries"""

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize with parent agent configuration"""
        super().__init__(config=config)
        
        # Get provider settings from config
        provider_cfg = config.get('llm_config', {}).get('agents', {}).get('semantic_slow_extractor', {})
        self.provider = LLMProvider(provider_cfg.get('provider', 'anthropic'))
        self.model = provider_cfg.get('model', 'claude-3-opus-20240229')
        self.temperature = provider_cfg.get('temperature', 0)
        
        # Build model string based on provider
        self.model_str = f"{self.provider.value}/{self.model}"
        if self.provider == LLMProvider.OPENAI:
            self.model_str = self.model  # OpenAI doesn't need prefix
            
        logger.info("slow_extractor.initialized",
                   provider=str(self.provider),
                   model=self.model,
                   temperature=self.temperature)

    def _get_agent_name(self) -> str:
        return "semantic_slow_extractor"

    def _format_request(self, context: Dict[str, Any]) -> str:
        """Format extraction request for slow mode using config template"""
        if not context.get('config'):
            logger.error("slow_extractor.missing_config")
            raise ValueError("Extract config required")

        extract_template = self._get_prompt('extract')
        position = context.get('position', 0)
        
        # Add explicit completion marker to prompt
        return extract_template.format(
            ordinal=self._get_ordinal(position + 1),
            content=context.get('content', ''),
            instruction=f"{context['config'].instruction}\nIf no more items exist, respond exactly with 'NO_MORE_ITEMS'",
            format=context['config'].format
        )

    @staticmethod
    def _get_ordinal(n: int) -> str:
        """Generate ordinal string for a number"""
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10 if n % 100 not in [11, 12, 13] else 0, 'th')
        return f"{n}{suffix}"

    def create_iterator(self, content: Any, config: ExtractConfig) -> SlowItemIterator:
        """Create iterator for slow extraction"""
        logger.debug("slow_extractor.creating_iterator",
                    content_type=type(content).__name__)
        return SlowItemIterator(self, content, config)