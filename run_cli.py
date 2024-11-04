# run_cli.py

import os
from pathlib import Path

# Ensure we're in the project root directory
os.chdir(Path(__file__).parent)

from src.cli import main

if __name__ == "__main__":
    main()