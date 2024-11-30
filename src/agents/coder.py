"""
Primary coder agent implementation for processing code changes.
Path: src/agents/coder.py
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import structlog
from datetime import datetime
import json
from pathlib import Path

from agents.base import BaseAgent, LLMProvider
from skills.semantic_merge import SemanticMerge, MergeConfig
from skills.semantic_iterator import SemanticIterator, ExtractorConfig
from skills.asset_manager import AssetManager, AssetResult
from skills.shared.types import ExtractConfig

logger = structlog.get_logger()

@dataclass
class CoderResult:
    """Result of code processing operation"""
    success: bool
    changes: List[AssetResult]
    error: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None

class Coder(BaseAgent):
    def __init__(self,
                provider: LLMProvider = LLMProvider.ANTHROPIC,
                model: Optional[str] = None,
                temperature: float = 0,
                config: Optional[Dict[str, Any]] = None):
        """Initialize coder with configuration"""
        super().__init__(provider=provider, model=model, temperature=temperature, config=config)
        
        # Initialize backup location
        backup_path = Path(config.get('backup', {}).get('path', 'workspaces/backups')) if config else None
        
        # Create semantic tools - pass through same config 
        self.iterator = SemanticIterator(
            provider=provider,
            model=model,
            temperature=temperature,
            config=config,
            extractor_config=ExtractorConfig()
        )
        
        merger = SemanticMerge(
            provider=provider,
            model=model,
            temperature=temperature, 
            config=config
        )
        
        # Setup asset management
        self.asset_manager = AssetManager(
            backup_enabled=True,
            backup_dir=backup_path,
            merger=merger
        )

        logger.info("coder.config", config=json.dumps(config, indent=2) if config else None)

    def _get_agent_name(self) -> str:
        return "coder"

    async def process(self, context: Dict[str, Any]) -> CoderResult:
        """Process code changes"""
        logger.info("coder.input_context", context=json.dumps(context, indent=2))
        metrics = {"start_time": datetime.utcnow().isoformat()}
        changes = []

        try:
            # Log raw input for debugging
            input_data = context.get('input_data')
            logger.info("coder.raw_input", data=input_data)

            # Create extraction config from context
            extract_config = ExtractConfig(
                instruction=context.get('instruction', ''),
                format=context.get('format', 'json')
            )

            # Extract and process changes
            async for change in self.iterator.iter_extract(input_data, extract_config):
                logger.info("coder.processing_change", change=json.dumps(change, indent=2))
                result = self.asset_manager.process_action(change)
                logger.info("coder.change_result", 
                          success=result.success,
                          path=str(result.path) if result.path else None,
                          error=result.error if result.error else None)
                changes.append(result)

            # Determine overall success
            success = any(c.success for c in changes)
            logger.info("coder.results", 
                       success=success,
                       total_changes=len(changes),
                       successful_changes=sum(1 for c in changes if c.success))

            return CoderResult(
                success=success,
                changes=changes,
                error=None if success else "All changes failed",
                metrics=metrics
            )

        except Exception as e:
            logger.error("coder.process_failed", error=str(e))
            return CoderResult(success=False, changes=changes, error=str(e), metrics=metrics)