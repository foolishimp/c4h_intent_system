# src/main.py

import asyncio
import sys
import os
import argparse
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional
import structlog
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

class IntentProcessor:
    """Orchestrates the intent processing workflow using specialized agents"""
    
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

    async def process_intent(self, intent: Intent) -> Dict[str, Any]:
        """Process intent through the agent workflow"""
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
            
            # Architecture phase - Now with loop prevention
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

async def process_intent(project_path: Path, intent_desc: str, strategy: RefactoringStrategy) -> Dict[str, Any]:
    """Main entry point for intent processing"""
    intent = Intent(
        description=intent_desc,
        project_path=str(project_path)
    )
    processor = IntentProcessor(strategy=strategy)
    return await processor.process_intent(intent)

def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(description="Refactor Python code")
    parser.add_argument('command', choices=['refactor'])
    parser.add_argument('project_path', type=Path)
    parser.add_argument('intent', type=str)
    parser.add_argument('--strategy', choices=['codemod', 'llm'], default='codemod',
                      help="Refactoring strategy to use")
    parser.add_argument('--max-iterations', type=int, default=3,
                      help="Maximum number of refactoring iterations")
    
    args = parser.parse_args()
    
    if not args.project_path.exists():
        print(f"Error: Project path does not exist: {args.project_path}")
        sys.exit(1)
        
    try:
        strategy = RefactoringStrategy(args.strategy)
        print(f"\nStarting refactoring with {strategy.value} strategy...")
        print(f"Max iterations: {args.max_iterations}")
        print(f"Project path: {args.project_path}")
        print(f"Intent: {args.intent}")
        
        result = asyncio.run(process_intent(args.project_path, args.intent, strategy))
        
        print(f"\nRefactoring completed with status: {result['status']}")
        if result['status'] == 'success':
            print(f"Completed in {result.get('iterations', 1)} iterations")
        else:
            print(f"Error: {result.get('error', 'Unknown error')}")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()