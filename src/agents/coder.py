"""
Coder orchestrator for managing semantic operations on assets.
Path: src/agents/coder.py
"""

from typing import Dict, Any, List, Optional
from pathlib import Path
from dataclasses import dataclass
import structlog
from src.skills.semantic_iterator import SemanticIterator, ExtractConfig
from src.skills.semantic_merge import SemanticMerge, MergeConfig
from src.skills.asset_manager import AssetManager, AssetResult

logger = structlog.get_logger()

@dataclass
class CoderResult:
    """Result of code processing"""
    success: bool
    changes: List[AssetResult]
    error: Optional[str] = None

class Coder:
    """Orchestrates semantic operations on code assets"""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize with configuration dictionary.
        
        Args:
            config: Configuration including:
                - provider: LLM provider
                - model: Model name
                - merge_style: Merge strategy
                - backup_enabled: Whether to create backups
                - backup_dir: Optional backup directory
        """
        # Initialize semantic tools
        self.iterator = SemanticIterator(
            provider=config['provider'],
            model=config['model'],
            config=config
        )
        
        merger = SemanticMerge(
            provider=config['provider'],
            model=config['model'],
            config=config,
            merge_config=MergeConfig(
                style=config.get('merge_style', 'smart'),
                preserve_formatting=True
            )
        )
        
        # Initialize asset manager with merger
        self.asset_manager = AssetManager(
            backup_enabled=config.get('backup_enabled', True),
            backup_dir=Path(config['backup_dir']) if config.get('backup_dir') else None,
            merger=merger
        )
        
        logger.info("coder.initialized",
                   provider=config['provider'],
                   model=config['model'])

    def process(self, input_data: str, description: str) -> CoderResult:
        """Process asset modifications.
        
        Args:
            input_data: Input containing changes to process
            description: Description of how to extract changes
        """
        try:
            # Configure extraction
            extract_config = ExtractConfig(
                instruction=description,
                format="json"
            )
            
            changes = []
            
            # Process each action through asset manager
            for action in self.iterator.extract_all(input_data, extract_config):
                result = self.asset_manager.process_action(action)
                changes.append(result)

            # Overall success if any changes succeeded
            success = any(c.success for c in changes)
            return CoderResult(
                success=success,
                changes=changes,
                error=None if success else "All changes failed"
            )

        except Exception as e:
            logger.error("process_failed", error=str(e))
            return CoderResult(
                success=False,
                changes=[],
                error=str(e)
            )