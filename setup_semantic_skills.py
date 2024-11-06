#!/usr/bin/env python3
# setup_semantic_skills.py

import os
from pathlib import Path

def create_file(path: Path, content: str):
    """Create a file with given content"""
    path.parent.mkdir(parents=True, exist_ok=True)
    
    if not path.exists():
        with open(path, 'w') as f:
            f.write(content)
        print(f"Created {path}")
    else:
        print(f"Skipped existing {path}")

# Define base path
src_path = Path("src")
skills_path = src_path / "skills"

# File contents
shared_init = """# src/skills/shared/__init__.py
"""

types_content = """# src/skills/shared/types.py
from typing import Dict, Any, Optional
from dataclass import dataclass

@dataclass
class InterpretResult:
    \"\"\"Result from semantic interpretation\"\"\"
    data: Any
    raw_response: str
    context: Dict[str, Any]
"""

interpreter_content = """# src/skills/semantic_interpreter.py
from typing import Dict, Any, List, Optional, Union
import autogen
import structlog
from .shared.types import InterpretResult

logger = structlog.get_logger()

class SemanticInterpreter:
    \"\"\"Uses LLM to extract structured information from text\"\"\"
    
    def __init__(self, config_list: List[Dict[str, Any]]):
        self.interpreter = autogen.AssistantAgent(
            name="semantic_interpreter",
            llm_config={"config_list": config_list},
            system_message=\"\"\"You are a semantic interpreter that extracts structured information from text.
            Given source content and a prompt describing what to find:
            1. Analyze the content according to the prompt
            2. Return the requested information in the specified format
            3. Be precise in following format requests
            4. Return exactly what was asked for without additions\"\"\"
        )
        
        self.coordinator = autogen.UserProxyAgent(
            name="interpreter_coordinator",
            human_input_mode="NEVER",
            code_execution_config=False
        )

    async def interpret(self, 
                       content: Union[str, Dict, List], 
                       prompt: str,
                       **context: Any) -> InterpretResult:
        \"\"\"Interpret content according to prompt\"\"\"
        try:
            # Normalize content to string if needed
            content_str = (json.dumps(content) 
                         if isinstance(content, (dict, list)) 
                         else str(content))
            
            response = await self.coordinator.a_initiate_chat(
                self.interpreter,
                message=f\"\"\"Interpret this content according to the instructions:

                INSTRUCTIONS:
                {prompt}

                CONTENT:
                {content_str}
                \"\"\",
                max_turns=1
            )
            
            return self._process_response(response, content, prompt, context)
            
        except Exception as e:
            logger.error("interpretation.failed", error=str(e))
            return InterpretResult(
                data=None,
                raw_response=str(e),
                context={
                    "error": str(e),
                    "original_content": content,
                    "prompt": prompt,
                    **context
                }
            )
"""

loop_content = """# src/skills/semantic_loop.py
from typing import Dict, Any, List, Optional, Callable
import autogen
import structlog
from .shared.types import InterpretResult

logger = structlog.get_logger()

class SemanticLoop:
    \"\"\"Uses LLM to iteratively improve results\"\"\"
    
    def __init__(self, config_list: List[Dict[str, Any]], max_iterations: int = 3):
        self.max_iterations = max_iterations
        self.improver = autogen.AssistantAgent(
            name="semantic_improver",
            llm_config={"config_list": config_list},
            system_message=\"\"\"You help improve results through iteration.
            When given a result and improvement goal:
            1. Analyze what worked and what didn't
            2. Suggest specific improvements
            3. Maintain successful parts while fixing issues\"\"\"
        )
        
        self.coordinator = autogen.UserProxyAgent(
            name="loop_coordinator",
            human_input_mode="NEVER",
            code_execution_config=False
        )
        
        self.context = {}

    async def iterate(self,
                     initial_result: Any,
                     improvement_goal: str,
                     success_check: Optional[Callable[[Any], bool]] = None) -> Dict[str, Any]:
        \"\"\"Iteratively improve a result\"\"\"
        current_result = initial_result
        iteration = 0
        
        while iteration < self.max_iterations:
            if success_check and success_check(current_result):
                break
                
            try:
                response = await self.coordinator.a_initiate_chat(
                    self.improver,
                    message=f\"\"\"Improve this result:
                    
                    CURRENT RESULT:
                    {current_result}
                    
                    IMPROVEMENT GOAL:
                    {improvement_goal}
                    
                    ITERATION: {iteration + 1} of {self.max_iterations}
                    \"\"\",
                    max_turns=1
                )
                
                # Update result and context
                current_result = self._process_response(response)
                self.context[f"iteration_{iteration}"] = {
                    "result": current_result,
                    "response": response
                }
                
            except Exception as e:
                logger.error("iteration.failed", 
                           iteration=iteration,
                           error=str(e))
                break
                
            iteration += 1
            
        return {
            "final_result": current_result,
            "iterations": iteration,
            "context": self.context
        }
"""

# Create directory structure and files
files_to_create = [
    (skills_path / "shared" / "__init__.py", shared_init),
    (skills_path / "shared" / "types.py", types_content),
    (skills_path / "semantic_interpreter.py", interpreter_content),
    (skills_path / "semantic_loop.py", loop_content),
]

for path, content in files_to_create:
    create_file(path, content)

print("\nSetup complete! The semantic skills have been added to your project.")
print("\nFolder structure created:")
print("src/")
print("└── skills/")
print("    ├── semantic_interpreter.py")
print("    ├── semantic_loop.py")
print("    └── shared/")
print("        ├── __init__.py")
print("        └── types.py")
