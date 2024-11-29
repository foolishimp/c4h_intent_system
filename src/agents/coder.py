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
from src.skills.asset_manager import AssetManager, AssetChange

logger = structlog.get_logger()

@dataclass
class ChangeResult:
    """Result of a single change operation"""
    path: str
    success: bool
    backup_path: Optional[str] = None
    error: Optional[str] = None

@dataclass
class CoderResult:
    """Result of code processing"""
    success: bool
    changes: List[ChangeResult]
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
        self.config = config
        
        # Initialize skills
        self.iterator = SemanticIterator(
            provider=config['provider'],
            model=config['model'],
            config=config
        )
        
        self.merger = SemanticMerge(
            provider=config['provider'],
            model=config['model'],
            config=config,
            merge_config=MergeConfig(
                style=config.get('merge_style', 'smart'),
                preserve_formatting=True
            )
        )
        
        self.asset_manager = AssetManager(
            backup_enabled=config.get('backup_enabled', True),
            backup_dir=Path(config['backup_dir']) if config.get('backup_dir') else None
        )
        
        logger.info("coder.initialized",
                   provider=config['provider'],
                   model=config['model'])

    def process(self, input_data: str, description: str) -> CoderResult:
        """Process asset modifications.
        
        Args:
            input_data: Input containing changes to process
            description: Description of how to extract changes
            
        Returns:
            CoderResult with success status and changes
        """
        try:
            # Configure extraction
            extract_config = ExtractConfig(
                instruction=description,
                format="json"
            )
            
            changes: List[ChangeResult] = []
            
            # Extract and process changes
            for item in self.iterator.extract_all(input_data, extract_config):
                try:
                    # Validate required fields
                    if not item.get('file_path') or not (item.get('content') or item.get('diff')):
                        logger.warning("invalid_change_format", item=item)
                        continue

                    path = Path(item['file_path'])
                    
                    # Get original content
                    original = self.asset_manager.read_asset(path)
                    
                    # Merge changes
                    merge_result = self.merger.merge(
                        original,
                        item.get('content', item.get('diff'))
                    )
                    
                    if merge_result.success:
                        # Apply merged changes
                        asset_change = AssetChange(
                            path=path,
                            content=merge_result.content
                        )
                        
                        success = self.asset_manager.write_change(asset_change)
                        
                        changes.append(ChangeResult(
                            path=str(path),
                            success=success,
                            backup_path=str(asset_change.backup_path) if asset_change.backup_path else None
                        ))
                    else:
                        changes.append(ChangeResult(
                            path=str(path),
                            success=False,
                            error=merge_result.error
                        ))
                        
                except Exception as e:
                    logger.error("change_failed",
                               path=str(item.get('file_path')),
                               error=str(e))
                    changes.append(ChangeResult(
                        path=str(item.get('file_path', 'unknown')),
                        success=False,
                        error=str(e)
                    ))

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