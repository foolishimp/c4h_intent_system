"""
Semantic merge implementation using hierarchical configuration.
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
    """Semantic merge implementation using hierarchical configuration."""
    
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize merger with configuration."""
        super().__init__(config=config)
        
        # Get our complete merge config directly
        merge_config = locate_config(self.config or {}, self._get_agent_name())
        
        # Extract merge-specific settings
        self.style = merge_config.get('merge_config', {}).get('style', 'smart')
        self.preserve_formatting = merge_config.get('merge_config', {}).get('preserve_formatting', True)
        
        # Get runtime values from our config
        self.original_code = merge_config.get('original_code')
        self.changes = merge_config.get('changes')
        
        # Add more detailed debug logging
        logger.debug("semantic_merge.initialization",
                merge_config=merge_config,
                original_code=self.original_code,
                changes=self.changes)
                
        logger.info("semantic_merge.initialized",
                style=self.style,
                preserve_formatting=self.preserve_formatting,
                has_original=bool(self.original_code),
                has_changes=bool(self.changes))
        
    def _get_agent_name(self) -> str:
        """Get agent name for config lookup"""
        return "semantic_merge"

    def _format_request(self, context: Dict[str, Any]) -> str:
        """Format merge request using config template"""
        merge_template = self._get_prompt('merge')
        
        # Debug log the values we're using
        self.logger.debug("semantic_merge.format_request",
            original=self.original_code,
            changes=self.changes,
            style=self.style,
            preserve_formatting=self.preserve_formatting
        )
        
        # Call parent's format method first to get base formatting
        formatted = super()._format_request(context)
        
        # Now apply our specific template 
        return merge_template.format(
            original=self.original_code,
            changes=self.changes,
            style=self.style,
            preserve_formatting=str(self.preserve_formatting).lower()
        )

    def merge(self, original: str, changes: Union[str, Dict[str, Any]]) -> MergeResult:
        """Process a merge operation"""
        try:
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
