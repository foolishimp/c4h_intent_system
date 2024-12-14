"""
Primary coder agent implementation using semantic extraction.
Path: src/agents/coder.py
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import structlog
from datetime import datetime
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
                   backup_path=str(backup_path))

    def _get_agent_name(self) -> str:
        return "coder"

    def process(self, context: Dict[str, Any]) -> AgentResponse:
        """Process code changes using semantic extraction"""
        logger.info("coder.process_start", context_keys=list(context.keys()))
        self.operation_metrics = CoderMetrics(
            start_time=datetime.utcnow().isoformat()
        )
        changes: List[AssetResult] = []

        try:
            # Configure iterator with raw context - let LLM handle interpretation
            self.iterator.configure(
                context,
                ExtractConfig(
                    instruction=self._get_prompt('system'),
                    format="json"
                )
            )
            
            # Process each action extracted by LLM
            for action in self.iterator:
                if not action:
                    continue

                # Process the action
                result = self.asset_manager.process_action(action)
                
                # Update metrics
                self.operation_metrics.total_changes += 1
                if result.success:
                    self.operation_metrics.successful_changes += 1
                else:
                    self.operation_metrics.failed_changes += 1
                    self.operation_metrics.error_count += 1

                logger.info("coder.action_result",
                        success=result.success,
                        file_path=str(result.path),
                        error=result.error if not result.success else None)

                changes.append(result)

            success = bool(changes) and any(result.success for result in changes)
            
            self.operation_metrics.end_time = datetime.utcnow().isoformat()

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