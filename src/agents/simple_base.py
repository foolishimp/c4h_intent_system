# src/agents/intent_agent.py

from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import structlog
import asyncio
from dataclasses import dataclass
from enum import Enum

from models.intent import Intent, IntentStatus
from agents.discovery import DiscoveryAgent 
from agents.solution_architect import SolutionArchitect
from agents.coder import Coder, MergeMethod
from agents.assurance import AssuranceAgent
from skills.semantic_iterator import SemanticIterator
from skills.semantic_extract import SemanticExtract
from skills.shared.types import ExtractConfig, InterpretResult

logger = structlog.get_logger()

class ValidationScope(str, Enum):
    """Validation scope levels"""
    FILE = "file"      # Validate individual file changes
    MODULE = "module"  # Validate related files together
    PROJECT = "project"  # Validate entire project

@dataclass
class ValidationStrategy:
    """Defines how validation should be performed"""
    scope: ValidationScope
    max_retries: int = 3
    allow_partial: bool = False
    rollback_on_failure: bool = True
    validation_timeout: int = 300  # 5 minutes

class IntentAgent:
    """Orchestrates the complete intent processing workflow with validation"""
    
    def __init__(self, 
                 validation_strategy: Optional[ValidationStrategy] = None,
                 max_iterations: int = 3):
        """Initialize intent agent with validation strategy"""
        self.max_iterations = max_iterations
        self.validation_strategy = validation_strategy or ValidationStrategy(
            scope=ValidationScope.FILE
        )
        
        # Initialize specialized agents
        self.discovery = DiscoveryAgent()
        self.architect = SolutionArchitect()
        self.coder = Coder()
        self.assurance = AssuranceAgent()
        
        # Initialize semantic tools
        self.semantic_iterator = SemanticIterator([])  # Config passed in process()
        self.extractor = SemanticExtract()
        
        logger.info("intent_agent.initialized",
                   max_iterations=max_iterations,
                   validation_strategy=validation_strategy)

    async def _execute_discovery(self, intent: Intent) -> Dict[str, Any]:
        """Execute discovery phase"""
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

    async def _execute_solution_planning(self, 
                                      intent: Intent, 
                                      discovery_data: Dict[str, Any]) -> Dict[str, Any]:
        """Plan solution with validation requirements"""
        logger.info("solution.planning", intent_id=str(intent.id))
        print("\nPlanning solution and validation strategy...")
        
        result = await self.architect.process({
            "intent": intent.description,
            "discovery_data": discovery_data,
            "validation_scope": self.validation_strategy.scope,
            "require_tests": True
        })
        
        if not result.success:
            raise ValueError(f"Solution planning failed: {result.error}")
            
        return result.data

    async def _execute_changes(self,
                             intent: Intent,
                             solution: Dict[str, Any]) -> Dict[str, Any]:
        """Execute changes with validation"""
        logger.info("changes.starting", intent_id=str(intent.id))
        intent.status = IntentStatus.TRANSFORMING
        
        async def apply_and_validate(changes: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
            """Apply changes and validate results"""
            try:
                # Apply changes
                coder_result = await self.coder.process(changes)
                if not coder_result.success:
                    return False, {"error": coder_result.error}
                
                # Run validation
                validation_result = await self.assurance.process({
                    "changes": coder_result.data,
                    "validation": solution.get("validation", {})
                })
                
                return validation_result.success, validation_result.data
                
            except Exception as e:
                return False, {"error": str(e)}

        # Configure semantic iteration
        config = ExtractConfig(
            pattern="Extract each code change as a separate action",
            validation=solution.get("validation", {})
        )
        
        # Use semantic iterator for changes
        iterator = await self.semantic_iterator.iter_extract(
            solution.get("changes", []),
            config
        )
        
        results = {
            "successful_changes": [],
            "failed_changes": [],
            "validation_results": []
        }
        
        while iterator.has_next():
            change = next(iterator)
            success, result = await apply_and_validate(change)
            
            if success:
                results["successful_changes"].append(change)
                results["validation_results"].append(result)
            else:
                if self.validation_strategy.rollback_on_failure:
                    # Implement rollback logic here
                    pass
                    
                if not self.validation_strategy.allow_partial:
                    raise ValueError(f"Change failed: {result.get('error')}")
                    
                results["failed_changes"].append({
                    "change": change,
                    "error": result.get("error")
                })
        
        # Update intent status
        if not results["failed_changes"]:
            intent.status = IntentStatus.COMPLETED
        elif self.validation_strategy.allow_partial:
            intent.status = IntentStatus.COMPLETED
            logger.warning("intent.partial_completion",
                         failed_count=len(results["failed_changes"]))
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
            
            results = await self._execute_changes(intent, solution)
            
            # Prepare response
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