# src/agents/intent_agent.py

import os
import structlog
from enum import Enum
from typing import Dict, Any, Optional
from pathlib import Path

from models.intent import Intent, IntentStatus
from agents.discovery import DiscoveryAgent
from agents.coder import Coder
from agents.assurance import AssuranceAgent
from agents.solution_architect import SolutionArchitect

logger = structlog.get_logger()

class RefactoringStrategy(str, Enum):
    """Available refactoring strategies"""
    CODEMOD = "codemod"
    LLM = "llm"

class IntentAgent:
    """Agent responsible for orchestrating the intent processing workflow"""
    
    def __init__(self, strategy: RefactoringStrategy = RefactoringStrategy.CODEMOD, max_iterations: int = 3):
        self.strategy = strategy
        self.max_iterations = max_iterations
        
        # Check for API key
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
            
        config_list = [{"model": "gpt-4", "api_key": api_key}]
        
        # Initialize specialized agents
        self.discovery = DiscoveryAgent()
        self.architect = SolutionArchitect(config_list)
        self.coder = Coder(config_list)
        self.assurance = AssuranceAgent(config_list)
        
        logger.info("intent_agent.initialized", strategy=strategy)

    async def process(self, project_path: Path, intent_desc: str) -> Dict[str, Any]:
        """Process an intent for a given project path"""
        intent = Intent(
            description=intent_desc,
            project_path=str(project_path)
        )
        return await self._process_intent(intent)

    async def _process_intent(self, intent: Intent) -> Dict[str, Any]:
        """Internal method to process intent through the agent workflow"""
        try:
            # Discovery phase
            logger.info("Starting discovery phase", intent_id=str(intent.id))
            intent.status = IntentStatus.ANALYZING
            discovery_result = await self.discovery.analyze(intent.project_path)
            context = {
                "intent_id": str(intent.id),
                "project_path": intent.project_path,
                "intent_description": intent.description,
                "discovery_output": discovery_result.get("discovery_output", "")
            }
            
            # Architecture phase
            logger.info("Starting architecture phase", intent_id=str(intent.id))
            architectural_result = await self.architect.analyze(context)
            if not architectural_result or "architectural_plan" not in architectural_result:
                raise ValueError("No valid architectural plan produced")
                
            context.update(architectural_result)
            
            # Implementation phase
            logger.info("Starting implementation phase", intent_id=str(intent.id))
            intent.status = IntentStatus.TRANSFORMING
            implementation = await self.coder.transform(context)
            
            if implementation.get("status") == "failed":
                logger.error("Implementation failed", 
                           intent_id=str(intent.id),
                           error=implementation.get("error"))
                intent.status = IntentStatus.FAILED
                return implementation
                
            context.update(implementation)
            
            # Validation phase
            logger.info("Starting validation phase", intent_id=str(intent.id))
            intent.status = IntentStatus.VALIDATING
            validation = await self.assurance.validate(context)
            
            if validation.get("status") == "success":
                intent.status = IntentStatus.COMPLETED
                return {
                    "status": "success",
                    "context": context,
                    "iterations": 1
                }
                
            intent.status = IntentStatus.FAILED
            return {
                "status": "failed",
                "error": "Validation failed",
                "context": context
            }
            
        except Exception as e:
            logger.error("Intent processing failed", 
                        intent_id=str(intent.id),
                        error=str(e),
                        exc_info=True)
            intent.status = IntentStatus.FAILED
            return {
                "status": "failed",
                "error": str(e),
                "context": context
            }

    @property
    def supported_strategies(self) -> list[str]:
        """Return list of supported refactoring strategies"""
        return [strategy.value for strategy in RefactoringStrategy]