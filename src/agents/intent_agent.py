# src/agents/intent_agent.py

from typing import Dict, Any, Optional
from pathlib import Path
import structlog
import asyncio

from ..models.intent import Intent, IntentStatus
from .discovery import DiscoveryAgent 
from .solution_architect import SolutionArchitect
from .coder import Coder, MergeMethod
from .assurance import AssuranceAgent
from ..skills.semantic_extract import SemanticExtract
from ..skills.semantic_iterator import SemanticIterator

logger = structlog.get_logger()

class IntentAgent:
    """Agent responsible for orchestrating the intent processing workflow"""
    
    def __init__(self, max_iterations: int = 3):
        """Initialize intent agent with validation strategy"""
        self.max_iterations = max_iterations
        
        # Initialize specialized agents
        self.discovery = DiscoveryAgent()
        self.architect = SolutionArchitect()
        self.coder = Coder()
        self.assurance = AssuranceAgent()
        
        # Initialize semantic tools
        self.extractor = SemanticExtract()
        self.semantic_iterator = SemanticIterator([])  # Config passed in process()
        
        logger.info("intent_agent.initialized", max_iterations=max_iterations)

    async def _execute_discovery(self, intent: Intent) -> Dict[str, Any]:
        """Execute discovery phase"""
        logger.info("discovery.starting", intent_id=str(intent.id))
        print("\nRunning project discovery...")
        
        intent.status = IntentStatus.ANALYZING
        result = await self.discovery.process({
            "project_path": str(intent.project_path)
        })
        
        if not result.success:
            raise ValueError(f"Discovery failed: {result.error}")
            
        return result.data

    async def _execute_solution_planning(self, intent: Intent, discovery_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute solution planning phase"""
        logger.info("solution.planning", intent_id=str(intent.id))
        
        result = await self.architect.process({
            "intent": intent.description,
            "discovery_output": discovery_data
        })
        
        if not result.success:
            raise ValueError(f"Solution planning failed: {result.error}")
            
        return result.data

    async def _execute_implementation(self, intent: Intent, solution: Dict[str, Any]) -> Dict[str, Any]:
        """Execute implementation phase"""
        logger.info("implementation.starting", intent_id=str(intent.id))
        intent.status = IntentStatus.TRANSFORMING
        
        # Extract actions from solution
        extract_result = await self.extractor.extract(
            content=solution,
            prompt="""Find all code change actions. Each action should have:
                    - file_path: Path to the file to modify
                    - change_type: Type of change
                    - instructions: Change instructions""",
            format_hint="json"
        )
        
        if not extract_result.success:
            raise ValueError(f"Failed to extract actions: {extract_result.error}")
            
        actions = extract_result.value.get("actions", [])
        if not actions:
            raise ValueError("No valid actions found in solution")
        
        # Process each action
        results = {
            "successful_changes": [],
            "failed_changes": [],
            "validation_results": []
        }
        
        for action in actions:
            # Apply change
            change_result = await self.coder.process(action)
            if not change_result.success:
                results["failed_changes"].append({
                    "action": action,
                    "error": change_result.error
                })
                continue
                
            # Validate change
            validation_result = await self.assurance.process({
                "changes": change_result.data,
                "validation": solution.get("validation", {})
            })
            
            if validation_result.success:
                results["successful_changes"].append(action)
                results["validation_results"].append(validation_result.data)
            else:
                results["failed_changes"].append({
                    "action": action,
                    "error": validation_result.error
                })
        
        # Update intent status
        if not results["failed_changes"]:
            intent.status = IntentStatus.COMPLETED
        else:
            intent.status = IntentStatus.FAILED
            
        return results

    async def process(self, project_path: Path, intent_desc: Dict[str, Any]) -> Dict[str, Any]:
        """Process an intent through the complete workflow"""
        try:
            # Create intent
            intent = Intent(
                description=intent_desc,
                project_path=str(project_path)
            )
            
            logger.info("intent.processing", 
                       intent_id=str(intent.id),
                       project_path=str(project_path))
            
            # Execute workflow phases
            discovery_data = await self._execute_discovery(intent)
            
            solution = await self._execute_solution_planning(
                intent,
                discovery_data
            )
            
            results = await self._execute_implementation(intent, solution)
            
            return {
                "status": "success" if intent.status == IntentStatus.COMPLETED else "failed",
                "intent_id": str(intent.id),
                "changes": results["successful_changes"],
                "failed_changes": results["failed_changes"],
                "validation_results": results["validation_results"],
                "context": {
                    "discovery": discovery_data,
                    "solution": solution,
                    "intent_status": intent.status
                }
            }
            
        except Exception as e:
            logger.error("intent.failed",
                        intent_id=str(intent.id) if 'intent' in locals() else None,
                        error=str(e))
            return {
                "status": "failed",
                "error": str(e)
            }