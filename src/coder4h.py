"""
Bootstrap configuration and invoke coder agent.
Path: src/coder4h.py
"""

import argparse
import asyncio
from pathlib import Path
import structlog
from agents.coder import Coder
from agents.base import LLMProvider
from config import SystemConfig, ConfigValidationError

logger = structlog.get_logger()

async def run_coder(config_path: str) -> None:
    """Bootstrap coder agent with merged config"""
    try:
        # Load and merge configs 
        config = SystemConfig.load_with_app_config(
            Path("config/system_config.yml"),
            Path(config_path)
        )
        config_dict = config.model_dump()  # Updated from dict() to model_dump()
        runtime = config.get_runtime_config()
        
        # Get coder agent config
        coder_config = config.get_agent_config("coder")
        
        # Initialize coder with proper configuration
        coder = Coder(
            provider=coder_config.provider_enum,
            model=coder_config.model,
            temperature=coder_config.temperature,
            config=config_dict
        )

        result = await coder.process(runtime)
        if not result.success:
            logger.info("coder.completed", success=False, error=result.error)
            return

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