# src/skills/semantic_merge.py

from typing import Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path
import structlog
from difflib import unified_diff
import re

from .semantic_extract import SemanticExtract
from src.agents.base import BaseAgent, LLMProvider
from src.agents.coder import MergeStrategy

logger = structlog.get_logger()

@dataclass
class MergeResult:
    """Result of semantic merge operation"""
    success: bool
    content: str
    error: Optional[str] = None
    context: Dict[str, Any] = None

class SemanticMerge(BaseAgent):
    """Semantically-aware code merge tool"""
    
    def __init__(self,
                 provider: LLMProvider = LLMProvider.ANTHROPIC,
                 model: Optional[str] = None):
        """Initialize merger with specified provider"""
        super().__init__(
            provider=provider,
            model=model,
            temperature=0
        )
        self.extractor = SemanticExtract(provider=provider, model=model)
        
    def _get_agent_name(self) -> str:
        return "semantic_merge"
        
    def _get_system_message(self) -> str:
        return """You are an expert code merger that combines changes intelligently.
        When merging code changes:
        1. Preserve existing functionality
        2. Maintain code style consistency
        3. Handle conflicts carefully
        4. Consider code context and dependencies
        5. Return clean, formatted results
        """
    
    def _apply_gitdiff(self, original: str, diff: str) -> str:
        """Apply git-style diff to content"""
        # Parse diff hunks
        hunks = []
        current_hunk = []
        
        for line in diff.splitlines():
            if line.startswith("@@"):
                if current_hunk:
                    hunks.append(current_hunk)
                current_hunk = [line]
            elif current_hunk:
                current_hunk.append(line)
        
        if current_hunk:
            hunks.append(current_hunk)
            
        # Apply hunks
        lines = original.splitlines()
        for hunk in hunks:
            # Parse hunk header
            header = hunk[0]
            match = re.match(r"@@ -(\d+),?(\d+)? \+(\d+),?(\d+)? @@", header)
            if not match:
                continue
                
            start = int(match.group(3))
            count = int(match.group(4)) if match.group(4) else 1
            
            # Apply changes
            new_lines = []
            for line in hunk[1:]:
                if line.startswith(" "):
                    new_lines.append(line[1:])
                elif line.startswith("+"):
                    new_lines.append(line[1:])
                    
            lines[start-1:start-1+count] = new_lines
            
        return "\n".join(lines)
    
    async def merge(self, original: str, changes: Dict[str, Any],
                   strategy: MergeStrategy) -> MergeResult:
        """Merge changes into original content"""
        try:
            if strategy == MergeStrategy.INLINE:
                # Direct replacement
                return MergeResult(
                    success=True,
                    content=changes["content"]
                )
                
            elif strategy == MergeStrategy.GITDIFF:
                # Apply git-style diff
                merged = self._apply_gitdiff(original, changes["content"])
                return MergeResult(
                    success=True,
                    content=merged
                )
                
            elif strategy == MergeStrategy.PATCH:
                # Use semantic extraction to understand patch
                patch_result = await self.extractor.extract(
                    content=changes,
                    prompt="""Extract patch details:
                    1. Location of changes
                    2. New content
                    3. Context lines
                    Return as structured patch instructions."""
                )
                
                if not patch_result.success:
                    return MergeResult(
                        success=False,
                        content="",
                        error=f"Failed to parse patch: {patch_result.error}"
                    )
                    
                # Let LLM merge with context
                response = await self.process({
                    "original": original,
                    "patch": patch_result.value
                })
                
                if not response.success:
                    return MergeResult(
                        success=False,
                        content="",
                        error=f"Merge failed: {response.error}"
                    )
                    
                return MergeResult(
                    success=True,
                    content=response.data["merged_content"]
                )
                
            else:
                raise ValueError(f"Unsupported merge strategy: {strategy}")
                
        except Exception as e:
            logger.error("semantic_merge.failed", error=str(e))
            return MergeResult(
                success=False,
                content="",
                error=str(e)
            )