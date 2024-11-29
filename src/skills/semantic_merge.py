"""
Semantic merge implementation following agent design principles.
Path: src/skills/semantic_merge.py
"""

from typing import Dict, Any, Optional, Union
from dataclasses import dataclass
import structlog
from src.agents.base import BaseAgent, LLMProvider, AgentResponse

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
        if not context.get('original_code'):
            raise ValueError("Original code required for merge")
            
        merge_template = self._get_prompt('merge')
        return merge_template.format(
            original=context.get('original_code', ''),
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
            
        # Remove any markdown code block markers
        content = content.strip()
        if content.startswith('```'):
            content = '\n'.join(content.split('\n')[1:-1])
            
        return content

    async def merge(self, original: str, changes: Union[str, Dict[str, Any]]) -> MergeResult:
        """Process a merge operation"""
        try:
            # Prepare merge context
            context = {
                'original_code': original,
                'changes': changes,
                'style': self.merge_config.style
            }
            
            # Process through LLM
            response = await self.process(context)
            
            if not response.success:
                return MergeResult(
                    success=False,
                    content="",
                    error=response.error,
                    raw_response=response.raw_response
                )

            # Extract and validate merged content
            merged_content = self._extract_code_content(response.data)
            if not merged_content or merged_content.isspace():
                return MergeResult(
                    success=False,
                    content="",
                    error="Empty merge result",
                    raw_response=response.raw_response
                )

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

    async def validate_merge(self, original: str, merged: str) -> bool:
        """Validate merged code meets requirements"""
        try:
            validation_prompt = self._get_prompt('validation')
            
            response = await self.process({
                'original': original,
                'merged': merged,
                'validation_prompt': validation_prompt
            })
            
            return response.success and response.data.get('is_valid', False)
            
        except Exception as e:
            logger.error("merge.validation_failed", error=str(e))
            return False