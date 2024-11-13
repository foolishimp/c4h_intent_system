# src/agents/solution_designer.py

from typing import Dict, Any, Optional
import structlog
from .base import BaseAgent, LLMProvider, AgentResponse

logger = structlog.get_logger()

class SolutionDesigner(BaseAgent):
    """Designs specific code modifications based on intent and discovery analysis.
    
    Responsibilities:
    - Interpret intent and code context
    - Design appropriate code modifications
    - Output structured change plans
    """
    
    def __init__(self, 
                 provider: LLMProvider = LLMProvider.ANTHROPIC,
                 model: Optional[str] = None,
                 temperature: float = 0):
        """Initialize with specified provider"""
        super().__init__(
            provider=provider,
            model=model,
            temperature=temperature
        )
        self.logger = structlog.get_logger(agent="solution_designer")

    def _get_agent_name(self) -> str:
        return "solution_designer"
    
    def _get_system_message(self) -> str:
        return """You are a code modification expert that generates specific code changes.
        When given source code and an intent, you must:

        1. First validate if changes are possible:
           a. If code already has intended changes, return {"no_changes_needed": "explain why"}
           b. If intent is missing or unclear, return {"needs_clarification": "specific question"}
           c. If code is missing, return {"needs_information": ["missing items"]}
           
        2. For each required change, provide exact code modifications:
        {
            "changes": [
                {
                    "file_path": "exact/path/to/file",
                    "change_type": "modify",
                    "original_code": "...",
                    "modified_code": "...",
                    "description": "..."
                }
            ]
        }
        3. Guidelines:
           - Return complete, valid code for each change
           - Preserve existing functionality unless explicitly changed
           - All necessary imports must be included in the code
           - Return ONLY valid JSON matching this schema"""

    def _format_request(self, context: Optional[Dict[str, Any]]) -> str:
        """Format the solution design prompt using provided context"""
        self.logger.info("formatting_request",
                        intent=context.get('intent', {}).get('description'),
                        files=len(context.get('discovery_data', {}).get('files', {})))

        if not context:
            return "Error: No context provided"

        return f"""Based on the following code context, design specific code changes to implement this intent.

INTENT:
{context.get('intent', {}).get('description', 'No description provided')}

SOURCE CODE:
{context.get('discovery_data', {}).get('files', {})}

CONTEXT:
- Iteration: {context.get('iteration', 0)}
- Previous attempts: {context.get('previous_attempts', [])}"""

    async def process(self, context: Optional[Dict[str, Any]]) -> AgentResponse:
        """Process solution design request.
        Follows single responsibility principle - only designs solutions."""
        try:
            # Log request receipt
            self.logger.info("design_request_received",
                           intent=context.get('intent', {}).get('description'),
                           has_discovery=bool(context.get('discovery_data')))

            # Pass through to LLM
            response = await super().process(context)
            
            # Pass through response
            return response

        except Exception as e:
            # Log error but don't transform it
            self.logger.error("design_process_failed", error=str(e))
            raise