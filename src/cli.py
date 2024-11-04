# src/cli.py

import typer
import asyncio
from pathlib import Path
import structlog
from typing import Optional
import yaml
from pydantic import BaseModel, Field

from .agents.orchestrator import ProjectAnalysisSystem

# Config Models
class LLMConfig(BaseModel):
    """LLM Configuration"""
    api_key_env: str = "OPENAI_API_KEY"
    model: str = "gpt-4"
    temperature: float = 0
    timeout: int = 120

class SkillConfig(BaseModel):
    """Skill Configuration"""
    path: Path
    exclude_patterns: list[str] = Field(default_factory=lambda: ["*.pyc", "__pycache__", "*.DS_Store"])
    max_file_size: int = 10_485_760  # 10MB

class SystemConfig(BaseModel):
    """Simplified system configuration"""
    llm: LLMConfig = Field(default_factory=LLMConfig)
    skills: dict[str, SkillConfig]
    output_dir: Path = Path("output")
    max_rounds: int = 10

    class Config:
        arbitrary_types_allowed = True

def load_config(config_path: Path) -> SystemConfig:
    """Load system configuration"""
    with open(config_path) as f:
        raw_config = yaml.safe_load(f)
    
    # Convert skill paths to Path objects
    if 'skills' in raw_config:
        for skill in raw_config['skills'].values():
            if 'path' in skill:
                skill['path'] = Path(skill['path'])
    
    return SystemConfig(**raw_config)

# CLI App
app = typer.Typer()

@app.command()
def analyze(
    project_path: str,
    config_path: Optional[str] = typer.Option(
        "config/system_config.yml",
        "--config",
        "-c",
        help="Path to configuration file"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging"
    )
):
    """Analyze a Python project using AutoGen agents"""
    # Setup logging
    log_level = "DEBUG" if verbose else "INFO"
    logger = structlog.get_logger()
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(log_level)
    )
    
    try:
        # Validate paths
        project_path = Path(project_path)
        config_path = Path(config_path)
        
        if not project_path.exists():
            raise typer.BadParameter(f"Project path does not exist: {project_path}")
        
        if not config_path.exists():
            raise typer.BadParameter(f"Config file does not exist: {config_path}")
        
        # Show analysis start
        typer.echo(f"Starting analysis of {project_path}")
        if verbose:
            typer.echo(f"Using config from {config_path}")
        
        # Initialize system
        system = ProjectAnalysisSystem(str(config_path))
        
        # Run analysis
        result = asyncio.run(system.analyze_project(str(project_path)))
        
        # Show results
        typer.echo("\nAnalysis complete! 🎉")
        typer.echo(f"Results saved to: {result['output_path']}")
        
        # Show summary if available
        if "summary" in result["result"]:
            typer.echo("\nSummary:")
            for key, value in result["result"]["summary"].items():
                typer.echo(f"  {key}: {value}")
        
    except Exception as e:
        logger.exception("analysis.failed")
        typer.echo(f"Error: {str(e)}", err=True)
        raise typer.Exit(1)

if __name__ == "__main__":
    app()