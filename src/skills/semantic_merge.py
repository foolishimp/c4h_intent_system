"""
Semantic merge implementation following agent design principles.
Path: src/skills/semantic_merge.py
"""

from typing import Dict, Any, Optional, Union
from dataclasses import dataclass
import structlog
from agents.base import BaseAgent, LLMProvider, AgentResponse
from config import deep_merge

logger = structlog.get_logger()

@dataclass
class MergeConfig:
    """Configuration for merge operation"""
    style: str = "smart"  # smart, inline, git
    preserve_formatting: bool = True
    allow_partial: bool = False

@dataclass 
class MergeResult:
    """Result of semantic merge operation"""
    success: bool
    content: str
    raw_response: Optional[str] = None
    error: Optional[str] = None

class SemanticMerge(BaseAgent):
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize merger with config and optional merge settings."""
        super().__init__(config=config)
        
        # Get agent-specific config
        agent_cfg = config.get('llm_config', {}).get('agents', {}).get('semantic_merge', {})
        
        # Initialize merge configuration from agent config
        merge_config = agent_cfg.get('merge_config', {})
        self._merge_config = {
            'style': merge_config.get('style', 'smart'),
            'preserve_formatting': merge_config.get('preserve_formatting', True),
            'allow_partial': merge_config.get('allow_partial', False)
        }
        
        logger.info("semantic_merge.initialized",
                   merge_style=self._merge_config['style'],
                   preserve_formatting=self._merge_config['preserve_formatting'])

    def _get_agent_name(self) -> str:
        """Get agent name for config lookup"""
        return "semantic_merge"

    def _format_request(self, context: Dict[str, Any]) -> str:
        """Format merge request using config template"""
        merge_template = self._get_prompt('merge')
        return merge_template.format(
            original=context.get('original_code', ''),  # Empty string for new files
            changes=context.get('changes', ''),
            style=self._merge_config['style'],
            preserve_formatting=str(self._merge_config['preserve_formatting']).lower()
        )

    def _extract_code_content(self, response: Dict[str, Any]) -> str:
        """Extract clean code content from LLM response"""
        if not response:
            return ""

        content = response.get('response', '')
        if not content:
            content = response.get('raw_content', '')
                
        # Remove any markdown code block markers if present
        content = content.strip()
        if content.startswith('```'):
            # Handle case where language is specified after backticks
            lines = content.split('\n')
            if len(lines) > 2:  # At least opening, content, and closing
                # Skip first line (```python etc) and last line (```)
                content = '\n'.join(lines[1:-1])
            else:
                content = content.strip('`')
                
        return content

    def merge(self, original: str, changes: Union[str, Dict[str, Any]]) -> MergeResult:
        """Process a merge operation - synchronous interface"""
        try:
            context = {
                'original_code': original,
                'changes': changes,
                'style': self._merge_config['style']
            }
            
            # Use parent's synchronous process method
            response = self.process(context)
            
            if not response.success:
                return MergeResult(
                    success=False,
                    content="",
                    error=response.error,
                    raw_response=response.raw_response
                )

            # Extract and return merged content
            merged_content = self._extract_code_content(response.data)
            return MergeResult(
                success=True,
                content=merged_content,
                raw_response=response.raw_response
            )

        except Exception as e:
            logger.error("merge.failed", error=str(e))
            return MergeResult(
                success=False,
                content="",
                error=str(e)
            )