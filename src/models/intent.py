# src/models/intent.py

from pydantic import BaseModel, Field  # Added Field import
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
            if self.type == IntentType.SCOPE:
                return self._validate_scope_analysis()
            elif self.type == IntentType.ACTION:
                return self._validate_action()
                
            return True
            
        except Exception:
            return False

    def transformTo(self, new_type: Union[IntentType, str]) -> 'Intent':
        """Create new intent of different type while maintaining lineage"""
        new_intent = Intent(
            type=new_type,
            description=f"Transformed from {self.type}: {self.description}",
            environment=self.environment.copy(),
            context=self.context.copy(),
            criteria=self.criteria.copy(),
            parent_id=self.id
        )
        
        # Record transformation with resolution state
        self._record_transformation(
            target_id=new_intent.id,
            reason=f"Type transformation from {self.type} to {new_type}",
            resolution_state=self.resolution_state
        )
        
        # Copy existing lineage
        new_intent.lineage.transformations.extend(self.lineage.transformations)
        new_intent.lineage.assets = self.lineage.assets.copy()
        new_intent.lineage.metadata = self.lineage.metadata.copy()
        
        return new_intent

    def update_resolution(self, state: ResolutionState) -> None:
        """Update the resolution state and corresponding status"""
        self.resolution_state = state
        
        # Update main status based on resolution state
        if state in [ResolutionState.SKILL_FAILURE, ResolutionState.NEEDS_CLARIFICATION]:
            self.status = IntentStatus.ERROR
        elif state == ResolutionState.SKILL_SUCCESS:
            self.status = IntentStatus.COMPLETED
        elif state == ResolutionState.VERIFICATION_NEEDED:
            self.status = IntentStatus.VERIFICATION_NEEDED
        else:
            self.status = IntentStatus.PROCESSING

    def needs_skill(self) -> bool:
        """Check if intent requires direct skill execution"""
        return self.resolution_state == ResolutionState.NEEDS_SKILL

    def needs_decomposition(self) -> bool:
        """Check if intent requires decomposition"""
        return self.resolution_state == ResolutionState.NEEDS_DECOMPOSITION

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

    def _validate_scope_analysis(self) -> bool:
        """Validate scope analysis intent"""
        required_fields = ['project_path', 'analysis_depth']
        return all(field in self.criteria for field in required_fields)

    def _validate_action(self) -> bool:
        """Validate action intent"""
        required_fields = ['action_type', 'target']
        return all(field in self.criteria for field in required_fields)

    class Config:
        """Pydantic model configuration"""
        arbitrary_types_allowed = True
        json_encoders = {
            UUID: str,
            datetime: lambda v: v.isoformat()
        }