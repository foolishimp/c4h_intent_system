import pytest
from pathlib import Path
import structlog
from src.agents.base import LLMProvider
from src.agents.coder import Coder

SAMPLE_CHANGES = {
    'raw_output': {
        'changes': [{
            'file_path': 'tests/test_projects/project1/sample.py',
            'type': 'modify',
            'description': 'Add logging to functions and replace prints with logs',
            'diff': '''diff --git a/test.py b/test.py
--- a/test.py
+++ b/test.py
@@ -1,10 +1,14 @@
+import logging
+
+logging.basicConfig(level=logging.INFO)
+
 def greet(name):
-    print(f"Hello, {name}!")
+    logging.info(f"Hello, {name}!")
 
 def calculate_sum(numbers):
+    logging.info(f"Calculating sum of numbers: {numbers}")
     return sum(numbers)
 
 if __name__ == "__main__":
     greet("World")
-    print(calculate_sum([1, 2, 3, 4, 5]))
+    result = calculate_sum([1, 2, 3, 4, 5])
+    logging.info(f"Sum result: {result}")'''
        }]
    }
}

ORIGINAL_CODE = '''def greet(name):
    print(f"Hello, {name}!")

def calculate_sum(numbers):
    return sum(numbers)

if __name__ == "__main__":
    greet("World")
    print(calculate_sum([1, 2, 3, 4, 5]))'''

@pytest.fixture
def test_file(tmp_path):
    file = tmp_path / "test.py"
    file.write_text(ORIGINAL_CODE)
    return file

@pytest.mark.asyncio 
async def test_coder_process(test_file):
    coder = Coder(provider=LLMProvider.ANTHROPIC)
    
    changes = {'changes': SAMPLE_CHANGES}
    
    result = await coder.process(changes)
    assert result.success
    assert len(result.data['changes']) == 1
    assert result.data['changes'][0]['status'] == 'success'
