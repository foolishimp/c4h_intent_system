"""
Slow extraction mode with lazy LLM calls.
Path: src/skills/_semantic_slow.py
"""

from typing import Dict, Any, Optional
import structlog
from agents.base import BaseAgent, LLMProvider, AgentResponse
from skills.shared.types import ExtractConfig
import json
from config import locate_config

logger = structlog.get_logger()

class SlowItemIterator:
    """Iterator for slow extraction results with lazy LLM calls"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize with parent agent configuration"""
        super().__init__(config=config)
        
        # Get provider settings from config - most specific to least
        agent_cfg = config.get('llm_config', {}).get('agents', {}).get('semantic_slow_extractor', {})
        provider_name = agent_cfg.get('provider', 
                                    config.get('llm_config', {}).get('default_provider', 'anthropic'))
        
        # Build provider config chain
        provider_cfg = config.get('providers', {}).get(provider_name, {})
        
        self.provider = LLMProvider(provider_name)
        # Prefer agent specific settings over provider defaults
        self.model = agent_cfg.get('model', provider_cfg.get('default_model', 'claude-3-opus-20240229'))
        self.temperature = agent_cfg.get('temperature', 0)
        
        # Build model string based on provider
        self.model_str = f"{self.provider.value}/{self.model}"
        if self.provider == LLMProvider.OPENAI:
            self.model_str = self.model  # OpenAI doesn't need prefix

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
        
        # Get our config section
        slow_cfg = locate_config(self.config or {}, self._get_agent_name())
        
        logger.info("slow_extractor.initialized",
                settings=slow_cfg)

    def _get_agent_name(self) -> str:
        return "semantic_slow_extractor"
    
    """
    Slow extraction mode with lazy LLM calls.
    Path: src/skills/_semantic_slow.py
    """

    def _format_request(self, context: Dict[str, Any]) -> str:
        """Format extraction request for slow mode using config template"""
        if not context.get('config'):
            logger.error("slow_extractor.missing_config")
            raise ValueError("Extract config required")

        extract_template = self._get_prompt('extract')
        position = context.get('position', 0)
        
        # Let LLM handle all content interpretation via the prompt
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