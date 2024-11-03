# Intent-Based Architecture System

## Overview
This system implements an intent-based architecture designed to unify all operations within a software system into a singular, cohesive processing mechanism using AutoGen 0.3.1.

## Setup
1. Create virtual environment: `python -m venv venv`
2. Activate virtual environment: 
   - Windows: `venv\Scripts\activate`
   - Unix/MacOS: `source venv/bin/activate`
3. Install requirements: `pip install -r requirements.txt`
4. Configure environment variables:
   ```bash
   export OPENAI_API_KEY=your-key-here
   ```
5. Run the system: `python -m intent_system`

## Development
- Use type hints consistently
- Run tests: `pytest`
- Format code: `black .`
- Sort imports: `isort .`
- Type checking: `mypy .`

## Architecture
See `docs/architecture.md` for detailed system design
