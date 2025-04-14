from setuptools import setup, find_packages

setup(
    name="nba-mcp",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "httpx",
        "fastmcp",
    ],
    entry_points={
        "console_scripts": [
            "nba-mcp=nba_server:main",
        ],
    },
)