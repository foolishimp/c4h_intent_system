"""
Workflow state tracking and management for refactoring operations.
Path: src/models/workflow_state.py
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import structlog
from enum import Enum

from .intent import Intent, IntentStatus, AgentState
from agents.base import AgentResponse

logger = structlog.get_logger()

class WorkflowStage(str, Enum):
    """Stages in the workflow process"""
    DISCOVERY = "discovery"
    SOLUTION_DESIGN = "solution_design"
    IMPLEMENTATION = "coder"
    VALIDATION = "assurance"
    
    @classmethod
    def get_ordered_stages(cls) -> List['WorkflowStage']:
        """Get stages in processing order"""
        return [
            cls.DISCOVERY,
            cls.SOLUTION_DESIGN,
            cls.IMPLEMENTATION,
            cls.VALIDATION
        ]

@dataclass
class StageData:
    """Data for a workflow stage"""
    status: str = "pending"  # pending, in_progress, completed, failed
    raw_output: str = ""
    files: Dict[str, Any] = field(default_factory=dict)
    timestamp: Optional[str] = None
    error: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)

@dataclass 
class WorkflowState:
    """Current state of the intent workflow"""
    intent_description: Dict[str, Any]
    project_path: str
    iteration: int = 0
    max_iterations: int = 3
    discovery_data: Optional[StageData] = None
    solution_design_data: Optional[StageData] = None  
    implementation_data: Optional[StageData] = None
    validation_data: Optional[StageData] = None
    error: Optional[str] = None
    last_action: Optional[str] = None
    action_history: List[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    backup_path: Optional[Path] = None

    def __post_init__(self):
        """Initialize intent model and stage data"""
        self.intent = Intent(
            description=self.intent_description,
            project_path=self.project_path
        )
        
        # Initialize stage data if not provided
        if not self.discovery_data:
            self.discovery_data = StageData()
        if not self.solution_design_data:
            self.solution_design_data = StageData()
        if not self.implementation_data:
            self.implementation_data = StageData()
        if not self.validation_data:
            self.validation_data = StageData()

    @property
    def has_error(self) -> bool:
        """Check if workflow has encountered an error"""
        return bool(self.error)

    @property
    def is_complete(self) -> bool:
        """Check if workflow is complete"""
        return self.get_current_agent() is None and not self.has_error

    @property
    def duration(self) -> float:
        """Get workflow duration in seconds"""
        end = self.completed_at or datetime.utcnow()
        return (end - self.started_at).total_seconds()

    def get_current_agent(self) -> Optional[str]:
        """Get currently active agent"""
        if self.has_error:
            logger.debug("workflow.error_state", error=self.error)
            return None
                
        for stage in WorkflowStage.get_ordered_stages():
            data = self.get_stage_data(stage)
            is_complete = bool(data) and data.status == "completed"
            
            if not is_complete:
                return stage.value
                    
            logger.info(f"workflow.{stage.value}_completed")
                    
        return None

    def get_stage_data(self, stage: WorkflowStage) -> StageData:
        """Get data for a specific stage"""
        return getattr(self, f"{stage.value}_data")

    def set_stage_data(self, stage: WorkflowStage, data: StageData) -> None:
        """Set data for a specific stage"""
        setattr(self, f"{stage.value}_data", data)

    # In src/models/workflow_state.py

    async def update_agent_state(self, agent: str, result: AgentResponse) -> None:
        """Update agent state with status from agent"""
        try:
            # Create stage data preserving raw output
            stage_data = StageData(
                status="completed" if result.success else "failed",
                raw_output=result.data.get("raw_output", ""),  # Ensure we get raw_output
                files=result.data.get("files", {}),  # Keep files from discovery
                timestamp=datetime.utcnow().isoformat(),
                error=result.error,
                metrics=result.data.get("metrics", {})
            )
            
            # Map agent to stage and store data
            try:
                stage = WorkflowStage(agent)
                self.set_stage_data(stage, stage_data)
            except ValueError:
                logger.error("workflow.invalid_agent", agent=agent)
                return

            logger.info(f"workflow.{agent}_state_update",
                    status=stage_data.status,
                    has_error=bool(stage_data.error))

            self.action_history.append(agent)
            self.last_action = agent

            # Check if workflow is complete
            if self.get_current_agent() is None:
                self.completed_at = datetime.utcnow()

        except Exception as e:
            logger.error(f"workflow.{agent}_update_failed", error=str(e))

    def to_dict(self) -> Dict[str, Any]:
        """Convert workflow state to dictionary"""
        return {
            "intent_id": str(self.intent.id),
            "project_path": self.project_path,
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "current_stage": self.get_current_agent(),
            "error": self.error,
            "last_action": self.last_action,
            "action_history": self.action_history,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration": self.duration,
            "discovery_data": self.discovery_data.__dict__,
            "solution_data": self.solution_design_data.__dict__,
            "implementation_data": self.implementation_data.__dict__,
            "validation_data": self.validation_data.__dict__,
            "backup_path": str(self.backup_path) if self.backup_path else None
        }