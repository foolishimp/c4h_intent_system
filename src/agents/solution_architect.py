# src/agents/solution_architect.py

from typing import Dict, Any, Optional
from .base import BaseAgent, LLMProvider, AgentResponse
import structlog

logger = structlog.get_logger()

class SolutionArchitect(BaseAgent):
    """Solution architect that analyzes discovery output and provides concrete code changes"""
    
    def __init__(self, 
                 provider: LLMProvider = LLMProvider.ANTHROPIC,  # Changed default to Anthropic
                 model: str = "claude-3-sonnet-20240229"):      # Specified Claude 3.5 Sonnet
        """Initialize with specified provider"""
        super().__init__(
            provider=provider,
            model=model,           # Pass specific model to BaseAgent
            temperature=0,         # We want deterministic responses
            max_retries=2         # Allow one retry for complex analysis
        )

    def _get_agent_name(self) -> str:
        return "solution_architect"
    
    def _get_system_message(self) -> str:
        return """You are a solution architect that creates concrete code changes.
        When given discovery analysis and an intent:

        1. Analyze the current code structure and patterns
        2. For each file needing changes, provide specific modifications:
           - For small files (<100 lines): Provide complete new content
           - For large files: Provide content to change
        3. Consider:
           - Minimal necessary changes
           - Code style consistency
           - Maintainability
        4. Return a JSON object with this structure:
        {
            "actions": [
                {
                    "file_path": "path/to/file",
                    "type": "modify|create|delete",
                    "content": "new content or changes"
                }
            ],
            "rationale": "Brief explanation of the approach"
        }"""

    def _format_request(self, intent: Optional[Dict[str, Any]]) -> str:
        """Format the request for the LLM"""
        if not isinstance(intent, dict):
            return "Error: Invalid input"
            
        return f"""Based on this discovery analysis and intent, generate necessary changes.

        INTENT:
        {intent.get('intent', 'No intent provided')}

        DISCOVERY ANALYSIS:
        {intent.get('discovery_output', 'No discovery output provided')}

        Return a JSON object containing the actions array with specific file changes."""

    async def analyze(self, context: Dict[str, Any]) -> str:
        """Legacy method for backward compatibility
        Note: This will be deprecated in future versions
        """
        logger.warn(f"{self._get_agent_name()}.using_legacy_method")
        response = await self.process(context)
        return response.data.get("response", "")