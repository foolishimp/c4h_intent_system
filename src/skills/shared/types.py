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
    list_fields: List[str] = field(default_factory=lambda: ['items', 'changes', 'results'])  # Fields to check for lists
    strict_json: bool = True  # Whether to require strict JSON or allow fuzzy matching

    def __post_init__(self):
        """Add JSON requirements to instruction if strict"""
        if self.strict_json and 'json' in self.format.lower():
            self.instruction = f"""
{self.instruction}

RESPONSE FORMAT:
Your response must be a valid JSON array, starting with '[' and ending with ']'.
Do not include any text before or after the JSON array.

Example response:
[
    {{
        "field1": "value1",
        "field2": "value2"
    }},
    {{
        "field1": "value3",
        "field2": "value4"
    }}
]"""