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
    """Main orchestrator for the intent-based system"""
    
    def __init__(self, config_path: str):
        self.config = SystemConfig.from_yaml(config_path)
        self.logger = self._setup_logging()
        self.agents: Dict[str, BaseAgent] = {}
        
    def _setup_logging(self) -> logging.Logger:
        """Setup system logging"""
        logger = logging.getLogger("intent_system")
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logger.addHandler(handler)
        return logger

    async def initialize(self):
        """Initialize the system and required agents"""
        self.logger.info("Initializing Intent System")
        
        # Get the project root for skill paths
        project_root = Path(__file__).parent.parent
        
        # Initialize scoping agent with correct skill path
        self.agents["scoping"] = ScopingAgent(
            self.config.get_agent_config("skill_executor"),
            skill_path=str(project_root / "src" / "skills" / "tartxt.py")
        )
        
        # Ensure asset directory exists
        self.config.asset_base_path.mkdir(parents=True, exist_ok=True)
        
        self.logger.info("System initialized successfully")

    async def process_scope_request(self, project_path: str) -> Dict[str, Any]:
        """Process a scoping request and generate an action plan"""
        try:
            # Create initial intent with master prompt overlay
            intent = Intent(
                type="scope_analysis",
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
                status="created"
            )
            
            self.logger.info(f"Created scope analysis intent: {intent.id}")
            
            # Process with scoping agent
            scope_result = await self.agents["scoping"].process_intent(intent)
            
            # Generate action plan through orchestrator
            scope_result.status = "scope_complete"
            action_plan = await self.agents["orchestrator"].process_intent(scope_result)
            
            # Save results
            await self._save_results(action_plan)
            
            # Print action plan
            self._print_action_plan(action_plan)
            
            return {
                "intent_id": str(intent.id),
                "scope_result": scope_result.dict(),
                "action_plan": action_plan.dict(),
                "results_path": str(self.config.asset_base_path / f"action_plan_{intent.id}.yml")
            }
            
        except Exception as e:
            self.logger.error(f"Error processing scope request: {str(e)}")
            raise

    async def _save_results(self, action_plan: Intent):
        """Save results to asset directory"""
        import yaml
        
        output_path = self.config.asset_base_path / f"action_plan_{action_plan.id}.yml"
        with open(output_path, 'w') as f:
            yaml.dump(action_plan.dict(), f, default_flow_style=False)
            
        self.logger.info(f"Saved action plan to {output_path}")

    def _print_action_plan(self, action_plan: Intent):
        """Print formatted action plan to console"""
        print("\nAction Plan")
        print("="* 50)
        print(f"Intent ID: {action_plan.id}")
        print(f"Status: {action_plan.status}")
        print("\nProposed Actions:")
        for i, action in enumerate(action_plan.context.get("actions", []), 1):
            print(f"\n{i}. {action.get('description')}")
            if action.get('subtasks'):
                for j, subtask in enumerate(action['subtasks'], 1):
                    print(f"   {i}.{j} {subtask}")
        print("\n" + "="* 50)

async def main():
    # Initialize and run the system
    system = IntentSystem("config/system_config.yml")
    await system.initialize()
    
    # Process test project
    result = await system.process_scope_request("tests/test_project")
    return result

if __name__ == "__main__":
    asyncio.run(main())