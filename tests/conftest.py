# tests/conftest.py

import pytest
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@pytest.fixture(autouse=True)
def setup_test_env():
    """Setup test environment"""
    logger.info("Setting up test environment")
    yield
    logger.info("Tearing down test environment")