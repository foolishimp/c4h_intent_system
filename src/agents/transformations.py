# src/agents/transformations.py

from typing import List, Dict, Any, Optional
from pathlib import Path
from libcst.codemod import CodemodContext, VisitorBasedCodemodCommand
from libcst import MetadataWrapper, parse_module
import libcst as cst
import subprocess
import semgrep
import autogen
import os

def format_code(file_path: Path) -> None:
    """Format code using ruff CLI"""
    try:
        subprocess.run(['ruff', 'check', '--fix', str(file_path)], check=True)
        subprocess.run(['ruff', 'format', str(file_path)], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error formatting {file_path}: {e}")

def run_semgrep_check(files: List[Path], rules: Dict[str, Any]) -> Dict[str, Any]:
    """Run semgrep checks on files"""
    try:
        findings = semgrep.scan_files(
            [str(f) for f in files],
            config=rules
        )
        return findings
    except Exception as e:
        print(f"Error running semgrep: {e}")
        return {}

class CodemodTransform(VisitorBasedCodemodCommand):
    """Pure execution of analysis-provided transformations"""
    
    def __init__(self, context: CodemodContext, transform_args: Dict[str, Any]):
        super().__init__(context)
        self.actions = transform_args.get('actions', {})
        self.current_node_path = []

    def visit_Module(self, node: cst.Module) -> cst.Module:
        """Apply module-level transformations from analysis"""
        module_actions = self.actions.get('module', {})
        if not module_actions:
            return node
            
        return self._apply_actions(node, module_actions)

    def visit_FunctionDef(self, node: cst.FunctionDef) -> cst.FunctionDef:
        """Apply function-level transformations from analysis"""
        function_actions = self.actions.get('functions', {}).get(node.name.value, {})
        if not function_actions:
            return node
            
        return self._apply_actions(node, function_actions)

    def _apply_actions(self, node: cst.CSTNode, actions: Dict[str, Any]) -> cst.CSTNode:
        """Apply transformation actions to a node"""
        modified_node = node
        
        for action in actions.get('transforms', []):
            # Execute the transformation based on the action spec
            modified_node = self._execute_transform(modified_node, action)
            
        return modified_node

    def _execute_transform(self, node: cst.CSTNode, action: Dict[str, Any]) -> cst.CSTNode:
        """Execute a single transformation action"""
        try:
            # The action should contain the exact CST operation to perform
            transform_type = action['type']
            transform_data = action['data']
            
            match transform_type:
                case 'with_changes':
                    return node.with_changes(**transform_data)
                case 'insert_body':
                    return self._insert_body(node, transform_data)
                case 'replace_node':
                    return self._create_node(transform_data)
                case _:
                    return node
        except Exception as e:
            print(f"Error executing transform: {e}")
            return node

    def _insert_body(self, node: cst.CSTNode, insert_data: Dict[str, Any]) -> cst.CSTNode:
        """Insert nodes into a body"""
        if not hasattr(node, 'body'):
            return node
            
        position = insert_data.get('position', 'start')
        new_nodes = [self._create_node(n) for n in insert_data['nodes']]
        
        if isinstance(node.body, cst.IndentedBlock):
            current_body = list(node.body.body)
            if position == 'start':
                updated_body = new_nodes + current_body
            else:
                updated_body = current_body + new_nodes
                
            return node.with_changes(
                body=cst.IndentedBlock(body=updated_body)
            )
        return node

    def _create_node(self, node_spec: Dict[str, Any]) -> cst.CSTNode:
        """Create a CST node from specification"""
        node_type = node_spec['node_type']
        node_args = node_spec.get('args', {})
        
        # Get the CST class by name
        node_class = getattr(cst, node_type)
        return node_class(**node_args)

class LLMTransformation:
    """LLM-based code transformation"""
    
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
            
        self.config_list = [
            {
                "model": "gpt-4",
                "api_key": api_key,
            }
        ]
        
        self.llm_agent = autogen.AssistantAgent(
            name="llm_transformer",
            llm_config={"config_list": self.config_list},
            system_message="""You are a Python code transformation expert.
            When given Python code and a transformation request:
            1. Follow the exact transformation actions provided
            2. Return only the modified code
            3. No explanations, just code""")
        
        self.manager = autogen.UserProxyAgent(
            name="manager",
            human_input_mode="NEVER",
            code_execution_config=False
        )

    async def transform_code(self, source_code: str, actions: Dict[str, Any]) -> str:
        """Transform code using LLM"""
        try:
            # Pass both code and actions to LLM
            chat_response = await self.manager.a_initiate_chat(
                self.llm_agent,
                message=f"""Apply these transformations:

                Original code:
                {source_code}

                Transformation actions:
                {actions}
                
                Return only the complete modified code.""",
                max_turns=1
            )
            
            # Extract modified code
            assistant_messages = [
                msg['content'] for msg in chat_response.chat_messages
                if msg.get('role') == 'assistant'
            ]
            
            if not assistant_messages:
                return source_code
                
            code = self._extract_code(assistant_messages[-1])
            return code if code else source_code
            
        except Exception as e:
            print(f"Error in LLM transformation: {e}")
            return source_code

    def _extract_code(self, message: str) -> str:
        """Extract code from message"""
        if "```python" in message:
            return message.split("```python")[1].split("```")[0].strip()
        elif "```" in message:
            return message.split("```")[1].strip()
        return message.strip()

def get_transformer(strategy: str = "codemod", transform_args: Dict[str, Any] = None) -> CodemodTransform | LLMTransformation:
    """Factory function to get the right transformation implementation"""
    transform_args = transform_args or {}
    
    if strategy == "llm":
        return LLMTransformation()
    
    return CodemodTransform  # Default to codemod with supplied args