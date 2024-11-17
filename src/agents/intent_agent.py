"""
Intent agent implementation for orchestrating the refactoring workflow.
Handles coordination between discovery, solution design, implementation and validation stages.
Path: src/agents/intent_agent.py

Fixed:
- Proper state management
- Safe dictionary handling
- Robust error handling
- Consistent data flow
"""

from typing import Dict, Any, Optional, List
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import json
import structlog
from pydantic import BaseModel

from src.models.intent import Intent, IntentStatus, AgentState
from src.agents.discovery import DiscoveryAgent
from src.agents.solution_designer import SolutionDesigner
from src.agents.coder import Coder, MergeMethod
from src.agents.assurance import AssuranceAgent
from src.config import SystemConfig

logger = structlog.get_logger()

@dataclass
class WorkflowState:
    """Current state of the intent workflow"""
    intent: Intent
    iteration: int = 0
    max_iterations: int = 3
    discovery_data: Dict[str, Any] = field(default_factory=dict)
    solution_design_data: Dict[str, Any] = field(default_factory=dict)
    implementation_data: Dict[str, Any] = field(default_factory=dict)
    validation_data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    last_action: Optional[str] = None
    action_history: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Ensure intent description is properly serializable"""
        if isinstance(self.intent.description, dict):
            self.intent.description = json.dumps(self.intent.description)

    @property
    def has_error(self) -> bool:
        """Check if workflow has encountered an error"""
        return bool(self.error)

    def get_agent_status(self, agent: str) -> Dict[str, Any]:
        """Safely get agent status with defaults"""
        data_map = {
            "discovery": self.discovery_data,
            "solution_design": self.solution_design_data,
            "coder": self.implementation_data,
            "assurance": self.validation_data
        }
        
        agent_data = data_map.get(agent, {}) or {}
        return {
            "status": agent_data.get("status", "pending"),
            "timestamp": agent_data.get("timestamp"),
            "error": agent_data.get("error")
        }

    def get_current_agent(self) -> Optional[str]:
        """Get currently active agent with safe access"""
        if self.error:
            logger.debug("workflow.error_state", error=self.error)
            return None
            
        # Check agents in sequence
        agents = ["discovery", "solution_design", "coder", "assurance"]
        
        for agent in agents:
            status = self.get_agent_status(agent)
            logger.debug("agent_status_check", 
                        agent=agent,
                        status=status["status"])
                
            if status["status"] != "completed":
                return agent
                
        return None

    def get_intent_description(self) -> Dict[str, Any]:
        """Safely get intent description as dictionary"""
        if isinstance(self.intent.description, str):
            try:
                return json.loads(self.intent.description)
            except json.JSONDecodeError:
                return {"description": self.intent.description}
        return self.intent.description if isinstance(self.intent.description, dict) else {}

    def update_agent_state(self, agent: str, result: Dict[str, Any]) -> None:
        """Update agent state with result"""
        data_map = {
            "discovery": "discovery_data",
            "solution_design": "solution_design_data",
            "coder": "implementation_data",
            "assurance": "validation_data"
        }
        
        attr_name = data_map.get(agent)
        if not attr_name:
            logger.error("workflow.invalid_agent", agent=agent)
            return
            
        state_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "status": "completed" if result.get("success", False) else "failed",
            "error": result.get("error"),
            **(result or {})
        }
        
        setattr(self, attr_name, state_data)
        self.action_history.append(agent)
        self.last_action = agent
        
        if not result.get("success", False):
            self.error = result.get("error")
            logger.error("workflow.agent_failed",
                        agent=agent,
                        error=result.get("error"))
        else:
            logger.info("workflow.agent_completed", 
                       agent=agent,
                       status="completed")

class IntentAgent:
    """Orchestrates the intent workflow."""
    
    def __init__(self, config: SystemConfig, max_iterations: int = 3):
        """Initialize intent agent with system configuration."""
        self.max_iterations = max_iterations
        self.config = config
        
        try:
            # Initialize all required agents
            config_dict = config.dict()
            
            self.discovery = DiscoveryAgent(
                provider=config.get_agent_config("discovery").provider_enum,
                model=config.get_agent_config("discovery").model,
                config=config_dict
            )
            
            self.designer = SolutionDesigner(
                provider=config.get_agent_config("solution_designer").provider_enum,
                model=config.get_agent_config("solution_designer").model,
                config=config_dict
            )
            
            self.coder = Coder(
                provider=config.get_agent_config("coder").provider_enum,
                model=config.get_agent_config("coder").model,
                max_file_size=config.project.max_file_size,
                config=config_dict
            )
            
            self.assurance = AssuranceAgent(
                provider=config.get_agent_config("assurance").provider_enum,
                model=config.get_agent_config("assurance").model,
                config=config_dict
            )
            
            self.current_state: Optional[WorkflowState] = None
            
            logger.info("intent_agent.initialized",
                       max_iterations=max_iterations,
                       discovery=self.discovery.model,
                       designer=self.designer.model,
                       coder=self.coder.model,
                       assurance=self.assurance.model)
                       
        except Exception as e:
            logger.error("intent_agent.initialization_failed",
                        error=str(e))
            raise

    async def process(self, project_path: Path, intent_desc: str) -> Dict[str, Any]:
        """Process an intent through the complete workflow"""
        try:
            # Initialize workflow state - keep description as simple string
            if not self.current_state:
                logger.info("workflow.initializing_state", 
                           project_path=str(project_path))
                intent = Intent(
                    description=intent_desc,  # Just use the string
                    project_path=str(project_path)
                )
                self.current_state = WorkflowState(
                    intent=intent,
                    max_iterations=self.max_iterations
                )

            # Get the current agent to process
            current_agent = self.current_state.get_current_agent()
            
            logger.info("workflow.current_agent", 
                       agent=current_agent,
                       state=self._get_workflow_data())

            if not current_agent:
                return self._create_result_response()

            # Execute current agent
            result = await self._execute_agent(current_agent)
            if not result or not result.get("success", False):
                error_msg = result.get("error") if result else "Unknown error"
                logger.error("agent.execution_failed",
                           agent=current_agent,
                           error=error_msg)
                return self._create_error_response(error_msg)

            return self._create_result_response()

        except Exception as e:
            logger.error("intent.process_failed", error=str(e))
            if self.current_state:
                self.current_state.error = str(e)
            return self._create_error_response(str(e))
            
    async def _execute_discovery(self) -> Dict[str, Any]:
        """Execute discovery stage"""
        if not self.current_state or not self.current_state.intent.project_path:
            return {
                "success": False,
                "error": "No project path specified"
            }

        result = await self.discovery.process({
            "project_path": self.current_state.intent.project_path
        })

        self.current_state.discovery_data = {
            "files": result.data.get("files", {}),
            "project_path": result.data.get("project_path"),
            "discovery_output": result.data.get("discovery_output"),
            "raw_output": result.data.get("raw_output"),
            "timestamp": datetime.utcnow().isoformat(),
            "status": "completed" if result.success else "failed",
            "error": result.error
        }

        return {
            "success": result.success,
            "error": result.error
        }

    async def _execute_solution_design(self) -> Dict[str, Any]:
        """Execute solution design stage"""
        if not self.current_state or not self.current_state.discovery_data:
            return {
                "success": False,
                "error": "Discovery data required for solution design"
            }

        try:
            intent_desc = self.current_state.get_intent_description()
            
            # Format request with full context
            result = await self.designer.process({
                "intent": intent_desc,
                "discovery_data": self.current_state.discovery_data,
                "iteration": self.current_state.iteration
            })

            # Store result data
            self.current_state.solution_design_data = {
                "status": "completed" if result.success else "failed",
                "timestamp": datetime.utcnow().isoformat(),
                "changes": result.data.get("response", {}).get("changes", []),
                "response": result.data.get("response", {}),
                "error": result.error
            }

            return {
                "success": result.success,
                "error": result.error
            }

        except Exception as e:
            logger.error("solution_design.failed", error=str(e))
            return {
                "success": False,
                "error": str(e)
            }

    async def _execute_code_changes(self) -> Dict[str, Any]:
        """Execute code changes stage"""
        if not self.current_state or not self.current_state.solution_design_data:
            return {
                "success": False,
                "error": "Solution design required for code changes"
            }

        result = await self.coder.process({
            "changes": self.current_state.solution_design_data.get("changes", [])
        })

        self.current_state.implementation_data = {
            "changes": result.data.get("changes", []),
            "timestamp": datetime.utcnow().isoformat(),
            "status": "completed" if result.success else "failed",
            "error": result.error
        }

        return {
            "success": result.success,
            "error": result.error
        }

    async def _execute_assurance(self) -> Dict[str, Any]:
        """Execute assurance stage"""
        if not self.current_state or not self.current_state.implementation_data:
            return {
                "success": False,
                "error": "Implementation required for assurance"
            }

        intent_desc = self.current_state.get_intent_description()
        
        result = await self.assurance.process({
            "changes": self.current_state.implementation_data.get("changes", []),
            "intent": intent_desc
        })

        self.current_state.validation_data = {
            "results": result.data,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "completed" if result.success else "failed",
            "error": result.error
        }

        return {
            "success": result.success,
            "error": result.error
        }

    async def _execute_agent(self, agent_type: str) -> Dict[str, Any]:
        """Execute specific agent"""
        try:
            logger.info("workflow.executing_agent",
                       agent=agent_type,
                       current_state=self.current_state.get_current_agent())

            # Execute appropriate agent
            result = None
            if agent_type == "discovery":
                result = await self._execute_discovery()
            elif agent_type == "solution_design":
                result = await self._execute_solution_design()
            elif agent_type == "coder":
                result = await self._execute_code_changes()
            elif agent_type == "assurance":
                result = await self._execute_assurance()

            if result:
                logger.info("workflow.agent_transition",
                           agent=agent_type,
                           success=result.get("success", False),
                           next_agent=self.current_state.get_current_agent())

                if result["success"]:
                    self.current_state.iteration += 1
                else:
                    self.current_state.error = result["error"]

            return result or {"success": False, "error": "Invalid agent type"}

        except Exception as e:
            logger.error("agent.execution_failed",
                        agent=agent_type,
                        error=str(e))
            return {"success": False, "error": str(e)}

    def _create_error_response(self, error: str) -> Dict[str, Any]:
        """Create error response"""
        return {
            "status": "error",
            "error": error,
            "workflow_data": self._get_workflow_data()
        }

    def _create_result_response(self) -> Dict[str, Any]:
        """Create standardized result response"""
        if not self.current_state:
            return self._create_error_response("No workflow state")
            
        workflow_data = self._get_workflow_data()
        
        # Determine overall status
        has_failures = any(
            data.get("status") == "failed"
            for data in workflow_data.values()
            if isinstance(data, dict)
        )
        
        stages_complete = all(
            self.current_state.get_agent_status(stage).get("status") == "completed"
            for stage in ["discovery", "solution_design", "coder", "assurance"]
        )
        
        success = (
            not self.current_state.has_error
            and not has_failures
            and stages_complete
        )

        return {
            "status": "success" if success else "error",
            "intent_id": str(self.current_state.intent.id),
            "iterations": self.current_state.iteration,
            "workflow_data": workflow_data,
            "changes": self.current_state.implementation_data.get("changes", []) if success else [],
            "validation": self.current_state.validation_data if success else None,
            "error": self.current_state.error
        }

    def _get_workflow_data(self) -> Dict[str, Any]:
        """Get current workflow data with safe access"""
        if not self.current_state:
            return {
                "current_stage": None,
                "discovery_data": {},
                "solution_design_data": {},
                "implementation_data": {},
                "validation_data": {},
                "error": "No workflow state"
            }
            
        return {
            "current_stage": self.current_state.get_current_agent(),
            "discovery_data": self.current_state.discovery_data or {},
            "solution_design_data": self.current_state.solution_design_data or {},
            "implementation_data": self.current_state.implementation_data or {},
            "validation_data": self.current_state.validation_data or {},
            "error": self.current_state.error
        }

    def reset_workflow(self) -> None:
        """Reset workflow state"""
        if self.current_state:
            project_path = self.current_state.intent.project_path
            intent_desc = self.current_state.get_intent_description()
            
            # Create new intent with same project and description
            intent = Intent(
                description=json.dumps(intent_desc),
                project_path=project_path
            )
            
            self.current_state = WorkflowState(
                intent=intent,
                max_iterations=self.max_iterations
            )
            
            logger.info("workflow.reset",
                       project_path=project_path)
        else:
            logger.warning("workflow.reset_no_state")

    def get_progress(self) -> Dict[str, Any]:
        """Get workflow progress information"""
        if not self.current_state:
            return {
                "current_stage": None,
                "completed_stages": 0,
                "total_stages": 4,
                "has_error": False,
                "iterations": 0
            }
            
        completed = sum(
            1 for stage in ["discovery", "solution_design", "coder", "assurance"]
            if self.current_state.get_agent_status(stage).get("status") == "completed"
        )
        
        return {
            "current_stage": self.current_state.get_current_agent(),
            "completed_stages": completed,
            "total_stages": 4,
            "has_error": self.current_state.has_error,
            "iterations": self.current_state.iteration
        }

    def get_agent_results(self, agent: str) -> Optional[Dict[str, Any]]:
        """Get results for a specific agent"""
        if not self.current_state:
            return None
            
        data_map = {
            "discovery": self.current_state.discovery_data,
            "solution_design": self.current_state.solution_design_data,
            "coder": self.current_state.implementation_data,
            "assurance": self.current_state.validation_data
        }
        
        return data_map.get(agent)

    def can_proceed(self) -> bool:
        """Check if workflow can proceed to next stage"""
        if not self.current_state:
            return False
            
        if self.current_state.has_error:
            return False
            
        if self.current_state.iteration >= self.max_iterations:
            return False
            
        current = self.current_state.get_current_agent()
        if not current:
            return False  # No more stages
            
        # Check if current stage is completed
        status = self.current_state.get_agent_status(current)
        return status.get("status") == "pending"

    def validate_state(self) -> List[str]:
        """Validate current workflow state and return any issues"""
        issues = []
        
        if not self.current_state:
            issues.append("No workflow state initialized")
            return issues
            
        if not self.current_state.intent.project_path:
            issues.append("No project path specified")
            
        if not self.current_state.get_intent_description():
            issues.append("No intent description provided")
            
        # Validate stage sequence
        stages = ["discovery", "solution_design", "coder", "assurance"]
        completed_stages = []
        
        for stage in stages:
            status = self.current_state.get_agent_status(stage)
            if status.get("status") == "completed":
                completed_stages.append(stage)
                
        # Check for gaps in completion sequence
        for i, stage in enumerate(stages):
            if stage in completed_stages and i > 0:
                prev_stage = stages[i-1]
                if prev_stage not in completed_stages:
                    issues.append(f"Stage {stage} completed before {prev_stage}")
                    
        return issues

    def get_execution_summary(self) -> Dict[str, Any]:
        """Get summary of execution status and results"""
        if not self.current_state:
            return {
                "status": "not_started",
                "stages_completed": 0,
                "current_stage": None,
                "has_error": False,
                "execution_time": None
            }
            
        stages_completed = sum(
            1 for stage in ["discovery", "solution_design", "coder", "assurance"]
            if self.current_state.get_agent_status(stage).get("status") == "completed"
        )
        
        # Get execution times where available
        execution_times = {}
        for stage in ["discovery", "solution_design", "coder", "assurance"]:
            data = self.current_state.get_agent_status(stage)
            if data.get("timestamp"):
                try:
                    execution_times[stage] = data["timestamp"]
                except (ValueError, TypeError):
                    pass
                    
        return {
            "status": "error" if self.current_state.has_error else "in_progress",
            "stages_completed": stages_completed,
            "current_stage": self.current_state.get_current_agent(),
            "has_error": self.current_state.has_error,
            "error": self.current_state.error,
            "execution_times": execution_times,
            "iterations": self.current_state.iteration
        }
