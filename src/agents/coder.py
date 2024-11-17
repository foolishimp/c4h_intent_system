# src/agents/coder.py

"""
Code modification agent implementation.
Path: src/agents/coder.py
"""

from typing import Dict, Any, Optional, List, Union
from pathlib import Path
import structlog
from enum import Enum
import shutil
import re
from dataclasses import dataclass

from .base import BaseAgent, LLMProvider, AgentResponse, ModelConfig
from src.skills.semantic_extract import SemanticExtract, ExtractResult
from src.skills.semantic_merge import SemanticMerge
from src.skills.semantic_iterator import SemanticIterator

logger = structlog.get_logger()

def _get_model_config(provider: LLMProvider, model: Optional[str] = None) -> Dict[str, Any]:
    """Get complete model configuration"""
    return {
        "model": model or ModelConfig.MODELS[provider],
        "api_base": ModelConfig.PROVIDER_CONFIG[provider]["api_base"],
        "temperature": 0,
        "context_length": ModelConfig.PROVIDER_CONFIG[provider]["context_length"]
    }

class MergeMethod(str, Enum):
    """Available merge methods"""
    INLINE = "inline"    # Direct content replacement
    SMART = "smart"      # Semantic understanding merge

class AssetType(str, Enum):
    """Supported asset types"""
    PYTHON = "python"
    JAVA = "java"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    HTML = "html"
    CSS = "css"
    MARKDOWN = "markdown"
    TEXT = "text"
    UNKNOWN = "unknown"

@dataclass
class TransformResult:
    """Result of a code transformation"""
    success: bool
    file_path: str
    backup_path: Optional[str] = None
    action: Optional[str] = None
    error: Optional[str] = None
    changes: Optional[List[Dict[str, Any]]] = None

class Coder(BaseAgent):
    """Code modification agent using semantic tools"""
    
    def __init__(self, 
                 provider: LLMProvider = LLMProvider.ANTHROPIC,
                 model: Optional[str] = None,
                 max_file_size: int = 1024 * 1024,
                 **kwargs):  # Added **kwargs to handle extra config params
        """Initialize coder with specified provider.
        
        Args:
            provider: LLM provider to use
            model: Specific model to use
            max_file_size: Maximum file size to process
            **kwargs: Additional configuration parameters including temperature
        """
        super().__init__(
            provider=provider,
            model=model,
            temperature=kwargs.get('temperature', 0)  # Get temperature from kwargs with default
        )
        self.max_file_size = max_file_size
        
        try:
            # Get complete model configuration
            config = _get_model_config(provider, model)
            config['temperature'] = kwargs.get('temperature', 0)  # Use provided temperature
            
            # Initialize semantic tools with consistent configuration
            self.extractor = SemanticExtract(provider=provider, model=config["model"])
            self.merger = SemanticMerge(provider=provider, model=config["model"])
            self.iterator = SemanticIterator([config])
            
            logger.info("coder.initialized", 
                       provider=provider.value,
                       model=config["model"],
                       max_file_size=max_file_size)
                       
        except KeyError as e:
            logger.error("coder.initialization_failed", 
                        error=f"Missing configuration: {str(e)}")
            raise ValueError(f"Invalid configuration: missing {str(e)}")
        except Exception as e:
            logger.error("coder.initialization_failed", error=str(e))
            raise

        
    def _get_agent_name(self) -> str:
        return "coder"
        
    def _get_system_message(self) -> str:
        return """You are an expert code modification agent.
        When given code changes to implement:
        1. Analyze the change request carefully
        2. Identify exact files to modify
        3. Apply changes precisely
        4. Return results in the specified format"""
    
    def _get_asset_type(self, file_path: str) -> AssetType:
        """Determine asset type from file extension"""
        ext = Path(file_path).suffix.lower()
        
        type_map = {
            '.py': AssetType.PYTHON,
            '.java': AssetType.JAVA,
            '.js': AssetType.JAVASCRIPT,
            '.ts': AssetType.TYPESCRIPT,
            '.html': AssetType.HTML,
            '.css': AssetType.CSS,
            '.md': AssetType.MARKDOWN,
            '.txt': AssetType.TEXT
        }
        
        return type_map.get(ext, AssetType.UNKNOWN)
    
    def _validate_request(self, request: Dict[str, Any]) -> Optional[str]:
        """Validate request parameters
        Returns None if valid, error message if invalid"""
        
        if not isinstance(request, dict):
            return "Invalid request format: must be a dictionary"
            
        # Required fields
        if "file_path" not in request:
            return "Missing required field: file_path"
            
        if "change_type" not in request:
            return "Missing required field: change_type"
            
        if "instructions" not in request:
            return "Missing required field: instructions"
            
        # Field validation
        if not request["file_path"]:
            return "Invalid file_path: cannot be empty"
            
        # Additional path validation
        file_path = request["file_path"]
        if file_path == "NOT_FOUND" or file_path == "null" or file_path == "None":
            return "Invalid file_path: path not properly specified"
            
        # Check if path looks valid
        if not any(c in file_path for c in ['/', '\\', '.']):
            return f"Invalid file path format: {file_path}"

        if not request["change_type"] in ["create", "modify", "delete"]:
            return f"Invalid change_type: {request['change_type']}"
            
        if not request["instructions"]:
            return "Invalid instructions: cannot be empty"
            
        # File size check for existing files
        try:
            path = Path(file_path)
            if path.exists() and path.stat().st_size > self.max_file_size:
                return f"File exceeds maximum size of {self.max_file_size} bytes"
        except Exception as e:
            return f"Error checking file: {str(e)}"
            
        return None

    async def _extract_change_details(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Extract file path and change details using semantic extract"""
        prompt = """Extract these details from the change request:
        1. Target file path
        2. Change type (create/modify/delete)
        3. Change instructions
        Return as JSON with fields: file_path, change_type, instructions"""
        
        result = await self.extractor.extract(
            content=context,
            prompt=prompt,
            format_hint="json"
        )
        
        if not result.success:
            raise ValueError(f"Failed to extract change details: {result.error}")
        
        # Get response data
        extract_data = result.value
        if isinstance(extract_data, dict) and "raw_message" in extract_data:
            extract_data = extract_data.get("raw_message", {})
        
        if not isinstance(extract_data, dict):
            raise ValueError("Invalid extraction result format")
            
        required_fields = ["file_path", "change_type", "instructions"]
        if not all(field in extract_data for field in required_fields):
            raise ValueError(f"Missing required fields in extraction: {required_fields}")
        
        # Additional validation to prevent NOT_FOUND file creation
        if extract_data["file_path"] == "NOT_FOUND":
            raise ValueError("Invalid file path: path not found in request")
            
        # Validate it's a reasonable file path
        if not any(c in extract_data["file_path"] for c in ['/', '\\', '.']):
            raise ValueError(f"Invalid file path format: {extract_data['file_path']}")
            
        return extract_data

    def _create_backup(self, file_path: Path) -> Optional[Path]:
        """Create numbered backup of existing file"""
        if not file_path.exists():
            return None
            
        # Find next available backup number
        backup_pattern = re.compile(rf"{file_path}\.bak_(\d+)$")
        existing_backups = [
            int(match.group(1))
            for match in (backup_pattern.match(str(p)) for p in file_path.parent.glob(f"{file_path.name}.bak_*"))
            if match
        ]
        
        next_num = max(existing_backups, default=-1) + 1
        backup_path = file_path.with_suffix(f"{file_path.suffix}.bak_{next_num:03d}")
        
        # Create backup
        shutil.copy2(file_path, backup_path)
        logger.info("coder.backup_created", 
                   original=str(file_path),
                   backup=str(backup_path))
        
        return backup_path

    def _cleanup_backup(self, backup_path: Optional[Path]) -> None:
        """Clean up backup file if it exists"""
        if backup_path and backup_path.exists():
            try:
                backup_path.unlink()
                logger.info("coder.backup_cleaned", backup=str(backup_path))
            except Exception as e:
                logger.warning("coder.backup_cleanup_failed",
                             backup=str(backup_path),
                             error=str(e))

    async def _process_changes(self, content: str, instructions: str) -> str:
        """Process changes using semantic iterator"""
        changes_config = {
            "pattern": "Extract each change from the instructions",
            "format": "json",
            "validation": {
                "requires_fields": ["type", "content", "location"]
            }
        }
        
        iterator = await self.iterator.iter_extract(instructions, changes_config)
        modified_content = content
        
        while iterator.has_next():
            change = next(iterator)
            merge_result = await self.merger.merge(modified_content, change["content"])
            if merge_result.success:
                modified_content = merge_result.content
                
        return modified_content

    async def transform(self, context: Dict[str, Any]) -> TransformResult:
        """Apply code changes with backup"""
        try:
            # Validate request
            error = self._validate_request(context)
            if error:
                logger.error("coder.invalid_request", error=error)
                return TransformResult(
                    success=False,
                    file_path=context.get("file_path", ""),
                    error=error
                )

            # Extract and validate change details
            details = await self._extract_change_details(context)
            file_path = Path(details["file_path"])
            
            # Create backup if file exists
            backup_path = self._create_backup(file_path)
            
            try:
                # Handle deletion
                if details["change_type"] == "delete":
                    if file_path.exists():
                        file_path.unlink()
                        logger.info("coder.file_deleted", file=str(file_path))
                    return TransformResult(
                        success=True,
                        file_path=str(file_path),
                        backup_path=str(backup_path) if backup_path else None,
                        action="deleted"
                    )

                # Get original content if file exists
                original = file_path.read_text() if file_path.exists() else ""
                
                # Process changes using semantic iterator and merger
                modified_content = await self._process_changes(original, details["instructions"])
                
                # Write modified content
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(modified_content)
                
                # If successful creation/modification, clean up backup
                if details["change_type"] == "create":
                    self._cleanup_backup(backup_path)
                    backup_path = None
                
                return TransformResult(
                    success=True,
                    file_path=str(file_path),
                    backup_path=str(backup_path) if backup_path else None,
                    action=details["change_type"]
                )
                
            except Exception as e:
                # Restore from backup on error
                if backup_path and backup_path.exists():
                    try:
                        shutil.copy2(backup_path, file_path)
                        logger.info("coder.backup_restored", 
                                  file=str(file_path),
                                  backup=str(backup_path))
                    except Exception as restore_error:
                        logger.error("coder.backup_restore_failed",
                                   error=str(restore_error))
                raise
                
        except Exception as e:
            logger.error("coder.transform_failed", error=str(e))
            return TransformResult(
                success=False,
                file_path=context.get("file_path", ""),
                error=str(e)
            )

    def _map_suggestion_to_action(self, suggestion: Dict[str, Any]) -> Dict[str, Any]:
        """Map architect suggestions to concrete actions"""
        return {
            "file_path": suggestion.get("file_path"),
            "change_type": suggestion.get("change_type", "modify"),
            "instructions": suggestion.get("suggested_approach")
        }

    async def process(self, context: Dict[str, Any]) -> AgentResponse:
        """Process a change request with proper validation"""
        try:
            logger.info("coder.processing_request", context_keys=list(context.keys()))
            
            # Handle special cases from architect
            if 'needs_clarification' in context:
                logger.info("coder.needs_clarification", question=context['needs_clarification'])
                return AgentResponse(
                    success=False,
                    data={},
                    error=f"Need clarification: {context['needs_clarification']}"
                )
                
            if 'needs_information' in context:
                logger.info("coder.needs_information", missing=context['needs_information'])
                return AgentResponse(
                    success=False,
                    data={},
                    error=f"Insufficient information: {', '.join(context['needs_information'])}"
                )
                
            if 'no_changes_needed' in context:
                logger.info("coder.no_changes_needed", reason=context['no_changes_needed'])
                return AgentResponse(
                    success=True,
                    data={"message": f"No changes needed: {context['no_changes_needed']}"},
                    error=None
                )
            
            # Handle architect suggestions format
            if 'suggestions' in context:
                suggestions = context['suggestions']
                if not suggestions:
                    logger.info("coder.no_suggestions")
                    return AgentResponse(
                        success=True,
                        data={"message": "No changes suggested"},
                        error=None
                    )
                actions = [self._map_suggestion_to_action(s) for s in suggestions]
            else:
                actions = context.get('actions', [])
                if not actions:
                    logger.info("coder.no_actions")
                    return AgentResponse(
                        success=True,
                        data={"message": "No actions provided"},
                        error=None
                    )

            # Process each action
            results = []
            for action in actions:
                try:
                    result = await self.transform(action)
                    if result.success:
                        results.append({
                            "status": "success",
                            "file_path": result.file_path,
                            "backup_path": result.backup_path,
                            "action": result.action
                        })
                        logger.info("coder.change_succeeded", 
                                  file=action.get('file_path'),
                                  type=action.get('change_type'))
                    else:
                        logger.warning("coder.change_failed",
                                     file=action.get('file_path'),
                                     error=result.error)
                        results.append({
                            "status": "failed",
                            "file_path": result.file_path,
                            "error": result.error
                        })

                except Exception as e:
                    logger.error("coder.action_failed",
                               action=action,
                               error=str(e))
                    results.append({
                        "status": "failed",
                        "file_path": action.get('file_path'),
                        "error": str(e)
                    })

            return AgentResponse(
                success=any(r["status"] == "success" for r in results),
                data={
                    "changes": results,
                    "message": f"Implemented {len([r for r in results if r['status'] == 'success'])} changes"
                },
                error=None if results else "No changes were processed"
            )
                
        except Exception as e:
            logger.error("coder.process_failed", error=str(e))
            return AgentResponse(
                success=False,
                data={},
                error=str(e)
            )