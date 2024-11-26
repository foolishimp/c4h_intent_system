"""
Standalone code modification tool using the Coder agent.
Path: src/coder4h.py

This module handles configuration loading and bootstrapping,
then passes clean configuration to the Coder agent.
"""

import argparse
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
import structlog
import json
from pydantic import BaseModel

from src.agents.coder import Coder
from src.agents.base import LLMProvider, AgentResponse

logger = structlog.get_logger()

class CoderConfig(BaseModel):
    """External configuration format for the CLI tool"""
    # LLM Configuration
    provider: str = "anthropic"
    model: str = "claude-3-opus-20240229"
    temperature: float = 0
    env_var: str = "ANTHROPIC_API_KEY"
    api_base: str = "https://api.anthropic.com"
    
    # Project Configuration
    project_path: str
    input_data: str
    instruction: str
    format: str = "json"
    merge_method: str = "smart"

def create_agent_config(config: CoderConfig) -> Dict[str, Any]:
    """Convert CLI config into clean agent configuration"""
    return {
        'providers': {
            config.provider: {
                'api_base': config.api_base,
                'env_var': config.env_var
            }
        },
        'project_path': str(Path(config.project_path))
    }

def create_change_request(config: CoderConfig) -> Dict[str, Any]:
    """Create a clean change request for the agent"""
    return {
        "input": config.input_data,
        "instruction": config.instruction,
        "format": config.format,
        "merge_method": config.merge_method
    }

def process_changes(config: CoderConfig) -> None:
    """Process code changes using the Coder agent"""
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
        
        # Create clean agent config and initialize agent
        agent_config = create_agent_config(config)
        coder = Coder(
            provider=LLMProvider(config.provider),
            model=config.model,
            temperature=config.temperature,
            config=agent_config
        )
        
        # Create clean change request
        change_request = create_change_request(config)
        
        print_section("PROCESSING CHANGES", "")
        
        # Process changes through the agent
        result = coder.process(change_request)
        handle_agent_response(result)
            
    except Exception as e:
        logger.error("processing_failed", error=str(e))
        raise

def handle_agent_response(result: AgentResponse) -> None:
    """Handle the agent's response"""
    if result.success:
        print_section("RESULTS", result.data)
        
        # Show detailed changes if available
        if 'changes' in result.data:
            for i, change in enumerate(result.data['changes'], 1):
                print(f"\nChange {i}:")
                print("-" * 40)
                print(json.dumps(change, indent=2))
    else:
        print_section("ERROR", result.error)

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
        description="Process code changes using the Coder agent"
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