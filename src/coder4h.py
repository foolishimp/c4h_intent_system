"""
Bootstrap configuration and invoke coder agent.
Path: src/coder4h.py
"""

import argparse
import asyncio
from pathlib import Path
import structlog
from src.agents.coder import Coder
from src.agents.base import LLMProvider
from src.config import SystemConfig, ConfigValidationError

logger = structlog.get_logger()

async def run_coder(config_path: str) -> None:
    """Bootstrap coder agent with merged config"""
    try:
        # Load and merge configs 
        config = SystemConfig.load_with_app_config(
            Path("config/system_config.yml"),
            Path(config_path)
        )
        runtime = config.get_runtime_config()
        
        # Initialize coder and let it handle extraction
        coder = Coder(
            provider=LLMProvider(runtime['provider']),
            model=runtime['model'],
            temperature=runtime['temperature'],
            config=config.dict()
        )

        result = await coder.process(runtime)
        if not result.success:
            logger.info("coder.completed", success=False, error=result.error)
            return  # Graceful exit on expected failures

    except Exception as e:
        logger.error("execution_failed", error=str(e))
        raise

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Process code changes using the Coder agent"
    )
    parser.add_argument("config", help="Path to YAML config file")
    
    try:
        asyncio.run(run_coder(parser.parse_args().config))
    except Exception as e:
        logger.error("bootstrap_failed", error=str(e))
        raise SystemExit(1)

if __name__ == "__main__":
    main()
