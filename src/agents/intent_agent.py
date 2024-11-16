# src/agents/intent_agent.py

import os
import shutil
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
from src.agents.coder import Coder
from src.agents.assurance import AssuranceAgent
from src.skills.semantic_iterator import SemanticIterator

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

    def get_current_agent(self) -> Optional[str]:
        """Get currently active agent"""
        if self.error:
            return None
            
        # Priority order
        agents = ["discovery", "solution_design", "coder", "assurance"]
        
        # Find first incomplete agent
        for agent in agents:
            if not getattr(self, f"{agent}_data", None):
                return agent
                
        return None

class IntentAgent:
    """Orchestrates the intent workflow using semantic iteration."""
    
    def __init__(self, max_iterations: int = 3):
        """Initialize intent agent"""
        self.max_iterations = max_iterations
        
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
            
        self.config = {
            "model": "claude-3-sonnet-20240229",
            "api_key": api_key,
            "max_tokens": 4000,
            "temperature": 0
        }
        
        self.semantic_iterator = SemanticIterator([self.config])
        self.discovery = DiscoveryAgent()
        self.designer = SolutionDesigner()
        self.coder = Coder()
        self.assurance = AssuranceAgent()
        
        self.current_state: Optional[WorkflowState] = None
        self.backup_dir: Optional[Path] = None

        logger.info("intent_agent.initialized", 
                   max_iterations=max_iterations,
                   model=self.config["model"])

    async def process(self, project_path: Path, intent_desc: Dict[str, Any]) -> Dict[str, Any]:
        """Process an intent through the complete workflow"""
        try:
            if not self.current_state:
                self.current_state = WorkflowState(
                    intent=Intent(
                        description=intent_desc,
                        project_path=str(project_path)
                    ),
                    max_iterations=self.max_iterations
                )

            # Create backup directory if needed
            if not self.backup_dir and project_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                self.backup_dir = Path(f"workspaces/backups/backup_{timestamp}")
                self.backup_dir.parent.mkdir(parents=True, exist_ok=True)

                if project_path.exists():
                    if project_path.is_file():
                        shutil.copy2(project_path, self.backup_dir / project_path.name)
                    else:
                        shutil.copytree(project_path, self.backup_dir / project_path.name)

            logger.info("intent.process_started", 
                       intent_id=str(self.current_state.intent.id),
                       project_path=str(project_path))

            current_agent = self.current_state.get_current_agent()
            if not current_agent:
                return self._create_result_response()

            # Execute agent
            result = await self._execute_agent(current_agent)
            
            if not result.get("success", False) and self.backup_dir:
                # Restore from backup on failure
                backup_path = self.backup_dir / project_path.name
                if backup_path.exists():
                    shutil.rmtree(project_path) if project_path.is_dir() else project_path.unlink(missing_ok=True)
                    shutil.copytree(backup_path, project_path) if backup_path.is_dir() else shutil.copy2(backup_path, project_path)
                    logger.info("intent.restored_backup")
                return self._create_error_response(result.get("error", "Unknown error"))

            return self._create_result_response()

        except Exception as e:
            logger.error("intent.process_failed", error=str(e))
            self.current_state.error = str(e)
            return self._create_error_response(str(e))

    async def _execute_discovery(self) -> Dict[str, Any]:
        """Execute discovery stage"""
        try:
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
                "timestamp": datetime.utcnow().isoformat(),
                "status": "completed" if result.success else "failed",
                "error": result.error
            }

            return {
                "success": result.success,
                "error": result.error
            }

        except Exception as e:
            logger.error("discovery.execution_failed", error=str(e))
            return {
                "success": False,
                "error": str(e)
            }

    async def _execute_solution_design(self) -> Dict[str, Any]:
        """Execute solution design stage"""
        try:
            if not self.current_state or not self.current_state.discovery_data:
                return {
                    "success": False,
                    "error": "Discovery data required for solution design"
                }

            result = await self.designer.process({
                "intent": self.current_state.intent.description,
                "discovery_data": self.current_state.discovery_data,
                "iteration": self.current_state.iteration
            })

            self.current_state.solution_data = {
                "changes": result.data.get("response", {}).get("changes", []),
                "timestamp": datetime.utcnow().isoformat(),
                "status": "completed" if result.success else "failed",
                "error": result.error
            }

            return {
                "success": result.success,
                "error": result.error
            }

        except Exception as e:
            logger.error("solution_design.execution_failed", error=str(e))
            return {
                "success": False,
                "error": str(e)
            }

    async def _execute_code_changes(self) -> Dict[str, Any]:
        """Execute code changes stage"""
        try:
            if not self.current_state or not self.current_state.solution_data:
                return {
                    "success": False,
                    "error": "Solution design required for code changes"
                }

            result = await self.coder.process({
                "changes": self.current_state.solution_data.get("changes", [])
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

        except Exception as e:
            logger.error("code_changes.execution_failed", error=str(e))
            return {
                "success": False,
                "error": str(e)
            }

    async def _execute_assurance(self) -> Dict[str, Any]:
        """Execute assurance stage"""
        try:
            if not self.current_state or not self.current_state.implementation_data:
                return {
                    "success": False,
                    "error": "Implementation required for assurance"
                }

            result = await self.assurance.process({
                "changes": self.current_state.implementation_data.get("changes", []),
                "intent": self.current_state.intent.description
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

        except Exception as e:
            logger.error("assurance.execution_failed", error=str(e))
            return {
                "success": False,
                "error": str(e)
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
                if not result["success"]:
                    self.current_state.error = result["error"]
                else:
                    self.current_state.iteration += 1
                    
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
        success = not self.current_state.has_error and self.current_state.intent.status == IntentStatus.COMPLETED
        return {
            "status": "success" if success else "failed",
            "intent_id": str(self.current_state.intent.id),
            "iterations": self.current_state.iteration,
            "workflow_data": self._get_workflow_data(),
            "changes": self.current_state.implementation_data.get("changes", []) if success else [],
            "validation": self.current_state.validation_data if success else None,
            "error": self.current_state.error,
            "action_history": self.current_state.action_history
        }

    def _get_workflow_data(self) -> Dict[str, Any]:
        """Get current workflow data for display"""
        if not self.current_state:
            return {}
            
        return {
            "current_stage": self.current_state.get_current_agent(),
            "discovery_data": self.current_state.discovery_data,
            "solution_data": self.current_state.solution_data,
            "implementation_data": self.current_state.implementation_data,
            "validation_data": self.current_state.validation_data,
            "error": self.current_state.error
        }