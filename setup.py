"""
location: setup.py


"""
from setuptools import setup, find_packages

setup(
    name="nba-mcp",
    version="0.5.0",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "fastmcp>=2.2.0",
        "httpx>=0.28.1",
        "nba_api>=1.9.0",
        "pandas>=2.2.3",
        "pydantic>=2.11.3",
        "python-dotenv>=1.1.0",
        "langchain-mcp-adapters>=0.0.9",
        "langchain-ollama>=0.3.2",
        "langgraph>=0.3.31",
        "ollama>=0.4.8",
        "jupyter>=1.1.1",
        "streamlit>=1.37.1",
        "rich>=10.14.0,<14",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "mypy>=1.0.0",
            "black>=23.0.0",
            "isort>=5.0.0",
            "invoke>=2.2.0",
        ]
    },
    entry_points={
        "console_scripts": [
            "nba-mcp = nba_mcp.nba_server:main",
        ],
    },
)
