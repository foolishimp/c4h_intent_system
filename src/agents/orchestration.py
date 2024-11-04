# src/agents/orchestrator.py

import os
import json
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
import autogen
import structlog
from pydantic import BaseModel

class AnalysisConfig(BaseModel):
    """Configuration for project analysis"""
    project_path: str
    output_dir: Path = Path("output")
    exclude_patterns: list[str] = ["*.pyc", "__pycache__", "*.DS_Store"]
    max_file_size: int = 10_485_760  # 10MB

class ProjectAnalysisSystem:
    """AutoGen-based project analysis system"""
    
    def __init__(self, config_path: str):
        self.logger = structlog.get_logger()
        self.config_path = config_path
        self._setup_agents()
        
    def _setup_agents(self):
        """Initialize AutoGen agent network"""
        # Configuration for GPT-4
        config_list = [
            {
                "model": "gpt-4",
                "api_key": os.getenv("OPENAI_API_KEY")
            }
        ]

        # Create agents
        self.orchestrator = autogen.AssistantAgent(
            name="orchestrator",
            llm_config={
                "config_list": config_list,
                "temperature": 0
            },
            system_message="""You are an orchestrator for Python project analysis.
            Your responsibilities:
            1. Coordinate the analysis of Python project structure
            2. Manage the tartxt skill execution for file analysis
            3. Process and validate analysis results
            4. Generate clear, structured reports
            
            Follow this workflow:
            1. Receive project path
            2. Execute tartxt analysis
            3. Process results
            4. Generate report"""
        )
        
        self.executor = autogen.UserProxyAgent(
            name="executor",
            human_input_mode="NEVER",
            code_execution_config={
                "work_dir": "workspace",
                "use_docker": False,
            }
        )
        
        self.verifier = autogen.AssistantAgent(
            name="verifier",
            llm_config={
                "config_list": config_list,
                "temperature": 0
            },
            system_message="""You verify project analysis results:
            1. Validate tartxt output format
            2. Ensure all required files were analyzed
            3. Check for analysis completeness
            4. Verify report structure"""
        )
        
        # Create group chat
        self.group_chat = autogen.GroupChat(
            agents=[self.orchestrator, self.executor, self.verifier],
            messages=[],
            max_rounds=10
        )
        
        self.manager = autogen.GroupChatManager(
            groupchat=self.group_chat,
            llm_config={
                "config_list": config_list,
                "temperature": 0
            }
        )

    async def analyze_project(self, project_path: str) -> Dict[str, Any]:
        """Analyze a Python project using AutoGen agent network"""
        try:
            # Validate project path
            if not os.path.exists(project_path):
                raise ValueError(f"Project path does not exist: {project_path}")
            
            # Create analysis config
            config = AnalysisConfig(project_path=project_path)
            
            # Prepare tartxt command
            tartxt_command = f"""
            python src/skills/tartxt.py
            --exclude "*.pyc,__pycache__,*.DS_Store"
            --output {project_path}
            """
            
            # Create initial message
            message = {
                "type": "analyze_project",
                "config": config.dict(),
                "command": tartxt_command,
                "requirements": {
                    "analyze_structure": True,
                    "find_dependencies": True,
                    "generate_report": True
                }
            }
            
            # Run analysis through group chat
            self.logger.info("analysis.starting", project_path=project_path)
            result = await self.manager.run(message)
            
            # Save and return results
            output_path = self._save_results(result)
            
            self.logger.info("analysis.complete", 
                           project_path=project_path,
                           output_path=str(output_path))
            
            return {
                "result": result,
                "output_path": str(output_path)
            }
            
        except Exception as e:
            self.logger.exception("analysis.failed",
                                project_path=project_path,
                                error=str(e))
            raise

    def _save_results(self, results: Dict[str, Any]) -> Path:
        """Save analysis results"""
        output_path = Path("output") / f"analysis_{datetime.now().isoformat()}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with output_path.open('w') as f:
            json.dump(results, f, indent=2)
            
        return output_path