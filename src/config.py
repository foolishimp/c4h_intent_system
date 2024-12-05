"""
Configuration handling with robust dictionary merging and comprehensive logging.
Path: src/config.py
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional
import structlog
from copy import deepcopy
import collections.abc

logger = structlog.get_logger()

def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep merge dictionaries with clear precedence rules and logging.
    
    Rules:
    1. Override values take precedence over base values
    2. Dictionaries are merged recursively
    3. Lists from override replace lists from base
    4. None values in override delete keys from base
    5. Path objects are converted to strings for consistency
    
    Args:
        base: Base configuration dictionary
        override: Override configuration dictionary
    
    Returns:
        Merged configuration dictionary
    """
    result = deepcopy(base)
    
    try:
        for key, value in override.items():
            # Log each override attempt at debug level
            logger.debug(
                "config.merge.processing_key",
                key=key,
                override_type=type(value).__name__,
                base_type=type(result.get(key)).__name__ if key in result else None
            )
            
            # None deletes keys
            if value is None:
                if key in result:
                    logger.debug("config.merge.deleting_key", key=key)
                    result.pop(key, None)
                continue
                
            # Key not in base, just set it
            if key not in result:
                logger.debug("config.merge.adding_new_key", key=key)
                result[key] = deepcopy(value)
                continue
                
            # Handle different types
            if isinstance(value, collections.abc.Mapping):
                # Recursive merge for dictionaries
                logger.debug("config.merge.recursive_merge", key=key)
                result[key] = deep_merge(result[key], value)
            elif isinstance(value, Path):
                # Convert paths to strings
                logger.debug("config.merge.converting_path", key=key)
                result[key] = str(value)
            elif isinstance(value, list):
                # Lists replace rather than merge
                logger.debug("config.merge.replacing_list", key=key)
                result[key] = deepcopy(value)
            else:
                # Simple values replace
                logger.debug("config.merge.replacing_value", 
                           key=key,
                           old_value=result[key],
                           new_value=value)
                result[key] = deepcopy(value)
            
        return result

    except Exception as e:
        logger.error("config.merge.failed", 
                    error=str(e),
                    error_type=type(e).__name__,
                    keys_processed=list(override.keys()))
        raise

def load_config(path: Path) -> Dict[str, Any]:
    """Load configuration from YAML file with comprehensive logging"""
    try:
        logger.info("config.load.starting", path=str(path))
        
        if not path.exists():
            logger.error("config.load.file_not_found", path=str(path))
            return {}
            
        with open(path) as f:
            config = yaml.safe_load(f) or {}
            
        logger.info("config.load.success",
                   path=str(path),
                   keys=list(config.keys()),
                   size=len(str(config)))
                   
        return config
        
    except yaml.YAMLError as e:
        logger.error("config.load.yaml_error",
                    path=str(path),
                    error=str(e),
                    line=getattr(e, 'line', None),
                    column=getattr(e, 'column', None))
        return {}
    except Exception as e:
        logger.error("config.load.failed",
                    path=str(path),
                    error=str(e),
                    error_type=type(e).__name__)
        return {}

def load_with_app_config(system_path: Path, app_path: Path) -> Dict[str, Any]:
    """Load and merge system config with app config with full logging"""
    try:
        logger.info("config.merge.starting",
                   system_path=str(system_path),
                   app_path=str(app_path))
        
        system_config = load_config(system_path)
        app_config = load_config(app_path)
        
        result = deep_merge(system_config, app_config)
        
        logger.info("config.merge.complete",
                   total_keys=len(result),
                   system_keys=len(system_config),
                   app_keys=len(app_config))
        
        return result
        
    except Exception as e:
        logger.error("config.merge.failed",
                    error=str(e),
                    error_type=type(e).__name__)
        return {}