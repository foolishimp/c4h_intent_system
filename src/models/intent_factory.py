# src/models/intent_factory.py

from typing import Dict, Any
from .intent import Intent, IntentStatus, ResolutionState
from src.config import Config

class IntentFactory:
    """Creates intents based on system configuration"""
    
    def __init__(self, config: Config):
        """Initialize with system configuration
        
        Args:
            config: System configuration instance
        """
        self.config = config
        self.intent_configs = config.intents  # Access intents field directly

    def create_initial_intent(self, intent_type: str, **params) -> Intent:
        """Create an initial intent from configuration"""
        if 'initial' not in self.intent_configs or intent_type not in self.intent_configs['initial']:
            raise ValueError(f"No configuration found for initial intent type: {intent_type}")
            
        intent_config = self.intent_configs['initial'][intent_type]
        
        # Format description template with params
        description = intent_config.description_template.format(**params)
        
        # Build environment dict
        environment = {
            **intent_config.environment,
            **params
        }
        
        # Create the intent
        return Intent(
            type=intent_type,
            description=description,
            environment=environment,
            criteria=intent_config.criteria,
            status=IntentStatus.CREATED,
            resolution_state=ResolutionState.INTENT_RECEIVED
        )

    def create_action_intent(self, action_type: str, parent_id: str, **params) -> Intent:
        """Create an action intent from configuration"""
        if 'actions' not in self.intent_configs or action_type not in self.intent_configs['actions']:
            raise ValueError(f"No configuration found for action type: {action_type}")
            
        action_config = self.intent_configs['actions'][action_type]
        
        # Format description template with params
        description = action_config.description_template.format(**params)
        
        return Intent(
            type=action_type,
            description=description,
            environment=params,
            criteria=action_config.criteria,
            parent_id=parent_id,
            status=IntentStatus.CREATED,
            resolution_state=ResolutionState.INTENT_RECEIVED
        )