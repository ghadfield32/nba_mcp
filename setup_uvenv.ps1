#setup_uvenv.ps1:
# Script to set up a uv virtual environment for the NBA data project

Write-Host "NBA Data Project - uv Environment Setup" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green

# Function to check if a directory is locked or has access issues
function Test-DirectoryAccess {
    param (
        [string]$Path
    )
    try {
        $testFile = Join-Path -Path $Path -ChildPath "test_access_$([Guid]::NewGuid()).tmp"
        [io.file]::OpenWrite($testFile).Close()
        Remove-Item -Path $testFile -Force -ErrorAction Stop
        return $true
    }
    catch {
        Write-Host "Directory $Path appears to be locked or inaccessible" -ForegroundColor Yellow
        return $false
    }
}

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
$removalSuccess = $true

if (Test-Path $envPath) {
    Write-Host "Virtual environment already exists at $envPath" -ForegroundColor Yellow
    $reinstall = Read-Host "Do you want to reinstall it? (y/n)"
    if ($reinstall -eq "y") {
        Write-Host "Removing existing environment..." -ForegroundColor Yellow
        
        # Kill any Python processes that might be using the environment
        Write-Host "Terminating Python processes..." -ForegroundColor Yellow
        taskkill /F /IM python.exe 2>$null
        
        # Wait a moment for processes to fully terminate
        Start-Sleep -Seconds 2
        
        # Try to remove the environment directory
        try {
            # Test if directory is accessible
            if (Test-DirectoryAccess -Path $envPath) {
                # First try with -Force
                Remove-Item -Path $envPath -Recurse -Force -ErrorAction Stop
                Write-Host "Existing environment removed successfully" -ForegroundColor Green
            }
            else {
                Write-Host "Environment directory appears to be locked. Attempting alternative removal approach..." -ForegroundColor Yellow
                
                # Try more aggressive approach
                cmd /c rd /s /q $envPath

                # Verify removal
                if (Test-Path $envPath) {
                    Write-Host "Environment could not be completely removed using standard methods." -ForegroundColor Red
                    Write-Host "Please close any applications that might be using files in the environment and try again." -ForegroundColor Red
                    $removalSuccess = $false
                }
                else {
                    Write-Host "Existing environment removed successfully with alternative method" -ForegroundColor Green
                }
            }
        }
        catch {
            Write-Host "Failed to remove the environment. Some files might be in use." -ForegroundColor Red
            Write-Host "Error: $_" -ForegroundColor Red
            
            # Try alternative removal approach if standard Remove-Item failed
            Write-Host "Attempting alternative removal approach..." -ForegroundColor Yellow
            cmd /c rd /s /q $envPath
            
            # Verify if the alternative approach worked
            if (Test-Path $envPath) {
                Write-Host "Environment could not be completely removed." -ForegroundColor Red
                Write-Host "Please close any applications that might be using files in the environment and try again." -ForegroundColor Red
                $removalSuccess = $false
            }
            else {
                Write-Host "Existing environment removed successfully with alternative method" -ForegroundColor Green
            }
        }
        
        # If removal failed, exit
        if (-not $removalSuccess) {
            exit 1
        }
    }
    else {
        Write-Host "Using existing environment" -ForegroundColor Green
        Write-Host "Activate it with: .\$envPath\Scripts\activate" -ForegroundColor Cyan
        Write-Host "IMPORTANT: Do NOT use Import-Module with the environment directory" -ForegroundColor Yellow
        exit 0
    }
}

# Verify environment directory doesn't exist before creating a new one
if (Test-Path $envPath) {
    Write-Host "ERROR: Environment directory still exists at $envPath" -ForegroundColor Red
    Write-Host "Please manually remove this directory and try again." -ForegroundColor Red
    exit 1
}

# Create a new virtual environment
Write-Host "Creating a new uv virtual environment..." -ForegroundColor Cyan
try {
    uv venv $envPath
    
    # Verify the environment was created successfully
    if (Test-Path (Join-Path $envPath "Scripts\activate")) {
        Write-Host "Virtual environment created successfully at $envPath" -ForegroundColor Green
    }
    else {
        Write-Host "Virtual environment creation appears to have failed. Environment may be incomplete." -ForegroundColor Red
        exit 1
    }
}
catch {
    Write-Host "Failed to create virtual environment" -ForegroundColor Red
    Write-Host "Error: $_" -ForegroundColor Red
    exit 1
}

# Activate the environment and install requirements
Write-Host "Installing packages from requirements.txt..." -ForegroundColor Cyan
try {
    # Verify requirements file exists
    if (-not (Test-Path "requirements.txt")) {
        Write-Host "requirements.txt file not found!" -ForegroundColor Red
        Write-Host "Please create this file with your dependencies and try again." -ForegroundColor Red
        exit 1
    }
    
    # Activate and install directly (need to use Invoke-Expression for complex commands)
    Invoke-Expression "& '$envPath\Scripts\activate'; uv pip install -r requirements.txt"
    
    # Make sure ipykernel is installed
    Invoke-Expression "& '$envPath\Scripts\activate'; uv pip install ipykernel"
    # Install uvicorn
    Invoke-Expression "& '$envPath\Scripts\activate'; uv pip install uvicorn"

    # More thorough verification with better diagnostics
    Write-Host "Verifying package installation..." -ForegroundColor Cyan
    try {
        $testInstall = Invoke-Expression "& '$envPath\Scripts\python' -c 'import ipykernel; print(""success"")'" 2>&1
        if ($testInstall -eq "success") {
            Write-Host "Package verification: ipykernel successfully imported" -ForegroundColor Green
        }
        else {
            Write-Host "WARNING: Package verification failed for ipykernel" -ForegroundColor Yellow
            Write-Host "Output: $testInstall" -ForegroundColor Yellow
        }
        
        # Check a few more critical packages
        $criticalPackages = @("pandas", "numpy", "uvicorn")
        foreach ($pkg in $criticalPackages) {
            $pkgTest = Invoke-Expression "& '$envPath\Scripts\python' -c 'import $pkg; print(""$pkg success"")'" 2>&1
            if ($pkgTest -eq "$pkg success") {
                Write-Host "Package verification: $pkg successfully imported" -ForegroundColor Green
            }
            else {
                Write-Host "WARNING: Package verification failed for $pkg" -ForegroundColor Yellow
                Write-Host "Output: $pkgTest" -ForegroundColor Yellow
            }
        }
        
        Write-Host "Packages installed successfully" -ForegroundColor Green
    }
    catch {
        Write-Host "ERROR during package verification: $_" -ForegroundColor Red
    }
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
    
    # Verify kernel installation
    $kernelPath = "$env:APPDATA\jupyter\kernels\nba_env"
    if (Test-Path $kernelPath) {
        Write-Host "Jupyter kernel registered successfully at $kernelPath" -ForegroundColor Green
    }
    else {
        Write-Host "WARNING: Kernel may not have been registered correctly" -ForegroundColor Yellow
        Write-Host "Expected kernel path: $kernelPath" -ForegroundColor Yellow
    }
}
catch {
    Write-Host "Failed to register Jupyter kernel" -ForegroundColor Red
    Write-Host "Error: $_" -ForegroundColor Red
    exit 1
}

Write-Host "Setup completed successfully!" -ForegroundColor Green
Write-Host "To activate the environment, run: .\$envPath\Scripts\activate" -ForegroundColor Cyan
Write-Host "IMPORTANT: Do NOT use Import-Module with the virtual environment directory" -ForegroundColor Yellow
Write-Host "When using Jupyter, select the 'NBA API (uv)' kernel" -ForegroundColor Cyan 
