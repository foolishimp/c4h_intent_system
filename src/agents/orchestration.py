# src/agents/orchestration.py

import os
from typing import Dict, Any, List
from pathlib import Path
import autogen
from pydantic import BaseModel
import libcst as cst
import structlog

class RefactorConfig(BaseModel):
    """Configuration for code refactoring"""
    project_path: str
    output_dir: Path = Path("output")
    exclude_patterns: list[str] = ["*.pyc", "__pycache__", "*.DS_Store"]
    max_file_size: int = 10_485_760  # 10MB

class RefactorAction(BaseModel):
    """Represents a single refactoring action"""
    type: str
    target_file: str
    transformation: str
    cst_transformer_class: str
    validation_rules: List[str] = []

class ProjectRefactorSystem:
    """AutoGen-based project refactoring system"""
    
    def __init__(self, config_path: str):
        self.logger = structlog.get_logger()
        self.config_path = config_path
        self._setup_agents()
        
    def _setup_agents(self):
        """Initialize AutoGen agent network"""
        # Configuration for the LLM
        config_list = [
            {
                "model": "gpt-4",
                "api_key": os.getenv("OPENAI_API_KEY")
            }
        ]

        # Create the solution architect agent
        self.solution_agent = autogen.AssistantAgent(
            name="solution_architect",
            llm_config={
                "config_list": config_list,
                "temperature": 0
            },
            system_message="""You are a solution architect that analyzes code refactoring requirements.
            Your role is to:
            1. Analyze the refactoring intent
            2. Break down the requirements into specific libcst transformations
            3. Generate a detailed action plan for each file
            4. Ensure all transformations are reversible
            5. Consider error handling and edge cases
            
            Output Format:
            - List of RefactorAction objects
            - Each action must specify the exact libcst transformer class needed
            - Include validation rules for the transformation"""
        )
        
        # Create the code refactoring agent
        self.refactor_agent = autogen.UserProxyAgent(
            name="refactor_executor",
            human_input_mode="NEVER",
            code_execution_config={
                "work_dir": "workspace",
                "use_docker": False,
            }
        )
        
        # Create the verification agent
        self.verifier = autogen.AssistantAgent(
            name="code_verifier",
            llm_config={
                "config_list": config_list,
                "temperature": 0
            },
            system_message="""You verify code transformations:
            1. Check syntax validity
            2. Verify transformation correctness
            3. Run specified tests
            4. Ensure no unintended changes
            5. Validate against provided rules"""
        )
        
        # Create the supervisor agent
        self.supervisor = autogen.AssistantAgent(
            name="supervisor",
            llm_config={
                "config_list": config_list,
                "temperature": 0
            },
            system_message="""You coordinate the refactoring process:
            1. Manage the flow between agents
            2. Handle errors and retries
            3. Maintain project state
            4. Ensure all validations pass
            5. Manage the refactoring lifecycle"""
        )
        
        # Create group chat
        self.group_chat = autogen.GroupChat(
            agents=[self.supervisor, self.solution_agent, self.refactor_agent, self.verifier],
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

    async def process_refactor_request(self, intent_msg: str, project_path: str) -> Dict[str, Any]:
        """Process a refactoring request through the agent network"""
        try:
            # Validate project path
            if not os.path.exists(project_path):
                raise ValueError(f"Project path does not exist: {project_path}")
            
            # Create refactor config
            config = RefactorConfig(project_path=project_path)
            
            # Create initial message for the group chat
            message = {
                "type": "refactor_request",
                "intent": intent_msg,
                "config": config.dict(),
                "requirements": {
                    "use_libcst": True,
                    "maintain_functionality": True,
                    "generate_validation": True
                }
            }
            
            # Run the refactoring process through group chat
            self.logger.info("refactor.starting", 
                           project_path=project_path,
                           intent=intent_msg)
            
            result = await self.manager.run(message)
            
            # Process and validate results
            validated_result = await self._validate_results(result)
            
            self.logger.info("refactor.complete", 
                           project_path=project_path,
                           status="success")
            
            return validated_result
            
        except Exception as e:
            self.logger.exception("refactor.failed",
                                project_path=project_path,
                                error=str(e))
            raise

    async def _validate_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Validate refactoring results through the verification agent"""
        verification_message = {
            "type": "verify_refactor",
            "results": results,
            "validation_rules": {
                "syntax_valid": True,
                "tests_pass": True,
                "no_unintended_changes": True
            }
        }
        
        return await self.verifier.run(verification_message)