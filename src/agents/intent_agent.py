# src/agents/intent_agent.py

import os
import structlog
from typing import Dict, Any, List, Optional
from pathlib import Path
import autogen

from models.intent import Intent, IntentStatus
from agents.discovery import DiscoveryAgent
from agents.coder import Coder
from agents.assurance import AssuranceAgent
from agents.solution_architect import SolutionArchitect

logger = structlog.get_logger()

class IntentAgent:
    """Agent responsible for orchestrating the intent processing workflow"""
    
    def __init__(self, max_iterations: int = 3):
        """Initialize the intent agent and its sub-agents
        
        Args:
            max_iterations: Maximum number of refinement iterations
        """
        self.max_iterations = max_iterations
        
        # Initialize base configuration
        config_list = self._get_config_list()
        
        # Initialize orchestrator for agent coordination
        self.orchestrator = autogen.UserProxyAgent(
            name="intent_orchestrator",
            human_input_mode="NEVER",
            code_execution_config=False,
            system_message="""
            I orchestrate the refactoring workflow by:
            1. Coordinating discovery, solution, implementation, and validation phases
            2. Maintaining context between phases
            3. Managing the success/failure state of the workflow
            """
        )
        
        # Initialize specialized agents
        self.discovery = DiscoveryAgent.from_env()
        self.architect = SolutionArchitect(config_list)
        self.coder = Coder(config_list)
        self.assurance = AssuranceAgent(config_list)
        
        logger.info("intent_agent.initialized", max_iterations=max_iterations)

    def _get_config_list(self) -> List[Dict[str, Any]]:
        """Get OpenAI configuration list
        
        Returns:
            List of configuration dictionaries for OpenAI
        
        Raises:
            ValueError: If OPENAI_API_KEY environment variable is not set
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        return [{"model": "gpt-4", "api_key": api_key}]

    async def _execute_discovery(self, intent: Intent) -> Dict[str, Any]:
        """Execute discovery phase
        
        Args:
            intent: The intent to analyze
            
        Returns:
            Discovery analysis results
            
        Raises:
            ValueError: If discovery fails
        """
        logger.info("discovery.starting", intent_id=str(intent.id))
        intent.status = IntentStatus.ANALYZING
        
        discovery_result = await self.discovery.analyze(str(intent.project_path))
        if not discovery_result:
            raise ValueError("Discovery analysis failed")
            
        return {
            "project_path": str(intent.project_path),
            "discovery_output": discovery_result
        }

    async def _execute_solution(self, intent: Intent, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute solution planning phase
        
        Args:
            intent: The intent being processed
            context: Current workflow context
            
        Returns:
            Solution architecture plan
        """
        logger.info("solution.starting", intent_id=str(intent.id))
        
        solution_context = {
            "intent": intent.description,
            "discovery_output": context.get("discovery_output", {})
        }
        
        solution = await self.architect.analyze(solution_context)
        if not solution or "changes" not in solution:
            raise ValueError("No valid solution generated")
            
        return solution

    async def _execute_implementation(self, intent: Intent, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute implementation phase
        
        Args:
            intent: The intent being processed
            context: Current workflow context
            
        Returns:
            Implementation results
        """
        logger.info("implementation.starting", intent_id=str(intent.id))
        intent.status = IntentStatus.TRANSFORMING
        
        implementation_context = {
            "intent": intent.description,
            "changes": context.get("changes", []),
            "files_to_modify": context.get("files_to_modify", [])
        }
        
        return await self.coder.transform(implementation_context)

    async def _execute_validation(self, intent: Intent, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute validation phase
        
        Args:
            intent: The intent being processed
            context: Current workflow context
            
        Returns:
            Validation results
        """
        logger.info("validation.starting", intent_id=str(intent.id))
        intent.status = IntentStatus.VALIDATING
        
        validation_context = {
            "intent": intent.description,
            "modified_files": context.get("modified_files", []),
            "validation_rules": context.get("validation_rules", [])
        }
        
        return await self.assurance.validate(validation_context)

    async def process(self, project_path: Path, intent_desc: Dict[str, Any]) -> Dict[str, Any]:
        """Process an intent through the complete workflow
        
        Args:
            project_path: Path to the project to refactor
            intent_desc: Structured intent description
            
        Returns:
            Processing results with status and context
        """
        # Initialize intent
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
            context.update(solution_result)
            
            # Implementation Phase
            implementation_result = await self._execute_implementation(intent, context)
            if implementation_result["status"] != "success":
                intent.status = IntentStatus.FAILED
                return implementation_result
            context.update(implementation_result)
            
            # Validation Phase
            validation_result = await self._execute_validation(intent, context)
            if validation_result["status"] == "success":
                intent.status = IntentStatus.COMPLETED
                return {
                    "status": "success",
                    "context": context,
                    "iterations": 1
                }
            
            intent.status = IntentStatus.FAILED
            return {
                "status": "failed",
                "error": validation_result.get("error", "Validation failed"),
                "context": context
            }
            
        except Exception as e:
            logger.error("intent_processing.failed",
                        intent_id=str(intent.id),
                        error=str(e),
                        exc_info=True)
            intent.status = IntentStatus.FAILED
            return {
                "status": "failed",
                "error": str(e),
                "context": context
            }

    @property
    def supported_stages(self) -> List[str]:
        """Get list of supported workflow stages"""
        return ["discovery", "solution", "implementation", "validation"]