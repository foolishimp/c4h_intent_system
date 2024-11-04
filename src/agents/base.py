# src/agents/base.py

from typing import Dict, Any, Optional, List, Union, Callable
from datetime import datetime
import structlog
from autogen import (
    ConversableAgent,
    Agent,
    AssistantAgent,
    GroupChat,
    GroupChatManager,
    config_list_from_json
)
from pydantic import BaseModel

from src.models.intent import Intent, IntentStatus, ResolutionState
from src.config import Config

class AgentMessage(BaseModel):
    """Structured message format for agent communication"""
    intent_id: str
    message_type: str
    content: Dict[str, Any]
    timestamp: datetime = datetime.utcnow()

class IntentAgent(ConversableAgent):
    """Base agent class integrating AutoGen 0.3.1 with Intent Architecture"""
    
    def __init__(
        self,
        name: str,
        config: Config,
        llm_config: Optional[Dict] = None,
        system_message: Optional[str] = None,
        **kwargs
    ):
        # Configure LLM settings from config
        if llm_config is None:
            llm_config = {
                "config_list": config_list_from_json(
                    config.providers[config.default_llm].dict()
                ),
                "temperature": config.providers[config.default_llm].temperature,
                "timeout": config.providers[config.default_llm].timeout
            }
        
        # Initialize AutoGen agent with 0.3.1 parameters
        super().__init__(
            name=name,
            llm_config=llm_config,
            system_message=system_message or config.master_prompt_overlay,
            **kwargs
        )
        
        self.config = config
        self.logger = structlog.get_logger()
        
        # Register reply functions with AutoGen 0.3.1 syntax
        self.register_reply(
            trigger=self._is_intent_message,
            reply_func=self._handle_intent,
            config={"filter_dict": {"type": "intent"}}
        )
        
        # Set up skill registry
        self.skills = {}
        self._initialize_skills()

    async def _handle_intent(
        self,
        message: Dict[str, Any],
        sender: Optional[Agent] = None,
        context: Optional[Dict] = None
    ) -> Union[str, Dict]:
        """Process incoming intent messages"""
        try:
            intent = Intent(**message["content"])
            
            self.logger.info(
                "agent.intent_received",
                agent=self.name,
                intent_id=str(intent.id),
                intent_type=intent.type
            )
            
            # Process intent
            result = await self.process_intent(intent)
            
            # Structure response
            response = AgentMessage(
                intent_id=str(result.id),
                message_type="intent_result",
                content=result.dict()
            )
            
            return response.dict()
            
        except Exception as e:
            self.logger.exception(
                "agent.intent_processing_failed",
                error=str(e),
                message=message
            )
            raise

    def register_function(
        self,
        function: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None
    ) -> None:
        """Register a function for AutoGen function calling"""
        function_config = {
            "name": name or function.__name__,
            "description": description or function.__doc__ or "",
            "parameters": {
                # Extract parameters from function signature
                # This could be enhanced with more type information
                "type": "object",
                "properties": {},
                "required": []
            }
        }
        
        self.register_reply(
            lambda msg: msg.get("function_call", {}).get("name") == function_config["name"],
            function,
            config={"function": function_config}
        )

    def _initialize_skills(self) -> None:
        """Initialize available skills from config"""
        if hasattr(self.config, 'skills'):
            for skill_name, skill_config in self.config.skills.items():
                try:
                    # Import and initialize skill
                    module_path = skill_config.path
                    if module_path.exists():
                        # Register skill as a function
                        self.register_function(
                            function=self._create_skill_function(skill_name, skill_config),
                            name=skill_name,
                            description=skill_config.config.get('description', '')
                        )
                        
                        self.skills[skill_name] = {
                            "config": skill_config,
                            "path": module_path
                        }
                except Exception as e:
                    self.logger.error(
                        "agent.skill_initialization_failed",
                        skill=skill_name,
                        error=str(e)
                    )

    def _create_skill_function(self, skill_name: str, skill_config: Any) -> Callable:
        """Create a callable function wrapper for a skill"""
        async def skill_function(**kwargs):
            # Implement skill execution logic here
            pass
        
        skill_function.__name__ = skill_name
        skill_function.__doc__ = skill_config.config.get('description', '')
        return skill_function

    async def process_intent(self, intent: Intent) -> Intent:
        """Process an intent - to be implemented by concrete agents"""
        raise NotImplementedError

class IntentAssistantAgent(IntentAgent, AssistantAgent):
    """Assistant agent specialized for intent analysis and orchestration"""
    
    def __init__(
        self,
        name: str,
        config: Config,
        **kwargs
    ):
        super().__init__(
            name=name,
            config=config,
            system_message=self._build_system_message(config),
            **kwargs
        )

    def _build_system_message(self, config: Config) -> str:
        """Build specialized system message for assistant"""
        base_message = config.master_prompt_overlay
        return f"""{base_message}
        
        As an Intent Assistant Agent, you:
        1. Analyze incoming intents to determine processing strategy
        2. Coordinate with other agents for intent resolution
        3. Maintain intent lineage and transformation history
        4. Handle error recovery and debugging
        
        Follow the intent architecture flow:
        - Analyze intent requirements
        - Determine skill needs
        - Manage decomposition
        - Track resolution state
        """

class IntentGroupChat:
    """Manages multi-agent conversations for intent processing using AutoGen 0.3.1"""
    
    def __init__(
        self,
        agents: List[IntentAgent],
        config: Config,
        max_rounds: int = 10
    ):
        self.agents = agents
        self.config = config
        
        # Create AutoGen 0.3.1 GroupChat with enhanced configuration
        self.group_chat = GroupChat(
            agents=agents,
            messages=[],
            max_rounds=max_rounds,
            speaker_selection_method="auto",
            allow_repeat_speaker=False
        )
        
        # Create chat manager with timeout
        self.manager = GroupChatManager(
            groupchat=self.group_chat,
            name="intent_manager",
            llm_config={"timeout": config.providers[config.default_llm].timeout}
        )
    
    async def process_intent(self, intent: Intent) -> Intent:
        """Process intent through group chat"""
        message = AgentMessage(
            intent_id=str(intent.id),
            message_type="intent",
            content=intent.dict()
        )
        
        # Use 0.3.1 chat initiation
        result = await self.manager.run(
            message=message.dict(),
            sender=self.agents[0]  # Specify initial sender
        )
        
        if isinstance(result, dict) and "content" in result:
            return Intent(**result["content"])
        
        raise ValueError("Invalid result from group chat")