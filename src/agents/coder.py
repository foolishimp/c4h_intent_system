"""
Code modification agent using semantic tools.
Path: src/agents/coder.py
"""

from pathlib import Path
import structlog
import shutil
from enum import Enum
from typing import Dict, Any, Optional
from .base import BaseAgent, LLMProvider, AgentResponse 
from src.skills.semantic_iterator import SemanticIterator
from src.skills.semantic_merge import SemanticMerge
from src.skills.shared.types import ExtractConfig

logger = structlog.get_logger()

class MergeMethod(str, Enum):
    INLINE = "inline"
    SMART = "smart"

class Coder(BaseAgent):
    def __init__(self, provider: LLMProvider, model: Optional[str] = None, temperature: float = 0,
                 config: Optional[Dict[str, Any]] = None):
        super().__init__(provider=provider, model=model, temperature=temperature, config=config)
        self.merger = SemanticMerge(provider=provider, model=model, temperature=temperature, config=config)
        self.iterator = SemanticIterator([{'provider': provider.value, 'model': model, 'temperature': temperature, 'config': config}])

    def _get_agent_name(self) -> str:
        """Required by BaseAgent - name of this agent"""
        return "coder"

    def _get_system_message(self) -> str:
        """Required by BaseAgent - system prompt for this agent"""
        return """You are an expert code modification agent. Your task is to safely and precisely apply code changes.
        
        Rules:
        1. Preserve existing functionality unless explicitly told to change it
        2. Maintain code style and formatting
        3. Apply changes exactly as specified
        4. Handle errors gracefully with backups
        5. Validate code after changes"""

    async def process(self, context: Dict[str, Any]) -> AgentResponse:
        try:
            changes_data = context.get('changes', {}).get('raw_output', {})
            config = ExtractConfig(
                pattern="""Extract each code change from the provided data.
                For each change return a JSON object with:
                - file_path: The target file path 
                - content: The complete new content or diff
                - type: The type of change (create/modify/delete)""",
                format="json"
            )
            
            iterator = await self.iterator.iter_extract(changes_data, config)
            results = []

            while iterator.has_next():
                change = next(iterator)
                file_path = Path(change.get('file_path', ''))
                backup = file_path.with_suffix(file_path.suffix + '.bak') if file_path.exists() else None
                
                try:
                    if backup:
                        shutil.copy2(file_path, backup)
                    result = await self.merger.merge(file_path.read_text() if file_path.exists() else "", 
                                                   change.get('content', ''))
                    
                    if result.success:
                        file_path.parent.mkdir(parents=True, exist_ok=True)
                        file_path.write_text(result.content)
                        results.append({"status": "success", "file": str(file_path)})
                    else:
                        if backup:
                            shutil.copy2(backup, file_path)
                        results.append({"status": "failed", "file": str(file_path), 
                                     "error": result.error})
                except Exception as e:
                    logger.error("change.failed", error=str(e))
                    if backup:
                        shutil.copy2(backup, file_path)
                    results.append({"status": "failed", "file": str(file_path), 
                                 "error": str(e)})

            success = any(r["status"] == "success" for r in results)
            return AgentResponse(success=success, data={"changes": results}, 
                               error=None if success else "No changes were successful")

        except Exception as e:
            logger.error("process.failed", error=str(e))
            return AgentResponse(success=False, data={"changes": []}, error=str(e))