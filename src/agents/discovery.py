# src/agents/discovery.py

from typing import Dict, Any
import structlog
import subprocess
import sys
from pathlib import Path

logger = structlog.get_logger()

class DiscoveryAgent:
    """Agent responsible for project discovery using tartxt"""
    
    def __init__(self):
        """Initialize Discovery Agent - no config needed for MVP"""
        pass
    
    async def analyze(self, project_path: str) -> Dict[str, Any]:
        """Run tartxt discovery on project and return output
        
        Args:
            project_path: Path to project to analyze
            
        Returns:
            Dict containing tartxt discovery output
        """
        try:
            # Run tartxt discovery
            result = subprocess.run(
                [sys.executable, "src/skills/tartxt.py", "-o", str(project_path)],
                capture_output=True,
                text=True,
                check=True
            )
            
            return {
                "project_path": project_path,
                "discovery_output": result.stdout,
            }
            
        except subprocess.CalledProcessError as e:
            logger.error("discovery.tartxt_failed", 
                        error=str(e),
                        stderr=e.stderr)
            raise
        except Exception as e:
            logger.error("discovery.failed", error=str(e))
            raise