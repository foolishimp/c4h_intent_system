# src/agents/solution_designer.py

from typing import Dict, Any, Optional
import structlog
from .base import BaseAgent, LLMProvider, AgentResponse

logger = structlog.get_logger()

class SolutionDesigner(BaseAgent):
    """Designs specific code modifications based on intent and discovery analysis."""
    
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
        }"""

    def _format_request(self, context: Optional[Dict[str, Any]]) -> str:
        """Format the solution design prompt using provided context"""
        if not context:
            return "No context provided. Please specify intent and code to modify."

        # Get file count for logging
        file_count = len(context.get('discovery_data', {}).get('files', {}))
        
        self.logger.info("formatting_request",
                        intent=context.get('intent', {}).get('description'),
                        file_count=file_count)

        return f"""Based on the following code context, design specific code changes to implement this intent.

INTENT:
{context.get('intent', {}).get('description', 'No description provided')}

SOURCE CODE:
{context.get('discovery_data', {}).get('files', {})}

CONTEXT:
- Iteration: {context.get('iteration', 0)}
- Previous attempts: {context.get('previous_attempts', [])}"""

    def _validate_context(self, context: Optional[Dict[str, Any]]) -> Optional[str]:
        """Validate required context fields are present"""
        if not context:
            return None  # Handle in process() as needs_clarification
            
        if not isinstance(context, dict):
            return "Invalid context: must be a dictionary"
            
        if not context.get('intent', {}).get('description'):
            return "Missing required field: intent.description"
            
        if not context.get('discovery_data'):
            return "Missing required field: discovery_data"
            
        return None

    async def process(self, context: Optional[Dict[str, Any]]) -> AgentResponse:
        """Process solution design request.
        Follows single responsibility principle - only designs solutions."""
        try:
            # Handle None or empty context as needs_clarification
            if not context:
                return AgentResponse(
                    success=True,
                    data={
                        "response": {
                            "needs_clarification": "No context provided. Please provide intent and code to modify."
                        }
                    }
                )

            # Validate context and treat missing required data as failure
            validation_error = self._validate_context(context)
            if validation_error:
                return AgentResponse(
                    success=False,
                    data={},
                    error=validation_error
                )

            # Log request receipt
            self.logger.info("design_request_received",
                           intent=context.get('intent', {}).get('description'),
                           has_discovery=bool(context.get('discovery_data')))

            # Pass through to LLM for valid requests
            return await super().process(context)

        except Exception as e:
            self.logger.error("design_process_failed", error=str(e))
            raise