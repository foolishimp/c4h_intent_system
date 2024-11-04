# src/models/intent_lineage.py

from typing import Dict, List, Optional, Union
from datetime import datetime
from uuid import UUID, uuid4
from pydantic import BaseModel, Field

class TransformationRecord(BaseModel):
    """Record of a single transformation in the intent chain"""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    agent: str
    action_type: str
    source_intent: UUID
    result_intent: UUID
    reason: str
    context: Dict = Field(default_factory=dict)
    artifacts: Dict[str, str] = Field(default_factory=dict)

class IntentLineage(BaseModel):
    """Tracks the complete lineage of an intent transformation chain"""
    root_intent_id: UUID
    current_intent_id: UUID
    transformations: List[TransformationRecord] = Field(default_factory=list)
    branch_point: Optional[UUID] = None
    metadata: Dict = Field(default_factory=dict)
    
    def add_transformation(
        self,
        agent: str,
        action_type: str,
        source_intent: UUID,
        result_intent: UUID,
        reason: str,
        context: Dict = None,
        artifacts: Dict[str, str] = None
    ) -> None:
        """Add a new transformation to the lineage"""
        record = TransformationRecord(
            agent=agent,
            action_type=action_type,
            source_intent=source_intent,
            result_intent=result_intent,
            reason=reason,
            context=context or {},
            artifacts=artifacts or {}
        )
        self.transformations.append(record)
        self.current_intent_id = result_intent

    def get_transformation_chain(self) -> List[TransformationRecord]:
        """Get the complete transformation chain"""
        return self.transformations

    def get_branch_point(self) -> Optional[UUID]:
        """Get the point where this lineage branched from another"""
        return self.branch_point

class Intent(BaseModel):
    """Enhanced intent model with lineage tracking"""
    id: UUID = Field(default_factory=uuid4)
    type: str
    description: str
    project_path: str
    context: Dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    parent_id: Optional[UUID] = None
    lineage: IntentLineage = None

    def __init__(self, **data):
        super().__init__(**data)
        if not self.lineage:
            # Initialize lineage if this is a root intent
            self.lineage = IntentLineage(
                root_intent_id=self.id,
                current_intent_id=self.id
            )

    def create_child_intent(
        self,
        type: str,
        description: str,
        agent: str,
        reason: str,
        context: Dict = None
    ) -> 'Intent':
        """Create a child intent with lineage tracking"""
        child = Intent(
            type=type,
            description=description,
            project_path=self.project_path,
            parent_id=self.id,
            context=context or {}
        )
        
        # Create new lineage or continue existing
        child.lineage = IntentLineage(
            root_intent_id=self.lineage.root_intent_id,
            current_intent_id=child.id,
            transformations=self.lineage.transformations.copy()
        )
        
        # Record the transformation
        child.lineage.add_transformation(
            agent=agent,
            action_type=type,
            source_intent=self.id,
            result_intent=child.id,
            reason=reason,
            context=context
        )
        
        return child

    def branch_intent(
        self,
        type: str,
        description: str,
        agent: str,
        reason: str,
        context: Dict = None
    ) -> 'Intent':
        """Create a new branch in the intent tree"""
        branch = self.create_child_intent(
            type=type,
            description=description,
            agent=agent,
            reason=reason,
            context=context
        )
        branch.lineage.branch_point = self.id
        return branch