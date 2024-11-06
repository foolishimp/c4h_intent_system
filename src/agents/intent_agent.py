# src/agents/intent_agent.py

from typing import Dict, Any, List, Optional
from pathlib import Path
import structlog
import autogen
import os

from models.intent import Intent, IntentStatus
from agents.discovery import DiscoveryAgent 
from agents.solution_architect import SolutionArchitect
from agents.coder import Coder, MergeMethod
from agents.assurance import AssuranceAgent
from skills.semantic_interpreter import SemanticInterpreter
from skills.semantic_loop import SemanticLoop

logger = structlog.get_logger()

class IntentAgent:
    """Agent responsible for orchestrating the intent processing workflow"""
    
    def __init__(self, max_iterations: int = 3):
        """Initialize the intent agent and its sub-agents"""
        self.max_iterations = max_iterations
        
        # Initialize base configuration
        config_list = self._get_config_list()
        
        # Initialize specialized agents
        self.discovery = DiscoveryAgent(config_list)         
        self.architect = SolutionArchitect(config_list)         
        self.coder = Coder(config_list)         
        self.assurance = AssuranceAgent(config_list)

        # Initialize semantic skills
        self.interpreter = SemanticInterpreter(config_list)
        self.semantic_loop = SemanticLoop(config_list, max_iterations)

        logger.info("intent_agent.initialized", max_iterations=max_iterations)

    def _get_config_list(self) -> List[Dict[str, Any]]:
        """Get OpenAI configuration list"""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        return [{"model": "gpt-4", "api_key": api_key}]

    async def _execute_discovery(self, intent: Intent) -> Dict[str, Any]:
        """Execute discovery phase"""
        logger.info("discovery.starting", intent_id=str(intent.id))
        print("\nRunning discovery and analysis...")
        intent.status = IntentStatus.ANALYZING
        return await self.discovery.analyze(str(intent.project_path))

    async def _execute_solution(self, intent: Intent, discovery_output: str) -> Dict[str, Any]:
        """Execute solution planning phase"""
        logger.info("solution.starting", intent_id=str(intent.id))
        
        # Get raw solution from architect
        solution_context = {
            "intent": intent.description,
            "discovery_output": discovery_output
        }
        
        response = await self.architect.analyze(solution_context)
        logger.debug("solution.architect_response", response=response)
        
        # Use semantic interpreter to extract actions
        result = await self.interpreter.interpret(
            content=response,
            prompt="""Find all code change actions in this response.
                     Each action should have:
                     - file_path: Path to the file to modify
                     - changes: Complete new file content
                     Return as JSON: {"actions": [...]}""",
            context_type="solution_analysis",
            intent_id=str(intent.id)
        )
        
        if not result.data or "actions" not in result.data:
            raise ValueError("No valid actions found in solution architect response")
            
        return {
            "actions": result.data["actions"],
            "context": {
                "full_response": response,
                "interpretation": result.raw_response
            }
        }

    async def _execute_implementation(self, intent: Intent, solution: Dict[str, Any]) -> Dict[str, Any]:
        """Execute implementation phase with semantic loop"""
        logger.info("implementation.starting", intent_id=str(intent.id))
        intent.status = IntentStatus.TRANSFORMING
        
        actions = solution.get("actions", [])
        if not actions:
            raise ValueError("No actions to implement")

        # Define success criteria
        def check_success(result: Any) -> bool:
            return (isinstance(result, dict) and 
                   result.get("status") == "success" and 
                   not result.get("failed_files", []))

        # Use semantic loop for implementation
        loop_result = await self.semantic_loop.iterate(
            initial_result={"actions": actions},
            improvement_goal="""Implement these code changes successfully.
                              For any failures:
                              1. Analyze the error
                              2. Suggest fixes
                              3. Try alternative approaches""",
            success_check=check_success
        )
        
        # Update intent status based on result
        final_result = loop_result["final_result"]
        if check_success(final_result):
            intent.status = IntentStatus.COMPLETED
        else:
            intent.status = IntentStatus.FAILED
        
        return {
            "status": final_result.get("status", "failed"),
            "modified_files": final_result.get("modified_files", []),
            "failed_files": final_result.get("failed_files", []),
            "iterations": loop_result["iterations"],
            "context": loop_result["context"]
        }

    async def process(self, project_path: Path, intent_desc: Dict[str, Any]) -> Dict[str, Any]:
        """Process an intent through the complete workflow"""
        print(f"\nStarting refactoring process...")
        print(f"Project path: {project_path}")
        print(f"Intent: {intent_desc.get('description', '')}")
        print(f"Merge strategy: {intent_desc.get('merge_strategy', 'llm')}\n")

        intent = Intent(
            description=intent_desc,
            project_path=str(project_path)
        )
        
        context = {}
        try:
            # Discovery Phase
            discovery_output = await self._execute_discovery(intent)
            
            # Solution Phase with semantic interpretation
            solution = await self._execute_solution(intent, discovery_output)
            
            # Implementation Phase with semantic loop
            implementation_result = await self._execute_implementation(intent, solution)
            
            # Store everything in context for debugging
            context.update({
                "discovery_output": discovery_output,
                "solution": solution,
                "implementation": implementation_result
            })
            
            return {
                "status": implementation_result["status"],
                "context": context,
                "iterations": implementation_result["iterations"]
            }
            
        except Exception as e:
            logger.error("intent_processing.failed",
                        intent_id=str(intent.id),
                        error=str(e))
            intent.status = IntentStatus.FAILED
            return {
                "status": "failed",
                "error": str(e),
                "context": context
            }