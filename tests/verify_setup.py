# tests/verify_setup.py

import pytest
import sys
import asyncio

def test_environment():
    """Verify environment setup"""
    import pytest
    import pytest_asyncio
    
    print("\nEnvironment Info:")
    print(f"Python: {sys.version}")
    print(f"Pytest: {pytest.__version__}")
    print(f"Pytest-asyncio: {pytest_asyncio.__version__}")

@pytest.mark.asyncio
async def test_async_works():
    """Verify async test support"""
    await asyncio.sleep(0.1)
    assert True

@pytest.mark.asyncio
async def test_timeout_handling():
    """Verify timeout handling works"""
    try:
        async with asyncio.timeout(0.5):
            await asyncio.sleep(0.1)
            assert True
    except asyncio.TimeoutError:
        pytest.fail("Timeout occurred when it shouldn't")

if __name__ == "__main__":
    pytest.main(["-v", __file__])