# src/agents/orchestration.py
"""
Orchestration Agent Implementation for Intent-Based Architecture
Handles intent routing, decomposition, and skill execution coordination
"""

from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
import structlog
import yaml

from .base import BaseAgent
from ..models.intent import Intent, IntentStatus, ResolutionState
from ..models.intent_factory import IntentFactory
from ..config import Config
from .discovery import DiscoveryAgent 

@dataclass
class Analysis:
    """Intent analysis results"""
    resolution_state: ResolutionState = ResolutionState.INTENT_RECEIVED
    skill_name: Optional[str] = None
    verification_required: bool = False
    details: Dict[str, Any] = field(default_factory=dict)
    
    def needs_decomposition(self) -> bool:
        """Check if intent needs to be broken down"""
        return self.resolution_state == ResolutionState.NEEDS_DECOMPOSITION
    
    def needs_skill(self) -> bool:
        """Check if intent requires direct skill execution"""
        return self.resolution_state == ResolutionState.NEEDS_SKILL
    
    def needs_verification(self) -> bool:
        """Check if result requires verification"""
        return self.verification_required

class OrchestrationAgent(BaseAgent):
    def __init__(self, config: Config):
        super().__init__(config)
        self.intent_factory = IntentFactory(config)
        self.logger = structlog.get_logger()

    async def process_scope_request(self, project_path: str) -> Dict[str, Any]:
        """Process a scoping request and generate an action plan"""
        try:
            # Create initial intent from config
            intent = self.intent_factory.create_initial_intent(
                'project_discovery',  # Updated from scope_analysis
                project_path=project_path
            )
            
            self.logger.info("scope_request.created", intent_id=str(intent.id))
            
            # Process the intent
            result = await self.process_intent(intent)
            
            if result.status == IntentStatus.ERROR:
                raise Exception(result.context.get('error'))
            
            # Save and display results
            results_path = await self._save_results(result)
            await self._display_action_plan(result)
            
            return {
                "intent_id": str(intent.id),
                "result": result.dict(),
                "results_path": str(results_path)
            }
            
        except Exception as e:
            self.logger.exception("scope_request.failed")
            raise

    async def process_intent(self, intent: Intent) -> Intent:
        """Process intent according to architecture specification"""
        try:
            # Update state to analyzing
            intent.update_resolution(ResolutionState.ANALYZING_INTENT)
            
            # Analyze intent
            analysis = await self.analyze_intent(intent)
            
            if analysis.needs_decomposition():
                # Create action intents based on config
                actions = self.config.intents['actions'].keys()
                results = []
                
                for action in actions:
                    action_intent = self.intent_factory.create_action_intent(
                        action,
                        parent_id=str(intent.id),
                        target=intent.environment['project_path']
                    )
                    result = await self.process_intent(action_intent)
                    results.append(result)
                    
                return await self.combine_results(results)
                
            # Process using appropriate skill
            if intent.type in self.config.intents['actions']:
                action_config = self.config.intents['actions'][intent.type]
                skill_name = action_config['skill']
                result = await self.execute_skill(skill_name, intent)
                return result
                
            return intent
            
        except Exception as e:
            return await self.handle_error(e, intent)

    async def analyze_intent(self, intent: Intent) -> Analysis:
        """Analyze intent to determine processing strategy"""
        if intent.type == 'project_discovery':
            return Analysis(
                resolution_state=ResolutionState.NEEDS_DECOMPOSITION,
                verification_required=True,
                details={
                    "reason": "Project discovery requires multiple analysis steps",
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
        elif intent.type in self.config.intents['actions']:
            action_config = self.config.intents['actions'][intent.type]
            return Analysis(
                resolution_state=ResolutionState.NEEDS_SKILL,
                skill_name=action_config['skill'],
                verification_required=action_config.get('requires_verification', False),
                details={
                    "action_type": intent.type,
                    "config": action_config,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
        else:
            raise ValueError(f"Unknown intent type: {intent.type}")

    async def execute_skill(self, skill_name: str, intent: Intent) -> Intent:
        """Execute a skill on an intent"""
        self.logger.info("skill.executing", 
                        skill=skill_name, 
                        intent_id=str(intent.id))
        
        skill_config = self.config.skills[skill_name]
        # Skill execution logic here
        return intent

    async def combine_results(self, results: List[Intent]) -> Intent:
        """Combine multiple intent results into a single result"""
        # Implementation for combining results
        if not results:
            raise ValueError("No results to combine")
            
        primary = results[0]
        for result in results[1:]:
            primary.context.update(result.context)
            
        return primary

    async def _save_results(self, result: Intent) -> Path:
        """Save analysis results to file"""
        output_path = self.config.asset_base_path / f"analysis_{result.id}.yml"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with output_path.open('w') as f:
            yaml.safe_dump(result.dict(), f)
            
        return output_path

    async def _display_action_plan(self, result: Intent) -> None:
        """Display the action plan derived from analysis"""
        self.logger.info("action_plan.generated",
                        intent_id=str(result.id),
                        status=result.status,
                        steps=len(result.context.get('actions', [])))
