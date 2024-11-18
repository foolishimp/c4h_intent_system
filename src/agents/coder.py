"""
Code modification agent using semantic tools.
Path: src/agents/coder.py
"""

from pathlib import Path
import structlog
import shutil
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, Optional

from .base import BaseAgent, LLMProvider, AgentResponse 
from src.skills.semantic_iterator import SemanticIterator
from src.skills.semantic_merge import SemanticMerge

logger = structlog.get_logger()

class MergeMethod(str, Enum):
    INLINE = "inline"
    SMART = "smart"

@dataclass
class TransformResult:
    success: bool
    file_path: str
    backup_path: Optional[str] = None
    error: Optional[str] = None

class Coder(BaseAgent):
    def __init__(self, provider: LLMProvider, model: Optional[str] = None, temperature: float = 0,
                 config: Optional[Dict[str, Any]] = None):
        super().__init__(provider=provider, model=model, temperature=temperature, config=config)
        
        self.merger = SemanticMerge(
            provider=provider,
            model=model,
            temperature=temperature,
            config=config  # Pass config to merger
        )
        
        self.iterator = SemanticIterator([{
            'provider': provider.value,
            'model': model,
            'temperature': temperature,
            'config': config  # Pass config to iterator
        }])

    def _get_agent_name(self) -> str:
        return "coder"

    def _get_system_message(self) -> str:
        return """You are an expert code modification agent. Extract changes from instructions and apply them precisely."""

    def _backup_file(self, file_path: Path) -> Optional[Path]:
        """Create backup of file"""
        if not file_path.exists():
            return None
        backup_path = Path(f"{file_path}.bak")
        shutil.copy2(file_path, backup_path)
        return backup_path

    async def process(self, context: Dict[str, Any]) -> AgentResponse:
        """Process change request using semantic iterator and merger"""
        try:
            changes_data = context.get('changes', {}).get('raw_output', {})
            
            iterator = await self.iterator.iter_extract(changes_data, {
                "pattern": """Extract each code change from the provided data.
                For each change return a JSON object with:
                - file_path: The target file path
                - content: The complete new content or diff
                - type: The type of change (create/modify/delete)""",
                "format": "json"
            })

            results = []
            while iterator.has_next():
                change = next(iterator)
                file_path = Path(change.get('file_path', ''))
                backup_path = self._backup_file(file_path)

                try:
                    original = file_path.read_text() if file_path.exists() else ""
                    result = await self.merger.merge(original, change.get('content', ''))
                    
                    if result.success:
                        file_path.parent.mkdir(parents=True, exist_ok=True)
                        file_path.write_text(result.content)
                        results.append({"status": "success", "file": str(file_path)})
                    else:
                        if backup_path:
                            shutil.copy2(backup_path, file_path)
                        results.append({
                            "status": "failed",
                            "file": str(file_path),
                            "error": result.error
                        })

                except Exception as e:
                    logger.error("transform.failed", error=str(e))
                    if backup_path:
                        shutil.copy2(backup_path, file_path)
                    results.append({
                        "status": "failed", 
                        "file": str(file_path),
                        "error": str(e)
                    })

            success = any(r["status"] == "success" for r in results)
            return AgentResponse(
                success=success,
                data={"changes": results},
                error=None if success else "No changes were successful"
            )

        except Exception as e:
            logger.error("coder.process_failed", error=str(e))
            return AgentResponse(success=False, data={}, error=str(e))