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

from agents.base import BaseAgent, LLMProvider, AgentResponse
from skills.semantic_merge import SemanticMerge
from skills.semantic_iterator import SemanticIterator
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
    data: Optional[Dict[str, Any]] = None  # Add data field for test harness compatibility

class Coder(BaseAgent):
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize coder with configuration"""
        super().__init__(config=config)
        
        # Initialize backup location
        backup_path = Path(config.get('backup', {}).get('path', 'workspaces/backups')) if config else None
        
        # Create semantic tools - pass through same config 
        self.iterator = SemanticIterator(config=config)
        merger = SemanticMerge(config=config)
        
        # Setup asset management
        self.asset_manager = AssetManager(
            backup_enabled=True,
            backup_dir=backup_path,
            merger=merger
        )

        logger.info("coder.config", config=json.dumps(config, indent=2) if config else None)

    def _get_agent_name(self) -> str:
        return "coder"

    def process(self, context: Dict[str, Any]) -> CoderResult:
        """Process code changes using semantic iterator"""
        logger.info("coder.process_start", context=json.dumps(context, indent=2))
        metrics = {"start_time": datetime.utcnow().isoformat()}
        changes = []

        try:
            # Configure iterator with complete input and extraction config
            extract_config = ExtractConfig(
                instruction="""Extract all code change actions from the input.
                            Look for file_path, type, content/diff, and description.
                            Handle any input format including raw LLM responses.""",
                format="json"
            )

            # Pass complete context to iterator
            self.iterator.configure(context.get('input_data'), extract_config)
            logger.info("coder.iterator_configured")

            # Process changes using iterator
            results = []
            for change in self.iterator:
                logger.debug("coder.extracted_change", change=json.dumps(change, indent=2))

                if not isinstance(change, dict):
                    logger.warning("coder.invalid_change_format", 
                                change_type=type(change).__name__)
                    continue

                # Validate minimum required fields
                required_fields = ['file_path', 'type']
                if not all(field in change for field in required_fields):
                    logger.warning("coder.missing_required_fields",
                                change=change,
                                required=required_fields)
                    continue

                # Process the change
                logger.info("coder.processing_change",
                        file_path=change.get('file_path'),
                        change_type=change.get('type'))

                result = self.asset_manager.process_action(change)
                
                logger.info("coder.change_result",
                        success=result.success,
                        file_path=str(result.path),
                        error=result.error if not result.success else None)

                changes.append(result)
                # Store complete result information
                results.append({
                    "file": str(result.path),
                    "type": change.get('type'),
                    "description": change.get('description'),
                    "success": result.success,
                    "error": result.error,
                    "backup": str(result.backup_path) if result.backup_path else None
                })

            # Calculate success and metrics
            success = any(c.success for c in changes)
            metrics["end_time"] = datetime.utcnow().isoformat()
            metrics["total_changes"] = len(changes)
            metrics["successful_changes"] = sum(1 for c in changes if c.success)

            logger.info("coder.process_complete",
                    success=success,
                    total_changes=len(changes),
                    successful_changes=metrics["successful_changes"],
                    metrics=metrics)

            return CoderResult(
                success=success,
                changes=changes,
                error=None if success else "All changes failed",
                metrics=metrics,
                data={
                    "changes": results,
                    "metrics": metrics,
                    "success": success,
                    "total": len(changes),
                    "successful": metrics["successful_changes"]
                }
            )

        except Exception as e:
            logger.error("coder.process_failed", error=str(e))
            metrics["end_time"] = datetime.utcnow().isoformat()
            metrics["error"] = str(e)
            return CoderResult(
                success=False,
                changes=changes,
                error=str(e),
                metrics=metrics,
                data={"error": str(e), "metrics": metrics}
            )