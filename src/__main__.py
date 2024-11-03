# src/__main__.py

import asyncio
import os
from pathlib import Path
from src.orchestrator import IntentSystem
import logging

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger("intent_system")

async def main():
    logger = setup_logging()
    
    # Get project root directory
    project_root = Path(__file__).parent.parent
    config_path = project_root / "config" / "system_config.yml"
    
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found at {config_path}")
    
    logger.info(f"Initializing Intent System with config from {config_path}")
    
    try:
        # Initialize the system
        system = IntentSystem(str(config_path))
        await system.initialize()
        
        # Process test project
        test_project_path = project_root / "tests" / "test_project"
        logger.info(f"Processing test project at {test_project_path}")
        
        result = await system.process_scope_request(str(test_project_path))
        
        logger.info(f"Processing complete. Results saved to {result['results_path']}")
        
        return result
        
    except Exception as e:
        logger.error(f"Error during execution: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(main())