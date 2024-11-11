# tests/test_verify_async.py

import pytest
import asyncio

@pytest.mark.asyncio
async def test_async_works():
    """Simple test to verify async testing works"""
    await asyncio.sleep(0.1)
    assert True

if __name__ == "__main__":
    pytest.main(["-v", __file__])
