"""
Command-line tool for testing semantic iterator functionality.
Path: src/sem_iter.py
"""

import argparse
import yaml
from pathlib import Path
from typing import Dict, Any
import structlog
from dataclasses import dataclass
import logging.config
from enum import Enum

from skills.semantic_iterator import SemanticIterator, ExtractorConfig, ExtractionMode
from skills.shared.types import ExtractConfig
from agents.base import LLMProvider

# Configure structured logging with different processors for debug/normal modes
class LogMode(str, Enum):
    DEBUG = "debug"
    NORMAL = "normal"

def setup_logging(mode: LogMode = LogMode.NORMAL) -> None:
    """Configure structured logging based on mode"""
    processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    
    if mode == LogMode.DEBUG:
        processors.extend([
            structlog.processors.dict_tracebacks,
            structlog.dev.ConsoleRenderer(colors=True, exception_formatter=structlog.dev.exception_formatter)
        ])
    else:
        processors.append(
            structlog.processors.JSONRenderer(indent=None)
        )

    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure standard logging
    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': False,
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'level': 'DEBUG' if mode == LogMode.DEBUG else 'INFO',
            },
        },
        'root': {
            'handlers': ['console'],
            'level': 'DEBUG' if mode == LogMode.DEBUG else 'INFO',
        }
    })

logger = structlog.get_logger()

def print_separator(title: str) -> None:
    print(f" {title} ".center(80, "="))

def load_configs(test_config_path: str) -> Dict[str, Any]:
    """Load and merge system and test configurations"""
    try:
        # Load system config first
        system_config_path = Path("config/system_config.yml")
        if not system_config_path.exists():
            raise ValueError(f"System configuration not found at {system_config_path}")
            
        with open(system_config_path) as f:
            config = yaml.safe_load(f)
            logger.debug("system_config.loaded", 
                      config_keys=list(config.keys()),
                      agent_configs=list(config.get('llm_config', {}).get('agents', {}).keys()) if config.get('llm_config') else None)
            
        # Load test specific config
        with open(test_config_path) as f:
            test_config = yaml.safe_load(f)

        # Add test-specific items while preserving system config structure
        config.update({
            'input_data': test_config['input_data'],
            'instruction': test_config['instruction'],
            'format': test_config.get('format', 'json'),
            'extractor_config': test_config.get('extractor_config', {})
        })
        
        logger.debug("final_config.ready",
                  config_keys=list(config.keys()),
                  agent_configs=list(config.get('llm_config', {}).get('agents', {}).keys()) if config.get('llm_config') else None)

        return config

    except Exception as e:
        logger.error("config.load_failed", error=str(e))
        raise

def process_items(config_path: str, mode: str, log_mode: LogMode) -> None:
    """Process and display items using semantic iterator"""
    try:
        setup_logging(log_mode)
        
        # Load configuration
        config = load_configs(config_path)
        
        # Create both configs first
        extractor_config = ExtractorConfig(
            initial_mode=ExtractionMode(mode),
            allow_fallback=True,
            fallback_modes=[ExtractionMode.SLOW] if mode == "fast" else []
        )

        extract_config = ExtractConfig(
            instruction=config["instruction"],
            format=config.get("format", "json")
        )
        
        if log_mode == LogMode.DEBUG:
            logger.debug("process_items.config_loaded",
                        config_keys=list(config.keys()),
                        has_providers=bool(config.get('providers')),
                        has_llm_config=bool(config.get('llm_config')),
                        provider_keys=list(config.get('providers', {}).keys()))
        
        # Print test setup
        print_separator("TEST CONFIGURATION")
        print(f"Config File: {config_path}")
        print(f"Mode: {mode}")
        
        print_separator("INPUT DATA")
        print(config["input_data"])
        
        print_separator("EXTRACTION PROMPT") 
        print(config["instruction"])

        # Get settings from config
        llm_config = config.get('llm_config', {})
        provider = LLMProvider(llm_config.get('default_provider', 'anthropic'))
        model = llm_config.get('default_model', 'claude-3-opus-20240229')

        # Initialize iterator with complete config
        iterator = SemanticIterator(
            provider=provider,
            model=model,
            temperature=0,
            config=config,  # Pass complete config
            extractor_config=extractor_config
        )

        # Configure the iterator
        iterator.configure(config["input_data"], extract_config)

        # Get items using standard iterator interface
        print_separator("EXTRACTED ITEMS")
        item_count = 0
        for item in iterator:
            if item:
                item_count += 1
                # Always log item count and content at INFO level
                logger.info(f"item.extracted", 
                          item_number=item_count,
                          content=item)
                print(f"\nItem {item_count}:")
                print("-" * 40)
                print(item)

        if item_count == 0:
            logger.warning("extraction.no_items")
            print("\nNo items extracted")

    except Exception as e:
        logger.error("process.failed", error=str(e))
        raise

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test semantic iterator functionality"
    )
    parser.add_argument(
        "config", 
        help="Path to YAML config file"
    )
    parser.add_argument(
        "--mode",
        choices=["fast", "slow"],
        default="fast",
        help="Extraction mode to use (default: fast)"
    )
    parser.add_argument(
        "--log-mode",
        type=LogMode,
        choices=list(LogMode),
        default=LogMode.NORMAL,
        help="Logging mode (default: normal)"
    )
    
    args = parser.parse_args()
    
    try:
        process_items(args.config, args.mode, args.log_mode)
    except Exception as e:
        logger.error("execution_failed", error=str(e))
        raise

if __name__ == "__main__":
    main()
