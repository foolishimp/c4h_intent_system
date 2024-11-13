# src/agents/discovery.py

from typing import Dict, Any, Optional
import structlog
import subprocess
import sys
from pathlib import Path
from coder4h.base import BaseAgent, LLMProvider, AgentResponse

logger = structlog.get_logger()

class DiscoveryAgent(BaseAgent):
    """Agent responsible for project discovery using tartxt
    
    Note: Currently uses tartxt for discovery with no LLM dependency.
    The base agent infrastructure is in place for future enhancements.
    """
    
    def __init__(self,
                 provider: LLMProvider = LLMProvider.ANTHROPIC,
                 model: Optional[str] = None):
        """Initialize Discovery Agent
        
        Args:
            provider: LLM provider for future enhancements
            model: Specific model to use, or None for provider default
        """
        super().__init__(
            provider=provider,
            model=model,
            temperature=0
        )

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
        """Parse manifest section from tartxt output to get file list
        
        Args:
            output: Raw tartxt output
            
        Returns:
            Dict mapping file paths to True
        """
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
                # Skip any non-file lines
                if not line.startswith(('==', 'Warning:', 'Error:')):
                    # Convert Windows paths if present
                    norm_path = line.replace('\\', '/')
                    files[norm_path] = True
                    
        return files

    async def _run_tartxt(self, project_path: str) -> Dict[str, Any]:
        """Run tartxt discovery on project
        
        Args:
            project_path: Path to project to analyze
            
        Returns:
            Dict containing tartxt discovery output and file list
            
        Raises:
            subprocess.CalledProcessError: If tartxt execution fails
            Exception: For other errors
        """
        try:
            # Run tartxt discovery
            result = subprocess.run(
                [sys.executable, "src/skills/tartxt.py", "-o", str(project_path)],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Extract file list from manifest
            files = self._parse_manifest(result.stdout)
            
            if not files:
                logger.warning("discovery.no_files_found",
                            project_path=project_path)
            
            discovery_result = {
                "project_path": project_path,
                "discovery_output": result.stdout,
                "files": files
            }
            
            logger.info("discovery.completed", file_count=len(files))
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
        """Process a project discovery request
        
        Args:
            context: Must contain "project_path" key with path to analyze
            
        Returns:
            AgentResponse containing discovery results or error
        """
        try:
            project_path = context.get("project_path")
            if not project_path:
                return AgentResponse(
                    success=False,
                    data={},
                    error="No project path provided"
                )

            # Validate path exists
            if not Path(project_path).exists():
                return AgentResponse(
                    success=False,
                    data={},
                    error=f"Project path does not exist: {project_path}"
                )

            # Run discovery
            result = await self._run_tartxt(project_path)
            
            return AgentResponse(
                success=True,
                data=result
            )

        except Exception as e:
            logger.error("discovery.failed", error=str(e))
            return AgentResponse(
                success=False,
                data={},
                error=str(e)
            )