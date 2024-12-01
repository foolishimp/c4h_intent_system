"""
Solution designer implementation following BaseAgent design patterns.
Path: src/agents/solution_designer.py
"""

from typing import Dict, Any, Optional
import structlog
from datetime import datetime
import json
from .base import BaseAgent, LLMProvider, AgentResponse

logger = structlog.get_logger()

class SolutionDesigner(BaseAgent):
    """Designs specific code modifications based on intent and discovery analysis."""
    
    def __init__(self,
                provider: LLMProvider = LLMProvider.ANTHROPIC,
                model: Optional[str] = None,
                temperature: float = 0,
                config: Optional[Dict[str, Any]] = None):
        """Initialize designer with system configuration."""
        super().__init__(
            provider=provider,
            model=model,
            temperature=temperature,
            config=config
        )
        
        logger.info("solution_designer.initialized", 
                   provider=str(provider),
                   model=model,
                   config_keys=list(config.keys()) if isinstance(config, dict) else None)

    def _get_agent_name(self) -> str:
        """Get agent name for config lookup"""
        return "solution_designer"

    def _format_request(self, context: Optional[Dict[str, Any]]) -> str:
        """Format request using configured prompt template"""
        if not context:
            return self._get_prompt('validation')

        try:
            # Use template from config
            template = self._get_prompt('design')
            
            # Extract values from context
            discovery_data = context.get('discovery_data', {})
            raw_output = discovery_data.get('raw_output', '')
            intent_desc = context.get('intent', {}).get('description', '')
            iteration = context.get('iteration', 0)
            
            # Apply template
            return template.format(
                intent=intent_desc,
                source_code=raw_output,
                iteration=iteration
            )

        except Exception as e:
            logger.error("solution_designer.format_error", error=str(e))
            return str(context)

    def process(self, context: Optional[Dict[str, Any]]) -> AgentResponse:
        """Process solution design request synchronously"""
        try:
            logger.info("solution_designer.process_start", 
                       has_context=bool(context),
                       intent=context.get('intent', {}).get('description') if context else None)
            
            # Validate required data
            discovery_data = context.get('discovery_data', {})
            if not discovery_data or 'raw_output' not in discovery_data:
                logger.error("solution_designer.missing_discovery")
                return self._create_standard_response(
                    False,
                    {},
                    "Missing discovery output data - cannot analyze code"
                )
            
            # Use BaseAgent's synchronous process
            response = super().process(context)
            
            logger.info("solution_designer.process_complete",
                       success=response.success,
                       error=response.error if not response.success else None)
            
            if response.success:
                logger.debug("solution_designer.changes_generated",
                           changes_count=len(response.data.get('changes', [])) if response.data else 0)

            return response

        except Exception as e:
            logger.error("solution_designer.process_failed", error=str(e))
            return self._create_standard_response(False, {}, str(e))