# src/agents/assurance.py

from typing import Dict, Any
import py_compile
from pathlib import Path
from .base import BaseAgent, AgentConfig

class AssuranceAgent(BaseAgent):
    """Agent responsible for validating code changes"""
    
    def __init__(self):
        super().__init__(AgentConfig(
            name="assurance",
            system_message="""You are an assurance agent that validates code changes.
            Your role is to verify that modifications maintain code integrity."""
        ))

    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Process validation request"""
        modified_files = context.get("modified_files", [])
        project_path = context.get("project_path")
        
        if not project_path:
            raise ValueError("Missing project path")
            
        # Basic validation: Try to compile all Python files
        results = []
        for file_path in modified_files:
            try:
                py_compile.compile(file_path, doraise=True)
                results.append({"file": file_path, "status": "success"})
            except Exception as e:
                results.append({"file": file_path, "status": "failed", "error": str(e)})
                
        return {"validation_results": results}
