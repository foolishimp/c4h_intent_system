"""
Semantic merge implementation following agent design principles.
Path: src/skills/semantic_merge.py
"""

from typing import Dict, Any, Optional, Union
from dataclasses import dataclass
import structlog
from agents.base import BaseAgent, LLMProvider, AgentResponse

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
    """Merges code changes using semantic understanding"""
    
    def __init__(self,
                 provider: LLMProvider,
                 model: str,
                 temperature: float = 0,
                 config: Optional[Dict[str, Any]] = None,
                 merge_config: Optional[MergeConfig] = None):
        """Initialize merger with configuration"""
        super().__init__(
            provider=provider,
            model=model,
            temperature=temperature,
            config=config
        )
        self.merge_config = merge_config or MergeConfig()
        
        logger.debug("semantic_merge.initialized",
                    provider=str(provider),
                    model=model,
                    merge_style=self.merge_config.style)

    def _get_agent_name(self) -> str:
        return "semantic_merge"

    def _format_request(self, context: Dict[str, Any]) -> str:
        """Format merge request using config template"""
        merge_template = self._get_prompt('merge')
        return merge_template.format(
            original=context.get('original_code', ''),  # Empty string for new files
            changes=context.get('changes', ''),
            style=self.merge_config.style,
            preserve_formatting=str(self.merge_config.preserve_formatting).lower()
        )

def _extract_code_content(self, response: Dict[str, Any]) -> str:
    """Extract clean code content from LLM response"""
    if not response:
        return ""

    content = response.get('response', '')
    if not content:
        content = response.get('raw_content', '')

    # Clean markdown and code blocks    
    content = content.strip()
    
    # If entire content is a code block
    if content.startswith('```') and content.endswith('```'):
        lines = content.split('\n')
        # Remove first line containing backticks and optional language
        if lines[0].startswith('```'):
            lines = lines[1:]
        # Remove last line containing closing backticks
        if lines[-1].strip() == '```':
            lines = lines[:-1]
        content = '\n'.join(lines)
    
    # Strip any remaining backticks
    content = content.strip('`')
    
    logger.debug("merge.extracted_content", 
                original_length=len(response.get('response', '')),
                cleaned_length=len(content),
                starts_with=content[:20])
    
    return content

    async def merge(self, original: str, changes: Union[str, Dict[str, Any]]) -> MergeResult:
        """Process a merge operation"""
        try:
            # Trust LLM to handle empty/missing original code
            context = {
                'original_code': original,
                'changes': changes,
                'style': self.merge_config.style
            }
            
            # Pass through to LLM without validation
            response = await self.process(context)
            
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