# src/agents/intent_agent.py

from typing import Dict, Any, Optional, List
from pathlib import Path
import structlog
import asyncio
from dataclasses import dataclass
import os
from datetime import datetime

from ..models.intent import Intent, IntentStatus
from .discovery import DiscoveryAgent 
from .solution_designer import SolutionDesigner
from .coder import Coder
from .assurance import AssuranceAgent
from ..skills.semantic_extract import SemanticExtract
from ..skills.semantic_iterator import SemanticIterator
from ..skills.shared.types import ExtractConfig, InterpretResult

logger = structlog.get_logger()

@dataclass
class IntentContext:
    """Context maintained between intent iterations"""
    original_intent: Dict[str, Any]
    iteration_count: int = 0
    max_iterations: int = 3
    assurance_outputs: List[Dict[str, Any]] = None
    sub_intent: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Initialize optional fields"""
        if self.assurance_outputs is None:
            self.assurance_outputs = []
    
    def increment(self) -> bool:
        """Increment iteration count and check if max reached"""
        self.iteration_count += 1
        return self.iteration_count < self.max_iterations
    
    def update_from_assurance(self, assurance_result: Dict[str, Any]) -> None:
        """Update context with assurance results"""
        self.assurance_outputs.append(assurance_result)
        
        # Create focused sub-intent if needed
        if not assurance_result.get('success'):
            self.sub_intent = {
                "type": "fix_validation",
                "description": "Fix validation failures from previous attempt",
                "validation_errors": assurance_result.get('error'),
                "parent_intent": self.original_intent
            }
            logger.info("intent.sub_intent_created", 
                       original=self.original_intent.get('description'),
                       sub_intent=self.sub_intent['description'])

class IntentAgent:
    """Orchestrates the complete intent processing workflow"""
    
    def __init__(self, max_iterations: int = 3):
        """Initialize intent agent with iteration limit"""
        # Initialize basic LLM config
        self.config_list = [{
            "model": "claude-3-sonnet-20240229",
            "api_key": os.getenv("ANTHROPIC_API_KEY"),
            "max_tokens": 4000,
            "temperature": 0
        }]
        
        if not self.config_list[0]["api_key"]:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
        
        # Initialize specialized agents
        self.discovery = DiscoveryAgent()
        self.architect = SolutionDesigner()
        self.coder = Coder()
        self.assurance = AssuranceAgent()
        
        # Initialize semantic tools with config
        self.extractor = SemanticExtract()
        self.semantic_iterator = SemanticIterator(self.config_list)
        
        self.max_iterations = max_iterations
        logger.info("intent_agent.initialized", 
                   max_iterations=max_iterations,
                   model=self.config_list[0]["model"])

    async def _execute_discovery(self, intent: Intent) -> Dict[str, Any]:
        """Execute discovery/scope phase"""
        logger.info("discovery.starting", 
                   intent_id=str(intent.id),
                   project_path=str(intent.project_path))
        
        intent.status = IntentStatus.ANALYZING
        result = await self.discovery.process({
            "project_path": str(intent.project_path),
            "intent": intent.description
        })
        
        if not result.success:
            logger.error("discovery.failed", error=result.error)
            raise ValueError(f"Discovery failed: {result.error}")
            
        logger.info("discovery.completed", files_found=len(result.data.get("files", {})))
        return result.data

    async def _execute_solution_planning(self, 
                                      intent: Intent, 
                                      discovery_data: Dict[str, Any],
                                      context: Optional[IntentContext] = None) -> Dict[str, Any]:
        """Execute solution design phase"""
        logger.info("solution.planning", 
                   intent_id=str(intent.id),
                   intent_type=intent.description.get("type"))
        
        solution_context = {
            "intent": intent.description,
            "discovery_data": discovery_data
        }
        
        # Include iteration context if available
        if context:
            solution_context["iteration"] = context.iteration_count
            solution_context["previous_attempts"] = context.assurance_outputs
            
        result = await self.architect.process(solution_context)
        
        if not result.success:
            logger.error("solution.failed", error=result.error)
            raise ValueError(f"Solution planning failed: {result.error}")
            
        logger.info("solution.completed", 
                   actions=len(result.data.get("actions", [])))
        return result.data

    async def _execute_implementation(self, intent: Intent, solution: Dict[str, Any]) -> Dict[str, Any]:
        """Execute implementation phase"""
        logger.info("implementation.starting", intent_id=str(intent.id))
        intent.status = IntentStatus.TRANSFORMING
        
        # Extract actions from solution
        actions = await self._extract_actions(solution)
        
        results = {
            "changes": [],
            "successful_changes": [],
            "failed_changes": []
        }
        
        # Process each action
        for action in actions:
            try:
                logger.info("implementation.applying_change", 
                           file=action.get("file"),
                           change_type=action.get("type"))
                
                coder_result = await self.coder.process(action)
                
                if coder_result.success:
                    results["successful_changes"].append({
                        "action": action,
                        "result": coder_result.data
                    })
                else:
                    results["failed_changes"].append({
                        "action": action,
                        "error": coder_result.error
                    })
                
                results["changes"].append({
                    "action": action,
                    "result": coder_result.data if coder_result.success else None,
                    "success": coder_result.success,
                    "error": coder_result.error
                })
                
            except Exception as e:
                logger.error("implementation.change_failed",
                           file=action.get("file"),
                           error=str(e))
                results["failed_changes"].append({
                    "action": action,
                    "error": str(e)
                })
        
        logger.info("implementation.completed",
                   total_changes=len(actions),
                   successful=len(results["successful_changes"]),
                   failed=len(results["failed_changes"]))
                   
        return results

    async def _execute_assurance(self, intent: Intent, changes: Dict[str, Any]) -> Dict[str, Any]:
        """Execute assurance phase"""
        logger.info("assurance.starting", 
                   intent_id=str(intent.id),
                   changes_count=len(changes.get("changes", [])))
        
        intent.status = IntentStatus.VALIDATING
        
        result = await self.assurance.process({
            "changes": changes,
            "project_path": str(intent.project_path),
            "intent": intent.description
        })
        
        if result.success:
            logger.info("assurance.passed")
        else:
            logger.warning("assurance.failed", error=result.error)
            
        return result.data

    async def _extract_actions(self, solution: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract implementation actions from solution"""
        extract_result = await self.extractor.extract(
            content=solution,
            prompt="Extract all concrete code change actions as a list of objects with file, type, and changes fields",
            format_hint="json"
        )
        
        if not extract_result.success:
            logger.error("action_extraction.failed", error=extract_result.error)
            raise ValueError(f"Failed to extract actions: {extract_result.error}")
        
        actions = extract_result.value.get("actions", [])
        logger.info("actions.extracted", count=len(actions))
        return actions

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
        
        logger.info("intent.processing_started",
                   intent_id=str(intent.id),
                   project_path=str(project_path),
                   max_iterations=self.max_iterations)
        
        while context.increment():
            try:
                logger.info("intent.iteration_starting",
                           intent_id=str(intent.id),
                           iteration=context.iteration_count)
                
                # Execute workflow phases
                discovery_data = await self._execute_discovery(intent)
                
                solution = await self._execute_solution_planning(
                    intent,
                    discovery_data,
                    context
                )
                
                implementation_results = await self._execute_implementation(
                    intent,
                    solution
                )
                
                assurance_results = await self._execute_assurance(
                    intent,
                    implementation_results
                )
                
                # Update context with results
                context.update_from_assurance(assurance_results)
                
                # Check if we succeeded
                if assurance_results.get("success"):
                    intent.status = IntentStatus.COMPLETED
                    logger.info("intent.completed_successfully",
                              intent_id=str(intent.id),
                              iterations=context.iteration_count)
                    
                    return {
                        "status": "success",
                        "intent_id": str(intent.id),
                        "iterations": context.iteration_count,
                        "changes": implementation_results["changes"],
                        "assurance": assurance_results
                    }
                
                # Update intent for next iteration
                intent.description = context.sub_intent or intent_desc
                logger.info("intent.preparing_next_iteration",
                          iteration=context.iteration_count + 1,
                          has_sub_intent=bool(context.sub_intent))
                
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
        logger.error("intent.max_iterations_reached",
                    intent_id=str(intent.id),
                    iterations=context.iteration_count)
        
        return {
            "status": "failed",
            "intent_id": str(intent.id),
            "iterations": context.iteration_count,
            "error": "Maximum iterations reached",
            "last_assurance": context.assurance_outputs[-1] if context.assurance_outputs else None
        }