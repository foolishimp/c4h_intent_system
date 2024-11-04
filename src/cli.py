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

from .app import create_app
from .config import load_config

# Initialize CLI components
cli = typer.Typer()
console = Console()
logger = structlog.get_logger()

def resolve_path(path: str) -> Path:
    """Resolve path relative to current working directory"""
    # Convert to absolute path if relative
    abs_path = Path(path).resolve()
    
    # Verify the path exists
    if not abs_path.exists():
        raise typer.BadParameter(f"Path does not exist: {abs_path}")
    if not abs_path.is_dir():
        raise typer.BadParameter(f"Path must be a directory: {abs_path}")
        
    logger.debug("path.resolved", original=path, resolved=str(abs_path))
    return abs_path

def setup_logging(verbose: bool = False) -> None:
    """Setup structured logging with rich output"""
    level = logging.DEBUG if verbose else logging.INFO
    
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
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

async def run_analysis(project_path: Path, config_path: Path) -> None:
    """Execute the project analysis workflow"""
    try:
        logger.info("analysis.starting", 
                   project_path=str(project_path), 
                   exists=project_path.exists(),
                   is_dir=project_path.is_dir())
        
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

@cli.command()
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
    try:
        setup_logging(verbose)
        
        # Resolve paths
        try:
            project_path = resolve_path(project_path)
            logger.info("cli.resolved_project_path", path=str(project_path))
            
            if config_path:
                config_path = resolve_path(config_path)
            else:
                # Default config path relative to project root
                config_path = Path(__file__).parent.parent / "config" / "system_config.yml"
            
            logger.info("cli.resolved_config_path", path=str(config_path))
            
            if not config_path.exists():
                raise typer.BadParameter(f"Config file not found: {config_path}")
                
        except Exception as e:
            logger.error("cli.path_resolution_failed", error=str(e))
            raise typer.BadParameter(str(e))
        
        # Run analysis
        try:
            asyncio.run(run_analysis(project_path, config_path))
        except Exception as e:
            logger.exception("cli.analysis_failed", error=str(e))
            raise
            
    except Exception as e:
        logger.exception("cli.failed", error=str(e))
        console.print(f"\n[bold red]Error:[/] {str(e)}")
        raise typer.Exit(code=1)

def main():
    """Entry point for the CLI application"""
    cli()

if __name__ == "__main__":
    main()