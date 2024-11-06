# src/skills/shared/types.py
from typing import Dict, Any, Optional
from dataclass import dataclass

@dataclass
class InterpretResult:
    """Result from semantic interpretation"""
    data: Any
    raw_response: str
    context: Dict[str, Any]
