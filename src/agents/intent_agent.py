# src/agents/intent_agent.py

from typing import Dict, Any, Optional, List
from pathlib import Path
import structlog
import asyncio
from dataclasses import dataclass
from datetime import datetime

from models.intent import Intent, IntentStatus
from agents.discovery import DiscoveryAgent 
from agents.solution_architect import SolutionArchitect
from agents.coder import Coder
from agents.assurance import AssuranceAgent
from skills.semantic_extract import SemanticExtract
from skills.semantic_iterator import SemanticIterator
from skills.shared.types import ExtractConfig, InterpretResult

logger = structlog.get_logger()

@dataclass
class IntentContext:
    """Context maintained between intent iterations"""
    original_intent: Dict[str, Any]
    iteration_count: int = 0
    max_iterations: int = 3
    assurance_outputs: List[Dict[str, Any]] = None
    sub_intent: Optional[Dict[str, Any]] = None
    
    def increment(self) -> bool:
        """Increment iteration count and check if max reached"""
        self.iteration_count += 1
        return self.iteration_count < self.max_iterations
    
    def update_from_assurance(self, assurance_result: Dict[str, Any]) -> None:
        """Update context with assurance results"""
        if self.assurance_outputs is None:
            self.assurance_outputs = []
        self.assurance_outputs.append(assurance_result)
        
        # Create focused sub-intent if needed
        if not assurance_result.get('success'):
            self.sub_intent = {
                "type": "fix_validation",
                "description": "Fix validation failures from previous attempt",
                "validation_errors": assurance_result.get('error'),
                "parent_intent": self.original_intent
            }

class IntentAgent:
    """Orchestrates the complete intent processing workflow"""
    
    def __init__(self, max_iterations: int = 3):
        """Initialize intent agent with iteration limit"""
        # Initialize specialized agents
        self.discovery = DiscoveryAgent()
        self.architect = SolutionArchitect()
        self.coder = Coder()
        self.assurance = AssuranceAgent()
        
        # Initialize semantic tools
        self.extractor = SemanticExtract()
        self.semantic_iterator = SemanticIterator([])
        
        logger.info("intent_agent.initialized", max_iterations=max_iterations)

    async def _execute_discovery(self, intent: Intent) -> Dict[str, Any]:
        """Execute discovery/scope phase"""
        logger.info("discovery.starting", intent_id=str(intent.id))
        print("\nRunning project discovery...")
        
        intent.status = IntentStatus.ANALYZING
        result = await self.discovery.process({
            "project_path": str(intent.project_path),
            "intent": intent.description
        })
        
        if not result.success:
            raise ValueError(f"Discovery failed: {result.error}")
            
        return result.data

    async def _execute_solution_planning(self, intent: Intent, discovery_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute solution design phase"""
        logger.info("solution.planning", intent_id=str(intent.id))
        print("\nPlanning solution approach...")
        
        result = await self.architect.process({
            "intent": intent.description,
            "discovery_data": discovery_data,
            "context": intent.context  # Pass through any iteration context
        })
        
        if not result.success:
            raise ValueError(f"Solution planning failed: {result.error}")
            
        return result.data

    async def _execute_implementation(self, intent: Intent, solution: Dict[str, Any]) -> Dict[str, Any]:
        """Execute implementation phase"""
        logger.info("implementation.starting", intent_id=str(intent.id))
        intent.status = IntentStatus.TRANSFORMING
        
        # Extract actions from solution
        actions = await self._extract_actions(solution)
        
        results = {
            "changes": [],
            "assurance_results": []
        }
        
        # Process each action
        for action in actions:
            # Apply change
            coder_result = await self.coder.process(action)
            if not coder_result.success:
                logger.error("coder.failed", error=coder_result.error)
                continue
            
            results["changes"].append({
                "action": action,
                "result": coder_result.data
            })
            
        return results
        
    async def _execute_assurance(self, intent: Intent, changes: Dict[str, Any]) -> Dict[str, Any]:
        """Execute assurance phase"""
        logger.info("assurance.starting", intent_id=str(intent.id))
        intent.status = IntentStatus.VALIDATING
        
        result = await self.assurance.process({
            "changes": changes,
            "project_path": str(intent.project_path)
        })
        
        return result.data

    async def _extract_actions(self, solution: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract implementation actions from solution"""
        extract_result = await self.extractor.extract(
            content=solution,
            prompt="Extract all concrete code change actions",
            format_hint="json"
        )
        
        if not extract_result.success:
            raise ValueError(f"Failed to extract actions: {extract_result.error}")
            
        return extract_result.value.get("actions", [])

    async def process(self, project_path: Path, intent_desc: Dict[str, Any]) -> Dict[str, Any]:
        """Process an intent through the complete workflow with retries"""
        # Create initial intent and context
        intent = Intent(
            description=intent_desc,
            project_path=str(project_path)
        )
        
        context = IntentContext(
            original_intent=intent_desc,
            max_iterations=self.max_iterations
        )
        
        while context.increment():
            try:
                logger.info("intent.iteration_starting",
                           intent_id=str(intent.id),
                           iteration=context.iteration_count)
                
                # Execute workflow phases
                discovery_data = await self._execute_discovery(intent)
                
                solution = await self._execute_solution_planning(
                    intent,
                    discovery_data
                )
                
                implementation_results = await self._execute_implementation(
                    intent,
                    solution
                )
                
                assurance_results = await self._execute_assurance(
                    intent,
                    implementation_results["changes"]
                )
                
                # Update context with results
                context.update_from_assurance(assurance_results)
                
                # Check if we succeeded
                if assurance_results.get("success"):
                    intent.status = IntentStatus.COMPLETED
                    return {
                        "status": "success",
                        "intent_id": str(intent.id),
                        "iterations": context.iteration_count,
                        "changes": implementation_results["changes"],
                        "assurance": assurance_results
                    }
                
                # Update intent for next iteration
                intent.description = context.sub_intent or intent_desc
                
            except Exception as e:
                logger.error("intent.iteration_failed",
                            intent_id=str(intent.id),
                            iteration=context.iteration_count,
                            error=str(e))
                context.update_from_assurance({
                    "success": False,
                    "error": str(e)
                })
        
        # If we get here, we hit max iterations
        intent.status = IntentStatus.FAILED
        return {
            "status": "failed",
            "intent_id": str(intent.id),
            "iterations": context.iteration_count,
            "error": "Maximum iterations reached",
            "last_assurance": context.assurance_outputs[-1] if context.assurance_outputs else None
        }