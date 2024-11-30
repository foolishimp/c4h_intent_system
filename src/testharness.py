"""
Generic test harness for running agent classes with configuration.
Path: src/testharness.py
"""

import argparse
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Type
import structlog
from enum import Enum
import logging.config
from dataclasses import dataclass
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import json

from agents.base import BaseAgent, LLMProvider
from agents.coder import Coder
from skills.semantic_iterator import SemanticIterator
from config import SystemConfig
from skills.shared.types import ExtractConfig

logger = structlog.get_logger()

class LogMode(str, Enum):
    """Logging modes supported by harness"""
    DEBUG = "debug"
    NORMAL = "normal"

def parse_param(param_str: str) -> tuple[str, Any]:
    """Parse a parameter string in format key=value"""
    try:
        key, value = param_str.split('=', 1)
        # Try to interpret as Python literal (for bool, int, etc)
        try:
            import ast
            value = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            pass  # Keep as string if not a valid Python literal
        return key.strip(), value
    except ValueError:
        raise ValueError(f"Invalid parameter format: {param_str}. Use key=value format")

@dataclass
class AgentConfig:
    """Configuration for agent instantiation"""
    agent_type: str
    config_path: Path
    extra_args: Dict[str, Any] = None

class AgentTestHarness:
    """Generic test harness for running agent classes"""
    
    # Registry of supported agent types
    AGENT_TYPES = {
        "coder": Coder,
        "semantic_iterator": SemanticIterator
    }

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        
    def setup_logging(self, mode: LogMode = LogMode.NORMAL) -> None:
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
                structlog.dev.ConsoleRenderer(colors=True)
            ])
        else:
            processors.append(structlog.processors.JSONRenderer(indent=2))

        structlog.configure(
            processors=processors,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

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

    def load_configs(self, test_config_path: str) -> Dict[str, Any]:
        """Load and merge system and test configurations"""
        try:
            # Load system config first
            system_config_path = Path("config/system_config.yml")
            if not system_config_path.exists():
                raise ValueError(f"System configuration not found at {system_config_path}")
                
            with open(system_config_path) as f:
                config = yaml.safe_load(f)
                
            # Load test specific config
            with open(test_config_path) as f:
                test_config = yaml.safe_load(f)

            # Add test-specific items while preserving system config structure
            config.update({
                'input_data': test_config.get('input_data'),
                'instruction': test_config.get('instruction'),
                'format': test_config.get('format', 'json'),
                'agent_config': test_config.get('agent_config', {})
            })
            
            return config

        except Exception as e:
            logger.error("config.load_failed", error=str(e))
            raise

    def create_agent(self, agent_type: str, config: Dict[str, Any]) -> BaseAgent:
        """Create agent instance based on type"""
        if agent_type not in self.AGENT_TYPES:
            raise ValueError(f"Unsupported agent type: {agent_type}")
            
        agent_class = self.AGENT_TYPES[agent_type]
        
        # Get agent-specific config
        agent_config = config.get('llm_config', {}).get('agents', {}).get(agent_type, {})
        
        return agent_class(
            provider=LLMProvider(agent_config.get('provider', 'anthropic')),
            model=agent_config.get('model', 'claude-3-opus-20240229'),
            temperature=agent_config.get('temperature', 0),
            config=config
        )

    def process_agent(self, config: AgentConfig) -> None:
        """Process agent with configuration"""
        try:
            # Load configuration
            configs = self.load_configs(str(config.config_path))
            
            # Create agent instance
            agent = self.create_agent(config.agent_type, configs)
            
            # Get any extra parameters passed via command line
            extra_params = config.extra_args or {}
            
            if isinstance(agent, SemanticIterator):
                # Handle iterator case
                self.console.print("[cyan]Processing with semantic iterator...[/]")
                
                # Create extractor config with any overrides
                extract_config = ExtractConfig(
                    instruction=configs.get('instruction'),
                    format=configs.get('format', 'json')
                )
                
                # Add any additional extractor config parameters
                for key, value in extra_params.items():
                    if hasattr(extract_config, key):
                        setattr(extract_config, key, value)
                        logger.info(f"config.override", key=key, value=value)
                
                # Configure the iterator
                agent.configure(
                    content=configs.get('input_data'),
                    config=extract_config
                )
                
                # Collect all items
                results = []
                for item in agent:
                    results.append(item)
                    
                self.display_results(results)
                
            elif isinstance(agent, Coder):
                # Handle coder case
                self.console.print("[cyan]Processing with coder...[/]")
                
                # Build context with any additional parameters
                context = {
                    'input_data': configs.get('input_data'),
                    'instruction': configs.get('instruction'),
                    **extra_params  # Add any extra parameters
                }
                
                result = agent.process(context)
                
                if not result.success:
                    self.console.print(f"[red]Error:[/] {result.error}")
                    return
                    
                self.display_results(result.data)

        except Exception as e:
            logger.error("agent.process_failed", error=str(e))
            raise

    def display_results(self, results: Any) -> None:
        """Display agent processing results"""
        try:
            # If results is a string containing JSON, parse it
            if isinstance(results, str):
                try:
                    parsed = json.loads(results)
                    results = parsed
                except json.JSONDecodeError:
                    pass  # Keep original if not JSON

            if isinstance(results, dict):
                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("Key")
                table.add_column("Value")
                
                for key, value in results.items():
                    table.add_row(str(key), str(value))
                    
                self.console.print(Panel(table, title="Results"))
            elif isinstance(results, list):
                # For each item in list, create a separate panel
                for i, item in enumerate(results, 1):
                    if isinstance(item, dict):
                        table = Table(show_header=True, header_style="bold cyan")
                        table.add_column("Property")
                        table.add_column("Value")
                        
                        for key, value in item.items():
                            formatted_value = (
                                json.dumps(value, indent=2)
                                if isinstance(value, (dict, list))
                                else str(value)
                            )
                            table.add_row(str(key), formatted_value)
                            
                        self.console.print(Panel(table, title=f"Result {i}"))
                    else:
                        self.console.print(Panel(str(item), title=f"Result {i}"))
            else:
                self.console.print(Panel(str(results), title="Results"))

        except Exception as e:
            logger.error("display.failed", error=str(e))
            self.console.print(f"[red]Error displaying results:[/] {str(e)}")

def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Generic agent test harness"
    )
    parser.add_argument(
        "agent_type",
        choices=AgentTestHarness.AGENT_TYPES.keys(),
        help="Type of agent to test"
    )
    parser.add_argument(
        "config",
        type=str,
        help="Path to YAML config file"
    )
    parser.add_argument(
        "--log-mode",
        type=LogMode,
        choices=list(LogMode),
        default=LogMode.NORMAL,
        help="Logging mode"
    )
    parser.add_argument(
        "--param",
        action='append',
        help="Additional parameters in key=value format. Can be specified multiple times.",
        default=[]
    )
    
    args = parser.parse_args()
    
    try:
        # Parse any additional parameters
        extra_params = {}
        for param_str in args.param:
            try:
                key, value = parse_param(param_str)
                extra_params[key] = value
            except ValueError as e:
                logger.error("param.parse_failed", param=param_str, error=str(e))
                raise SystemExit(1)
        
        harness = AgentTestHarness()
        harness.setup_logging(args.log_mode)
        
        harness.process_agent(AgentConfig(
            agent_type=args.agent_type,
            config_path=args.config,
            extra_args=extra_params
        ))
        
    except Exception as e:
        logger.error("harness.failed", error=str(e))
        raise SystemExit(1)

if __name__ == "__main__":
    main()