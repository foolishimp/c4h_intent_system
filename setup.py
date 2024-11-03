# requirements.txt
typer>=0.9.0
rich>=13.7.0
pydantic>=2.6.0
python-dotenv>=1.0.0
structlog>=24.1.0
pyyaml>=6.0.1
openai>=1.12.0
anthropic>=0.18.1
litellm>=1.30.7

# setup.py
from setuptools import setup, find_packages

setup(
    name="intent-system",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'typer>=0.9.0',
        'rich>=13.7.0',
        'pydantic>=2.6.0',
        'python-dotenv>=1.0.0',
        'structlog>=24.1.0',
        'pyyaml>=6.0.1',
        'openai>=1.12.0',
        'anthropic>=0.18.1',
        'litellm>=1.30.7',
    ],
    entry_points={
        'console_scripts': [
            'intent-system=src.cli:cli',
        ],
    },
)
