"""
Solution designer agent implementation.
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
            config=config  # Pass config directly
        )
        self.logger = structlog.get_logger(agent="solution_designer")

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
    }

    Your response must be valid JSON. The diff section should use standard unified diff format with - for removed lines and + for added lines.

    Example response for adding logging:
    {
        "changes": [
            {
                "file_path": "sample.py",
                "type": "modify",
                "description": "Add logging instead of print statements",
                "diff": "diff --git a/sample.py b/sample.py\\n--- a/sample.py\\n+++ b/sample.py\\n@@ -1,6 +1,9 @@\\n+import logging\\n+\\n+logging.basicConfig(level=logging.INFO)\\n\\n def greet(name):\\n-    print(f\\"Hello, {name}!\\")\\n+    logging.info(f\\"Greeting user: {name}\\")\\n+    return f\\"Hello, {name}!\\"\\n"
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
        
        IMPORTANT: Provide ALL code changes in git diff format using - for removed lines and + for added lines.
        Include proper diff headers and chunk headers (@@ marks).
        
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
        """Process solution design request with proper response handling"""
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

            # Get LLM response
            response = await self.llm.process(self._format_request(context))

            if not response.success:
                return response

            # Ensure response is properly structured
            processed_response = self._process_llm_response(response.data)
            
            # Return complete response with status
            return AgentResponse(
                success=True,
                data={
                    "response": processed_response,
                    "status": "completed",
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

        except Exception as e:
            self.logger.error("design_process_failed", error=str(e))
            return AgentResponse(
                success=False,
                data={},
                error=str(e)
            )

    def _process_llm_response(self, response_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process and validate LLM response"""
        if not isinstance(response_data, dict):
            return {
                "needs_clarification": "Invalid response format from LLM"
            }

        # Handle special cases
        if "needs_clarification" in response_data:
            return response_data

        if "no_changes_needed" in response_data:
            return response_data

        # Process normal change response
        if "changes" not in response_data:
            return {
                "needs_clarification": "No changes specified in response"
            }

        # Ensure changes is a list
        changes = response_data["changes"]
        if not isinstance(changes, list):
            changes = [changes]

        # Return properly formatted response
        return {
            "changes": changes,
            "message": f"Generated {len(changes)} change(s)"
        }