# src/agents/solution_architect.py

from typing import Dict, Any, Optional
from .base import BaseAgent, LLMProvider, AgentResponse
import structlog

logger = structlog.get_logger()

class SolutionArchitect(BaseAgent):
    """Solution architect that analyzes discovery output and suggests possible code changes"""
    
    def __init__(self, 
                 provider: LLMProvider = LLMProvider.ANTHROPIC,  
                 model: str = "claude-3-sonnet-20240229"):      
        """Initialize with specified provider"""
        super().__init__(
            provider=provider,
            model=model,           
            temperature=0          
        )

    def _get_agent_name(self) -> str:
        return "solution_architect"
    
    def _get_system_message(self) -> str:
        return """You are a solution architect that analyzes code and suggests possible changes.
        When given discovery analysis and an intent:

        1. First, validate if there's enough information to proceed
           - If the intent is unclear, return {"needs_clarification": "specific question"}
           - If data is insufficient, return {"needs_information": ["missing items"]}
           - If no changes needed, return {"no_changes_needed": "reason"}

        2. If changes are possible, suggest an approach:
           - What files might need changing
           - What specific changes could help
           - Any potential risks or concerns
           - What to validate after changes

        3. Return suggestions in this format:
        {
            "analysis": {
                "feasible": true/false,
                "risks": ["any potential issues"],
                "prerequisites": ["any required setup"]
            },
            "suggestions": [
                {
                    "file_path": "path/to/file",
                    "change_type": "modify/create/delete",
                    "rationale": "why this change helps",
                    "suggested_approach": "how to implement"
                }
            ],
            "validation": {
                "requirements": ["what to check"],
                "concerns": ["what might break"]
            }
        }"""

    def _format_request(self, intent: Optional[Dict[str, Any]]) -> str:
        """Format the request for the LLM"""
        if not isinstance(intent, dict):
            return "Error: Invalid input"
            
        discovery_data = intent.get('discovery_data', {})
        intent_desc = intent.get('intent', {})
        context = intent.get('context', {})
        
        # Extract files and their content from discovery data
        files = discovery_data.get('files', {})
        file_content = ""
        for file_path in files:
            if isinstance(files[file_path], str):
                file_content += f"\nFile: {file_path}\n{files[file_path]}\n"
        
        # Include iteration context if available
        iteration_info = ""
        if context:
            iteration_info = f"""
            Iteration Context:
            - Previous attempts: {len(context.get('previous_attempts', []))}
            - Last issues: {context.get('last_issues', 'None')}
            """
        
        return f"""Analyze this codebase and intent, suggest possible changes if appropriate.

        INTENT:
        {intent_desc.get('description', 'No description provided')}
        
        PROJECT FILES:
        {file_content}
        
        {iteration_info}

        First determine if changes are appropriate and feasible.
        If yes, suggest specific approaches that might help.
        If no, explain why not."""

    async def process(self, context: Dict[str, Any]) -> AgentResponse:
        """Process the architect request with minimal validation"""
        try:
            response = await super().process(context)
            
            if response.success:
                data = response.data.get('response', {})
                logger.debug("architect.response_received", 
                           raw_response=data)
                
                # Check for special cases
                if 'needs_clarification' in data:
                    logger.info("architect.needs_clarification",
                              question=data['needs_clarification'])
                    return AgentResponse(
                        success=True,
                        data={"needs_clarification": data['needs_clarification']},
                        error=None
                    )
                    
                if 'needs_information' in data:
                    logger.info("architect.needs_information",
                              missing=data['needs_information'])
                    return AgentResponse(
                        success=True,
                        data={"needs_information": data['needs_information']},
                        error=None
                    )
                    
                if 'no_changes_needed' in data:
                    logger.info("architect.no_changes_needed",
                              reason=data['no_changes_needed'])
                    return AgentResponse(
                        success=True,
                        data={"no_changes_needed": data['no_changes_needed']},
                        error=None
                    )
                
                # For actual suggestions, do minimal validation
                if 'suggestions' in data:
                    logger.info("architect.suggestions_provided",
                              count=len(data['suggestions']))
                
                return AgentResponse(
                    success=True,
                    data=data
                )
                
            return response
            
        except Exception as e:
            logger.error("architect.process_failed", error=str(e))
            return AgentResponse(
                success=False,
                data={},
                error=str(e)
            )