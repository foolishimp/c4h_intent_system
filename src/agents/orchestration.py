# src/agents/orchestration.py

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import structlog
import yaml
from pathlib import Path
from datetime import datetime

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
    """Agent responsible for orchestrating intent processing"""

    def __init__(self, config: Config):
        super().__init__(config)
        self.intent_factory = IntentFactory(config)
        self.discovery_agent = DiscoveryAgent(config)
        self.logger = structlog.get_logger()

    async def process_scope_request(self, project_path: str) -> Dict[str, Any]:
        """Process a scoping request and generate an action plan"""
        self.logger.info("orchestration.scope_request.starting", 
                        project_path=project_path)
        
        try:
            # Create initial intent from config
            self.logger.info("orchestration.creating_intent")
            intent = self.intent_factory.create_initial_intent(
                'project_discovery',
                project_path=project_path,
                target=project_path  # Add target for action creation
            )
            
            self.logger.info("orchestration.processing_intent",
                            intent_id=str(intent.id))
            
            # Process the intent
            result = await self.process_intent(intent)
            
            if result.status == IntentStatus.ERROR:
                error_msg = result.context.get('error', 'Unknown error')
                self.logger.error("orchestration.intent_failed", error=error_msg)
                raise Exception(error_msg)
            
            # Save and display results
            self.logger.info("orchestration.saving_results")
            output_path = await self._save_results(result)
            
            response = {
                "intent_id": str(intent.id),
                "result": result.dict(),
                "results_path": str(output_path)
            }
            
            self.logger.info("orchestration.complete", **response)
            return response
            
        except Exception as e:
            self.logger.exception("orchestration.failed")
            raise

    async def process_intent(self, intent: Intent) -> Intent:
        """Process intent according to architecture specification"""
        try:
            # Update state to analyzing
            intent.update_resolution(ResolutionState.ANALYZING_INTENT)
            
            # Analyze intent
            analysis = await self.analyze_intent(intent)
            
            # Handle initial discovery intent
            if intent.type == 'project_discovery':
                # First try to execute the skill directly
                if intent.resolution == 'skill':
                    skill_name = intent.skill
                    if not skill_name:
                        raise ValueError("Discovery intent requires skill but none specified")
                    result = await self.execute_skill(skill_name, intent)
                    
                    # If successful, check for follow-up actions
                    if result.status == IntentStatus.COMPLETED and intent.actions:
                        action_results = []
                        project_path = intent.environment.get('project_path')
                        if not project_path:
                            raise ValueError("Missing project_path in environment")
                            
                        action_params = {
                            'project_path': project_path,
                            'target': project_path
                        }
                        
                        # Create and process each follow-up action
                        for action in intent.actions:
                            action_intent = self.intent_factory.create_action_intent(
                                action_type=action,
                                parent_id=str(intent.id),
                                **action_params
                            )
                            action_result = await self.process_intent(action_intent)
                            action_results.append(action_result)
                            
                        # Combine discovery result with action results
                        final_result = result
                        for action_result in action_results:
                            final_result.context.update(action_result.context)
                            
                        return final_result
                    
                    return result
                else:
                    raise ValueError(f"Unsupported resolution type for discovery: {intent.resolution}")
            
            # Handle action intents
            if intent.type in self.config.intents['actions']:
                action_config = self.config.intents['actions'][intent.type]
                if action_config.resolution == 'skill':
                    skill_name = action_config.skill
                    if not skill_name:
                        raise ValueError(f"Action {intent.type} requires skill but none specified")
                    return await self.execute_skill(skill_name, intent)
                else:
                    raise ValueError(f"Unsupported resolution type for action: {action_config.resolution}")
            
            raise ValueError(f"Unsupported intent type: {intent.type}")
            
        except Exception as e:
            return await self.handle_error(e, intent)


            
    async def analyze_intent(self, intent: Intent) -> Analysis:
        """Analyze intent to determine processing strategy"""
        # For initial discovery intent
        if intent.type == 'project_discovery':
            config = self.config.intents['initial']['project_discovery']
            return Analysis(
                resolution_state=ResolutionState.NEEDS_SKILL,
                skill_name=config.skill,
                verification_required=bool(config.validation_rules),
                details={
                    "reason": "Project discovery requires analysis",
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
            
        # For action intents
        elif intent.type in self.config.intents['actions']:
            action_config = self.config.intents['actions'][intent.type]
            return Analysis(
                resolution_state=ResolutionState.NEEDS_SKILL,
                skill_name=action_config.skill,
                verification_required=bool(action_config.validation_rules),
                details={
                    "action_type": intent.type,
                    "config": action_config.dict(),
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
        
        try:
            # Get skill configuration
            if skill_name not in self.config.skills:
                raise ValueError(f"Unknown skill: {skill_name}")

            skill_config = self.config.skills[skill_name]
            intent.update_resolution(ResolutionState.SKILL_EXECUTION)
            
            # Execute the appropriate skill based on type
            result = None
            
            if skill_name == 'tartxt':
                # Use discovery agent for tartxt skill
                result = await self.discovery_agent.process_intent(intent)
            else:
                # Generic skill execution - not implemented yet
                raise NotImplementedError(f"Skill type not implemented: {skill_name}")

            if not result:
                raise ValueError("Skill execution returned no result")

            intent.update_resolution(ResolutionState.SKILL_SUCCESS)
            return result
            
        except Exception as e:
            self.logger.exception("skill.execution_failed", 
                                skill=skill_name,
                                error=str(e))
            intent.update_resolution(ResolutionState.SKILL_FAILURE)
            raise

    async def combine_results(self, results: List[Intent]) -> Intent:
        """Combine multiple intent results into a single result"""
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