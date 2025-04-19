from setuptools import setup, find_packages

setup(
    name="nba-mcp",
    version="0.2.0",
    packages=find_packages(),
    install_requires=[
        "fastmcp>=0.1.0",
        "pandas",
        "nba_api>=1.2.1",
    ],
    entry_points={
        "console_scripts": [
            "nba-mcp=nba_mcp.nba_server:main",
        ],
    },
    python_requires=">=3.10",
)