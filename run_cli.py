# run_cli.py

import os
from pathlib import Path
import structlog
import logging

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger("intent_system")

# Ensure we're in the project root directory
os.chdir(Path(__file__).parent)

from src.cli import main

if __name__ == "__main__":
    main()