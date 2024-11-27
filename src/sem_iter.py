"""
Command-line tool for testing semantic iterator functionality.
Path: src/sem_iter.py
"""

import argparse
import yaml
from pathlib import Path
from typing import Dict, Any
import structlog
import asyncio
from dataclasses import dataclass

from src.skills.semantic_iterator import SemanticIterator, ExtractorConfig, ExtractionMode
from src.skills.shared.types import ExtractConfig
from src.agents.base import LLMProvider

logger = structlog.get_logger()

def print_separator(title: str) -> None:
    print("\n" + "="*80)
    print(f" {title} ".center(80, "="))
    print("="*80)

def load_configs(test_config_path: str) -> Dict[str, Any]:
    """Load and merge system and test configurations"""
    try:
        # Load test config
        with open(test_config_path) as f:
            test_config = yaml.safe_load(f)

        # Build provider configuration
        config = {
            'providers': {
                'anthropic': {
                    'api_base': test_config.get('api_base', 'https://api.anthropic.com'),
                    'env_var': test_config.get('env_var', 'ANTHROPIC_API_KEY'),
                    'context_length': 200000
                }
            },
            'llm_config': {
                'default_provider': 'anthropic',
                'default_model': test_config.get('model', 'claude-3-opus-20240229'),
                'agents': {
                    'semantic_iterator': {
                        'provider': 'anthropic',
                        'model': test_config.get('model', 'claude-3-opus-20240229'),
                        'temperature': test_config.get('temperature', 0)
                    },
                    'semantic_fast_extractor': {
                        'provider': 'anthropic',
                        'model': test_config.get('model', 'claude-3-opus-20240229'),
                        'temperature': test_config.get('temperature', 0)
                    },
                    'semantic_slow_extractor': {
                        'provider': 'anthropic',
                        'model': test_config.get('model', 'claude-3-opus-20240229'),
                        'temperature': test_config.get('temperature', 0)
                    }
                }
            }
        }

        # Add test inputs
        config.update({
            'input_data': test_config['input_data'],
            'instruction': test_config['instruction'],
            'format': test_config.get('format', 'json'),
            'extractor_config': test_config.get('extractor_config', {})
        })

        return config

    except Exception as e:
        logger.error("config.load_failed", error=str(e))
        raise

async def process_items(config_path: str, mode: str) -> None:
    """Process items using semantic iterator"""
    try:
        # Load configuration
        config = load_configs(config_path)
        
        # Print test setup
        print_separator("TEST CONFIGURATION")
        print(f"Config File: {config_path}")
        print(f"Mode: {mode}")
        
        print_separator("INPUT DATA")
        print(config["input_data"])
        
        print_separator("EXTRACTION PROMPT") 
        print(config["instruction"])

        # Create extractor configuration
        extractor_config = ExtractorConfig(
            initial_mode=ExtractionMode(mode),
            allow_fallback=config.get("extractor_config", {}).get("allow_fallback", True),
            fallback_modes=[ExtractionMode(m) for m in 
                          config.get("extractor_config", {}).get("fallback_modes", [])]
        )

        # Initialize iterator
        iterator = SemanticIterator(
            provider=LLMProvider(config['llm_config']['default_provider']),
            model=config['llm_config']['default_model'],
            temperature=config['llm_config']['agents']['semantic_iterator']['temperature'],
            config=config,
            extractor_config=extractor_config
        )

        # Create extraction config
        extract_config = ExtractConfig(
            instruction=config["instruction"],
            format=config.get("format", "json")
        )

        # Get items
        print_separator("EXTRACTED ITEMS")
        item_iterator = await iterator.iter_extract(config["input_data"], extract_config)
        
        count = 0
        async for item in item_iterator:
            if item:
                count += 1
                print(f"\nItem {count}:")
                print("-" * 40)
                print(item)

        if count == 0:
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
    
    args = parser.parse_args()
    
    try:
        asyncio.run(process_items(args.config, args.mode))
    except Exception as e:
        logger.error("execution_failed", error=str(e))
        raise

if __name__ == "__main__":
    main()