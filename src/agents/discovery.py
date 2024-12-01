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
from dataclasses import dataclass, field
from .base import BaseAgent, LLMProvider, AgentResponse

logger = structlog.get_logger()

@dataclass
class DiscoveryResult:
    """Result of project discovery operation"""
    success: bool
    files: Dict[str, bool]
    raw_output: str
    project_path: str
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

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

    def _get_agent_name(self) -> str:  # Fixed signature to match abstract method
        """Get agent name for config lookup."""
        return "discovery"

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

    def _run_tartxt(self, project_path: str) -> DiscoveryResult:
        """Run tartxt discovery on project"""
        try:
            # Run tartxt with stdout capture
            result = subprocess.run(
                [sys.executable, "src/skills/tartxt.py", "-o", str(project_path)],
                capture_output=True,
                text=True,
                check=True
            )

            return DiscoveryResult(
                success=True,
                files=self._parse_manifest(result.stdout),
                raw_output=result.stdout,
                project_path=project_path
            )

        except subprocess.CalledProcessError as e:
            logger.error("discovery.tartxt_failed", 
                        error=str(e),
                        stderr=e.stderr)
            return DiscoveryResult(
                success=False,
                files={},
                raw_output=e.stderr,
                project_path=project_path,
                error=str(e)
            )
        except Exception as e:
            logger.error("discovery.failed", error=str(e))
            return DiscoveryResult(
                success=False,
                files={},
                raw_output="",
                project_path=project_path,
                error=str(e)
            )

    async def process(self, context: Dict[str, Any]) -> AgentResponse:
        """Process a project discovery request."""
        try:
            project_path = context.get("project_path")
            if not project_path:
                return AgentResponse(
                    success=False,
                    data={},
                    error="No project path provided"
                )
            
            path = Path(project_path)
            if not path.exists():
                return AgentResponse(
                    success=False,
                    data={},
                    error=f"Project path does not exist: {project_path}"
                )

            # Run discovery
            result = self._run_tartxt(str(project_path))
            
            # Convert DiscoveryResult to AgentResponse
            return AgentResponse(
                success=result.success,
                data={
                    "files": result.files,
                    "raw_output": result.raw_output,
                    "project_path": result.project_path,
                    "timestamp": result.timestamp
                },
                error=result.error
            )

        except Exception as e:
            logger.error("discovery.failed", error=str(e))
            return AgentResponse(
                success=False,
                data={},
                error=str(e)
            )