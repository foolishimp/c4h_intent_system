# src/app.py

from typing import Dict, Any
from pathlib import Path
import structlog
import asyncio

from src.config import Config
from src.agents.orchestration import OrchestrationAgent
from src.agents.assurance import AssuranceAgent

class IntentApp:
    """Main application class for the Intent System"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = structlog.get_logger()
        
        # Initialize agents
        self.logger.info("app.initializing_agents")
        self.orchestrator = OrchestrationAgent(config)
        self.assurance = AssuranceAgent(config)
        
        self.logger.info("app.initialized")

    async def initialize(self) -> None:
        """Initialize the application and its components"""
        self.logger.info("app.initialize.starting")
        
        try:
            await self.orchestrator.initialize()
            await self.assurance.initialize()
            
            # Ensure asset directory exists
            self.config.asset_base_path.mkdir(parents=True, exist_ok=True)
            
            self.logger.info("app.initialize.complete")
            
        except Exception as e:
            self.logger.exception("app.initialize.failed", error=str(e))
            raise

    async def process_scope_request(self, project_path: str) -> Dict[str, Any]:
        """Process a scoping request for project analysis
        
        Args:
            project_path: Path to the project to analyze
            
        Returns:
            Dictionary containing analysis results and metadata
        """
        self.logger.info("app.process_scope.starting", project_path=project_path)
        
        try:
            # Delegate to orchestrator
            result = await self.orchestrator.process_scope_request(project_path)
            
            if not result:
                self.logger.error("app.process_scope.no_results")
                raise ValueError("Analysis completed but no results were returned")
            
            self.logger.info("app.process_scope.complete", 
                           intent_id=result.get("intent_id"),
                           output_path=result.get("results_path"))
                           
            return result
            
        except Exception as e:
            self.logger.exception("app.process_scope.failed", error=str(e))
            raise

def create_app(config: Config) -> IntentApp:
    """Application factory function"""
    return IntentApp(config)