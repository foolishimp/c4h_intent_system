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

@dataclass
class ExtractConfig:
    """Configuration for semantic extraction"""
    instruction: str  # Pattern/prompt for extraction
    format: str = "json"  # Expected output format
    strict_json: bool = True
    
    def __post_init__(self):
        """Add format requirements to instruction if strict"""
        if self.strict_json and 'json' in self.format.lower():
            # Build complete instruction with format requirements
            self.instruction = f"""
{self.instruction}

RESPONSE FORMAT:
Your response must be a valid JSON object with these requirements:
1. Fields must match the example structure exactly
2. Use null for any missing or unavailable values
3. Empty arrays [] are acceptable for no values
4. Do not use empty strings "" for missing values
5. All optional fields must be present but can be null

Example format showing null handling:
{{
    "attr1": "Value String",
    "attr2": [],  // Empty array for no colors
    "attr3": ["feature1", "feature2"],
    "attr4": null  // null for unknown location
}}

{self.instruction}
"""