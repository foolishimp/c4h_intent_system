from setuptools import setup, find_packages

setup(
    name="coder4h",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        line.strip()
        for line in open("requirements.txt")
        if line.strip() and not line.startswith("#")
    ],
    entry_points={
        "console_scripts": [
            "coder4h=coder4h.cli:main",
        ],
    },
)
