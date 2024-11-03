# src/app.py
# These should be the imports at top:
from typing import Dict, Any
from pathlib import Path
import structlog

from src.config import Config
from src.agents.orchestration import OrchestrationAgent
from src.agents.assurance import AssuranceAgent

class IntentApp:
    """Main application class for the Intent System"""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = structlog.get_logger()
        self.orchestrator = OrchestrationAgent(config)
        self.assurance = AssuranceAgent(config)

    async def initialize(self) -> None:
        """Initialize the application and its components"""
        await self.orchestrator.initialize()
        await self.assurance.initialize()
        
        # Ensure asset directory exists
        self.config.asset_base_path.mkdir(parents=True, exist_ok=True)
        
        self.logger.info("app.initialized")
    
    async def analyze_project(self, project_path: Path) -> Dict[str, Any]:
        """Analyze a project and generate action plan"""
        self.logger.info("analyze_project.started", project_path=str(project_path))
        
        try:
            result = await self.orchestrator.process_scope_request(str(project_path))
            
            if not result:
                self.logger.error("analyze_project.no_results")
                raise ValueError("No results returned from analysis")
                
            self.logger.info("analyze_project.completed", 
                            intent_id=result.get("intent_id"),
                            results_path=result.get("results_path"))
            
            return result
            
        except Exception as e:
            self.logger.exception("analyze_project.failed", error=str(e))
            raise

def create_app(config: Config) -> IntentApp:
    """Application factory function"""
    return IntentApp(config)