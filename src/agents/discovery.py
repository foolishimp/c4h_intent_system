# src/agents/discovery.py

from typing import Dict, Any, List, Optional
import structlog
import subprocess
import sys
from pathlib import Path
import autogen
import re

logger = structlog.get_logger()

class DiscoveryAgent:
    """Agent responsible for project discovery using tartxt"""
    
    def __init__(self, config_list: Optional[List[Dict[str, Any]]] = None):
        """Initialize Discovery Agent with Autogen config
        
        Args:
            config_list: Autogen LLM configuration list
        """
        # Initialize Autogen components
        self.assistant = autogen.AssistantAgent(
            name="discovery_assistant",
            llm_config={"config_list": config_list} if config_list else None,
            system_message="""You are a discovery assistant that helps analyze project structure.
            You receive tartxt output and help process it for downstream agents."""
        )
        
        self.coordinator = autogen.UserProxyAgent(
            name="discovery_coordinator",
            human_input_mode="NEVER",
            code_execution_config=False
        )

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
    
    async def analyze(self, project_path: str) -> Dict[str, Any]:
        """Run tartxt discovery on project and return output
        
        Args:
            project_path: Path to project to analyze
            
        Returns:
            Dict containing tartxt discovery output and file list
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
            
            # Simple LLM verification
            try:
                await self.coordinator.a_initiate_chat(
                    self.assistant,
                    message=f"""Process this discovery output:
                    {result.stdout}
                    
                    Acknowledge receipt and confirm the content is parseable.""",
                    max_turns=1
                )
                
                logger.info("discovery.autogen_processed",
                          file_count=len(files))
            except Exception as e:
                logger.error("discovery.autogen_processing_failed", 
                           error=str(e))
            
            return discovery_result
            
        except subprocess.CalledProcessError as e:
            logger.error("discovery.tartxt_failed", 
                        error=str(e),
                        stderr=e.stderr)
            raise
        except Exception as e:
            logger.error("discovery.failed", error=str(e))
            raise