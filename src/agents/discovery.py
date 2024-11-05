# src/agents/discovery.py

from typing import Dict, Any, List, Optional
import structlog
import subprocess
import sys
from pathlib import Path
import autogen

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
            
            discovery_result = {
                "project_path": project_path,
                "discovery_output": result.stdout,
            }
            
            # Process through Autogen assistant
            try:
                chat_response = await self.coordinator.a_initiate_chat(
                    self.assistant,
                    message=f"""Process this discovery output:
                    {result.stdout}
                    
                    Acknowledge receipt and confirm the content is parseable."""
                )
                
                logger.info("discovery.autogen_processed")
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