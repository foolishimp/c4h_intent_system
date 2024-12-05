"""
Generic test harness for running agent classes with configuration.
Path: src/testharness.py
"""

from typing import List, Dict, Any, Optional, Type
import structlog
from enum import Enum
import logging.config
from dataclasses import dataclass
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import json
from pathlib import Path
import argparse
import yaml  # Add this import

from agents.base import BaseAgent, LLMProvider, LogDetail
from agents.coder import Coder
from skills.semantic_iterator import SemanticIterator
from skills.shared.types import ExtractConfig
from agents.discovery import DiscoveryAgent
from agents.solution_designer import SolutionDesigner
from skills.asset_manager import AssetManager
from skills.semantic_merge import SemanticMerge
from skills.semantic_extract import SemanticExtract
from config import deep_merge

logger = structlog.get_logger()

class LogMode(str, Enum):
    """Logging modes supported by harness"""
    DEBUG = "debug"     # Maps to LogDetail.DEBUG
    NORMAL = "normal"   # Maps to LogDetail.BASIC

    @property
    def to_log_detail(self) -> LogDetail:
        """Convert harness LogMode to agent LogDetail"""
        return {
            LogMode.DEBUG: LogDetail.DEBUG,
            LogMode.NORMAL: LogDetail.BASIC
        }[self]

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
        "semantic_iterator": SemanticIterator,
        "semantic_merge": SemanticMerge,
        "semantic_extract": SemanticExtract,
        "discovery": DiscoveryAgent,
        "solution_designer": SolutionDesigner,
        "asset_manager": AssetManager
    }

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def setup_logging(self, mode: LogMode) -> None:
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
        """Load and merge configurations"""
        try:
            # Find system config path
            system_config_paths = [
                Path("system_config.yml"),
                Path.cwd() / "system_config.yml",
                Path(__file__).parent.parent / "system_config.yml",
                Path("config/system_config.yml"),
                Path(__file__).parent.parent / "config" / "system_config.yml"
            ]
            
            system_config_path = next(
                (path for path in system_config_paths if path.exists()),
                None
            )
            
            if not system_config_path:
                paths_tried = "\n  - ".join(str(p) for p in system_config_paths)
                raise FileNotFoundError(f"System configuration not found. Tried:\n  - {paths_tried}")
            
            # Load system config using yaml
            with open(system_config_path) as f:
                system_config = yaml.safe_load(f)

            # Load test config using yaml
            with open(test_config_path) as f:
                test_config = yaml.safe_load(f)
            
            # Merge configs using deep_merge
            config = deep_merge(system_config, test_config)
            
            logger.debug("testharness.config_loaded",
                        system_path=str(system_config_path),
                        test_path=test_config_path,
                        merged_keys=list(config.keys()))
            
            return config

        except Exception as e:
            logger.error("testharness.config_load_failed", error=str(e))
            raise

    def create_agent(self, agent_type: str, config: Dict[str, Any]) -> BaseAgent:
        """Create agent instance based on type"""
        if agent_type not in self.AGENT_TYPES:
            raise ValueError(f"Unsupported agent type: {agent_type}")
                
        agent_class = self.AGENT_TYPES[agent_type]
        
        # Special handling for AssetManager which isn't a BaseAgent
        if agent_type == "asset_manager":
            return agent_class(
                backup_enabled=True,
                backup_dir=Path("workspaces/backups"),
                config=config
            )
        
        # Get agent-specific config or empty dict if not found
        agent_config = config.get('llm_config', {}).get('agents', {}).get(agent_type, {})
        
        return agent_class(config=config)

    def process_agent(self, config: AgentConfig) -> None:
        """Process agent with configuration"""
        try:
            # Load configuration
            configs = self.load_configs(str(config.config_path))
            logger.debug("testharness.loaded_config", 
                        config_path=str(config.config_path),
                        config_contents=configs)
                
            # Create agent instance
            agent = self.create_agent(config.agent_type, configs)
            logger.debug("testharness.created_agent",
                        agent_type=config.agent_type,
                        agent_class=agent.__class__.__name__)

            # Get any extra parameters passed via command line
            extra_params = config.extra_args or {}
                
            if isinstance(agent, SemanticIterator):
                # Handle iterator case
                self.console.print("[cyan]Processing with semantic iterator...[/]")
                
                extract_config = ExtractConfig(
                    instruction=configs.get('instruction'),
                    format=configs.get('format', 'json')
                )
                
                for key, value in extra_params.items():
                    if hasattr(extract_config, key):
                        setattr(extract_config, key, value)
                        logger.info(f"config.override", key=key, value=value)
                
                agent.configure(
                    content=configs.get('input_data'),
                    config=extract_config
                )
                
                results = []
                for item in agent:
                    results.append(item)
                        
                self.display_results(results)
                    
            else:
                # Generic agent processing
                self.console.print(f"[cyan]Processing with {config.agent_type}...[/]")
                
                context = {
                    'content': configs.get('input_data'),
                    'instruction': configs.get('instruction'),
                    'merge_style': configs.get('merge_style', 'smart'),
                    **extra_params
                }
                
                result = agent.process(context)  # Synchronous call
                
                if not result.success:
                    self.console.print(f"[red]Error:[/] {result.error}")
                    return
                        
                self.display_results(result.data)

        except Exception as e:
            logger.error("process_agent.failed", error=str(e))
            raise

    def display_results(self, results: Any) -> None:
        """Display processing results"""
        if not results:
            self.console.print("[yellow]No results to display[/]")
            return

        if isinstance(results, list):
            table = Table(title="Extracted Items")
            
            # Add columns based on first item if it's a dict
            if results and isinstance(results[0], dict):
                for key in results[0].keys():
                    table.add_column(key.title())
                
                for item in results:
                    table.add_row(*[str(v) for v in item.values()])
            else:
                table.add_column("Result")
                for item in results:
                    table.add_row(str(item))
                    
            self.console.print(table)
        else:
            self.console.print(Panel(str(results)))

def main():
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
        help="Logging mode for test harness"
    )
    parser.add_argument(
        "--param",
        action='append',
        help="Additional parameters in key=value format",
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
        
        logger.info("testharness.starting", 
                   agent_type=args.agent_type,
                   config_file=args.config,
                   log_mode=args.log_mode)

        harness = AgentTestHarness()
        harness.setup_logging(args.log_mode)
        
        try:
            harness.process_agent(AgentConfig(
                agent_type=args.agent_type,
                config_path=Path(args.config),
                extra_args=extra_params
            ))
        except FileNotFoundError as e:
            logger.error("config.not_found", path=args.config)
            print(f"\nError: Configuration file not found: {args.config}")
            raise SystemExit(1)
        except Exception as e:
            logger.error("process_agent.failed", error=str(e))
            raise
            
        logger.info("testharness.completed")
        
    except Exception as e:
        logger.error("harness.failed", error=str(e))
        print(f"\nError: {str(e)}")
        raise SystemExit(1)

if __name__ == "__main__":
    main()