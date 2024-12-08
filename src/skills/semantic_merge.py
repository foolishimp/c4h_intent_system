"""
Semantic merge implementation following agent design principles.
Path: src/skills/semantic_merge.py
"""

from typing import Dict, Any, Optional, Union
from dataclasses import dataclass
import structlog
from agents.base import BaseAgent, LLMProvider, AgentResponse
from config import locate_config
 
logger = structlog.get_logger()

@dataclass
class MergeResult:
    """Result of semantic merge operation"""
    success: bool
    content: str
    raw_response: Optional[str] = None
    error: Optional[str] = None

class SemanticMerge(BaseAgent):
    """
    Semantic merge implementation following agent design principles.
    Path: src/skills/semantic_merge.py
    """

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize merger with configuration."""
        super().__init__(config=config)
        
        # Basic config handled by BaseAgent
        agent_config = self._get_agent_config()
        
        # Get merge-specific settings using locate_config
        merge_config = locate_config(self.config or {}, 'merge_config')
        self.style = merge_config.get('style', 'smart')
        self.preserve_formatting = merge_config.get('preserve_formatting', True)
        
        logger.info("semantic_merge.initialized",
                style=self.style,
                preserve_formatting=self.preserve_formatting)

    def _get_agent_name(self) -> str:
        """Get agent name for config lookup"""
        return "semantic_merge"

    def _format_request(self, context: Dict[str, Any]) -> str:
        """Format merge request using config template"""
        merge_template = self._get_prompt('merge')
        return merge_template.format(
            original=context.get('original_code', ''),
            changes=context.get('changes', ''),
            style=context.get('style', self.style),
            preserve_formatting=str(context.get('preserve_formatting', self.preserve_formatting)).lower()
        )

    def merge(self, original: str, changes: Union[str, Dict[str, Any]]) -> MergeResult:
        """Process a merge operation - synchronous interface"""
        try:
            # Use parent's process method directly
            result = self.process({
                'original_code': original,
                'changes': changes,
                'style': self.style,
                'preserve_formatting': self.preserve_formatting
            })

            if not result.success:
                logger.warning("merge.failed", error=result.error)
                return MergeResult(
                    success=False,
                    content="",
                    error=result.error,
                    raw_response=result.data.get("raw_output")
                )

            content = result.data.get("response", "")
            logger.info("merge.success", content_length=len(content))
            
            return MergeResult(
                success=True,
                content=content,
                raw_response=result.data.get("raw_output")
            )

        except Exception as e:
            logger.error("merge.failed", error=str(e))
            return MergeResult(
                success=False,
                content="",
                error=str(e)
            )