"""
Basic semantic iterator tests.
Path: tests/test_semantic_iterator_basic.py 
"""

import pytest
import json
import structlog
from src.skills.semantic_iterator import SemanticIterator, SemanticPrompt

logger = structlog.get_logger()

CHANGE_DATA = {
    "changes": [
        {
            "file_path": "src/agents/intent_agent.py",
            "type": "modify", 
            "description": "Fix solution designer state tracking",
            "diff": """diff --git a/src/agents/intent_agent.py b/src/agents/intent_agent.py
@@ -284,7 +284,8 @@ class IntentAgent:
     result.error
)"""
        },
        {
            "file_path": "src/agents/base.py",
            "type": "modify",
            "description": "Add error handling",
            "diff": """diff --git a/src/agents/base.py b/src/agents/base.py
@@ -51,6 +51,7 @@ class BaseAgent:
     try:
         result = await process()
         return result
+    except Exception as e:
+        logger.error("process failed", error=str(e))"""
        }
    ]
}

@pytest.mark.asyncio
async def test_llm_extraction(test_config):
    """Test iteration over changes"""
    iterator = SemanticIterator(
        config={
            'provider': 'anthropic',
            'model': test_config['llm_config']['default_model'],
            'temperature': 0,
            'config': test_config
        },
        content=CHANGE_DATA,
        prompt = SemanticPrompt(
            instruction="""Extract a list of code changes where each item contains:
            - file_path: The target file path
            - type: The type of change (modify/create/delete) 
            - description: Brief description of the change
            - diff: The git-style diff content

            Return as JSON array with these exact fields.""",
            format="json")
    )
    
    logger.info("iterator_input", data=json.dumps(CHANGE_DATA, indent=2))
    
    changes = []
    async for change in iterator:
        changes.append(change)
    
    logger.info("extracted_changes", changes=json.dumps(changes, indent=2))
    
    assert len(changes) == 2
    assert all(isinstance(c, dict) for c in changes)
    assert all(k in changes[0] for k in ['file_path', 'type', 'description', 'diff'])