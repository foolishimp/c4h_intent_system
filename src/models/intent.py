from pydantic import BaseModel
from uuid import UUID, uuid4
from typing import Optional, List, Dict, Any
from datetime import datetime

class Intent(BaseModel):
    id: UUID = uuid4()
    type: str
    description: str
    environment: Dict[str, Any]
    context: Dict[str, Any]
    criteria: Dict[str, Any]
    parent_id: Optional[UUID] = None
    children: List[UUID] = []
    status: str
    created_at: datetime = datetime.utcnow()
