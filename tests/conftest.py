"""
Test configuration and fixtures.
Path: tests/conftest.py
"""

import pytest
import structlog
import os
from typing import Dict, Any
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

# Configure structlog for testing
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M.%S"),
        structlog.stdlib.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.ConsoleRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True
)

logger = structlog.get_logger()

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup test environment and verify configuration"""
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")
        
    logger.info("setup.environment", 
                anthropic_key_set=bool(api_key),
                key_length=len(api_key))
    
    return {'ANTHROPIC_API_KEY': api_key}

@pytest.fixture(scope="function")
async def test_iterator(setup_test_environment, test_config):
    """Create pre-configured test iterator"""
    from src.skills.semantic_iterator import SemanticIterator
    
    return SemanticIterator(
        [{
            'provider': test_config['llm_config']['default_provider'],
            'model': test_config['llm_config']['default_model'],
            'temperature': test_config['llm_config']['temperature'],
            'config': test_config
        }],
        extraction_modes=["fast", "slow"]
    )

@pytest.fixture(scope="session")
def test_config() -> Dict[str, Any]:
    """Provide test configuration"""
    return {
        'providers': {
            'anthropic': {
                'api_base': 'https://api.anthropic.com',
                'env_var': 'ANTHROPIC_API_KEY',
                'context_length': 100000
            }
        },
        'llm_config': {
            'default_provider': 'anthropic',
            'default_model': 'claude-3-opus-20240229',
            'temperature': 0
        }
    }

@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session"""
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()