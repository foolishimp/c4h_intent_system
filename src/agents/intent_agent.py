# src/agents/intent_agent.py

from typing import Dict, Any, Optional, List
from pathlib import Path
import structlog
from dataclasses import dataclass
from datetime import datetime

from src.models.intent import Intent, IntentStatus
from src.agents.discovery import DiscoveryAgent
from src.agents.solution_designer import SolutionDesigner
from src.agents.coder import Coder, MergeMethod
from src.agents.assurance import AssuranceAgent
from src.skills.semantic_iterator import SemanticIterator
from src.skills.shared.types import ExtractConfig, InterpretResult

logger = structlog.get_logger()

@dataclass
class WorkflowState:
    """Current state of the intent workflow"""
    intent: Intent
    iteration: int = 0
    max_iterations: int = 3
    discovery_data: Optional[Dict[str, Any]] = None
    solution_data: Optional[Dict[str, Any]] = None
    implementation_data: Optional[Dict[str, Any]] = None
    validation_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    @property
    def has_error(self) -> bool:
        return self.error is not None

    @property
    def can_continue(self) -> bool:
        return self.iteration < self.max_iterations and not self.has_error

class IntentAgent:
    """Orchestrates the intent workflow using semantic iteration"""
    
    def __init__(self, max_iterations: int = 3):
        """Initialize intent agent with semantic tools"""
        self.max_iterations = max_iterations
        
        # Initialize base configuration
        config_list = [{
            "model": "claude-3-sonnet-20240229",
            "api_key": os.getenv("ANTHROPIC_API_KEY"),
            "max_tokens": 4000,
            "temperature": 0
        }]

        # Initialize semantic tools
        self.semantic_iterator = SemanticIterator(config_list)
        
        # Initialize specialized agents 
        self.discovery = DiscoveryAgent()
        self.designer = SolutionDesigner() 
        self.coder = Coder()
        self.assurance = AssuranceAgent()
        
        logger.info("intent_agent.initialized",
                   max_iterations=max_iterations,
                   model=config_list[0]["model"])

    async def process(self, project_path: Path, intent_desc: Dict[str, Any]) -> Dict[str, Any]:
        """Process an intent through complete workflow"""
        # Create initial state
        state = WorkflowState(
            intent=Intent(
                description=intent_desc,
                project_path=str(project_path)
            ),
            max_iterations=self.max_iterations
        )

        # Configure workflow iteration
        workflow_config = ExtractConfig(
            pattern="""Determine next workflow action based on current state. Output should be a JSON object with:
            {
                "action": "discovery" | "design" | "implement" | "validate" | "complete" | "error",
                "details": { action specific details }
            }""",
            format="json",
            validation={
                "required_fields": ["action", "details"],
                "allowed_actions": [
                    "discovery",
                    "design", 
                    "implement",
                    "validate",
                    "complete",
                    "error"
                ]
            }
        )

        logger.info("intent.process_started",
                   intent_id=str(state.intent.id),
                   project_path=str(project_path))

        while state.can_continue:
            state.iteration += 1
            
            try:
                # Get next workflow action
                iterator = await self.semantic_iterator.iter_extract(
                    content=state,
                    config=workflow_config
                )

                while iterator.has_next():
                    action = next(iterator)
                    state = await self._execute_action(state, action)
                    
                    if state.has_error or not state.can_continue:
                        break
                        
                    # Provide feedback to iterator
                    iterator.update_context({
                        "previous_state": state
                    })

            except Exception as e:
                state.error = str(e)
                logger.error("intent.iteration_failed",
                           intent_id=str(state.intent.id),
                           iteration=state.iteration,
                           error=str(e))

        # Return final result
        success = not state.has_error and state.intent.status == IntentStatus.COMPLETED
        
        return {
            "status": "success" if success else "failed",
            "intent_id": str(state.intent.id),
            "iterations": state.iteration,
            "changes": state.implementation_data.get("changes", []) if success else [],
            "validation": state.validation_data if success else None,
            "error": state.error
        }

    async def _execute_action(self, state: WorkflowState, action: Dict[str, Any]) -> WorkflowState:
        """Execute a single workflow action"""
        action_type = action["action"]
        details = action["details"]
        
        logger.info("intent.execute_action",
                   intent_id=str(state.intent.id),
                   action=action_type,
                   iteration=state.iteration)

        try:
            match action_type:
                case "discovery":
                    state.intent.status = IntentStatus.ANALYZING
                    result = await self.discovery.process({
                        "project_path": state.intent.project_path,
                        "intent": state.intent.description
                    })
                    if result.success:
                        state.discovery_data = result.data
                    else:
                        state.error = result.error

                case "design":
                    result = await self.designer.process({
                        "intent": state.intent.description,
                        "discovery_data": state.discovery_data,
                        "iteration": state.iteration
                    })
                    if result.success:
                        state.solution_data = result.data.get("response", {})
                    else:
                        state.error = result.error

                case "implement":
                    state.intent.status = IntentStatus.TRANSFORMING
                    result = await self.coder.process(state.solution_data)
                    if result.success:
                        state.implementation_data = result.data
                    else:
                        state.error = result.error

                case "validate":
                    state.intent.status = IntentStatus.VALIDATING
                    result = await self.assurance.process({
                        "changes": state.implementation_data,
                        "project_path": state.intent.project_path,
                        "intent": state.intent.description
                    })
                    if result.success:
                        state.validation_data = result.data
                        if result.data.get("success"):
                            state.intent.status = IntentStatus.COMPLETED
                    else:
                        state.error = result.error

                case "complete":
                    state.intent.status = IntentStatus.COMPLETED

                case "error":
                    state.error = details.get("error")
                    state.intent.status = IntentStatus.FAILED

        except Exception as e:
            state.error = str(e)
            logger.error("intent.action_failed",
                       intent_id=str(state.intent.id),
                       action=action_type,
                       error=str(e))

        return state