"""
Standalone code modification tool using semantic models.
Path: src/coder4h.py
"""

import argparse
import asyncio
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
import structlog
from dataclasses import dataclass
import json
from pydantic import BaseModel

from src.agents.coder import Coder, MergeMethod
from src.skills.semantic_iterator import SemanticIterator, ExtractionMode
from src.skills.shared.types import ExtractConfig
from src.agents.base import LLMProvider

logger = structlog.get_logger()

class CoderConfig(BaseModel):
    """Configuration for coder execution"""
    provider: str = "anthropic"
    model: str = "claude-3-opus-20240229"
    temperature: float = 0
    env_var: str = "ANTHROPIC_API_KEY"
    api_base: str = "https://api.anthropic.com"
    
    # Project configuration
    project_path: str  # Base path for resolving file locations
    
    # Code change configuration
    input_data: str  # Code changes to apply
    instruction: str  # How to parse the changes
    format: str = "json"
    merge_method: str = "smart"

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

async def process_changes(config: CoderConfig) -> None:
    """Process code changes using semantic coder"""
    try:
        # Verify project path exists
        project_path = Path(config.project_path)
        if not project_path.exists():
            raise ValueError(f"Project path does not exist: {project_path}")
            
        print_section("CONFIGURATION", {
            "provider": config.provider,
            "model": config.model,
            "temperature": config.temperature,
            "merge_method": config.merge_method,
            "project_path": str(project_path)
        })
        
        print_section("INPUT DATA", config.input_data)
        print_section("CHANGE INSTRUCTIONS", config.instruction)
        
        # Initialize coder with project path
        coder = Coder(
            provider=LLMProvider(config.provider),
            model=config.model,
            temperature=config.temperature,
            config={
                'providers': {
                    config.provider: {
                        'api_base': config.api_base,
                        'env_var': config.env_var
                    }
                },
                'project_path': str(project_path)  # Pass project path to coder
            }
        )
        
        # Initialize iterator
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
            extraction_modes=[ExtractionMode.FAST.value]
        )
        
        # Extract changes
        extract_config = ExtractConfig(
            instruction=config.instruction,
            format=config.format
        )
        
        change_iterator = iterator.iter_extract(config.input_data, extract_config)
        
        # Process changes
        print_section("PROCESSING CHANGES", "")
        
        changes = []
        count = 0
        
        # Collect changes first
        for change in change_iterator:
            if change:
                count += 1
                print(f"\nCHANGE {count}:")
                print("-" * 40)
                
                # Resolve file path relative to project path
                file_path = change.get('file_path', '')
                if not file_path.startswith(str(project_path)):
                    change['file_path'] = str(project_path / file_path)
                    
                print(json.dumps(change, indent=2))
                changes.append(change)
                
        # Apply changes using coder
        if changes:
            result = await coder.process({"changes": changes})
            print_section("RESULTS", result.data)
        else:
            print("No changes to process")
            
    except Exception as e:
        logger.error("processing_failed", error=str(e))
        raise

def load_config(config_path: str) -> CoderConfig:
    """Load configuration from YAML file"""
    path = Path(config_path)
    if not path.exists():
        raise ValueError(f"Config file not found: {path}")
        
    with open(path) as f:
        data = yaml.safe_load(f)
        return CoderConfig(**data)

def main() -> None:
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Process code changes using semantic coder"
    )
    parser.add_argument(
        "config", 
        help="Path to YAML config file"
    )
    
    args = parser.parse_args()
    
    try:
        config = load_config(args.config)
        asyncio.run(process_changes(config))
    except Exception as e:
        logger.error("execution_failed", error=str(e))
        raise

if __name__ == "__main__":
    main()