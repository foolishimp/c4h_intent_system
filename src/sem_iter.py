"""
Command-line tool for testing semantic iterator functionality.
Path: src/sem_iter.py
"""

import argparse
import yaml
from pathlib import Path
from typing import Dict, Any
import structlog
from enum import Enum

logger = structlog.get_logger()

class ExtractionMode(str, Enum):
    """Available extraction modes"""
    FAST = "fast"
    SLOW = "slow"

def print_separator(title: str) -> None:
    print("\n" + "="*80)
    print(f" {title} ".center(80, "="))
    print("="*80)

def load_configs(test_config_path: str) -> Dict[str, Any]:
    """Load and merge system and test configurations"""
    # Load system config first
    system_config_path = Path("config/system_config.yml")
    try:
        with open(system_config_path) as f:
            system_config = yaml.safe_load(f)
    except Exception as e:
        logger.error("system_config.load_failed", error=str(e))
        raise

    # Load test config
    with open(test_config_path) as f:
        test_config = yaml.safe_load(f)

    # Merge configurations
    config = {
        'providers': system_config['providers'],
        'llm_config': system_config['llm_config'],
        # Add test-specific settings
        'provider': test_config['provider'],
        'model': test_config['model'],
        'temperature': test_config['temperature'],
        'env_var': test_config['env_var'],
        'api_base': test_config['api_base'],
        'input_data': test_config['input_data'],
        'instruction': test_config['instruction'],
        'format': test_config['format']
    }

    return config

def process_items(config_path: str, mode: str) -> None:
    """Process items using semantic iterator"""
    try:
        # Late import to avoid cycles
        from src.skills.semantic_iterator import SemanticIterator
        from src.skills.shared.types import ExtractConfig
        from src.agents.base import LLMProvider

        # Load merged configuration
        config = load_configs(config_path)

        # Print test setup
        print_separator("TEST CONFIGURATION")
        print(f"Config File: {config_path}")
        print(f"Mode: {mode}")
        
        print_separator("INPUT DATA")
        print(config["input_data"])
        
        print_separator("EXTRACTION PROMPT") 
        print(config["instruction"])

        # Initialize iterator with full config
        iterator = SemanticIterator(
            provider=LLMProvider(config["provider"]),
            model=config["model"],
            temperature=config["temperature"],
            config=config,  # Now includes both system and test config
            extraction_modes=[mode]
        )

        # Create extraction config
        extract_config = ExtractConfig(
            instruction=config["instruction"],
            format=config["format"]
        )

        # Get items
        print_separator("EXTRACTED ITEMS")
        item_iterator = iterator.iter_extract(config["input_data"], extract_config)
        
        count = 0
        for item in item_iterator:
            if item:
                count += 1
                print(f"\nItem {count}:")
                print("-" * 40)
                print(item)

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
    
    args = parser.parse_args()
    
    try:
        process_items(args.config, args.mode)
    except Exception as e:
        logger.error("execution_failed", error=str(e))
        raise

if __name__ == "__main__":
    main()