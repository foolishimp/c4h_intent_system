"""
Test configuration and fixtures.
Path: tests/conftest.py
"""

import pytest
import logging
import structlog
import os
from typing import Dict, Any

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

@pytest.fixture(scope="module")
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

# Configure asyncio - remove the custom event_loop fixture
@pytest.fixture(scope="module")
def event_loop_policy():
    """Provide event loop policy for testing"""
    import asyncio
    return asyncio.WindowsSelectorEventLoopPolicy() if os.name == 'nt' else asyncio.DefaultEventLoopPolicy()