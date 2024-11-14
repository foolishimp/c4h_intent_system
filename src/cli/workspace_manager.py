# src/cli/workspace_manager.py

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional
from pathlib import Path
import json
import structlog
from datetime import datetime

logger = structlog.get_logger()

class AgentType(str, Enum):
    """Available agent types"""
    INTENT = "intent"
    DISCOVERY = "discovery" 
    SOLUTION = "solution_design"
    CODER = "coder"
    ASSURANCE = "assurance"
    
    @property
    def next_agent(self) -> Optional['AgentType']:
        """Get next agent in workflow"""
        agents = list(AgentType)
        try:
            idx = agents.index(self)
            return agents[idx + 1] if idx < len(agents) - 1 else None
        except ValueError:
            return None
            
    @property
    def prev_agent(self) -> Optional['AgentType']:
        """Get previous agent in workflow"""
        agents = list(AgentType)
        try:
            idx = agents.index(self)
            return agents[idx - 1] if idx > 0 else None
        except ValueError:
            return None

@dataclass
class AgentState:
    """State for a single agent"""
    prompt: str = ""
    response: Optional[Dict[str, Any]] = None
    llm_provider: str = "anthropic"
    model: str = "claude-3-sonnet-20240229"
    last_run: Optional[datetime] = None
    error: Optional[str] = None
    active: bool = False
    iterations: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary"""
        return {
            "prompt": self.prompt,
            "response": self.response,
            "llm_provider": self.llm_provider,
            "model": self.model,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "error": self.error,
            "active": self.active,
            "iterations": self.iterations
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgentState':
        """Create state from dictionary"""
        if data.get("last_run"):
            data["last_run"] = datetime.fromisoformat(data["last_run"])
        return cls(**data)

@dataclass
class WorkspaceState:
    """Complete workspace state"""
    workspace_path: Path
    intent_id: str
    project_path: Optional[Path] = None
    intent_description: Optional[str] = None
    current_agent: AgentType = AgentType.INTENT
    agents: Dict[AgentType, AgentState] = field(default_factory=lambda: {
        agent: AgentState() for agent in AgentType
    })
    
    def save(self) -> None:
        """Save workspace state to file"""
        state_file = self.workspace_path / "workspace_state.json"
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        
        state_dict = {
            "workspace_path": str(self.workspace_path),
            "intent_id": self.intent_id,
            "project_path": str(self.project_path) if self.project_path else None,
            "intent_description": self.intent_description,
            "current_agent": self.current_agent.value,
            "agents": {
                agent.value: state.to_dict()
                for agent, state in self.agents.items()
            }
        }
        
        with open(state_file, 'w') as f:
            json.dump(state_dict, f, indent=2)
            
        logger.info("workspace.state_saved", 
                   path=str(state_file),
                   intent_id=self.intent_id)
    
    @classmethod
    def load(cls, workspace_path: Path) -> 'WorkspaceState':
        """Load workspace state from file"""
        state_file = workspace_path / "workspace_state.json"
        
        if not state_file.exists():
            raise ValueError(f"No workspace state found at {state_file}")
            
        with open(state_file) as f:
            state_dict = json.load(f)
            
        # Convert agents data
        agents = {}
        for agent_str, agent_dict in state_dict["agents"].items():
            agent_type = AgentType(agent_str)
            agents[agent_type] = AgentState.from_dict(agent_dict)
            
        return cls(
            workspace_path=Path(state_dict["workspace_path"]),
            intent_id=state_dict["intent_id"],
            project_path=Path(state_dict["project_path"]) if state_dict.get("project_path") else None,
            intent_description=state_dict.get("intent_description"),
            current_agent=AgentType(state_dict["current_agent"]),
            agents=agents
        )

class WorkspaceManager:
    """Manages workspace state and persistence"""
    
    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        
# src/cli/workspace_manager.py (continued)

    def create_workspace(self, intent_id: str) -> WorkspaceState:
        """Create new workspace with initial state
        
        Args:
            intent_id: Unique identifier for this refactoring intent
            
        Returns:
            New WorkspaceState instance
        """
        state = WorkspaceState(
            workspace_path=self.workspace_path,
            intent_id=intent_id
        )
        
        # Initialize with default prompts
        state.agents[AgentType.INTENT].prompt = """Analyze the refactoring intent and provide:
1. Clear scope of changes
2. Success criteria
3. Any potential risks or concerns"""

        state.agents[AgentType.DISCOVERY].prompt = """Analyze the project structure and identify:
1. Relevant files to modify
2. Dependencies between files
3. Current implementation patterns"""

        state.agents[AgentType.SOLUTION].prompt = """Design specific code changes:
1. List exact files to modify
2. Provide detailed transformation instructions
3. Consider error cases and edge conditions"""

        state.agents[AgentType.CODER].prompt = """Implement code changes:
1. Follow exact transformation instructions
2. Maintain existing functionality
3. Preserve code style and formatting"""

        state.agents[AgentType.ASSURANCE].prompt = """Validate changes:
1. Verify all changes meet intent
2. Run tests if available
3. Check for regressions"""

        state.save()
        logger.info("workspace.created", 
                   path=str(self.workspace_path),
                   intent_id=intent_id)
        return state
        
    def load_workspace(self, intent_id: str) -> WorkspaceState:
        """Load existing workspace or create new one
        
        Args:
            intent_id: Intent identifier to load or create
            
        Returns:
            WorkspaceState instance
        """
        try:
            state = WorkspaceState.load(self.workspace_path)
            logger.info("workspace.loaded", 
                       path=str(self.workspace_path),
                       intent_id=state.intent_id)
            return state
            
        except Exception as e:
            logger.info("workspace.create_new",
                       reason=str(e))
            return self.create_workspace(intent_id)

    def get_agent_status(self, state: WorkspaceState, agent: AgentType) -> Dict[str, Any]:
        """Get detailed status for an agent"""
        agent_state = state.agents[agent]
        return {
            "active": agent_state.active,
            "last_run": agent_state.last_run.isoformat() if agent_state.last_run else None,
            "iterations": agent_state.iterations,
            "has_error": bool(agent_state.error),
            "can_run": self._can_run_agent(state, agent)
        }

    def _can_run_agent(self, state: WorkspaceState, agent: AgentType) -> bool:
        """Check if an agent can be run based on dependencies"""
        # Intent can always run
        if agent == AgentType.INTENT:
            return True
            
        # Discovery needs project path
        if agent == AgentType.DISCOVERY:
            return bool(state.project_path)
            
        # Other agents need previous agent to have run
        prev_agent = agent.prev_agent
        if not prev_agent:
            return False
            
        prev_state = state.agents[prev_agent]
        return bool(prev_state.last_run and not prev_state.error)

    def get_workflow_status(self, state: WorkspaceState) -> Dict[str, Any]:
        """Get overall workflow status"""
        return {
            "intent_id": state.intent_id,
            "project_path": str(state.project_path) if state.project_path else None,
            "current_agent": state.current_agent.value,
            "agents": {
                agent.value: self.get_agent_status(state, agent)
                for agent in AgentType
            }
        }

    def reset_agent(self, state: WorkspaceState, agent: AgentType) -> None:
        """Reset an agent's state"""
        agent_state = state.agents[agent]
        agent_state.active = False
        agent_state.error = None
        agent_state.response = None
        agent_state.iterations = 0
        state.save()
        logger.info("agent.reset", agent=agent.value)

    def set_project_path(self, state: WorkspaceState, path: Path) -> None:
        """Set the project path for the workspace"""
        if not path.exists():
            raise ValueError(f"Project path does not exist: {path}")
            
        state.project_path = path
        state.save()
        logger.info("workspace.project_set", 
                   path=str(path),
                   intent_id=state.intent_id)

    def set_intent_description(self, state: WorkspaceState, description: str) -> None:
        """Set the intent description for the workspace"""
        state.intent_description = description
        state.save()
        logger.info("workspace.intent_set",
                   intent_id=state.intent_id)