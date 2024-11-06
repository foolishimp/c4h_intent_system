# src/agents/solution_architect.py

from typing import Dict, Any
from .base import SingleShotAgent

class SolutionArchitect(SingleShotAgent):
    """Solution architect that provides concrete code changes"""
    
    def _get_agent_name(self) -> str:
        return "solution_architect"
    
    def _get_system_message(self) -> str:
        return """You are a solution architect that creates concrete code changes.
        When given code and an intent:
        1. Analyze the current code structure
        2. For each file needing changes:
           - Small files (<100 lines): Provide complete new content
           - Large files: Provide unified diff
        3. Return a JSON object with this structure:
        {
            "actions": [
                {
                    "file_path": "path/to/file",
                    "content": "new file content or diff"
                }
            ]
        }"""

    def _format_request(self, intent: Dict[str, Any]) -> str:
        return f"""Based on this intent and code, generate necessary changes.

        INTENT:
        {intent.get('intent')}

        CURRENT CODE:
        {intent.get('discovery_output', {}).get('discovery_output', '')}

        Return a JSON object containing an actions array with file changes."""
        
    async def analyze(self, context: Dict[str, Any]) -> str:
        """Legacy method for compatibility"""
        response = await self.process(context)
        return response.data.get("response", "")