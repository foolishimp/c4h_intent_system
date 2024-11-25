"""
Standalone code modification tool using semantic models.
Path: src/coder4h.py
"""

import argparse
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
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
    
    project_path: str
    input_data: str
    instruction: str
    format: str = "json"
    merge_method: str = "smart"

def process_changes(config: CoderConfig) -> None:
    """Process code changes using semantic coder"""
    try:
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
        
        # Initialize components
        llm_config = {
            'providers': {
                config.provider: {
                    'api_base': config.api_base,
                    'env_var': config.env_var
                }
            },
            'project_path': str(project_path)
        }
        
        iterator = SemanticIterator(
            [{
                'provider': config.provider,
                'model': config.model,
                'temperature': config.temperature,
                'config': llm_config
            }]
        )
        
        coder = Coder(
            provider=LLMProvider(config.provider),
            model=config.model,
            temperature=config.temperature,
            config=llm_config
        )
        
        # Extract changes
        extract_config = ExtractConfig(
            instruction=config.instruction,
            format=config.format
        )
        
        print_section("EXTRACTING CHANGES", "")
        
        # Use iterator synchronously
        change_iter = iterator.iter_extract(config.input_data, extract_config)
        changes = []
        
        # Collect changes
        for change in change_iter:
            if change:
                # Resolve file path relative to project path
                file_path = change.get('file_path', '')
                if not file_path.startswith(str(project_path)):
                    relative_path = file_path.replace('tests/test_projects/project1/', '')
                    change['file_path'] = str(project_path / relative_path)
                changes.append(change)
        
        print_section("FOUND CHANGES", changes)
        
        if not changes:
            print("No changes to process")
            return
            
        # Process changes
        print_section("APPLYING CHANGES", "")
        
        for i, change in enumerate(changes, 1):
            print(f"\nChange {i}:")
            print("-" * 40)
            print(json.dumps(change, indent=2))
            
        result = coder.process({"changes": changes})
        print_section("RESULTS", result.data)
            
    except Exception as e:
        logger.error("processing_failed", error=str(e))
        raise

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
        process_changes(config)
    except Exception as e:
        logger.error("execution_failed", error=str(e))
        raise

if __name__ == "__main__":
    main()