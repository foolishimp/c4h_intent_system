# src/agents/discovery.py

import os
from pathlib import Path
from typing import Dict, Any
from datetime import datetime
import subprocess
import sys
import structlog

from src.agents.base import BaseAgent
from src.models.intent import Intent, ResolutionState
from src.config import Config

class DiscoveryAgent(BaseAgent):
    """Agent responsible for discovering project structure, dependencies, and determining scope.
    
    The discovery process involves:
    1. Analyzing project structure
    2. Identifying key components and patterns
    3. Determining project boundaries and dependencies
    4. Creating a comprehensive project map
    """

    def __init__(self, config: Config):
        """Initialize the discovery agent with configuration"""
        super().__init__(config)
        try:
            # Access Pydantic model fields directly
            skill_config = config.skills.get("tartxt")
            if not skill_config:
                raise ValueError("Missing required skill config: tartxt")
                
            self.skill_path = skill_config.path
            if not self.skill_path.exists():
                raise FileNotFoundError(f"Required skill not found: {self.skill_path}")
                
            self.logger = structlog.get_logger()
            
        except Exception as e:
            raise ValueError(f"Discovery agent initialization failed: {str(e)}")

    async def process_intent(self, intent: Intent) -> Intent:
        """Process a discovery intent
        
        Args:
            intent: The intent to process
            
        Returns:
            Processed intent with results
        
        Raises:
            ValueError: If the intent type is invalid
        """
        try:
            if intent.type != "project_discovery":
                raise ValueError(f"Invalid intent type for DiscoveryAgent: {intent.type}")

            # Update resolution state
            intent.update_resolution(ResolutionState.ANALYZING_INTENT)
            
            project_path = intent.environment.get("project_path")
            if not project_path:
                raise ValueError("No project path provided in intent environment")

            # Run project discovery
            discovery_content = await self._discover_project(project_path)
            
            # Parse and structure results
            structured_discovery = self._structure_discovery(discovery_content)
            
            # Add results to intent context
            intent.context.update({
                "discovery_results": structured_discovery,
                "discovery_timestamp": datetime.utcnow().isoformat(),
                "discovered_path": project_path,
                "discovery_tools": ["tartxt"]
            })
            
            # Add discovery metrics
            intent.context["discovery_metrics"] = self._calculate_metrics(structured_discovery)
            
            # Set project scope
            intent.context["project_scope"] = self._determine_scope(structured_discovery)
            
            # Update resolution state
            intent.update_resolution(ResolutionState.SKILL_SUCCESS)
            
            return intent

        except Exception as e:
            return await self.handle_error(e, intent)

    async def _discover_project(self, project_path: str) -> str:
        """Run project discovery using tartxt skill"""
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(self.skill_path),  # Convert Path to string
                    "--exclude", "*.pyc,__pycache__,*.DS_Store",
                    "--output",
                    project_path
                ],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout
            
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to discover project: {e.stderr}")

    def _structure_discovery(self, raw_content: str) -> Dict[str, Any]:
        """Convert raw tartxt output into structured discovery results"""
        discovery = {
            "files": [],
            "directories": set(),
            "file_types": {},
            "manifest": [],
            "patterns": {},
            "dependencies": set()
        }
        
        # Parse the content
        sections = raw_content.split("==")
        for section in sections:
            if section.strip().startswith("Manifest"):
                discovery["manifest"] = [
                    line.strip() for line in section.split("\n") 
                    if line.strip() and "Manifest" not in line
                ]
                
            elif "File:" in section:
                file_info = {}
                for line in section.split("\n"):
                    if line.startswith("File:"):
                        file_info["path"] = line.split(":", 1)[1].strip()
                        discovery["directories"].add(str(Path(file_info["path"]).parent))
                    elif line.startswith("File Type:"):
                        file_type = line.split(":", 1)[1].strip()
                        file_info["type"] = file_type
                        discovery["file_types"][file_type] = discovery["file_types"].get(file_type, 0) + 1
                    elif line.startswith("Size:"):
                        file_info["size"] = int(line.split(":", 1)[1].split()[0])
                
                if file_info:
                    discovery["files"].append(file_info)
        
        # Convert sets to sorted lists
        discovery["directories"] = sorted(list(discovery["directories"]))
        discovery["dependencies"] = sorted(list(discovery["dependencies"]))
        
        return discovery

    def _calculate_metrics(self, discovery: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate metrics from the discovery results"""
        return {
            "total_files": len(discovery["files"]),
            "total_directories": len(discovery["directories"]),
            "file_type_distribution": discovery["file_types"],
            "total_size": sum(f["size"] for f in discovery["files"]),
            "average_file_size": sum(f["size"] for f in discovery["files"]) / len(discovery["files"]) if discovery["files"] else 0,
            "identified_patterns": len(discovery.get("patterns", {})),
            "detected_dependencies": len(discovery.get("dependencies", set()))
        }

    def _determine_scope(self, discovery: Dict[str, Any]) -> Dict[str, Any]:
        """Determine project scope based on discovery results"""
        return {
            "root_path": min(discovery["directories"], key=len) if discovery["directories"] else None,
            "included_paths": discovery["directories"],
            "excluded_patterns": ["*.pyc", "__pycache__", "*.DS_Store"],
            "primary_language": max(discovery["file_types"].items(), key=lambda x: x[1])[0] if discovery["file_types"] else None,
            "estimated_complexity": self._estimate_complexity(discovery),
            "boundaries": {
                "internal": [d for d in discovery["directories"] if "test" not in d.lower()],
                "test": [d for d in discovery["directories"] if "test" in d.lower()],
                "third_party": list(discovery.get("dependencies", set()))
            }
        }

    def _estimate_complexity(self, discovery: Dict[str, Any]) -> str:
        """Estimate project complexity based on discovery metrics"""
        total_files = len(discovery["files"])
        directory_depth = max(d.count(os.sep) for d in discovery["directories"]) if discovery["directories"] else 0
        
        if total_files < 10 and directory_depth < 3:
            return "simple"
        elif total_files < 50 and directory_depth < 5:
            return "moderate"
        else:
            return "complex"