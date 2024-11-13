#!/usr/bin/env python3

import os
from pathlib import Path
import re
import ast
from typing import List, Set

def get_imports(file_path: Path) -> Set[str]:
    """Extract all imports from a Python file"""
    with open(file_path) as f:
        try:
            tree = ast.parse(f.read())
        except:
            return set()

    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                imports.add(name.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module if node.module else ''
            if node.level > 0:  # relative import
                continue
            imports.add(module)
    return imports

def fix_file_imports(file_path: Path, show_changes: bool = True) -> bool:
    """Fix imports in a file"""
    with open(file_path, 'r') as f:
        content = f.read()

    # List of incorrect imports and their fixes
    fixes = [
        (r'from src\.discovery import', 'from src.agents.discovery import'),
        (r'from src\.solution_designer import', 'from src.agents.solution_designer import'),
        (r'from src\.coder import', 'from src.agents.coder import'),
        (r'from src\.assurance import', 'from src.agents.assurance import'),
    ]

    modified = content
    made_changes = False
    
    for pattern, replacement in fixes:
        new_content = re.sub(pattern, replacement, modified)
        if new_content != modified:
            if show_changes:
                print(f"  Fixing in {file_path.name}:")
                print(f"    {pattern} -> {replacement}")
            modified = new_content
            made_changes = True

    if made_changes:
        with open(file_path, 'w') as f:
            f.write(modified)
        return True
    return False

def main():
    src_dir = Path('src')
    print("Analyzing and fixing imports...")
    
    # Fix known import issues
    for py_file in src_dir.rglob("*.py"):
        if fix_file_imports(py_file):
            print(f"✓ Fixed imports in {py_file}")
    
    # Verify imports
    print("\nVerifying all imports are valid...")
    valid_modules = {
        'src',
        'src.agents',
        'src.models',
        'src.skills',
        'src.agents.discovery',
        'src.agents.intent_agent',
        'src.agents.coder',
        'src.agents.base',
        'src.agents.solution_designer',
        'src.agents.assurance',
        'src.models.intent',
        'src.skills.semantic_extract',
        'src.skills.semantic_merge',
        'src.skills.semantic_iterator',
        'src.skills.codemod',
    }

    all_imports = set()
    for py_file in src_dir.rglob("*.py"):
        imports = get_imports(py_file)
        for imp in imports:
            if imp.startswith('src.'):
                if imp not in valid_modules:
                    print(f"Warning: Invalid import '{imp}' in {py_file}")
                all_imports.add(imp)

    # Update __init__.py files to expose the correct modules
    with open(src_dir / 'agents' / '__init__.py', 'w') as f:
        f.write('''"""Agent modules."""
from src.agents.base import BaseAgent, LLMProvider, AgentResponse
from src.agents.intent_agent import IntentAgent
from src.agents.coder import Coder, MergeMethod
from src.agents.discovery import DiscoveryAgent
from src.agents.solution_designer import SolutionDesigner
from src.agents.assurance import AssuranceAgent
''')

    print("\nUpdated __init__ files with correct exports")
    print("\nTry running again:")
    print("python -m src.main refactor ./tests/test_projects/project1 'Add logging to all functions' -v")

if __name__ == "__main__":
    main()
