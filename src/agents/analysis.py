# src/agents/analysis.py

from typing import Dict, Any
from .base import BaseAgent, AgentConfig

class AnalysisAgent(BaseAgent):
    """Agent responsible for analyzing code and planning transformations"""
    
    def __init__(self):
        super().__init__(AgentConfig(
            name="analyzer",
            system_message="""You are an analysis agent that plans code transformations.
            Your role is to:
            1. Understand the requested changes
            2. Analyze the project structure
            3. Plan specific code modifications
            4. Provide detailed transformation instructions"""
        ))

    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Process code analysis request"""
        project_content = context.get("discovery_output")
        intent_description = context.get("intent_description")
        
        if not project_content or not intent_description:
            raise ValueError("Missing required context")
            
        # Use AutoGen for analysis
        analysis_prompt = f"""
        Given the following project structure:
        {project_content}
        
        And the transformation request:
        {intent_description}
        
        Provide a detailed plan for code modifications including:
        1. Files to modify
        2. Specific changes for each file
        3. Order of operations
        4. Validation requirements
        """
        
        response = await self.agent.generate_response(analysis_prompt)
        return {"transformation_plan": response}
