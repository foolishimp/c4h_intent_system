"""
Solution designer implementation following BaseAgent design principles.
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
        """Initialize designer with proper configuration."""
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
        """Get agent name for config lookup - required by BaseAgent"""
        return "solution_designer"

    def _format_request(self, context: Dict[str, Any]) -> str:
        """Format request using configured prompt template"""
        try:
            template = self._get_prompt('solution')
            
            # Extract values safely
            discovery_data = context.get('discovery_data', {})
            raw_output = discovery_data.get('raw_output', '')
            intent_desc = context.get('intent', {}).get('description', '')
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

    def process(self, context: Dict[str, Any]) -> AgentResponse:
        """Process solution design request"""
        try:
            logger.info("solution_designer.process_start", 
                       has_context=bool(context),
                       intent=context.get('intent', {}).get('description') if context else None)

            # Minimal validation - just ensure we have input
            if not context.get('discovery_data', {}).get('raw_output'):
                logger.error("solution_designer.missing_discovery")
                return AgentResponse(
                    success=False,
                    data={},
                    error="Missing discovery data - cannot analyze code"
                )

            # Use BaseAgent's process method
            response = super().process(context)
            
            logger.info("solution_designer.process_complete",
                      success=response.success,
                      error=response.error if not response.success else None)

            if response.success:
                logger.debug("solution_designer.changes_generated",
                          changes=json.dumps(response.data.get('changes', []), indent=2))

            return response

        except Exception as e:
            logger.error("solution_designer.process_failed", error=str(e))
            return AgentResponse(success=False, data={}, error=str(e))