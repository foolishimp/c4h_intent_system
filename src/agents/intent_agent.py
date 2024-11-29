"""
Intent agent implementation for orchestrating the refactoring workflow.
Handles coordination between discovery, solution design, implementation and validation stages.
Path: src/agents/intent_agent.py
"""

from typing import Dict, Any, Optional, List
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import shutil
import structlog

from models.intent import Intent, IntentStatus, AgentState
from agents.discovery import DiscoveryAgent 
from agents.solution_designer import SolutionDesigner
from agents.coder import Coder, MergeMethod  
from agents.assurance import AssuranceAgent
from config import SystemConfig
from agents.base import AgentResponse

logger = structlog.get_logger()

@dataclass 
class WorkflowState:
    """Current state of the intent workflow"""
    intent_description: Dict[str, Any]
    project_path: str
    iteration: int = 0
    max_iterations: int = 3
    discovery_data: Optional[Dict[str, Any]] = None
    solution_design_data: Optional[Dict[str, Any]] = None  
    implementation_data: Optional[Dict[str, Any]] = None
    validation_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    last_action: Optional[str] = None
    action_history: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Initialize intent model after dataclass initialization"""
        self.intent = Intent(
            description=self.intent_description,
            project_path=self.project_path
        )

    @property
    def has_error(self) -> bool:
        """Check if workflow has encountered an error"""
        return bool(self.error)

    def get_current_agent(self) -> Optional[str]:
        """Get currently active agent"""
        if self.error:
            logger.debug("workflow.error_state", error=self.error)
            return None
                
        # Priority order
        agents = ["discovery", "solution_design", "coder", "assurance"]
        
        # Find first incomplete agent
        for agent in agents:
            data_key = f"{agent}_data"
            data = getattr(self, data_key, None)
                
            logger.debug("checking_agent_status", 
                        agent=agent,
                        data=data,
                        has_data=bool(data) and data.get("status") == "completed")
                    
            # Report success on individual stage completion
            is_complete = bool(data) and data.get("status") == "completed"
            if not is_complete:
                return agent  # Return next agent to process
                
            # Log successful completion
            logger.info(f"workflow.{agent}_completed")
                    
        return None  # All stages complete

    async def update_agent_state(self, agent: str, result: AgentResponse) -> None:
        """Update agent state with status from agent"""
        try:
            # Create standard state data structure
            state_data = {
                "raw_output": result.data.get("raw_output", ""),  # Get raw_output from data dict
                "files": result.data.get("files", {}),  # Include files mapping
                "timestamp": datetime.utcnow().isoformat(),
                "status": "completed" if result.success else "failed",
                "error": result.error
            }
            
            # Store in appropriate field
            if agent == "discovery":
                self.discovery_data = state_data
            elif agent == "solution_design":
                self.solution_design_data = state_data
            elif agent == "coder":
                self.implementation_data = state_data
            elif agent == "assurance":
                self.validation_data = state_data
            else:
                logger.error("workflow.invalid_agent", agent=agent)
                return

            logger.info(f"workflow.{agent}_state_update",
                    status=state_data["status"],
                    has_error=bool(state_data.get("error")))

            self.action_history.append(agent)
            self.last_action = agent

        except Exception as e:
            logger.error(f"workflow.{agent}_update_failed", error=str(e))

class IntentAgent:
    """Orchestrates the intent workflow."""
    
    def __init__(self, config: SystemConfig, max_iterations: int = 3):
        """Initialize intent agent with system configuration."""
        self.max_iterations = max_iterations
        self.config = config
        
        try:
            config_dict = config.dict()
            
            discovery_config = config.get_agent_config("discovery")
            self.discovery = DiscoveryAgent(
                provider=discovery_config.provider_enum,
                model=discovery_config.model,
                temperature=discovery_config.temperature,
                config=config_dict,
                workspace_root=Path(config.project.workspace_root) if config.project.workspace_root else None
            )
            
            designer_config = config.get_agent_config("solution_designer")
            self.designer = SolutionDesigner(
                provider=designer_config.provider_enum,
                model=designer_config.model,
                temperature=designer_config.temperature,
                config=config_dict
            )
            
            coder_config = config.get_agent_config("coder")
            self.coder = Coder(
                provider=coder_config.provider_enum,
                model=coder_config.model,
                temperature=coder_config.temperature,
                config=config_dict
            )
            
            assurance_config = config.get_agent_config("assurance")
            self.assurance = AssuranceAgent(
                provider=assurance_config.provider_enum,
                model=assurance_config.model,
                temperature=assurance_config.temperature,
                config=config_dict,
                workspace_root=Path(config.project.workspace_root) if config.project.workspace_root else None
            )
            
            self.current_state: Optional[WorkflowState] = None
            self.backup_dir: Optional[Path] = None

            logger.info("intent_agent.initialized", 
                    max_iterations=max_iterations,
                    discovery_model=self.discovery.model,
                    designer_model=self.designer.model,
                    coder_model=self.coder.model,
                    assurance_model=self.assurance.model)
                    
        except Exception as e:
            logger.error("intent_agent.initialization_failed",
                        error=str(e),
                        config_keys=list(config_dict.keys()))
            raise ValueError(f"Failed to initialize intent agent: {str(e)}")
    
    def get_current_agent(self) -> Optional[str]:
        """Get current agent from workflow state"""
        if self.current_state:
            return self.current_state.get_current_agent()
        return None

    async def process(self, project_path: Path, intent_desc: Dict[str, Any]) -> Dict[str, Any]:
        """Process an intent through the complete workflow"""
        try:
            if not self.current_state:
                self.current_state = WorkflowState(
                    intent_description=intent_desc,
                    project_path=str(project_path),
                    max_iterations=self.max_iterations
                )

            if not self.backup_dir and project_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                self.backup_dir = Path(f"workspaces/backups/backup_{timestamp}")
                self.backup_dir.parent.mkdir(parents=True, exist_ok=True)

                if project_path.exists():
                    if project_path.is_file():
                        shutil.copy2(project_path, self.backup_dir / project_path.name)
                    else:
                        shutil.copytree(project_path, self.backup_dir / project_path.name)
                    logger.info("intent.backup_created", backup_path=str(self.backup_dir))

            logger.info("intent.process_started", 
                    intent_id=str(self.current_state.intent.id),
                    project_path=str(project_path))

            current_agent = self.current_state.get_current_agent()
            if not current_agent:
                return self._create_result_response()

            result = await self._execute_agent(current_agent)
            
            if not result.get("success", False):
                if self.backup_dir:
                    backup_path = self.backup_dir / project_path.name
                    if backup_path.exists():
                        if project_path.is_dir():
                            shutil.rmtree(project_path)
                        else:
                            project_path.unlink(missing_ok=True)
                        if backup_path.is_dir():
                            shutil.copytree(backup_path, project_path)
                        else:
                            shutil.copy2(backup_path, project_path)
                        logger.info("intent.restored_backup")
                return self._create_error_response(result.get("error", "Unknown error"))

            return self._create_result_response()

        except Exception as e:
            logger.error("intent.process_failed", error=str(e))
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

        logger.debug("discovery.result_received", 
                    success=result.success,
                    has_data=bool(result.data),
                    raw_output_size=len(result.data.get("raw_output", "")) if result.data else 0)

        await self.current_state.update_agent_state("discovery", result)

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
            result = await self.designer.process({
                "intent": self.current_state.intent.description,
                "discovery_data": self.current_state.discovery_data,
                "iteration": self.current_state.iteration
            })

            await self.current_state.update_agent_state("solution_design", result)

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

        await self.current_state.update_agent_state("coder", result)

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

        result = await self.assurance.process({
            "changes": self.current_state.implementation_data.get("changes", []),
            "intent": self.current_state.intent.description
        })

        await self.current_state.update_agent_state("assurance", result)

        return {
            "success": result.success,
            "error": result.error
        }

    async def _execute_agent(self, agent_type: str) -> Dict[str, Any]:
        """Execute specific agent"""
        try:
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
            logger.error("agent.execution_failed", error=str(e), agent=agent_type)
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
            return {
                "status": "error",
                "error": "No workflow state"
            }

        workflow_data = self._get_workflow_data()
        
        # The issue is here - we're marking as failed unless everything is complete
        stages_complete = all(
            data.get("status") == "completed"
            for name, data in workflow_data.items()
            if isinstance(data, dict) and name != "current_stage"
        )

        # We should instead check if the current stage completed successfully
        current_stage = self.current_state.get_current_agent()
        current_stage_data = workflow_data.get(
            f"{current_stage}_data" if current_stage else None, 
            {}
        )
        stage_success = current_stage_data.get("status") == "completed"

        return {
            "status": "success" if stage_success else "failed",  # Use current stage status
            "workflow_data": workflow_data,
            "error": self.current_state.error
        }

    def _get_workflow_data(self) -> Dict[str, Any]:
        """Get current workflow data for display"""
        if not self.current_state:
            return {}
            
        return {
            "current_stage": self.current_state.get_current_agent(),
            "discovery_data": self.current_state.discovery_data,
            "solution_data": self.current_state.solution_design_data,
            "implementation_data": self.current_state.implementation_data,
            "validation_data": self.current_state.validation_data,
            "error": self.current_state.error
        }