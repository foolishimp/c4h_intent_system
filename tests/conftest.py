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

# Get structlog logger
logger = structlog.get_logger()

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup test environment and verify configuration"""
    # Check if we have real API key from .env
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        # If no real key, set a mock one
        os.environ['ANTHROPIC_API_KEY'] = 'test-key-123'
        logger.warn("Using mock API key for tests")
    else:
        logger.info("Using real API key from environment")

    # Log environment state using structlog
    env_vars = {k: '***' if 'KEY' in k else v for k, v in os.environ.items()}
    logger.info(
        "test_environment",
        env_vars=env_vars,
        anthropic_key_present='ANTHROPIC_API_KEY' in os.environ
    )

@pytest.fixture(scope="session")
def test_config() -> Dict[str, Any]:
    """Provide test configuration with proper scoping"""
    return {
        'providers': {
            'anthropic': {
                'api_base': 'https://api.anthropic.com',
                'context_length': 100000,
                'env_var': 'ANTHROPIC_API_KEY'
            }
        },
        'llm_config': {
            'default_provider': 'anthropic',
            'default_model': 'claude-3-opus-20240229'
        }
    }

@pytest.fixture(scope="function")
def mock_api_key(monkeypatch):
    """Provide mock API key for testing"""
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-key-123')
    return 'test-key-123'

@pytest.fixture(scope="session")
def event_loop_policy():
    """Provide event loop policy for testing"""
    import asyncio
    return asyncio.WindowsSelectorEventLoopPolicy() if os.name == 'nt' else asyncio.DefaultEventLoopPolicy()

@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session"""
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
