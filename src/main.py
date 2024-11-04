# src/main.py

import asyncio
import typer
from pathlib import Path
import structlog
from typing import Optional

from agents.discovery import DiscoveryAgent
from agents.analysis import AnalysisAgent
from agents.refactor import RefactorAgent
from agents.assurance import AssuranceAgent
from models.intent import Intent, IntentStatus

app = typer.Typer()
logger = structlog.get_logger()

async def process_intent(intent: Intent) -> Dict[str, Any]:
    """Process an intent through the agent pipeline"""
    try:
        # Discovery phase
        discovery_agent = DiscoveryAgent()
        discovery_result = await discovery_agent.process({
            "project_path": intent.project_path
        })
        
        # Analysis phase
        analysis_agent = AnalysisAgent()
        analysis_result = await analysis_agent.process({
            "discovery_output": discovery_result["discovery_output"],
            "intent_description": intent.description
        })
        
        # Refactor phase
        refactor_agent = RefactorAgent()
        refactor_result = await refactor_agent.process({
            "transformation_plan": analysis_result["transformation_plan"],
            "project_path": intent.project_path
        })
        
        # Assurance phase
        assurance_agent = AssuranceAgent()
        assurance_result = await assurance_agent.process({
            "modified_files": refactor_result["modified_files"],
            "project_path": intent.project_path
        })
        
        return {
            "status": "success",
            "results": {
                "discovery": discovery_result,
                "analysis": analysis_result,
                "refactor": refactor_result,
                "assurance": assurance_result
            }
        }
        
    except Exception as e:
        logger.exception("intent.processing_failed")
        return {
            "status": "failed",
            "error": str(e)
        }

@app.command()
def refactor(
    project_path: str,
    description: str,
    verbose: bool = typer.Option(False, "--verbose", "-v")
):
    """Refactor a Python project based on a description"""
    # Configure logging
    log_level = "DEBUG" if verbose else "INFO"
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(log_level)
    )
    
    # Create and process intent
    intent = Intent(
        description=description,
        project_path=project_path
    )
    
    # Run processing
    result = asyncio.run(process_intent(intent))
    
    # Show results
    if result["status"] == "success":
        typer.echo(f"✨ Refactoring completed successfully!")
    else:
        typer.echo(f"❌ Refactoring failed: {result['error']}", err=True)

if __name__ == "__main__":
    app()
