from setuptools import setup, find_packages

setup(
    name="nba-mcp",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "httpx>=0.24.0",
        "fastmcp>=0.1.0",
        "pandas",
    ],
    entry_points={
        "console_scripts": [
            "nba-mcp=nba_mcp.nba_server:main",
        ],
    },
    python_requires=">=3.10",
)