#!/usr/bin/env python3

import os
from pathlib import Path
import re

def fix_file_imports(file_path: Path) -> bool:
    """Fix imports in a file"""
    with open(file_path, 'r') as f:
        content = f.read()

    # Comprehensive list of import fixes
    fixes = [
        # Fix agents imports
        (r'from src\.discovery import', 'from src.agents.discovery import'),
        (r'from src\.solution_designer import', 'from src.agents.solution_designer import'),
        (r'from src\.coder import', 'from src.agents.coder import'),
        (r'from src\.assurance import', 'from src.agents.assurance import'),
        (r'from src\.base import', 'from src.agents.base import'),
        
        # Fix skills imports
        (r'from src\.semantic_extract import', 'from src.skills.semantic_extract import'),
        (r'from src\.skills\.shared\.types import', 'from src.skills.shared.types import'),
        (r'from src\.shared\.types import', 'from src.skills.shared.types import'),
        
        # Fix absolute to relative imports within packages
        (r'from src\.agents\.base import', 'from .base import'),
    ]

    modified = content
    made_changes = False
    
    for pattern, replacement in fixes:
        new_content = re.sub(pattern, replacement, modified)
        if new_content != modified:
            print(f"  Fixing in {file_path.name}:")
            print(f"    {pattern} -> {replacement}")
            modified = new_content
            made_changes = True

    if made_changes:
        with open(file_path, 'w') as f:
            f.write(modified)
        return True
    return False

def create_init_files():
    """Create all necessary __init__.py files with correct imports"""
    src_dir = Path('src')
    
    init_files = {
        src_dir / '__init__.py': '''"""Code refactoring tool package."""
from . import agents
from . import models
from . import skills
''',

        src_dir / 'agents' / '__init__.py': '''"""Agent modules."""
from .base import BaseAgent, LLMProvider, AgentResponse
from .intent_agent import IntentAgent
from .coder import Coder, MergeMethod
from .discovery import DiscoveryAgent
from .solution_designer import SolutionDesigner
from .assurance import AssuranceAgent
''',

        src_dir / 'models' / '__init__.py': '''"""Model definitions."""
from .intent import Intent, IntentStatus
''',

        src_dir / 'skills' / '__init__.py': '''"""Skill modules."""
from . import semantic_extract
from . import semantic_merge
from . import semantic_iterator
from . import codemod
from . import shared
''',

        src_dir / 'skills' / 'shared' / '__init__.py': '''"""Shared skill utilities."""
from . import types
'''
    }

    for path, content in init_files.items():
        path.parent.mkdir(exist_ok=True)
        with open(path, 'w') as f:
            f.write(content)
        print(f"✓ Created/Updated {path}")

def main():
    print("Fixing imports and updating package structure...")
    
    # Create/update all __init__.py files first
    create_init_files()
    
    # Fix imports in all Python files
    src_dir = Path('src')
    for py_file in src_dir.rglob("*.py"):
        if py_file.name != '__init__.py':
            if fix_file_imports(py_file):
                print(f"✓ Fixed imports in {py_file}")

    print("\nImport fixes complete! Now try:")
    print("python -m src.main refactor ./tests/test_projects/project1 'Add logging to all functions' -v")

if __name__ == "__main__":
    main()