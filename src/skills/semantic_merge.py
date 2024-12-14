"""
Semantic merge implementation for code modifications.
Path: src/skills/semantic_merge.py
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass
import structlog
from agents.base import BaseAgent, AgentResponse
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
    """Handles merging of code modifications."""
    
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize merger with configuration."""
        super().__init__(config=config)
        
        # Get merge config section
        merge_config = locate_config(self.config or {}, self._get_agent_name())
        
        # Only preserve formatting flag is meaningful
        self.preserve_formatting = merge_config.get('merge_config', {}).get('preserve_formatting', True)
        
        logger.info("semantic_merge.initialized",
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
            preserve_formatting=str(self.preserve_formatting).lower()
        )

    def merge(self, original: str, changes: str) -> MergeResult:
        """Process a merge operation"""
        try:
            logger.debug("semantic_merge.format_request",
                        original_length=len(original),
                        changes_length=len(changes),
                        preserve_formatting=self.preserve_formatting)
                        
            result = self.process({
                'original_code': original,
                'changes': changes
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

    def _process_response(self, content: str, raw_response: Any) -> Dict[str, Any]:
        """Process LLM response into standard format"""
        logger.debug("merge.processing_response", 
                    content_length=len(content) if content else 0)

        return {
            "response": content,
            "raw_output": raw_response 
        }