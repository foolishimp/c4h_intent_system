"""Discovery agent using tartxt for project analysis."""

from typing import Dict, Any, Optional
import structlog
import subprocess
import sys
from pathlib import Path
from .base import BaseAgent, LLMProvider, AgentResponse

logger = structlog.get_logger()

class DiscoveryAgent(BaseAgent):
    """Agent responsible for project discovery using tartxt"""
    
    def __init__(self,
                 provider: LLMProvider = LLMProvider.ANTHROPIC,
                 model: Optional[str] = None):
        super().__init__(
            provider=provider,
            model=model,
            temperature=0
        )

    def _get_agent_name(self) -> str:
        """Get agent name - required by BaseAgent"""
        return "discovery_agent"
        
    def _get_system_message(self) -> str:
        """Get system message - required by BaseAgent"""
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
                if not line.startswith(('==', 'Warning:', 'Error:')):
                    norm_path = line.replace('\\', '/')
                    files[norm_path] = True
                    
        return files

    async def _run_tartxt(self, project_path: str) -> Dict[str, Any]:
        """Run tartxt discovery on project getting streamed output"""
        try:
            # Run tartxt with -o for streamed output
            result = subprocess.run(
                [sys.executable, "src/skills/tartxt.py", "-o", str(project_path)],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Get complete output from stdout
            output = result.stdout
            
            # Extract file list from manifest
            files = self._parse_manifest(output)
            
            if not files:
                logger.warning("discovery.no_files_found",
                            project_path=project_path)
            
            discovery_result = {
                "project_path": project_path,
                "discovery_output": output,  # Complete streamed output ready for solution designer
                "files": files,
                "stdout": result.stdout,  # Keep raw output too
                "stderr": result.stderr,  # Keep any warnings/debug info
            }
            
            logger.info("discovery.completed", 
                       file_count=len(files),
                       output_size=len(output))
            return discovery_result
            
        except subprocess.CalledProcessError as e:
            logger.error("discovery.tartxt_failed", 
                        error=str(e),
                        stderr=e.stderr)
            raise
        except Exception as e:
            logger.error("discovery.failed", error=str(e))
            raise

    async def process(self, context: Dict[str, Any]) -> AgentResponse:
        """Process a project discovery request"""
        try:
            project_path = context.get("project_path")
            if not project_path:
                return AgentResponse(
                    success=False,
                    data={},
                    error="No project path provided"
                )
            
            project_path = Path(context["project_path"])
            if not project_path.is_dir():
                logger.error("discovery.not_directory", path=str(project_path))
                return AgentResponse(success=False, error=f"Path is not a directory: {project_path}")

            # Validate path exists
            if not project_path.exists():
                return AgentResponse(
                    success=False,
                    data={},
                    error=f"Project path does not exist: {project_path}"
                )

            # Run discovery
            result = await self._run_tartxt(str(project_path))
            
            return AgentResponse(
                success=True,
                data={"project_path": str(project_path), "files": result["files"]}
            )

        except Exception as e:
            logger.error("discovery.failed", error=str(e))
            return AgentResponse(
                success=False,
                data={},
                error=str(e)
            )
