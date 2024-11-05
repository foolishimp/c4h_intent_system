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

        logger.info("intent_agent.initialized", max_iterations=max_iterations)

    def _get_config_list(self) -> List[Dict[str, Any]]:
        """Get OpenAI configuration list"""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        return [{"model": "gpt-4o", "api_key": api_key}]

    async def _execute_discovery(self, intent: Intent) -> Dict[str, Any]:
        """Execute discovery phase"""
        logger.info("discovery.starting", intent_id=str(intent.id))
        print("\nRunning discovery and analysis...")
        intent.status = IntentStatus.ANALYZING
        return await self.discovery.analyze(str(intent.project_path))

    async def _execute_solution(self, intent: Intent, discovery_output: str) -> Dict[str, Any]:
        """Execute solution planning phase"""
        logger.info("solution.starting", intent_id=str(intent.id))
        
        # Pass raw discovery output directly
        solution_context = {
            "intent": intent.description,
            "discovery_output": discovery_output
        }
    
        return await self.architect.analyze(solution_context)

    async def _execute_implementation(self, intent: Intent, solution: Dict[str, Any]) -> Dict[str, Any]:
        """Execute implementation phase"""
        logger.info("implementation.starting", intent_id=str(intent.id))
        intent.status = IntentStatus.TRANSFORMING
        
        # Solution architect returns the full response with actions
        # We just need to pass it through with the merge strategy
        return await self.coder.transform({
            **solution,  # Pass through the solution with actions
            "merge_strategy": intent.description.get("merge_strategy", MergeMethod.LLM)
        })


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
            # Discovery Phase - Keep raw output
            discovery_output = await self._execute_discovery(intent)
            
            # Solution Phase - Pass raw discovery output
            solution = await self._execute_solution(intent, discovery_output)
            
            # Implementation Phase - Pass solution dict
            implementation_result = await self._execute_implementation(intent, solution)
            
            if implementation_result["status"] != "success":
                intent.status = IntentStatus.FAILED
                return implementation_result
                
            # Store everything in context for debugging
            context.update({
                "discovery_output": discovery_output,
                "solution": solution,
                "implementation": implementation_result
            })
            
            # Success path
            intent.status = IntentStatus.COMPLETED
            return {
                "status": "success",
                "context": context,
                "iterations": 1
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