#!/usr/bin/env python3

import os
import shutil
from pathlib import Path
import re
import subprocess
import sys

class InPlaceMigrator:
    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.src_dir = project_dir / 'src'
        
    def fix_imports(self):
        """Update relative imports to absolute while preserving git history"""
        print("\nUpdating imports to absolute paths...")
        for py_file in self.src_dir.rglob("*.py"):
            with open(py_file, 'r') as f:
                content = f.read()

            # Replace relative imports
            modified = re.sub(
                r'from \.\.(.*?) import',
                r'from src.\1 import',
                content
            )
            modified = re.sub(
                r'from \.(.*?) import',
                r'from src.\1 import',
                modified
            )

            if modified != content:
                print(f"✓ Updated imports in {py_file.relative_to(self.project_dir)}")
                with open(py_file, 'w') as f:
                    f.write(modified)

    def update_setup_files(self):
        """Create or update package files while preserving existing ones"""
        print("\nUpdating package configuration...")
        
        # Update setup.py if it doesn't exist
        setup_path = self.project_dir / 'setup.py'
        if not setup_path.exists():
            setup_content = '''from setuptools import setup, find_packages

setup(
    name="coder4h",
    packages=find_packages(),
    package_dir={"": "."},
    include_package_data=True,
    install_requires=[
        "litellm>=1.52.3",
        "openai>=1.13.3",
        "anthropic>=0.18.1",
        "google-generativeai>=0.3.2",
        "libcst>=1.2.0",
        "pydantic>=2.6.3",
        "structlog>=24.1.0",
        "python-dotenv>=1.0.1",
        "PyYAML>=6.0.1",
    ],
    entry_points={
        "console_scripts": [
            "coder4h=src.main:main",
        ],
    },
)
'''
            setup_path.write_text(setup_content)
            print("✓ Created setup.py")

        # Update pyproject.toml if it doesn't exist
        pyproject_path = self.project_dir / 'pyproject.toml'
        if not pyproject_path.exists():
            pyproject_content = '''[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "coder4h"
version = "0.1.0"
description = "AI-powered code refactoring tool"
requires-python = ">=3.11"
'''
            pyproject_path.write_text(pyproject_content)
            print("✓ Created pyproject.toml")

        # Ensure requirements.txt exists
        req_path = self.project_dir / 'requirements.txt'
        if not req_path.exists():
            shutil.copy2(self.src_dir / 'requirements.txt', req_path)
            print("✓ Moved requirements.txt to root")

    def update_cli(self):
        """Update main.py to work as both module and CLI"""
        main_path = self.src_dir / 'main.py'
        if main_path.exists():
            with open(main_path, 'r') as f:
                content = f.read()
            
            # Only modify if needed
            if 'def main():' not in content:
                modified = content.replace('if __name__ == "__main__":', '''
def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(description="AI-powered code refactoring tool")
    parser.add_argument('command', choices=['refactor'])
    parser.add_argument('project_path', type=Path)
    parser.add_argument('intent', type=str)
    parser.add_argument('--merge-strategy', 
                       choices=[method.value for method in RefactoringStrategy],
                       default=RefactoringStrategy.CODEMOD.value,
                       help="Strategy for merging code changes")
    parser.add_argument('--max-iterations', type=int, default=3)
    
    args = parser.parse_args()
    
    try:
        result = process_refactoring(args)
        sys.exit(0 if result['status'] == 'success' else 1)
    except KeyboardInterrupt:
        print("\\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\\nUnexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":''')
                
                with open(main_path, 'w') as f:
                    f.write(modified)
                print("✓ Updated main.py with CLI handling")

    def setup_package(self):
        """Set up the package for local development"""
        print("\nSetting up package for development...")
        
        # Upgrade pip first
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', 'pip'], 
                     check=True)
        
        # Install development dependencies
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'wheel', 'setuptools>=61.0'], 
                     check=True)
        
        # Install package in development mode
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-e', '.'], 
                     cwd=str(self.project_dir), check=True)
        
        print("✓ Installed package in development mode")

    def migrate(self):
        """Run the in-place migration"""
        print("\nStarting in-place migration...")
        try:
            self.fix_imports()
            self.update_setup_files()
            self.update_cli()
            self.setup_package()
            
            print("\n✨ Migration completed successfully!")
            print("\nYou can now run the tool using:")
            print("1. As a module: python -m src.main refactor <project_path> \"<intent>\"")
            print("2. As a command: coder4h refactor <project_path> \"<intent>\"")
            
        except Exception as e:
            print(f"\n❌ Error during migration: {e}")
            raise

if __name__ == "__main__":
    project_dir = Path.cwd()
    if not (project_dir / 'src').exists():
        print("Error: No src directory found in current directory")
        sys.exit(1)
        
    migrator = InPlaceMigrator(project_dir)
    migrator.migrate()
