# src/app.py

from typing import Dict, Any
from pathlib import Path
import structlog

from src.config import Config
from src.agents.orchestration import OrchestrationAgent
from src.agents.discovery import DiscoveryAgent 
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
        return await self.orchestrator.process_scope_request(str(project_path))

def create_app(config: Config) -> IntentApp:
    """Application factory function"""
    return IntentApp(config)