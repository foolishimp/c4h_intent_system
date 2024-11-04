# src/models/intent.py

from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from datetime import datetime
from uuid import UUID, uuid4

class Intent(BaseModel):
    """Simplified intent model for AutoGen integration"""
    id: UUID = Field(default_factory=uuid4)
    type: str
    description: str
    project_path: str
    context: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    parent_id: Optional[UUID] = None
    
    class Config:
        json_encoders = {
            UUID: str,
            datetime: lambda v: v.isoformat()
        }