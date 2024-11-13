#!/usr/bin/env python3

import os
import shutil
from pathlib import Path
import re
import subprocess
import sys
import tempfile

class PackageMigrator:
    def __init__(self, source_dir: Path, package_name: str = "coder4h"):
        self.source_dir = source_dir
        self.package_name = package_name
        self.new_root = source_dir.parent / package_name
        self.package_dir = self.new_root / package_name

    def backup_existing(self):
        """Create backup of existing code"""
        timestamp = subprocess.check_output(['date', '+%Y%m%d_%H%M%S']).decode().strip()
        backup_dir = self.source_dir.parent / f"backup_{timestamp}"
        shutil.copytree(self.source_dir, backup_dir)
        print(f"✓ Created backup at: {backup_dir}")
        return backup_dir

    def setup_directory_structure(self):
        """Create new package directory structure"""
        # Create new directories
        self.new_root.mkdir(exist_ok=True)
        self.package_dir.mkdir(exist_ok=True)
        
        # Move src contents to package directory
        for item in self.source_dir.iterdir():
            if item.name not in ['.git', '.gitignore', '.env', 'venv']:
                dest = self.package_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest)
        
        # Move tests directory up
        if (self.source_dir / 'tests').exists():
            shutil.move(str(self.source_dir / 'tests'), str(self.new_root / 'tests'))

        print("✓ Created new directory structure")

    def fix_imports(self):
        """Update relative imports to absolute"""
        for py_file in self.package_dir.rglob("*.py"):
            with open(py_file, 'r') as f:
                content = f.read()

            # Replace relative imports
            content = re.sub(
                r'from \.\.(.*?) import',
                f'from {self.package_name}.\\1 import',
                content
            )
            content = re.sub(
                r'from \.(.*?) import',
                f'from {self.package_name}.\\1 import',
                content
            )

            with open(py_file, 'w') as f:
                f.write(content)

        print("✓ Updated imports to absolute paths")

    def create_package_files(self):
        """Create package configuration files"""
        # Create pyproject.toml
        pyproject_content = '''[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "coder4h"
version = "0.1.0"
description = "AI-powered code refactoring tool"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "litellm>=1.52.3",
    "openai>=1.13.3",
    "anthropic>=0.18.1",
    "google-generativeai>=0.3.2",
    "libcst>=1.2.0",
    "pydantic>=2.6.3",
    "structlog>=24.1.0",
    "python-dotenv>=1.0.1",
    "PyYAML>=6.0.1",
]

[project.scripts]
coder4h = "coder4h.cli:main"
'''
        (self.new_root / 'pyproject.toml').write_text(pyproject_content)

        # Create setup.py
        setup_content = '''from setuptools import setup, find_packages

setup(
    name="coder4h",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        line.strip()
        for line in open("requirements.txt")
        if line.strip() and not line.startswith("#")
    ],
    entry_points={
        "console_scripts": [
            "coder4h=coder4h.cli:main",
        ],
    },
)
'''
        (self.new_root / 'setup.py').write_text(setup_content)

        # Create cli.py
        cli_content = '''import argparse
from pathlib import Path
import sys
from .main import process_intent
from .agents.coder import MergeMethod as RefactoringStrategy

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
        result = process_intent(args)
        sys.exit(0 if result['status'] == 'success' else 1)
    except KeyboardInterrupt:
        print("\\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\\nUnexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
'''
        (self.package_dir / 'cli.py').write_text(cli_content)

        # Ensure __init__.py files exist
        for dir_path in [self.package_dir, self.package_dir / 'agents', 
                        self.package_dir / 'models', self.package_dir / 'skills']:
            init_file = dir_path / '__init__.py'
            if not init_file.exists():
                init_file.touch()

        # Move requirements.txt if it exists
        if (self.source_dir / 'requirements.txt').exists():
            shutil.copy2(self.source_dir / 'requirements.txt', self.new_root / 'requirements.txt')

        print("✓ Created package configuration files")

    def setup_venv(self):
        """Set up new virtual environment"""
        venv_dir = self.new_root / 'venv'
        subprocess.run([sys.executable, '-m', 'venv', str(venv_dir)], check=True)
        
        # Get pip path
        pip_path = venv_dir / 'bin' / 'pip'
        
        # Install requirements
        subprocess.run([str(pip_path), 'install', '-e', '.'], 
                     cwd=str(self.new_root), check=True)
        print("✓ Created virtual environment and installed package")

    def migrate(self):
        """Run full migration process"""
        print("\nStarting migration process...")
        try:
            backup_dir = self.backup_existing()
            self.setup_directory_structure()
            self.fix_imports()
            self.create_package_files()
            self.setup_venv()
            
            print("\n✨ Migration completed successfully!")
            print(f"\nNext steps:")
            print(f"1. cd {self.new_root}")
            print(f"2. source venv/bin/activate")
            print(f"3. coder4h refactor <project_path> \"<intent>\"")
            print(f"\nBackup of original code: {backup_dir}")
            
        except Exception as e:
            print(f"\n❌ Error during migration: {e}")
            print(f"Original code backup: {backup_dir}")
            raise

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python migrate.py <source_directory>")
        sys.exit(1)
        
    source_dir = Path(sys.argv[1]).resolve()
    if not source_dir.exists():
        print(f"Error: Source directory does not exist: {source_dir}")
        sys.exit(1)
        
    migrator = PackageMigrator(source_dir)
    migrator.migrate()
