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

from agents.base import BaseAgent, AgentResponse
from skills.semantic_merge import SemanticMerge
from skills.semantic_iterator import SemanticIterator
from skills.asset_manager import AssetManager, AssetResult
from skills.shared.types import ExtractConfig
from config import locate_config

logger = structlog.get_logger()

@dataclass
class CoderMetrics:
    """Detailed metrics for code processing operations"""
    total_changes: int = 0
    successful_changes: int = 0
    failed_changes: int = 0
    start_time: str = ""
    end_time: str = ""
    processing_time: float = 0.0
    error_count: int = 0

class Coder(BaseAgent):
    """Handles code modifications using semantic processing"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize coder with configuration"""
        super().__init__(config=config)
        
        # Get coder-specific config using locate_config pattern
        coder_config = locate_config(self.config or {}, self._get_agent_name())
        
        # Initialize backup location from config
        backup_path = Path(coder_config.get('backup', {}).get('path', 'workspaces/backups'))
        
        # Create semantic tools with same config inheritance
        self.iterator = SemanticIterator(config=config)
        self.merger = SemanticMerge(config=config)
        
        # Setup asset management with inherited config
        self.asset_manager = AssetManager(
            backup_enabled=coder_config.get('backup_enabled', True),
            backup_dir=backup_path,
            merger=self.merger,
            config=config
        )
        
        # Initialize metrics
        self.operation_metrics = CoderMetrics()
        
        logger.info("coder.initialized",
                   backup_path=str(backup_path),
                   config=json.dumps(coder_config, indent=2) if coder_config else None)

    def _get_agent_name(self) -> str:
        """Get agent name for config lookup"""
        return "coder"

    """
    Primary coder agent implementation for processing code changes.
    Path: src/agents/coder.py
    """

    def process(self, context: Dict[str, Any]) -> AgentResponse:
        """Process code changes using semantic iterator"""
        logger.info("coder.process_start", context=json.dumps(context, indent=2))
        self.operation_metrics = CoderMetrics(
            start_time=datetime.utcnow().isoformat()
        )
        changes: List[AssetResult] = []

        try:
            # Handle different input formats:
            # 1. Direct content in context
            # 2. Nested in input_data
            if all(k in context for k in ['content', 'file_path', 'type']):
                input_data = context
            else:
                input_data = context.get('input_data')
                if not input_data:
                    raise ValueError("No input data provided")

            # Configure iterator with extraction settings
            extract_config = ExtractConfig(
                instruction="""Extract all code change actions from the input.
                            Look for file_path, type, content/diff, and description.
                            Handle any input format including raw LLM responses.""",
                format="json"
            )
            
            # Configure iterator with prepared data
            self.iterator.configure(input_data, extract_config)
            logger.info("coder.iterator_configured")

            # Process each change using iterator
            for change in self.iterator:
                logger.debug("coder.extracted_change", 
                        change=json.dumps(change, indent=2))

                if not isinstance(change, dict):
                    logger.warning("coder.invalid_change_format",
                                change_type=type(change).__name__)
                    continue

                # Process the change
                logger.info("coder.processing_change",
                        file_path=change.get('file_path'),
                        change_type=change.get('type'))

                result = self.asset_manager.process_action(change)
                
                # Update metrics
                self.operation_metrics.total_changes += 1
                if result.success:
                    self.operation_metrics.successful_changes += 1
                else:
                    self.operation_metrics.failed_changes += 1
                    self.operation_metrics.error_count += 1

                logger.info("coder.change_result",
                        success=result.success,
                        file_path=str(result.path),
                        error=result.error if not result.success else None)

                changes.append(result)

            # Calculate overall success
            success = any(result.success for result in changes)

            # Return response with all results 
            return AgentResponse(
                success=success,
                data={
                    "changes": [
                        {
                            "file": str(result.path),
                            "success": result.success,
                            "error": result.error,
                            "backup": str(result.backup_path) if result.backup_path else None
                        }
                        for result in changes
                    ],
                    "metrics": self.operation_metrics.__dict__
                },
                error=None if success else "No changes were successful"
            )

        except Exception as e:
            logger.error("coder.process_failed", error=str(e))
            return AgentResponse(
                success=False,
                data={
                    "changes": [],
                    "metrics": self.operation_metrics.__dict__
                },
                error=str(e)
            )