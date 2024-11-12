# src/agents/solution_designer.py

from typing import Dict, Any, Optional
import structlog
from .base import BaseAgent, LLMProvider, AgentResponse

logger = structlog.get_logger()

class SolutionDesigner(BaseAgent):
    """Designs specific code modifications based on intent and discovery analysis"""
    
    def __init__(self, 
                 provider: LLMProvider = LLMProvider.ANTHROPIC,
                 model: Optional[str] = None):
        """Initialize with specified provider"""
        super().__init__(
            provider=provider,
            model=model,
            temperature=0
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
                    "file_path": "exact/path/to/file",  # Required
                    "change_type": "modify",            # Required: modify, create, or delete
                    "original_code": "...",             # Required for modify
                    "modified_code": "...",             # Required for modify/create
                    "description": "..."                # Required: explain the change
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
        if not isinstance(context, dict):
            self.logger.error("invalid_context", context_type=type(context))
            return "Error: Invalid input"

        intent = context.get('intent', {})
        discovery_data = context.get('discovery_data', {})
        files = discovery_data.get('files', {})

        self.logger.info("formatting_request",
                        intent_type=intent.get('type'),
                        file_count=len(files),
                        iteration=context.get('iteration', 0))

        return f"""Based on the following code context, design specific code changes to implement this intent.

INTENT:
{intent.get('description', 'No description provided')}

SOURCE CODE:
{files}

Return a valid JSON response containing the required changes."""

    async def process(self, context: Dict[str, Any]) -> AgentResponse:
        """Process the solution design request"""
        try:
            self.logger.info("design_request_received",
                           intent=context.get('intent', {}).get('description'),
                           has_discovery=bool(context.get('discovery_data')))

            # Get LLM response
            response = await super().process(context)
            
            # Simply pass through the LLM response
            return response

        except Exception as e:
            self.logger.error("design_process_failed", error=str(e))
            return AgentResponse(
                success=False,
                data={},
                error=str(e)
            )