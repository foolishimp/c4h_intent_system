# src/agents/discovery.py

from typing import Dict, Any
from pathlib import Path
import subprocess
import sys
import structlog
from .base import BaseAgent, AgentConfig

class DiscoveryAgent(BaseAgent):
    """Agent responsible for project discovery using tartxt"""
    
    def __init__(self):
        super().__init__(AgentConfig(
            name="discovery",
            system_message="""You are a discovery agent that analyzes Python project structure.
            Your role is to scan projects and identify files for potential modifications."""
        ))
        self.logger = structlog.get_logger()

    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Process project discovery request"""
        project_path = context.get("project_path")
        if not project_path:
            raise ValueError("No project path provided")
            
        # Run tartxt for project discovery
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "src/skills/tartxt.py",
                    "--exclude", "*.pyc,__pycache__,*.DS_Store",
                    "--output",
                    project_path
                ],
                capture_output=True,
                text=True,
                check=True
            )
            return {"discovery_output": result.stdout}
            
        except subprocess.CalledProcessError as e:
            self.logger.error("discovery.failed", error=str(e))
            raise
