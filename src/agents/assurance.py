# src/agents/assurance.py

from typing import Dict, Any, Optional, List
import structlog
import autogen
import py_compile
import os
from pathlib import Path

logger = structlog.get_logger()

class AssuranceAgent:
    """Agent responsible for validating code changes using Autogen patterns"""
    
    def __init__(self, config_list: Optional[List[Dict[str, Any]]] = None):
        if not config_list:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            config_list = [{"model": "gpt-4", "api_key": api_key}]
            
        self.validator = autogen.AssistantAgent(
            name="validator",
            llm_config={"config_list": config_list},
            system_message="""You are an assurance agent that validates code changes.
            When analyzing code changes:
            1. Verify syntax correctness
            2. Check for potential runtime errors
            3. Validate style consistency
            4. Ensure maintainability
            5. Return a detailed validation report"""
        )
        
        self.coordinator = autogen.UserProxyAgent(
            name="validator_coordinator",
            human_input_mode="NEVER",
            code_execution_config=False
        )

    async def validate(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Validate code changes using multiple verification steps"""
        try:
            modified_files = context.get("modified_files", {})
            validation_results = []
            
            # Basic syntax validation
            for file_path, content in modified_files.items():
                result = {"file": file_path, "checks": []}
                
                # Syntax check - try to compile
                try:
                    py_compile.compile(file_path, doraise=True)
                    result["checks"].append({
                        "type": "syntax",
                        "status": "success"
                    })
                except Exception as e:
                    result["checks"].append({
                        "type": "syntax",
                        "status": "failed",
                        "error": str(e)
                    })
                
                # Deep validation using LLM
                chat_response = await self.coordinator.a_initiate_chat(
                    self.validator,
                    message=f"""Validate this code change:
                    
                    File: {file_path}
                    Content:
                    {content}
                    
                    Analyze for:
                    1. Code style consistency
                    2. Potential runtime issues
                    3. Edge cases
                    4. Error handling
                    5. Documentation completeness
                    
                    Return validation results as JSON following this structure:
                    {{
                        "style_check": {{"status": "success|failed", "issues": []}},
                        "runtime_check": {{"status": "success|failed", "issues": []}},
                        "edge_cases": {{"status": "success|failed", "issues": []}},
                        "error_handling": {{"status": "success|failed", "issues": []}},
                        "documentation": {{"status": "success|failed", "issues": []}}
                    }}
                    """
                )
                
                # Get LLM validation results
                assistant_messages = [
                    msg['content'] for msg in chat_response.chat_messages
                    if msg.get('role') == 'assistant'
                ]
                validation = assistant_messages[-1] if assistant_messages else "{}"
                
                try:
                    import json
                    llm_results = json.loads(validation)
                    result["checks"].extend([
                        {"type": check_type, "results": check_data}
                        for check_type, check_data in llm_results.items()
                    ])
                except json.JSONDecodeError:
                    result["checks"].append({
                        "type": "llm_validation",
                        "status": "failed",
                        "error": "Invalid validation response format"
                    })
                
                validation_results.append(result)
            
            # Determine overall status
            has_failures = any(
                any(check["status"] == "failed" for check in result["checks"])
                for result in validation_results
            )
            
            return {
                "status": "failed" if has_failures else "success",
                "validation_results": validation_results
            }
            
        except Exception as e:
            logger.error("validation.failed", error=str(e))
            return {
                "status": "failed",
                "error": str(e)
            }