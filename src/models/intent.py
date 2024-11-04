# src/models/intent.py

from uuid import UUID, uuid4
from enum import Enum
from typing import Dict, Any, Optional
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

class Intent(BaseModel):
    """Simple intent model for code transformations"""
    id: UUID = Field(default_factory=uuid4)
    description: str
    project_path: str
    status: IntentStatus = IntentStatus.CREATED
    context: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    error: Optional[str] = None

    class Config:
        frozen = True
