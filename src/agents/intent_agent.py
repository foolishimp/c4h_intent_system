"""
Intent agent implementation for coordinating the refactoring workflow.
Path: src/agents/intent_agent.py
"""

from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime
import shutil
import structlog
import json

from agents.discovery import DiscoveryAgent 
from agents.solution_designer import SolutionDesigner
from agents.coder import Coder
from agents.assurance import AssuranceAgent
from config import locate_config
from models.workflow_state import WorkflowState, WorkflowStage

logger = structlog.get_logger()

class IntentAgent:
    """Orchestrates the intent workflow."""
    
    def __init__(self, config: Dict[str, Any], max_iterations: int = 3):
        """Initialize intent agent with configuration."""
        self.max_iterations = max_iterations
        self.config = config
        
        try:
            # Initialize all agents with complete system config
            self.discovery = DiscoveryAgent(config=config)
            self.solution_designer = SolutionDesigner(config=config)
            self.coder = Coder(config=config)
            self.assurance = AssuranceAgent(config=config)
            
            self.current_state: Optional[WorkflowState] = None
            
            logger.info("intent_agent.initialized", 
                    max_iterations=max_iterations,
                    discovery=bool(self.discovery),
                    designer=bool(self.solution_designer),
                    coder=bool(self.coder),
                    assurance=bool(self.assurance))
                    
        except Exception as e:
            logger.error("intent_agent.initialization_failed",
                        error=str(e),
                        config_keys=list(config.keys()) if config else None)
            raise ValueError(f"Failed to initialize intent agent: {str(e)}")

    def get_current_agent(self) -> Optional[str]:
        """Get current agent from workflow state"""
        if self.current_state:
            return self.current_state.get_current_agent()
        return None

    def process(self, project_path: Path, intent_desc: Dict[str, Any]) -> Dict[str, Any]:
        """Process an intent through the complete workflow"""
        try:
            logger.info("intent.process.started", 
                       project_path=str(project_path),
                       intent=intent_desc)
            
            # Initialize state if needed
            if not self.current_state:
                self.current_state = WorkflowState(
                    intent_description=intent_desc,
                    project_path=str(project_path),
                    max_iterations=self.max_iterations
                )

            current_agent = self.current_state.get_current_agent()
            if not current_agent:
                logger.info("intent.process.complete")
                return self._create_result_response()

            # Execute current agent
            logger.info("intent.process.executing_agent", agent=current_agent)
            result = self._execute_agent(current_agent)
            
            if not result.get("success", False):
                error_msg = result.get("error", "Unknown error")
                logger.error("intent.process.agent_failed", 
                           agent=current_agent,
                           error=error_msg)
                return self._create_error_response(error_msg)

            logger.info("intent.process.agent_succeeded", 
                       agent=current_agent,
                       iteration=self.current_state.iteration)
            return self._create_result_response()

        except Exception as e:
            logger.error("intent.process.failed", error=str(e))
            if self.current_state:
                self.current_state.error = str(e)
            return self._create_error_response(str(e))

    def _setup_backup(self, project_path: Path) -> None:
        """Setup backup directory for project"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_root = Path(self.config.get('backup', {}).get('path', 'workspaces/backups'))
            self.backup_dir = backup_root / f"backup_{timestamp}"
            self.backup_dir.parent.mkdir(parents=True, exist_ok=True)

            if project_path.exists():
                if project_path.is_file():
                    shutil.copy2(project_path, self.backup_dir / project_path.name)
                else:
                    shutil.copytree(project_path, self.backup_dir / project_path.name)
                logger.info("intent.backup_created", backup_path=str(self.backup_dir))
                if self.current_state:
                    self.current_state.backup_path = self.backup_dir
        except Exception as e:
            logger.error("intent.backup_failed", error=str(e))
            raise

    def _execute_agent(self, agent_type: str) -> Dict[str, Any]:
        """Execute specific agent"""
        try:
            result = None
            logger.info("intent.execute_agent.started", agent=agent_type)
            
            if agent_type == "discovery":
                result = self._execute_discovery()
            elif agent_type == "solution_design":
                result = self._execute_solution_design()
            elif agent_type == "coder":
                result = self._execute_code_changes()
            elif agent_type == "assurance":
                result = self._execute_assurance()
            
            if result:
                logger.info("intent.execute_agent.completed",
                        agent=agent_type,
                        success=result.get("success", False),
                        next_agent=self.current_state.get_current_agent())
                
                if result["success"]:
                    self.current_state.iteration += 1
                else:
                    self.current_state.error = result["error"]
                    
            return result or {"success": False, "error": "Invalid agent type"}

        except Exception as e:
            logger.error("intent.execute_agent.failed", error=str(e), agent=agent_type)
            return {"success": False, "error": str(e)}

    def _execute_discovery(self) -> Dict[str, Any]:
        """Execute discovery stage"""
        if not self.current_state or not self.current_state.intent.project_path:
            return {
                "success": False,
                "error": "No project path specified"
            }

        result = self.discovery.process({
            "project_path": self.current_state.intent.project_path
        })

        self.current_state.update_agent_state("discovery", result)

        return {
            "success": result.success,
            "error": result.error
        }
    

    def _execute_solution_design(self) -> Dict[str, Any]:
        """Execute solution design stage with proper sync/async handling"""
        if not self.current_state or not self.current_state.discovery_data:
            return {
                "success": False,
                "error": "Discovery data required for solution design"
            }

        try:
            formatted_input = {
                "input_data": {
                    "discovery_data": self.current_state.discovery_data.__dict__,
                    "intent": self.current_state.intent.description
                },
                "iteration": self.current_state.iteration
            }

            logger.debug("solution_design.input_prepared", 
                    discovery_data=formatted_input["input_data"]["discovery_data"],
                    intent=formatted_input["input_data"]["intent"])

            # Use synchronous process interface
            result = self.solution_designer.process(formatted_input)
            
            # Update state with result
            self.current_state.update_agent_state("solution_design", result)

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

    def _execute_code_changes(self) -> Dict[str, Any]:
        """Execute code changes stage"""
        if not self.current_state or not self.current_state.solution_design_data:
            return {
                "success": False,
                "error": "Solution design required for code changes"
            }

        try:
            solution_data = self.current_state.solution_design_data
            raw_output = solution_data.raw_output

            # Extract actual content from ModelResponse if needed
            input_data = raw_output.choices[0].message.content if hasattr(raw_output, 'choices') else raw_output

            logger.info("code_changes.starting", 
                    input_type=type(input_data).__name__)

            # Pass the content directly to coder
            result = self.coder.process({
                'input_data': input_data
            })
            
            self.current_state.update_agent_state("coder", result)
            
            return {
                "success": result.success,
                "error": result.error
            }

        except Exception as e:
            logger.error("code_changes.exception", error=str(e))
            return {
                "success": False,
                "error": str(e)
            }
        
    def _execute_assurance(self) -> Dict[str, Any]:
        """Execute assurance stage"""
        if not self.current_state or not self.current_state.implementation_data:
            return {
                "success": False,
                "error": "Implementation required for assurance"
            }

        try:
            result = self.assurance.process({
                "changes": self.current_state.implementation_data.get("changes", []),
                "intent": self.current_state.intent.description
            })

            self.current_state.update_agent_state("assurance", result)

            return {
                "success": result.success,
                "error": result.error
            }

        except Exception as e:
            logger.error("assurance.failed", error=str(e))
            return {
                "success": False,
                "error": str(e)
            }


    def _handle_error(self, error: str) -> None:
        """Handle workflow error with backup restoration"""
        try:
            if self.backup_dir and self.current_state:
                project_path = Path(self.current_state.project_path)
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
        except Exception as e:
            logger.error("error.restore_failed", error=str(e))

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
        current_stage = self.current_state.get_current_agent()
        current_stage_data = workflow_data.get(
            f"{current_stage}_data" if current_stage else None, 
            {}
        )
        stage_success = current_stage_data.get("status") == "completed"

        return {
            "status": "success" if stage_success else "failed",
            "workflow_data": workflow_data,
            "error": self.current_state.error
        }

    def _get_workflow_data(self) -> Dict[str, Any]:
        """Get current workflow data for display"""
        if not self.current_state:
            return {}
        return self.current_state.to_dict()
