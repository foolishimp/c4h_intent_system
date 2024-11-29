"""
Coder orchestrator for managing semantic operations on assets.
Path: src/agents/coder.py
"""

from typing import Dict, Any, List, Optional
from pathlib import Path
from dataclasses import dataclass
import structlog
from datetime import datetime
from skills.semantic_iterator import SemanticIterator
from skills.semantic_merge import SemanticMerge, MergeConfig
from skills.asset_manager import AssetManager, AssetResult
from agents.base import BaseAgent, LLMProvider

logger = structlog.get_logger()

@dataclass
class CoderResult:
    """Result of code processing"""
    success: bool
    changes: List[AssetResult]
    error: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None

class Coder(BaseAgent):
    """Orchestrates semantic operations on code assets"""
    
    def __init__(self,
                provider: LLMProvider = LLMProvider.ANTHROPIC,
                model: Optional[str] = None,
                temperature: float = 0,
                config: Optional[Dict[str, Any]] = None):
        """Initialize with configuration"""
        super().__init__(
            provider=provider,
            model=model,
            temperature=temperature,
            config=config
        )

        self.iterator = SemanticIterator(
            provider=provider,
            model=model,
            temperature=temperature,
            config=config
        )
        
        merger = SemanticMerge(
            provider=provider,
            model=model,
            temperature=temperature,
            config=config,
            merge_config=MergeConfig(
                preserve_formatting=True
            )
        )
        
        self.asset_manager = AssetManager(
            backup_enabled=True,
            backup_dir=Path(config['backup_dir']) if config.get('backup_dir') else None,
            merger=merger
        )

        logger.info("coder.initialized")

    def _get_agent_name(self) -> str:
        return "coder"
        
    async def process(self, context: Dict[str, Any]) -> CoderResult:
        """Process changes using the asset manager."""
        metrics = {
            "start_time": datetime.utcnow().isoformat(),
            "total_changes": 0,
            "successful_changes": 0,
            "failed_changes": 0
        }

        try:
            changes = []
            input_data = context.get('changes', [])

            # Process each change and collect metrics
            for action in self.iterator.extract_all(input_data, context):
                metrics["total_changes"] += 1
                try:
                    result = self.asset_manager.process_action(action)
                    changes.append(result)
                    if result.success:
                        metrics["successful_changes"] += 1
                        logger.info("change.succeeded", 
                                  path=str(result.path) if result.path else None)
                    else:
                        metrics["failed_changes"] += 1
                        logger.error("change.failed",
                                   path=str(result.path) if result.path else None,
                                   error=result.error)
                except Exception as e:
                    metrics["failed_changes"] += 1
                    logger.error("change.processing_failed", error=str(e))
                    changes.append(AssetResult(success=False, path=None, error=str(e)))

            success = any(c.success for c in changes)
            metrics["end_time"] = datetime.utcnow().isoformat()
            
            if not success:
                logger.warning("coder.no_successful_changes",
                             total_changes=metrics["total_changes"])

            return CoderResult(
                success=success,
                changes=changes,
                error=None if success else "All changes failed",
                metrics=metrics
            )

        except Exception as e:
            logger.error("coder.process_failed", error=str(e))
            metrics["end_time"] = datetime.utcnow().isoformat()
            metrics["error"] = str(e)
            
            return CoderResult(
                success=False,
                changes=[],
                error=str(e),
                metrics=metrics
            )