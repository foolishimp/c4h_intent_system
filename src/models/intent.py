# src/models/intent.py

from uuid import UUID, uuid4
from enum import Enum
from typing import Dict, Any, Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

class IntentStatus(str, Enum):
    """Status of an intent through its lifecycle"""
    CREATED = "created"
    ANALYZING = "analyzing"
    TRANSFORMING = "transforming"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"

class AgentState(BaseModel):
    """State tracking for each agent"""
    status: str = "not_started"
    last_run: Optional[datetime] = None
    iterations: int = 0
    last_action: Optional[str] = None  # Added this field
    error: Optional[str] = None
    response: Optional[Dict[str, Any]] = None

    class Config:
        extra = "allow"  # Allow extra fields for flexibility

class Intent(BaseModel):
    """Intent model for code transformations"""
    id: UUID = Field(default_factory=uuid4)
    description: Dict[str, Any]  # Structured intent
    project_path: str
    status: IntentStatus = IntentStatus.CREATED
    context: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    error: Optional[str] = None
    
    # Track state for each agent
    agent_states: Dict[str, AgentState] = Field(default_factory=lambda: {
        "intent": AgentState(),
        "discovery": AgentState(),
        "solution_design": AgentState(),
        "coder": AgentState(),
        "assurance": AgentState()
    })

    class Config:
        arbitrary_types_allowed = True