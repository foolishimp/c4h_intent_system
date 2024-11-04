# src/models/intent.py

from pydantic import BaseModel, Field
from uuid import UUID, uuid4
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from enum import Enum

class IntentType(str, Enum):
    """Core intent types supported by the system"""
    DISCOVERY = "project_discovery"
    DEBUG = "debug"
    VERIFICATION = "verification"
    ACTION = "action"

class IntentStatus(str, Enum):
    """Primary status states for intents"""
    CREATED = "created"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"
    VERIFICATION_NEEDED = "verification_needed"

class ResolutionState(str, Enum):
    """Detailed resolution states from architecture diagram"""
    INTENT_RECEIVED = "intent_received"
    ANALYZING_INTENT = "analyzing_intent"
    NEEDS_SKILL = "needs_skill"
    NEEDS_DECOMPOSITION = "needs_decomposition"
    NEEDS_CLARIFICATION = "needs_clarification"
    SKILL_EXECUTION = "skill_execution"
    SKILL_SUCCESS = "skill_success"
    SKILL_FAILURE = "skill_failure"
    ASSET_CREATED = "asset_created"
    VERIFICATION_NEEDED = "verification_needed"

class TransformationRecord(BaseModel):
    """Record of an intent transformation"""
    timestamp: datetime
    source_id: UUID
    target_id: UUID
    reason: str
    context: Dict[str, Any] = {}
    resolution_state: Optional[ResolutionState] = None

class Lineage(BaseModel):
    """Tracks the history and transformations of an intent"""
    transformations: List[TransformationRecord] = []
    assets: Dict[str, Any] = {}
    metadata: Dict[str, Any] = {}

class Intent(BaseModel):
    """Core intent model for the system"""
    id: UUID = Field(default_factory=uuid4)
    type: Union[IntentType, str]
    description: str
    environment: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)
    criteria: Dict[str, Any] = Field(default_factory=dict)
    persona: Optional[str] = None
    parent_id: Optional[UUID] = None
    children: List[UUID] = Field(default_factory=list)
    status: IntentStatus = Field(default=IntentStatus.CREATED)
    lineage: Lineage = Field(default_factory=Lineage)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolution_state: ResolutionState = Field(default=ResolutionState.INTENT_RECEIVED)
    
    # Add new fields
    resolution: Optional[str] = None  # skill, decompose, etc.
    skill: Optional[str] = None       # Name of skill to execute if resolution is 'skill'
    actions: List[str] = Field(default_factory=list)  # Follow-up actions

    def subdivide(self) -> List['Intent']:
        """Subdivide intent into smaller intents following architecture flow"""
        sub_intents = []
        
        # Create sub-intents based on criteria
        for sub_criteria in self.criteria.get('decomposition_rules', []):
            sub_intent = Intent(
                type=self.type,
                description=f"Sub-intent of {self.description}: {sub_criteria.get('description', '')}",
                environment=self.environment.copy(),
                context=self.context.copy(),
                criteria=sub_criteria,
                parent_id=self.id
            )
            self.children.append(sub_intent.id)
            sub_intents.append(sub_intent)
            
            # Record transformation
            self._record_transformation(
                target_id=sub_intent.id,
                reason="Intent decomposition",
                resolution_state=ResolutionState.NEEDS_DECOMPOSITION
            )
            
        return sub_intents

    def validate(self) -> bool:
        """Validate intent structure and content"""
        try:
            # Basic structural validation
            if not self.description:
                return False
                
            # Validate based on type
            if self.type == IntentType.DISCOVERY:
                return self._validate_discovery()
            elif self.type == IntentType.ACTION:
                return self._validate_action()
                
            return True
            
        except Exception:
            return False

    def _validate_discovery(self) -> bool:
        """Validate discovery intent requirements"""
        if self.resolution == 'skill' and not self.skill:
            return False
        return True
            
    def _validate_action(self) -> bool:
        """Validate action intent requirements"""
        if self.resolution == 'skill' and not self.skill:
            return False
        return True

    def _record_transformation(self, target_id: UUID, reason: str, 
                             resolution_state: Optional[ResolutionState] = None) -> None:
        """Record a transformation in the lineage"""
        transformation = TransformationRecord(
            timestamp=datetime.utcnow(),
            source_id=self.id,
            target_id=target_id,
            reason=reason,
            resolution_state=resolution_state
        )
        self.lineage.transformations.append(transformation)

    class Config:
        """Pydantic model configuration"""
        arbitrary_types_allowed = True
        json_encoders = {
            UUID: str,
            datetime: lambda v: v.isoformat()
        }