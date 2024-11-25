"""
Simple command-line tool for testing semantic iterator functionality with mode control.
Path: src/sem_iter.py
"""

import argparse
import asyncio
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
import structlog
from dataclasses import dataclass
from pydantic import BaseModel
import json
from enum import Enum

from skills.semantic_iterator import SemanticIterator, ExtractionMode
from skills.shared.types import ExtractConfig
from agents.base import LLMProvider

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
        # Print input configuration
        print_section("CONFIGURATION", {
            "provider": config.provider,
            "model": config.model,
            "temperature": config.temperature,
            "extraction_mode": mode.value
        })
        
        print_section("INPUT DATA", config.input_data)
        
        # Use instruction directly from config
        print_section("EXTRACTION PROMPT", config.instruction)
        
        # Initialize iterator with single mode
        iterator = SemanticIterator(
            [{
                'provider': config.provider,
                'model': config.model,
                'temperature': config.temperature,
                'config': {
                    'providers': {
                        config.provider: {
                            'api_base': config.api_base,
                            'env_var': config.env_var
                        }
                    }
                }
            }],
            extraction_modes=[mode.value]  # Only use specified mode
        )
        
        # Create extraction config
        extract_config = ExtractConfig(
            instruction=config.instruction,
            format=config.format
        )
        
        # Process items
        logger.info("starting_extraction", mode=mode.value)
        result = iterator.iter_extract(config.input_data, extract_config)
        
        # Get extraction state for debugging
        state = result.get_state()
        print_section("LLM RAW RESPONSE", state.raw_response)
        
        # Display any errors
        if state.error:
            print_section("EXTRACTION ERROR", state.error)
        
        # Process items
        print_section("EXTRACTED ITEMS", "")
        items = []
        count = 0

        # Iterate and process each item
        for item in result:
            if item:  # Guard against None items
                count += 1
                print(f"\nITEM {count}:")
                print("-" * 40)
                try:
                    if isinstance(item, str):
                        # Handle string responses
                        cleaned = item.strip()
                        # Handle array or object JSON
                        if cleaned.startswith('[') and cleaned.endswith(']'):
                            parsed = json.loads(cleaned)[0]  # Get first item from array
                        else:
                            parsed = json.loads(cleaned)
                        print(json.dumps(parsed, indent=2))
                        items.append(parsed)
                    elif isinstance(item, dict):
                        # Already parsed dictionary
                        print(json.dumps(item, indent=2))
                        items.append(item)
                    else:
                        # Unknown format - print as is
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
        
        # Print summary with processed items
        summary = {
            "total_items": len(items),
            "extraction_mode": state.current_mode,
            "attempted_modes": [mode.value for mode in state.attempted_modes],
            "items": items  # Include parsed items in summary
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