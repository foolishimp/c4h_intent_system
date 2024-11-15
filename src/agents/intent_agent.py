# src/agents/intent_agent.py

import os
import asyncio
import sys
import json
import structlog
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime

from src.models.intent import Intent, IntentStatus, AgentState
from src.agents.discovery import DiscoveryAgent
from src.agents.solution_designer import SolutionDesigner
from src.agents.coder import Coder, MergeMethod
from src.agents.assurance import AssuranceAgent
from src.skills.semantic_iterator import SemanticIterator
from src.skills.shared.types import ExtractConfig

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
    last_action: Optional[str] = None
    action_history: List[str] = field(default_factory=list)

    @property
    def has_error(self) -> bool:
        return bool(self.error)

    @property
    def can_continue(self) -> bool:
        return self.iteration < self.max_iterations and not self.has_error

    def get_agent_state(self, agent_type: str) -> AgentState:
        """Get state for a specific agent"""
        if agent_type not in self.intent.agent_states:
            self.intent.agent_states[agent_type] = AgentState()
        return self.intent.agent_states[agent_type]

    def update_agent_state(self, agent_type: str, **updates: Any) -> None:
        """Update state for a specific agent"""
        state = self.get_agent_state(agent_type)
        for key, value in updates.items():
            setattr(state, key, value)
        self.intent.agent_states[agent_type] = state

    def get_current_agent(self) -> Optional[str]:
        """Get currently active agent"""
        if self.error:
            return None
        
        # Priority order
        agents = ["discovery", "solution_design", "coder", "assurance"]
        
        # Find first incomplete agent
        for agent in agents:
            state = self.get_agent_state(agent)
            if state.status not in ["completed", "failed"]:
                return agent
                
        return None

class IntentAgent:
    """Orchestrates the intent workflow using semantic iteration
    
    Flow:
    1. Discovery - Uses tartxt to gather code scope
    2. Solution Design - Get LLM solution for intent
    3. Semantic Iterator - Process solution into actions
       - Each action passed to Coder for implementation
    4. Assurance - Validate changes
    5. Loop - If assurance fails, create new intent from feedback
    """
    
    def __init__(self, max_iterations: int = 3):
        """Initialize intent agent"""
        self.max_iterations = max_iterations
        
        # Verify API key availability
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
            
        self.config = {
            "model": "claude-3-sonnet-20240229",
            "api_key": api_key,
            "max_tokens": 4000,
            "temperature": 0
        }
        
        # Initialize semantic iterator for workflow control
        self.semantic_iterator = SemanticIterator([self.config])
        
        # Initialize specialized agents
        self.discovery = DiscoveryAgent()
        self.designer = SolutionDesigner()
        self.coder = Coder()
        self.assurance = AssuranceAgent()
        
        # Track current state
        self.current_state: Optional[WorkflowState] = None
        
        logger.info("intent_agent.initialized",
                   max_iterations=max_iterations,
                   model=self.config["model"])

    async def process(self, project_path: Path, intent_desc: Dict[str, Any]) -> Dict[str, Any]:
        """Process an intent through complete workflow"""
        if not self.current_state:
            self.current_state = WorkflowState(
                intent=Intent(
                    description=intent_desc,
                    project_path=str(project_path)
                ),
                max_iterations=self.max_iterations
            )

        logger.info("intent.process_started",
                   intent_id=str(self.current_state.intent.id),
                   project_path=str(project_path))

        try:
            current_agent = self.current_state.get_current_agent()
            if not current_agent:
                return self._create_result_response()

            # Execute appropriate agent
            if current_agent == "discovery":
                await self._execute_discovery()
            elif current_agent == "solution_design":
                await self._execute_solution_design()
            elif current_agent == "coder":
                await self._execute_code_changes()
            elif current_agent == "assurance":
                await self._execute_assurance()

        except Exception as e:
            self.current_state.error = str(e)
            logger.error("intent.process_failed",
                      error=str(e),
                      agent=current_agent)

        return self._create_result_response()

    async def _execute_discovery(self) -> None:
        """Execute discovery step"""
        self.current_state.intent.status = IntentStatus.ANALYZING
        result = await self.discovery.process({
            "project_path": self.current_state.intent.project_path,
            "intent": self.current_state.intent.description
        })
        
        if result.success:
            self.current_state.discovery_data = result.data
            self.current_state.update_agent_state("discovery",
                status="completed",
                last_action="Discovery completed",
                last_run=datetime.now())
        else:
            self.current_state.error = result.error
            self.current_state.update_agent_state("discovery",
                status="failed",
                error=result.error)

    async def _execute_solution_design(self) -> None:
        """Execute solution design step"""
        if not self.current_state.discovery_data:
            self.current_state.error = "Missing discovery data"
            return
            
        result = await self.designer.process({
            "intent": self.current_state.intent.description,
            "discovery_data": self.current_state.discovery_data,
            "iteration": self.current_state.iteration
        })
        
        if result.success:
            self.current_state.solution_data = result.data.get("response", {})
            self.current_state.update_agent_state("solution_design",
                status="completed",
                last_action="Design completed",
                last_run=datetime.now())
        else:
            self.current_state.error = result.error
            self.current_state.update_agent_state("solution_design",
                status="failed",
                error=result.error)

    async def _execute_code_changes(self) -> None:
        """Execute code changes step"""
        if not self.current_state.solution_data:
            self.current_state.error = "Missing solution data"
            return

        self.current_state.intent.status = IntentStatus.TRANSFORMING
        
        # Extract code actions
        action_iterator = await self.semantic_iterator.iter_extract(
            content=self.current_state.solution_data,
            config=ExtractConfig(
                pattern="""Extract specific code modification actions.
                For each code change, provide:
                {
                    "file_path": "path/to/file",
                    "change_type": "create|modify|delete",
                    "instructions": "detailed change instructions"
                }""",
                format="json"
            )
        )

        changes = []
        while action_iterator.has_next():
            try:
                action = next(action_iterator)
                if isinstance(action, str):
                    action = json.loads(action)
                
                result = await self.coder.process(action)
                if result.success:
                    changes.append(result.data)
                else:
                    self.current_state.error = result.error
                    self.current_state.update_agent_state("coder",
                        status="failed",
                        error=result.error)
                    return
                    
            except Exception as e:
                self.current_state.error = f"Action processing failed: {str(e)}"
                return

        self.current_state.implementation_data = {"changes": changes}
        self.current_state.update_agent_state("coder",
            status="completed",
            last_action=f"Implemented {len(changes)} changes",
            last_run=datetime.now())

    async def _execute_assurance(self) -> None:
        """Execute assurance step"""
        if not self.current_state.implementation_data:
            self.current_state.error = "Missing implementation data"
            return
            
        self.current_state.intent.status = IntentStatus.VALIDATING
        result = await self.assurance.process({
            "changes": self.current_state.implementation_data,
            "project_path": self.current_state.intent.project_path,
            "intent": self.current_state.intent.description
        })
        
        if result.success:
            self.current_state.validation_data = result.data
            if result.data.get("success"):
                self.current_state.intent.status = IntentStatus.COMPLETED
                self.current_state.update_agent_state("assurance",
                    status="completed",
                    last_action="Validation successful",
                    last_run=datetime.now())
            else:
                # Create new intent from validation feedback
                self.current_state.iteration += 1
                self.current_state.intent.description = {
                    "description": f"Fix validation issues: {result.data.get('error')}",
                    "original_intent": self.current_state.intent.description,
                    "validation_output": result.data.get("output")
                }
                # Reset agent states for new iteration
                for agent in ["discovery", "solution_design", "coder", "assurance"]:
                    self.current_state.update_agent_state(agent,
                        status="not_started",
                        last_action=None)
        else:
            self.current_state.error = result.error
            self.current_state.update_agent_state("assurance",
                status="failed",
                error=result.error)

    def _create_result_response(self) -> Dict[str, Any]:
        """Create standardized result response"""
        success = not self.current_state.has_error and \
                 self.current_state.intent.status == IntentStatus.COMPLETED
        
        return {
            "status": "success" if success else "failed",
            "intent_id": str(self.current_state.intent.id),
            "iterations": self.current_state.iteration,
            "current_agent": self.current_state.get_current_agent(),
            "changes": self.current_state.implementation_data.get("changes", []) if success else [],
            "validation": self.current_state.validation_data if success else None,
            "error": self.current_state.error,
            "action_history": self.current_state.action_history
        }