"""
Solution designer implementation for orchestrating code modifications.
Path: src/agents/solution_designer.py
"""

from typing import Dict, Any, Optional
import structlog
from datetime import datetime
from .base import BaseAgent, LLMProvider, AgentResponse

logger = structlog.get_logger()

class SolutionDesigner(BaseAgent):
    """Designs specific code modifications based on intent and discovery analysis."""
    
    def __init__(self, 
                 provider: LLMProvider = LLMProvider.ANTHROPIC,
                 model: Optional[str] = None,
                 temperature: float = 0,
                 config: Optional[Dict[str, Any]] = None):
        """Initialize designer with specified provider."""
        super().__init__(
            provider=provider,
            model=model,
            temperature=temperature,
            config=config
        )

    def _get_agent_name(self) -> str:
        return "solution_designer"
    
    def _get_system_message(self) -> str:
        return """You are a code modification expert that generates specific code changes.
        When given source code and an intent, you will:

        1. First validate if changes are possible:
           a. If code already has intended changes, return {"no_changes_needed": "explain why"}
           b. If intent is missing or unclear, return {"needs_clarification": "specific question"}
           c. If code is missing, return {"needs_information": ["missing items"]}

        2. For each required change, provide modifications in standard git diff format:
        {
            "changes": [
                {
                    "file_path": "exact/path/to/file",
                    "type": "modify",
                    "description": "Brief description of the change",
                    "diff": "diff --git a/path/to/file b/path/to/file\\n--- a/path/to/file\\n+++ b/path/to/file\\n@@ -1,5 +1,6 @@\\n unchanged line\\n-removed line\\n+added line\\n+added line\\n unchanged line"
                }
            ]
        }"""
    
    def _format_request(self, context: Optional[Dict[str, Any]]) -> str:
        """Format the solution design prompt using provided context"""
        if not context:
            return "No context provided. Please specify intent and code to modify."

        # Log raw input for debugging
        logger.debug("solution_design.input", 
                   context=context,
                   has_discovery=bool(context.get('discovery_data')))

        # Get the discovery output which contains file contents
        discovery_data = context.get('discovery_data', {})
        discovery_output = discovery_data.get('discovery_output', '')

        return f"""Based on the following source code, design specific code changes to implement this intent.
        
        INTENT:
        {context.get('intent', {}).get('description', 'No description provided')}

        SOURCE FILES:
        {discovery_output}

        ITERATION: {context.get('iteration', 0)}
        """

    async def process(self, context: Optional[Dict[str, Any]]) -> AgentResponse:
        """Process solution design request"""
        try:
            # Check for discovery output
            if not context.get('discovery_data', {}).get('discovery_output'):
                logger.warning("solution_design.missing_discovery_output")
                return AgentResponse(
                    success=False,
                    data={"status": "failed"},
                    error="Missing discovery output data - cannot analyze code"
                )

            # Pass through to LLM
            response = await super().process(context)
            
            # Add minimal state tracking without modifying response content
            if response.success:
                response.data["status"] = "completed"
            else:
                response.data["status"] = "failed"

            logger.info("solution_design.response_received", response=response.data)
            return response

        except Exception as e:
            logger.error("solution_design.failed", error=str(e))
            return AgentResponse(
                success=False,
                data={"status": "failed"},
                error=str(e)
            )