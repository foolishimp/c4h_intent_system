# src/agents/intent_agent.py

from typing import Dict, Any, List, Optional
from pathlib import Path
import structlog
import autogen
import json
import os

from models.intent import Intent, IntentStatus
from agents.discovery import DiscoveryAgent 
from agents.solution_architect import SolutionArchitect
from agents.coder import Coder
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
        intent.status = IntentStatus.ANALYZING
        
        discovery_result = await self.discovery.analyze(str(intent.project_path))
        if not discovery_result:
            raise ValueError("Discovery analysis failed")
            
        return discovery_result

    async def _execute_solution(self, intent: Intent, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute solution planning phase"""
        logger.info("solution.starting", intent_id=str(intent.id))
        
        # Restore original nesting that worked
        solution_context = {
            "intent": intent.description,
            "discovery_output": {
                "discovery_output": context
            }
        }
    
        return await self.architect.analyze(solution_context)

    async def _execute_implementation(self, intent: Intent, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute implementation phase"""
        logger.info("implementation.starting", intent_id=str(intent.id))
        intent.status = IntentStatus.TRANSFORMING
        
        if "refactor_actions" not in context:
            raise ValueError("No refactor actions in context")
            
        return await self.coder.transform({"actions": context["refactor_actions"]})

    async def process(self, project_path: Path, intent_desc: Dict[str, Any]) -> Dict[str, Any]:
        """Process an intent through the complete workflow"""
        intent = Intent(
            description=intent_desc,
            project_path=str(project_path)
        )
        
        context = {}
        try:
            # Discovery Phase
            discovery_result = await self._execute_discovery(intent)
            context.update(discovery_result)
            
            # Solution Phase
            solution_result = await self._execute_solution(intent, context)
            
            # Handle solution result - can be string or dict
            if isinstance(solution_result, str):
                try:
                    solution_result = json.loads(solution_result)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid solution format: {str(e)}")
            
            # Extract actions and add to context
            if "actions" in solution_result:
                context["refactor_actions"] = solution_result["actions"]
            else:
                raise ValueError("No actions in solution result")
            
            # Implementation Phase
            implementation_result = await self._execute_implementation(intent, context)
            if implementation_result["status"] != "success":
                intent.status = IntentStatus.FAILED
                return implementation_result
            context.update(implementation_result)
            
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