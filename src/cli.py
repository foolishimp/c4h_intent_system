# src/cli.py

import typer
import asyncio
from pathlib import Path
import os
from typing import Optional
from rich.console import Console
from rich.logging import RichHandler
import logging
import structlog
import sys

from .app import create_app
from .config import load_config

# Initialize CLI components
app = typer.Typer(name="intent-system", help="Intent System CLI")
console = Console()

def setup_logging(verbose: bool = False) -> None:
    """Setup structured logging with rich output"""
    level = logging.DEBUG if verbose else logging.INFO
    
    # Create a standard logger first
    logger = logging.getLogger("intent_system")
    logger.setLevel(level)
    
    # Setup Rich handler
    rich_handler = RichHandler(
        rich_tracebacks=True,
        markup=True,
        show_path=verbose
    )
    rich_handler.setLevel(level)
    logger.addHandler(rich_handler)
    
    # Configure structlog to use standard logging
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Create our logger instance
    logger = structlog.get_logger("intent_system")
    logger.debug("logging.initialized", level=level, verbose=verbose)
    return logger

def verify_environment() -> None:
    """Verify required environment setup"""
    logger = structlog.get_logger("intent_system")
    
    # Check Python version
    logger.debug("environment.python_version", version=sys.version)
    
    # Check current directory
    cwd = os.getcwd()
    logger.debug("environment.cwd", path=cwd)
    
    # Verify critical paths
    config_dir = Path("config")
    if not config_dir.exists():
        logger.error("environment.missing_config_dir")
        raise typer.Exit(code=1)

    logger.info("environment.verified", status="ok")

@app.callback()
def callback():
    """Intent System CLI - Project Analysis Tool"""
    pass

@app.command()
def analyze(
    project_path: str = typer.Argument(
        ...,
        help="Path to the project to analyze"
    ),
    config_path: Optional[str] = typer.Option(
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
    """Analyze a project using the intent system"""
    # Setup logging first
    logger = setup_logging(verbose)
    logger.debug("cli.command.started", command="analyze")
    
    try:
        # Get project root
        root_dir = Path(__file__).parent.parent.resolve()
        
        # Convert project path to absolute
        project_path_obj = Path(project_path).resolve()
        logger.debug("cli.paths", 
                    root=str(root_dir),
                    project_path=str(project_path_obj))
        
        # Verify project path
        if not project_path_obj.exists():
            raise typer.BadParameter(f"Project path does not exist: {project_path_obj}")
        if not project_path_obj.is_dir():
            raise typer.BadParameter(f"Project path must be a directory: {project_path_obj}")
        
        # Handle config path
        if config_path:
            config_path_obj = Path(config_path).resolve()
        else:
            config_path_obj = root_dir / "config" / "system_config.yml"
        
        if not config_path_obj.exists():
            raise typer.BadParameter(f"Config file not found: {config_path_obj}")
            
        logger.info("cli.starting_analysis", 
                   project=str(project_path_obj),
                   config=str(config_path_obj))
        
        # Run analysis
        try:
            asyncio.run(run_analysis(project_path_obj, config_path_obj))
        except Exception as e:
            logger.exception("cli.analysis_failed", error=str(e))
            raise
            
    except Exception as e:
        logger.exception("cli.failed", error=str(e))
        console.print(f"\n[bold red]Error:[/] {str(e)}")
        raise typer.Exit(code=1)

async def run_analysis(project_path: Path, config_path: Path) -> None:
    """Execute the project analysis workflow"""
    logger = structlog.get_logger("intent_system")
    
    try:
        logger.info("analysis.loading_config")
        config = load_config(config_path)
        
        logger.info("analysis.creating_app")
        app = create_app(config)
        
        logger.info("analysis.initializing")
        await app.initialize()
        
        with console.status("[bold blue]Analyzing project...") as status:
            result = await app.process_scope_request(str(project_path))
            
            if not result:
                logger.error("analysis.no_results")
                raise ValueError("Analysis completed but no results were returned")
            
            logger.info("analysis.complete", result=result)
            status.update("[bold green]Analysis complete!")
        
        console.print("\n[bold green]Analysis Complete![/]")
        console.print(f"\nResults saved to: {result.get('results_path', 'No path returned')}")
        
    except Exception as e:
        logger.exception("analysis.failed", error=str(e))
        console.print(f"\n[bold red]Analysis failed:[/] {str(e)}")
        raise

def main():
    """CLI entry point"""
    app()

if __name__ == "__main__":
    main()