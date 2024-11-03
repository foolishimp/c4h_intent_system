# src/agents/scoping.py

import os
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import subprocess
import sys
import yaml

from src.agents.base import BaseAgent
from src.models.intent import Intent
from src.config.handler import AgentConfig

class ScopingAgent(BaseAgent):
    """Agent responsible for analyzing project structure and determining scope"""

    def __init__(self, config: AgentConfig, skill_path: str):
        super().__init__(config)
        self.skill_path = skill_path
        if not os.path.exists(self.skill_path):
            raise FileNotFoundError(f"Required skill not found: {self.skill_path}")

    async def process_intent(self, intent: Intent) -> Intent:
        """Process a scoping intent"""
        try:
            if intent.type != "scope_analysis":
                raise ValueError(f"Invalid intent type for ScopingAgent: {intent.type}")

            project_path = intent.environment.get("project_path")
            if not project_path:
                raise ValueError("No project path provided in intent environment")

            # Run tartxt analysis
            scope_content = await self._analyze_project(project_path)
            
            # Parse and structure the analysis
            structured_analysis = self._structure_analysis(scope_content)
            
            # Update intent with structured analysis
            intent.context.update({
                "scope_analysis": structured_analysis,
                "analysis_timestamp": datetime.utcnow().isoformat(),
                "analyzed_path": project_path,
                "tools_used": ["tartxt"],
            })
            
            # Add summary metrics
            intent.context["analysis_metrics"] = self._calculate_metrics(structured_analysis)
            
            intent.status = "analysis_complete"
            return intent

        except Exception as e:
            return await self.handle_error(e, intent)

    async def _analyze_project(self, project_path: str) -> str:
        """Run project analysis using tartxt skill"""
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    self.skill_path,
                    "-x", "*.pyc,__pycache__,*.DS_Store",
                    "-o",
                    project_path
                ],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout
            
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to analyze project: {e.stderr}")

    def _structure_analysis(self, raw_content: str) -> Dict[str, Any]:
        """Convert raw tartxt output into structured analysis"""
        analysis = {
            "files": [],
            "directories": set(),
            "file_types": {},
            "manifest": []
        }
        
        # Parse the content
        sections = raw_content.split("==")
        for section in sections:
            if section.strip().startswith("Manifest"):
                analysis["manifest"] = [
                    line.strip() for line in section.split("\n") 
                    if line.strip() and "Manifest" not in line
                ]
                
            elif "File:" in section:
                file_info = {}
                for line in section.split("\n"):
                    if line.startswith("File:"):
                        file_info["path"] = line.split(":", 1)[1].strip()
                        analysis["directories"].add(str(Path(file_info["path"]).parent))
                    elif line.startswith("File Type:"):
                        file_type = line.split(":", 1)[1].strip()
                        file_info["type"] = file_type
                        analysis["file_types"][file_type] = analysis["file_types"].get(file_type, 0) + 1
                    elif line.startswith("Size:"):
                        file_info["size"] = int(line.split(":", 1)[1].split()[0])
                
                if file_info:
                    analysis["files"].append(file_info)
        
        # Convert directories set to sorted list
        analysis["directories"] = sorted(list(analysis["directories"]))
        
        return analysis

    def _calculate_metrics(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate summary metrics from the analysis"""
        return {
            "total_files": len(analysis["files"]),
            "total_directories": len(analysis["directories"]),
            "file_type_distribution": analysis["file_types"],
            "total_size": sum(f["size"] for f in analysis["files"]),
            "average_file_size": sum(f["size"] for f in analysis["files"]) / len(analysis["files"]) if analysis["files"] else 0
        }

    async def handle_error(self, error: Exception, intent: Intent) -> Intent:
        """Handle errors during intent processing"""
        error_intent = Intent(
            type="debug",
            description=f"Error in scope analysis: {str(error)}",
            environment=intent.environment,
            context={
                "original_intent": intent.dict(),
                "error": str(error),
                "error_type": type(error).__name__
            },
            criteria={"resolve_error": True},
            parent_id=intent.id,
            status="error"
        )
        return error_intent