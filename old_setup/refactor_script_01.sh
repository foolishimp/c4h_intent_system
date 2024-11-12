#!/bin/bash

# Remove existing files and directories that we don't need
echo "Cleaning up existing files..."
rm -rf src/agents/orchestration.py
rm -rf src/models/intent_lineage.py
rm -rf src/models/intent_factory.py
rm -rf src/app.py
rm -rf src/cli.py
rm -rf tests/unit
rm -rf tests/integration
rm -rf tests/test_project

# Create new directory structure
echo "Creating new directory structure..."
mkdir -p src/agents
mkdir -p src/models
mkdir -p src/skills
mkdir -p tests/test_projects/project1
mkdir -p tests/test_projects/project2
mkdir -p config

# Create initial Python files
echo "Creating initial Python files..."

# src/models/intent.py
cat > src/models/intent.py << 'EOF'
# src/models/intent.py

from uuid import UUID, uuid4
from enum import Enum
from typing import Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field

class IntentStatus(str, Enum):
    """Status of an intent through its lifecycle"""
    CREATED = "created"
    ANALYZING = "analyzing"
    TRANSFORMING = "transforming"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"

class Intent(BaseModel):
    """Simple intent model for code transformations"""
    id: UUID = Field(default_factory=uuid4)
    description: str
    project_path: str
    status: IntentStatus = IntentStatus.CREATED
    context: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    error: Optional[str] = None

    class Config:
        frozen = True
EOF

# src/agents/base.py
cat > src/agents/base.py << 'EOF'
# src/agents/base.py

from typing import Dict, Any, Optional
import autogen
from pydantic import BaseModel
import structlog

logger = structlog.get_logger()

class AgentConfig(BaseModel):
    """Configuration for AutoGen agent"""
    name: str
    model: str = "gpt-4"
    temperature: float = 0
    system_message: str

class BaseAgent:
    """Base class for all agents in the system"""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.logger = logger.bind(agent=config.name)
        
        # Initialize AutoGen agent
        self.agent = autogen.AssistantAgent(
            name=config.name,
            llm_config={
                "config_list": [{
                    "model": config.model,
                    "temperature": config.temperature,
                }],
            },
            system_message=config.system_message
        )
    
    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Process a request - to be implemented by concrete agents"""
        raise NotImplementedError()
EOF

# src/agents/discovery.py
cat > src/agents/discovery.py << 'EOF'
# src/agents/discovery.py

from typing import Dict, Any
from pathlib import Path
import subprocess
import sys
import structlog
from .base import BaseAgent, AgentConfig

class DiscoveryAgent(BaseAgent):
    """Agent responsible for project discovery using tartxt"""
    
    def __init__(self):
        super().__init__(AgentConfig(
            name="discovery",
            system_message="""You are a discovery agent that analyzes Python project structure.
            Your role is to scan projects and identify files for potential modifications."""
        ))
        self.logger = structlog.get_logger()

    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Process project discovery request"""
        project_path = context.get("project_path")
        if not project_path:
            raise ValueError("No project path provided")
            
        # Run tartxt for project discovery
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "src/skills/tartxt.py",
                    "--exclude", "*.pyc,__pycache__,*.DS_Store",
                    "--output",
                    project_path
                ],
                capture_output=True,
                text=True,
                check=True
            )
            return {"discovery_output": result.stdout}
            
        except subprocess.CalledProcessError as e:
            self.logger.error("discovery.failed", error=str(e))
            raise
EOF

# src/agents/analysis.py
cat > src/agents/analysis.py << 'EOF'
# src/agents/analysis.py

from typing import Dict, Any
from .base import BaseAgent, AgentConfig

class AnalysisAgent(BaseAgent):
    """Agent responsible for analyzing code and planning transformations"""
    
    def __init__(self):
        super().__init__(AgentConfig(
            name="analyzer",
            system_message="""You are an analysis agent that plans code transformations.
            Your role is to:
            1. Understand the requested changes
            2. Analyze the project structure
            3. Plan specific code modifications
            4. Provide detailed transformation instructions"""
        ))

    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Process code analysis request"""
        project_content = context.get("discovery_output")
        intent_description = context.get("intent_description")
        
        if not project_content or not intent_description:
            raise ValueError("Missing required context")
            
        # Use AutoGen for analysis
        analysis_prompt = f"""
        Given the following project structure:
        {project_content}
        
        And the transformation request:
        {intent_description}
        
        Provide a detailed plan for code modifications including:
        1. Files to modify
        2. Specific changes for each file
        3. Order of operations
        4. Validation requirements
        """
        
        response = await self.agent.generate_response(analysis_prompt)
        return {"transformation_plan": response}
EOF

# src/agents/refactor.py
cat > src/agents/refactor.py << 'EOF'
# src/agents/refactor.py

from typing import Dict, Any
from pathlib import Path
from .base import BaseAgent, AgentConfig

class RefactorAgent(BaseAgent):
    """Agent responsible for applying code transformations"""
    
    def __init__(self):
        super().__init__(AgentConfig(
            name="refactor",
            system_message="""You are a refactoring agent that applies code transformations.
            Your role is to safely modify code according to transformation plans."""
        ))

    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Process code transformation request"""
        plan = context.get("transformation_plan")
        project_path = context.get("project_path")
        
        if not plan or not project_path:
            raise ValueError("Missing required context")
            
        # Execute transformations using codemod skill
        # Implement transformation logic here
        return {"modified_files": []}
EOF

# src/agents/assurance.py
cat > src/agents/assurance.py << 'EOF'
# src/agents/assurance.py

from typing import Dict, Any
import py_compile
from pathlib import Path
from .base import BaseAgent, AgentConfig

class AssuranceAgent(BaseAgent):
    """Agent responsible for validating code changes"""
    
    def __init__(self):
        super().__init__(AgentConfig(
            name="assurance",
            system_message="""You are an assurance agent that validates code changes.
            Your role is to verify that modifications maintain code integrity."""
        ))

    async def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Process validation request"""
        modified_files = context.get("modified_files", [])
        project_path = context.get("project_path")
        
        if not project_path:
            raise ValueError("Missing project path")
            
        # Basic validation: Try to compile all Python files
        results = []
        for file_path in modified_files:
            try:
                py_compile.compile(file_path, doraise=True)
                results.append({"file": file_path, "status": "success"})
            except Exception as e:
                results.append({"file": file_path, "status": "failed", "error": str(e)})
                
        return {"validation_results": results}
EOF

# src/skills/codemod.py
cat > src/skills/codemod.py << 'EOF'
# src/skills/codemod.py

import ast
from typing import Dict, Any, List
from pathlib import Path

class CodeTransformation:
    """Represents a code transformation to be applied"""
    def __init__(self, source_file: str, changes: Dict[str, Any]):
        self.source_file = source_file
        self.changes = changes

class CodeModifier(ast.NodeTransformer):
    """AST transformer for code modifications"""
    def __init__(self, changes: Dict[str, Any]):
        self.changes = changes

    def visit_FunctionDef(self, node):
        """Example: Visit function definitions"""
        # Implement transformation logic here
        return node

def apply_transformation(transformation: CodeTransformation) -> str:
    """Apply a code transformation and return modified source"""
    # Read source file
    with open(transformation.source_file, 'r') as f:
        source = f.read()
    
    # Parse AST
    tree = ast.parse(source)
    
    # Apply transformations
    modifier = CodeModifier(transformation.changes)
    modified_tree = modifier.visit(tree)
    
    # Generate modified source
    return ast.unparse(modified_tree)

def save_transformation(source_file: str, modified_source: str) -> None:
    """Save transformed code back to file"""
    backup_file = source_file + '.bak'
    Path(backup_file).write_text(Path(source_file).read_text())
    Path(source_file).write_text(modified_source)
EOF

# src/main.py
cat > src/main.py << 'EOF'
# src/main.py

import asyncio
import typer
from pathlib import Path
import structlog
from typing import Optional

from agents.discovery import DiscoveryAgent
from agents.analysis import AnalysisAgent
from agents.refactor import RefactorAgent
from agents.assurance import AssuranceAgent
from models.intent import Intent, IntentStatus

app = typer.Typer()
logger = structlog.get_logger()

async def process_intent(intent: Intent) -> Dict[str, Any]:
    """Process an intent through the agent pipeline"""
    try:
        # Discovery phase
        discovery_agent = DiscoveryAgent()
        discovery_result = await discovery_agent.process({
            "project_path": intent.project_path
        })
        
        # Analysis phase
        analysis_agent = AnalysisAgent()
        analysis_result = await analysis_agent.process({
            "discovery_output": discovery_result["discovery_output"],
            "intent_description": intent.description
        })
        
        # Refactor phase
        refactor_agent = RefactorAgent()
        refactor_result = await refactor_agent.process({
            "transformation_plan": analysis_result["transformation_plan"],
            "project_path": intent.project_path
        })
        
        # Assurance phase
        assurance_agent = AssuranceAgent()
        assurance_result = await assurance_agent.process({
            "modified_files": refactor_result["modified_files"],
            "project_path": intent.project_path
        })
        
        return {
            "status": "success",
            "results": {
                "discovery": discovery_result,
                "analysis": analysis_result,
                "refactor": refactor_result,
                "assurance": assurance_result
            }
        }
        
    except Exception as e:
        logger.exception("intent.processing_failed")
        return {
            "status": "failed",
            "error": str(e)
        }

@app.command()
def refactor(
    project_path: str,
    description: str,
    verbose: bool = typer.Option(False, "--verbose", "-v")
):
    """Refactor a Python project based on a description"""
    # Configure logging
    log_level = "DEBUG" if verbose else "INFO"
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(log_level)
    )
    
    # Create and process intent
    intent = Intent(
        description=description,
        project_path=project_path
    )
    
    # Run processing
    result = asyncio.run(process_intent(intent))
    
    # Show results
    if result["status"] == "success":
        typer.echo(f"✨ Refactoring completed successfully!")
    else:
        typer.echo(f"❌ Refactoring failed: {result['error']}", err=True)

if __name__ == "__main__":
    app()
EOF

# config/system_config.yml
cat > config/system_config.yml << 'EOF'
# Minimal configuration for MVP

# OpenAI Configuration
openai:
  api_key_env: OPENAI_API_KEY
  model: gpt-4
  temperature: 0
  timeout: 120

# Agent Configuration
agents:
  discovery:
    name: discovery_agent
    model: gpt-4
    temperature: 0
  
  analysis:
    name: analysis_agent
    model: gpt-4
    temperature: 0
  
  refactor:
    name: refactor_agent
    model: gpt-4
    temperature: 0
  
  assurance:
    name: assurance_agent
    model: gpt-4
    temperature: 0

# Skill Configuration
skills:
  tartxt:
    path: src/skills/tartxt.py
    exclude_patterns:
      - "*.pyc"
      - "__pycache__"
      - "*.DS_Store"
    max_file_size: 10485760
EOF

# Create reference.txt with implementation notes
cat > reference.txt << 'EOF'
MVP Intent Architecture Implementation Notes

1. Command Line Usage:
   python -m src.main refactor <project_path> "<description>" [-v]

2. Example Commands:
   - Add logging:
     python -m src.main refactor ./myproject "Add logging to all functions"
   
   - Add type hints:
     python -m src.main refactor ./myproject "Add type hints to all functions"

3. Project Structure:
   - src/agents: AutoGen agents for each phase
   - src/models: Core data models
   - src/skills: Implementation skills
   - tests/: Test projects and cases

4. Flow:
   Discovery -> Analysis -> Refactor -> Assurance

5. Key Files:
   - main.py: Entry point and CLI
   - agents/*.py: Phase-specific agents
   - skills/codemod.py: Code transformation
   - models/intent.py: Core data model

6. Dependencies:
   - autogen==0.3.1
   - pydantic
   - typer
   - structlog

7. Development:
   - Add new transformations in skills/codemod.py
   - Enhance agents in src/agents/
   - Add test cases in tests/test_projects/
EOF

# Create test files
cat > tests/test_projects/project1/sample.py << 'EOF'
def greet(name):
    print(f"Hello, {name}!")

def calculate_sum(numbers):
    return sum(numbers)

if __name__ == "__main__":
    greet("World")
    print(calculate_sum([1, 2, 3, 4, 5]))
EOF

cat > tests/test_projects/project2/main.py << 'EOF'
from utils import format_name

def process_user(user_data):
    name = format_name(user_data["name"])
    age = user_data["age"]
    return f"{name} is {age} years old"
# Continue creating test project2 files
cat > tests/test_projects/project2/utils.py << 'EOF'
def format_name(name):
    return name.strip().title()

def validate_age(age):
    if not isinstance(age, int):
        raise TypeError("Age must be an integer")
    if age < 0 or age > 150:
        raise ValueError("Age must be between 0 and 150")
    return age
EOF

# Create test suite
cat > tests/test_refactoring.py << 'EOF'
# tests/test_refactoring.py

import pytest
import asyncio
from pathlib import Path
from src.models.intent import Intent
from src.main import process_intent

@pytest.fixture
def project1_path():
    return Path(__file__).parent / "test_projects" / "project1"

@pytest.fixture
def project2_path():
    return Path(__file__).parent / "test_projects" / "project2"

@pytest.mark.asyncio
async def test_add_logging(project1_path):
    """Test adding logging to functions"""
    intent = Intent(
        description="Add logging to all functions",
        project_path=str(project1_path)
    )
    
    result = await process_intent(intent)
    assert result["status"] == "success"
    
    # Verify changes
    with open(project1_path / "sample.py") as f:
        content = f.read()
        assert "import logging" in content
        assert "logging.info" in content

@pytest.mark.asyncio
async def test_add_type_hints(project2_path):
    """Test adding type hints to functions"""
    intent = Intent(
        description="Add type hints to all functions",
        project_path=str(project2_path)
    )
    
    result = await process_intent(intent)
    assert result["status"] == "success"
    
    # Verify changes
    with open(project2_path / "utils.py") as f:
        content = f.read()
        assert "def format_name(name: str) ->" in content
        assert "def validate_age(age: int) ->" in content

@pytest.mark.asyncio
async def test_error_handling(project2_path):
    """Test adding error handling to functions"""
    intent = Intent(
        description="Add try-except blocks to all functions",
        project_path=str(project2_path)
    )
    
    result = await process_intent(intent)
    assert result["status"] == "success"
    
    # Verify changes
    with open(project2_path / "main.py") as f:
        content = f.read()
        assert "try:" in content
        assert "except" in content
EOF

# Create requirements.txt
cat > requirements.txt << 'EOF'
autogen==0.3.1
pydantic>=2.0.0
typer>=0.9.0
structlog>=24.1.0
pytest>=7.0.0
pytest-asyncio>=0.23.0
libcst>=1.0.0
EOF

# Create basic pytest configuration
cat > pytest.ini << 'EOF'
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_functions = test_*
log_cli = true
log_cli_level = INFO
EOF

# Create a Makefile for common commands
cat > Makefile << 'EOF'
.PHONY: install test clean

install:
	pip install -r requirements.txt

test:
	pytest tests/test_refactoring.py -v

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type f -name ".coverage" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name "*.egg" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +

format:
	black src tests
	isort src tests

lint:
	flake8 src tests
	mypy src tests
EOF

# Create .gitignore
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Tests
.pytest_cache/
.coverage
htmlcov/

# Environments
.env
.venv
env/
venv/
ENV/

# IDE
.idea/
.vscode/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
EOF

# Make the script executable
chmod +x src/skills/tartxt.py

echo "Setup complete! Next steps:"
echo "1. Run: make install"
echo "2. Run: make test"
echo ""
echo "Example usage:"
echo "python -m src.main refactor ./tests/test_projects/project1 'Add logging to all functions' -v"
EOF
