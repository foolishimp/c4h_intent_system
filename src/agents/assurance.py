# src/agents/assurance.py

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import structlog
import asyncio

from .base import BaseAgent
from ..models.intent import Intent, IntentType
from ..config import Config

@dataclass
class ValidationRule:
    """Rule definition for validation"""
    type: str
    validator: str
    params: Dict[str, Any] = None

class AssuranceAgent(BaseAgent):
    """Agent responsible for verifying execution results and validating transformations"""

    def __init__(self, config: Config):
        """Initialize the assurance agent
        
        Args:
            config: System configuration
        """
        super().__init__(config)
        self.logger = structlog.get_logger()
        self.verification_rules = self._load_rules()

    async def verify(self, asset: 'Asset') -> Intent:
        """Verify an asset according to rules"""
        verification_intent = self.createVerificationIntent(asset)
        return await self.process_intent(verification_intent)

    async def validateSkillExecution(self, skill: str, result: Any) -> bool:
        """Validate skill execution results"""
        # Get skill-specific rules
        skill_rules = self.verification_rules.get(skill, {})
        
        # Default to valid if no rules defined
        if not skill_rules:
            self.logger.debug("assurance.no_rules_for_skill", skill=skill)
            return True

        # Apply validation rules
        try:
            for rule in skill_rules.values():
                self.logger.debug("assurance.applying_rule", 
                                skill=skill,
                                rule=rule)
                
                # Execute validation logic
                valid = await self._validate_rule(rule, result)
                if not valid:
                    return False
                    
            return True
            
        except Exception as e:
            self.logger.exception("assurance.validation_failed",
                                skill=skill,
                                error=str(e))
            return False

    async def process_intent(self, intent: Intent) -> Intent:
        """Process verification intents
        
        Args:
            intent: Intent to process
        
        Returns:
            Processed intent with verification results
        """
        try:
            if intent.type != IntentType.VERIFICATION:
                raise ValueError(f"Invalid intent type: {intent.type}")
                
            asset = intent.context.get('asset')
            if not asset:
                raise ValueError("No asset provided for verification")
                
            # Apply verification rules
            verification_results = {}
            for rule_name, rule in self.verification_rules.items():
                result = await self._validate_rule(rule, asset)
                verification_results[rule_name] = result
            
            # Update intent with results    
            intent.context['verification_results'] = verification_results
            intent.context['verification_complete'] = True
            
            return intent
            
        except Exception as e:
            return await self.handle_error(e, intent)

    def createVerificationIntent(self, asset: 'Asset') -> Intent:
        """Create intent for asset verification"""
        return Intent(
            type=IntentType.VERIFICATION,
            description=f"Verify asset: {asset.id}",
            context={"asset": asset.dict()},
            criteria={"verify": True}
        )

    def _load_rules(self) -> Dict[str, Any]:
        """Load verification rules from config"""
        if hasattr(self.config, 'validation'):
            rules = {}
            # Convert Pydantic model fields to dict format
            for rule_name, rule_config in self.config.validation.items():
                rules[rule_name] = ValidationRule(
                    type=rule_config.type,
                    validator=rule_config.validator
                )
            return rules
        return {}

    async def _validate_rule(self, rule: ValidationRule, data: Any) -> bool:
        """Execute a validation rule"""
        try:
            # Get validator function
            validator = getattr(self, f"_validate_{rule.validator}", None)
            if not validator:
                self.logger.warning("assurance.validator_not_found",
                                  validator=rule.validator)
                return False

            # Execute validation
            return await validator(data, rule.params or {})
            
        except Exception as e:
            self.logger.exception("assurance.rule_validation_failed",
                                rule=rule.validator,
                                error=str(e))
            return False