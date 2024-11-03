# src/app.py

from typing import Dict, Any
from pathlib import Path
import structlog
import asyncio  # Added for async support

from src.config import Config
from src.agents.orchestration import OrchestrationAgent
from src.agents.assurance import AssuranceAgent
from src.agents.discovery import DiscoveryAgent

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

def create_app(config: Config) -> IntentApp:
    """Application factory function"""
    return IntentApp(config)