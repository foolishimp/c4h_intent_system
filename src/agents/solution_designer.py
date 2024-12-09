"""
Solution designer implementation following BaseAgent design principles.
Path: src/agents/solution_designer.py
"""

from typing import Dict, Any, Optional
import structlog
from datetime import datetime
import json
from .base import BaseAgent, LLMProvider, AgentResponse
from config import locate_config

logger = structlog.get_logger()

class SolutionDesigner(BaseAgent):
    """Designs specific code modifications based on intent and discovery analysis."""
    
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize designer with proper configuration."""
        super().__init__(config=config)
        
        # Extract config using locate_config pattern
        solution_config = locate_config(self.config or {}, self._get_agent_name())
        
        logger.info("solution_designer.initialized", 
                   config_keys=list(solution_config.keys()) if solution_config else None)

    def _get_agent_name(self) -> str:
        """Get agent name for config lookup - required by BaseAgent"""
        return "solution_designer"

    # From class SolutionDesigner in src/agents/solution_designer.py

    def _format_request(self, context: Dict[str, Any]) -> str:
        """Format request using configured prompt template"""
        try:
            template = self._get_prompt('solution')
            
            # Extract with fallbacks for different structures
            raw_output = None
            intent_desc = None
            
            # Try input_data structure first
            if 'input_data' in context:
                input_data = context['input_data']
                discovery_data = input_data.get('discovery_data', {})
                raw_output = discovery_data.get('raw_output', '')
                intent = input_data.get('intent', {})
                intent_desc = intent.get('description', '')
            
            # Fallback to direct access
            if not raw_output and 'discovery_data' in context:
                raw_output = context['discovery_data'].get('raw_output', '')
            if not intent_desc and 'intent' in context:
                intent_desc = context['intent'].get('description', '')
            
            iteration = context.get('iteration', 0)
            
            logger.debug("solution_designer.format_request",
                        intent=intent_desc,
                        has_discovery=bool(raw_output),
                        iteration=iteration)
            
            return template.format(
                intent=intent_desc,
                source_code=raw_output,
                iteration=iteration
            )

        except Exception as e:
            logger.error("solution_designer.format_error", error=str(e))
            return str(context)

    # From class SolutionDesigner in src/agents/solution_designer.py

    def process(self, context: Dict[str, Any]) -> AgentResponse:
        """Process solution design request"""
        try:
            # Try direct access first, then check config structure
            discovery_data = None
            raw_output = None
            
            # Check for top-level input_data
            if 'input_data' in context:
                discovery_data = context['input_data'].get('discovery_data', {})
                raw_output = discovery_data.get('raw_output')
                
            # If not found, check direct discovery_data
            if not raw_output and 'discovery_data' in context:
                discovery_data = context['discovery_data']
                raw_output = discovery_data.get('raw_output')

            logger.info("solution_designer.process_start", 
                    has_discovery=bool(raw_output),
                    has_context=bool(context))

            if not raw_output:
                logger.error("solution_designer.missing_discovery",
                            context_keys=list(context.keys()))
                return AgentResponse(
                    success=False,
                    data={},
                    error="Missing discovery data - cannot analyze code"
                )

            # Use BaseAgent's process method with full context
            response = super().process(context)
            
            logger.info("solution_designer.process_complete",
                    success=response.success,
                    error=response.error if not response.success else None)

            return response

        except Exception as e:
            logger.error("solution_designer.process_failed", error=str(e))
            return AgentResponse(success=False, data={}, error=str(e))

    def _process_llm_response(self, content: str, raw_response: Any) -> Dict[str, Any]:
        """Process LLM response into standard format"""
        try:
            # Extract JSON changes from response
            if isinstance(content, str):
                data = json.loads(content)
            else:
                data = content

            return {
                "changes": data.get("changes", []),
                "raw_output": raw_response,
                "raw_content": content,
                "timestamp": datetime.utcnow().isoformat()
            }

        except json.JSONDecodeError as e:
            logger.error("solution_designer.json_parse_error", error=str(e))
            return {
                "error": f"Failed to parse LLM response: {str(e)}",
                "raw_output": raw_response,
                "raw_content": content,
                "timestamp": datetime.utcnow().isoformat()
            }