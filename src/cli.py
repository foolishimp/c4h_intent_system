# src/cli.py

import typer
import asyncio
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.logging import RichHandler
import logging
import structlog

from src.app import create_app
from src.config import load_config

# Initialize Typer app
cli = typer.Typer(
    name="intent_system",
    help="Intent-based processing system for code analysis",
    add_completion=False
)

# Initialize rich console
console = Console()

def setup_logging(verbose: bool = False) -> None:
    """Setup structured logging with rich output"""
    level = logging.DEBUG if verbose else logging.INFO
    
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)]
    )

@cli.command()
def analyze(
    project_path: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=True,
        file_okay=False,
        help="Path to the project to analyze"
    ),
    config_path: Optional[Path] = typer.Option(
        None,
        '--config', '-c',
        help="Path to custom config file"
    ),
    verbose: bool = typer.Option(
        False,
        '--verbose', '-v',
        help="Enable verbose logging"
    )
) -> None:
    """Analyze a project and generate an action plan."""
    try:
        # Setup logging
        setup_logging(verbose)
        logger = structlog.get_logger()
        
        # Load config
        if not config_path:
            config_path = Path("config/system_config.yml")
        
        logger.info("starting_analysis", 
                   project_path=str(project_path),
                   config_path=str(config_path))
        
        # Run the analysis
        asyncio.run(run_analysis(project_path, config_path))
        
    except Exception as e:
        logger.exception("analysis_failed")
        raise typer.Exit(1)

async def run_analysis(project_path: Path, config_path: Path) -> None:
    """Run the actual analysis process"""
    logger = structlog.get_logger()
    
    try:
        # Load config and create app
        config = load_config(config_path)
        app = create_app(config)
        
        # Initialize the app
        await app.initialize()
        
        # Run analysis
        with console.status("Analyzing project..."):
            result = await app.analyze_project(project_path)
            
        # Display results
        console.print("\n[bold green]Analysis Complete![/]")
        console.print(f"\nResults saved to: {result['results_path']}")
        
    except Exception as e:
        logger.exception("analysis_process_failed")
        raise
