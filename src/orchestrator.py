# src/orchestrator.py

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import logging

from src.config.handler import SystemConfig
from src.agents.base import BaseAgent 
from src.agents.scoping import ScopingAgent
from src.models.intent import Intent

class IntentSystem:
    async def initialize(self):
        """Initialize the system with architecture-aligned agents"""
        self.logger.info("Initializing Intent System")
        
        project_root = Path(__file__).parent.parent
        
        # Initialize according to architecture
        self.agents = {
            "orchestrator": OrchestrationAgent(
                self.config.get_agent_config("orchestrator"),
                skills_path=str(project_root / "src" / "skills")
            ),
            "assurance": AssuranceAgent(
                self.config.get_agent_config("assurance")
            )
        }
        
        # Ensure asset directory exists
        self.config.asset_base_path.mkdir(parents=True, exist_ok=True)
        
        self.logger.info("System initialized successfully")

    async def process_scope_request(self, project_path: str) -> Dict[str, Any]:
        """Process scope request using architecture flow"""
        try:
            # Create initial intent
            intent = Intent(
                type=IntentType.SCOPE_ANALYSIS,
                description=f"Analyze project scope for {project_path}",
                environment={
                    "project_path": project_path,
                    "master_prompt": self.config.master_prompt_overlay
                },
                context={
                    "creation_timestamp": datetime.utcnow().isoformat(),
                    "asset_base_path": str(self.config.asset_base_path)
                },
                criteria={
                    "include_file_analysis": True,
                    "generate_action_plan": True
                },
                status=IntentStatus.CREATED
            )
            
            self.logger.info(f"Created scope analysis intent: {intent.id}")
            
            # Process with orchestration agent
            result = await self.agents["orchestrator"].processIntent(intent)
            
            # Verify results with assurance agent
            verified = await self.agents["assurance"].verify(result)
            
            if verified.status == IntentStatus.ERROR:
                raise Exception(f"Verification failed: {verified.context.get('error')}")
            
            # Save and display results
            await self._save_results(result)
            self._print_action_plan(result)
            
            return {
                "intent_id": str(intent.id),
                "result": result.dict(),
                "results_path": str(self.config.asset_base_path / f"scope_{intent.id}.yml")
            }
            
        except Exception as e:
            self.logger.error(f"Error processing scope request: {str(e)}")
            raise

async def main():
    # Initialize and run the system
    system = IntentSystem("config/system_config.yml")
    await system.initialize()
    
    # Process test project
    result = await system.process_scope_request("tests/test_project")
    return result

if __name__ == "__main__":
    asyncio.run(main())