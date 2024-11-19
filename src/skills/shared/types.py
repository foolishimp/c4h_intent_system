# src/skills/shared/types.py
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field

@dataclass
class InterpretResult:
    """Result from semantic interpretation"""
    data: Any
    raw_response: str
    context: Dict[str, Any]

@dataclass
class ExtractConfig:
    """Configuration for semantic extraction"""
    instruction: str  # Pattern/prompt for extraction
    format: str = "json"  # Expected output format
    filters: Optional[List[Callable[[Any], bool]]] = field(default_factory=list)
    sort_key: Optional[str] = None
    validation: Optional[Dict[str, Any]] = field(default_factory=dict)