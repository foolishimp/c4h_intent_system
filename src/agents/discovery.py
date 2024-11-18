"""
Discovery agent implementation.
Path: src/agents/discovery.py
"""

from typing import Dict, Any, Optional
import structlog
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from .base import BaseAgent, LLMProvider, AgentResponse  # Fixed import

logger = structlog.get_logger()

class DiscoveryAgent(BaseAgent):
    """Agent responsible for project discovery using tartxt"""
    
    def __init__(self,
                 provider: LLMProvider = LLMProvider.ANTHROPIC,
                 model: Optional[str] = None,
                 workspace_root: Optional[Path] = None,
                 **kwargs):
        """Initialize discovery agent."""
        super().__init__(
            provider=provider,
            model=model,
            temperature=kwargs.get('temperature', 0),
            config=kwargs.get('config')
        )
        
        self.workspace_root = workspace_root
        if workspace_root:
            self.workspace_root.mkdir(parents=True, exist_ok=True)
        
    def _get_agent_name(self) -> str:
        return "discovery_agent"
        
    def _get_system_message(self) -> str:
        return """You are a project discovery agent.
        You analyze project structure and files to understand:
        1. Project organization
        2. File relationships
        3. Code dependencies
        4. Available functionality"""

    def _parse_manifest(self, output: str) -> Dict[str, bool]:
        """Parse manifest section from tartxt output to get file list"""
        files = {}
        manifest_section = False
        
        for line in output.split('\n'):
            line = line.strip()
            
            if line == "== Manifest ==":
                manifest_section = True
                continue
            elif line.startswith("== Content =="):
                break
                
            if manifest_section and line:
                if not line.startswith('=='):
                    norm_path = line.replace('\\', '/')
                    files[norm_path] = True
                    
        return files

    async def _run_tartxt(self, project_path: str) -> Dict[str, Any]:
        """Run tartxt discovery on project"""
        try:
            # Run tartxt with stdout capture
            result = subprocess.run(
                [sys.executable, "src/skills/tartxt.py", "-o", str(project_path)],
                capture_output=True,
                text=True,
                check=True
            )

            # Return discovery data
            return {
                "files": self._parse_manifest(result.stdout),
                "raw_output": result.stdout,  # Complete tartxt output
                "project_path": project_path
            }

        except subprocess.CalledProcessError as e:
            logger.error("discovery.tartxt_failed", 
                        error=str(e),
                        stderr=e.stderr)
            raise
        except Exception as e:
            logger.error("discovery.failed", error=str(e))
            raise

    async def process(self, context: Dict[str, Any]) -> AgentResponse:
        """Process a project discovery request."""
        try:
            project_path = context.get("project_path")
            if not project_path:
                return self._create_standard_response(
                    False,
                    {},
                    "No project path provided"
                )
            
            project_path = Path(project_path)
            if not project_path.exists():
                return self._create_standard_response(
                    False,
                    {},
                    f"Project path does not exist: {project_path}"
                )

            # Run discovery
            result = await self._run_tartxt(str(project_path))
            
            return self._create_standard_response(True, result)

        except Exception as e:
            logger.error("discovery.failed", error=str(e))
            return self._create_standard_response(False, {}, str(e))