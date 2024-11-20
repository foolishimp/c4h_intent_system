"""
Test configuration and fixtures.
Path: tests/conftest.py
"""

import pytest
import logging
import structlog
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure structlog
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

@pytest.fixture(autouse=True)
def setup_test_env():
    """Setup test environment"""
    logger.info("Setting up test environment")
    yield
    logger.info("Tearing down test environment")

@pytest.fixture
def test_config():
    """Provide test configuration"""
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

# Configure asyncio for pytest
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "asyncio: mark test as an asyncio test"
    )

@pytest.fixture
def event_loop(request):
    """Create an instance of the default event loop for each test case."""
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()