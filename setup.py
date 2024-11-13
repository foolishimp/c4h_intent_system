# setup.py
from setuptools import setup, find_packages

setup(
    name="coder4h",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "litellm>=1.52.3",
        "openai>=1.13.3",
        "anthropic>=0.18.1",
        "google-generativeai>=0.3.2",
        "libcst>=1.2.0",
        "pydantic>=2.6.3",
        "structlog>=24.1.0",
        "python-dotenv>=1.0.1",
        "PyYAML>=6.0.1",
    ],
    entry_points={
        'console_scripts': [
            'coder4h=src.main:main',
        ],
    },
)