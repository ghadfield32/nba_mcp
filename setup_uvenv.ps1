# Script to set up a uv virtual environment for the NBA data project

Write-Host "NBA Data Project - uv Environment Setup" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green

# Check if uv is installed
try {
    $uvVersion = uv --version
    Write-Host "Found uv version: $uvVersion" -ForegroundColor Cyan
}
catch {
    Write-Host "uv is not installed! Installing now..." -ForegroundColor Yellow
    try {
        pip install uv
        $uvVersion = uv --version
        Write-Host "Installed uv version: $uvVersion" -ForegroundColor Cyan
    }
    catch {
        Write-Host "Failed to install uv. Please install it manually with 'pip install uv'" -ForegroundColor Red
        exit 1
    }
}

# Check if virtual environment exists
$envPath = ".uvenv"
if (Test-Path $envPath) {
    Write-Host "Virtual environment already exists at $envPath" -ForegroundColor Yellow
    $reinstall = Read-Host "Do you want to reinstall it? (y/n)"
    if ($reinstall -eq "y") {
        Write-Host "Removing existing environment..." -ForegroundColor Yellow
        
        # Kill any Python processes that might be using the environment
        Write-Host "Terminating Python processes..." -ForegroundColor Yellow
        taskkill /F /IM python.exe 2>$null
        
        # Remove the environment directory
        try {
            Remove-Item -Path $envPath -Recurse -Force
            Write-Host "Existing environment removed successfully" -ForegroundColor Green
        }
        catch {
            Write-Host "Failed to remove the environment. Some files might be in use." -ForegroundColor Red
            Write-Host "Error: $_" -ForegroundColor Red
            exit 1
        }
    }
    else {
        Write-Host "Using existing environment" -ForegroundColor Green
        Write-Host "Activate it with: .\.uvenv\Scripts\activate" -ForegroundColor Cyan
        exit 0
    }
}

# Create a new virtual environment
Write-Host "Creating a new uv virtual environment..." -ForegroundColor Cyan
try {
    uv venv $envPath
    Write-Host "Virtual environment created at $envPath" -ForegroundColor Green
}
catch {
    Write-Host "Failed to create virtual environment" -ForegroundColor Red
    Write-Host "Error: $_" -ForegroundColor Red
    exit 1
}

# Activate the environment and install requirements
Write-Host "Installing packages from requirements.txt..." -ForegroundColor Cyan
try {
    # Activate and install directly (need to use Invoke-Expression for complex commands)
    Invoke-Expression "& '$envPath\Scripts\activate'; uv pip install -r requirements.txt"
    
    # Make sure ipykernel is installed
    Invoke-Expression "& '$envPath\Scripts\activate'; uv pip install ipykernel"
    
    Write-Host "Packages installed successfully" -ForegroundColor Green
}
catch {
    Write-Host "Failed to install packages" -ForegroundColor Red
    Write-Host "Error: $_" -ForegroundColor Red
    exit 1
}

# Register the kernel with Jupyter
Write-Host "Registering Jupyter kernel..." -ForegroundColor Cyan
try {
    Invoke-Expression "& '$envPath\Scripts\activate'; python -m ipykernel install --user --name=nba_env --display-name='NBA API (uv)'"
    Write-Host "Jupyter kernel registered successfully" -ForegroundColor Green
}
catch {
    Write-Host "Failed to register Jupyter kernel" -ForegroundColor Red
    Write-Host "Error: $_" -ForegroundColor Red
    exit 1
}

Write-Host "Setup completed successfully!" -ForegroundColor Green
Write-Host "To activate the environment, run: .\.uvenv\Scripts\activate" -ForegroundColor Cyan
Write-Host "When using Jupyter, select the 'NBA API (uv)' kernel" -ForegroundColor Cyan 
