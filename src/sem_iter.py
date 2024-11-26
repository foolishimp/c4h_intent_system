"""
Command-line tool for testing semantic iterator functionality.
Path: src/sem_iter.py
"""

import argparse
import asyncio
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
import structlog
from dataclasses import dataclass
import json
from enum import Enum
from pydantic import BaseModel

from src.skills.semantic_iterator import SemanticIterator, ExtractionMode
from src.skills.shared.types import ExtractConfig

logger = structlog.get_logger()

class IteratorConfig(BaseModel):
    """Configuration for semantic iterator"""
    provider: str = "anthropic"
    model: str = "claude-3-opus-20240229"
    temperature: float = 0
    env_var: str = "ANTHROPIC_API_KEY"
    api_base: str = "https://api.anthropic.com"
    
    input_data: str
    instruction: str
    format: str = "json"

def print_section(title: str, content: Any) -> None:
    """Print a section with clear formatting"""
    print("\n" + "="*80)
    print(f" {title} ".center(80, "="))
    print("="*80)
    
    if isinstance(content, (dict, list)):
        print(json.dumps(content, indent=2))
    else:
        print(content)
    print("="*80 + "\n")

def process_items(config: IteratorConfig, mode: ExtractionMode) -> None:
    """Process items using semantic iterator"""
    try:
        # Print configuration sections
        print_section("CONFIGURATION", {
            "provider": config.provider,
            "model": config.model,
            "temperature": config.temperature,
            "extraction_mode": mode.value
        })
        
        print_section("INPUT DATA", config.input_data)
        print_section("EXTRACTION PROMPT", config.instruction)
        
        # Initialize iterator
        """Process items using semantic iterator"""
        iterator = SemanticIterator(
            provider=config.provider,
            model=config.model,
            temperature=config.temperature,
            config={
                'providers': {
                    config.provider: {
                        'api_base': config.api_base,
                        'env_var': config.env_var
                    }
                }
            },
            extraction_modes=[mode.value]
        )
        
        # Create extraction config
        extract_config = ExtractConfig(
            instruction=config.instruction,
            format=config.format
        )
        
        # Process items
        logger.info("starting_extraction", mode=mode.value)
        item_iterator = iterator.iter_extract(config.input_data, extract_config)
        
        # Access state through proper method
        iterator_state = item_iterator.state
        print_section("LLM RAW RESPONSE", iterator_state.raw_response)
        
        if iterator_state.error:
            print_section("EXTRACTION ERROR", iterator_state.error)
        
        # Process items
        print_section("EXTRACTED ITEMS", "")
        items = []
        count = 0

        for item in item_iterator:
            if item:
                count += 1
                print(f"\nITEM {count}:")
                print("-" * 40)
                try:
                    if isinstance(item, str):
                        cleaned = item.strip()
                        if cleaned.startswith('[') and cleaned.endswith(']'):
                            parsed = json.loads(cleaned)[0]
                        else:
                            parsed = json.loads(cleaned)
                        print(json.dumps(parsed, indent=2))
                        items.append(parsed)
                    elif isinstance(item, dict):
                        print(json.dumps(item, indent=2))
                        items.append(item)
                    else:
                        print(str(item))
                        items.append(item)
                except json.JSONDecodeError as e:
                    logger.error("item.json_parse_failed", 
                               item_number=count, 
                               error=str(e),
                               content=str(item))
                    print(f"Failed to parse item {count}: {str(item)}")
                except Exception as e:
                    logger.error("item.processing_failed",
                               item_number=count,
                               error=str(e))
                    print(f"Error processing item {count}: {str(e)}")
        
        # Final state for summary
        final_state = item_iterator.state
        summary = {
            "total_items": len(items),
            "extraction_mode": final_state.current_mode,
            "attempted_modes": [mode.value for mode in final_state.attempted_modes],
            "items": items
        }
        
        print_section("SUMMARY", summary)
                   
    except Exception as e:
        logger.error("processing_failed", error=str(e))
        raise

def load_config(config_path: str) -> IteratorConfig:
    """Load configuration from YAML file"""
    path = Path(config_path)
    if not path.exists():
        raise ValueError(f"Config file not found: {path}")
        
    with open(path) as f:
        data = yaml.safe_load(f)
        return IteratorConfig(**data)

def main() -> None:
    """Main entry point"""
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
        config = load_config(args.config)
        mode = ExtractionMode(args.mode)
        process_items(config, mode)
    except Exception as e:
        logger.error("execution_failed", error=str(e))
        raise

if __name__ == "__main__":
    main()