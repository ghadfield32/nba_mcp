# NBA Data Project - Environment Setup Guide

This document provides instructions for setting up Python virtual environments for the NBA data project using `uv`.

## Environment Setup Options

This project provides two PowerShell scripts for environment setup:

1. **Standard Environment** (`setup_uvenv.ps1`): For regular usage
2. **Development Environment** (`setup_uvenv_dev.ps1`): For development work with additional tools

## Prerequisites

- Python 3.8+ installed
- PowerShell 5.0+ (Windows)
- Internet connection for package downloads

## Setting Up the Environment

### Standard Environment

1. Open PowerShell in the project root directory
2. Run the setup script:
   ```powershell
   .\setup_uvenv.ps1
   ```
3. Follow the prompts during the setup process
4. Once complete, activate the environment:
   ```powershell
   .\.uvenv\Scripts\activate
   ```

### Development Environment

1. Open PowerShell in the project root directory
2. Run the development setup script:
   ```powershell
   .\setup_uvenv_dev.ps1
   ```
3. Follow the prompts during the setup process
4. Once complete, activate the development environment:
   ```powershell
   .\.uvenv-dev\Scripts\activate
   ```

## Important Usage Notes

- **NEVER** use `Import-Module` with the virtual environment directories. This will cause errors.
- Always activate the environment using the `activate` script as shown above.
- When using Jupyter notebooks, select the appropriate kernel:
  - Standard: "NBA API (uv)"
  - Development: "NBA API Dev (uv)"

## Troubleshooting

### Common Issues

1. **"The module '.uvenv-dev' could not be loaded"**:
   - This occurs when trying to import the environment directory as a module
   - Solution: Use the activation command (`.\.uvenv-dev\Scripts\activate`) instead

2. **Package installation issues**:
   - If you see warnings about package verification failures
   - Solution: Try reinstalling the environment or manually install the specific package

3. **Environment cannot be removed**:
   - This typically happens when files are in use
   - Solution: Close all applications that might be using the environment (Python, Jupyter, VSCode, etc.) and try again

## Manual Package Installation

If you need to install additional packages:

1. Activate your environment first:
   ```powershell
   .\.uvenv\Scripts\activate  # or .\.uvenv-dev\Scripts\activate for dev
   ```

2. Install packages using uv:
   ```powershell
   uv pip install package_name
   ```

## Requirements Files

- `requirements.txt`: Core packages for standard usage
- `requirements-dev.txt`: Development packages (includes testing, linting, etc.)

If you modify these files, you'll need to reinstall the environment or manually install the new packages. 