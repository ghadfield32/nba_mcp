#setup_uvenv_dev.ps1:
# Script to set up a uv virtual environment for the NBA data project (Development)

Write-Host "NBA Data Project - uv Development Environment Setup" -ForegroundColor Green
Write-Host "=================================================" -ForegroundColor Green

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

# Helper: Remove a virtual-env folder safely
function Remove-EnvDir {
    param([string]$Path)
    # 1) Ensure we're not inside the venv
    Push-Location
    Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)

    # 2) Kill any python.exe running from the venv itself
    Write-Host "🔄 Stopping python.exe processes under $Path..." -ForegroundColor Yellow
    Get-Process python -ErrorAction SilentlyContinue |
      Where-Object { $_.Path -and $_.Path -like "*\$Path\*" } |
      ForEach-Object {
        Write-Host "   Terminating PID $($_.Id): $($_.Path)" -ForegroundColor Yellow
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
      }

    # 3) Try PowerShell removal
    try {
        Write-Host "🗑️ Removing $Path (PowerShell)..." -ForegroundColor Cyan
        Remove-Item -Path $Path -Recurse -Force -ErrorAction Stop
        Write-Host "✅ Environment removed successfully" -ForegroundColor Green
        Pop-Location
        return $true
    }
    catch {
        Write-Host "⚠️ PowerShell rm failed. Attempting CMD rd /s /q..." -ForegroundColor Yellow
        cmd /c rd /s /q "`"$Path`""

        if (Test-Path $Path) {
            Write-Host "❌ Still couldn't remove $Path." -ForegroundColor Red
            Write-Host "Please close any tools (editors, terminals) pointing into that folder and run again." -ForegroundColor Red
            Pop-Location
            return $false
        }
        else {
            Write-Host "✅ Environment removed via CMD rd" -ForegroundColor Green
            Pop-Location
            return $true
        }
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
$envPath = ".uvenv-dev"
$removalSuccess = $true

if (Test-Path $envPath) {
    Write-Host "Development virtual environment already exists at $envPath" -ForegroundColor Yellow
    $reinstall = Read-Host "Do you want to reinstall it? (y/n)"
    if ($reinstall -eq "y") {
        if (-not (Remove-EnvDir $envPath)) {
            exit 1    # abort if removal failed
        }
    }
    else {
        Write-Host "Using existing development environment" -ForegroundColor Green
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
Write-Host "Creating a new development uv virtual environment..." -ForegroundColor Cyan
try {
    uv venv $envPath
    
    # Verify the environment was created successfully
    if (Test-Path "$envPath\Scripts\python.exe") {
        Write-Host "✅ Virtual environment created successfully at $envPath" -ForegroundColor Green
    }
    else {
        Write-Host "❌ Virtual environment creation appears to have failed. Environment may be incomplete." -ForegroundColor Red
        exit 1
    }

    # Bootstrap pip into the venv
    Write-Host "Bootstrapping pip in the venv..." -ForegroundColor Cyan
    & "$envPath\Scripts\python.exe" -m ensurepip --upgrade 2>&1 | ForEach-Object { Write-Host "   $_" }
}
catch {
    Write-Host "Failed to create development virtual environment" -ForegroundColor Red
    Write-Host "Error: $_" -ForegroundColor Red
    exit 1
}

# Activate the environment and install requirements
Write-Host "Installing packages from requirements-dev.txt..." -ForegroundColor Cyan
try {
    # Verify requirements file exists
    if (-not (Test-Path "requirements-dev.txt")) {
        Write-Host "requirements-dev.txt file not found!" -ForegroundColor Red
        Write-Host "Please create this file with your development dependencies and try again." -ForegroundColor Red
        exit 1
    }
    
    # Install packages directly using the venv's Python executable
    Write-Host "Upgrading pip..." -ForegroundColor Cyan
    & "$envPath\Scripts\python.exe" -m pip install --upgrade pip
    
    # === Install runtime + dev deps, then verify ===
    Write-Host "Installing runtime requirements (requirements.txt)..." -ForegroundColor Cyan
    & "$envPath\Scripts\python.exe" -m pip install -r requirements.txt

    Write-Host "`nInstalling development requirements (requirements-dev.txt)..." -ForegroundColor Cyan
    & "$envPath\Scripts\python.exe" -m pip install -r requirements-dev.txt

    Write-Host "`nInstalling ipykernel and uvicorn..." -ForegroundColor Cyan
    & "$envPath\Scripts\python.exe" -m pip install ipykernel uvicorn

    # Verification with better diagnostics
    Write-Host "`nVerifying package installation..." -ForegroundColor Cyan
    $critical = @("ipykernel", "pandas", "numpy", "uvicorn")
    
    foreach ($pkg in $critical) {
        $cmd = "& `"$envPath\Scripts\python.exe`" -c `"import $pkg; print('$pkg OK')`""
        $output = Invoke-Expression $cmd 2>&1
        $exit = $LASTEXITCODE

        if ($exit -eq 0) {
            Write-Host "✅ [$pkg] imported successfully: $output" -ForegroundColor Green
        }
        else {
            Write-Host "❌ [$pkg] import failed (exit $exit). Output:" -ForegroundColor Red
            Write-Host "   $output" -ForegroundColor Red
        }
    }
    
    Write-Host "Development packages installed" -ForegroundColor Green
}
catch {
    Write-Host "Failed to install development packages" -ForegroundColor Red
    Write-Host "Error: $_" -ForegroundColor Red
    exit 1
}

# Register the kernel with Jupyter
Write-Host "Registering Jupyter kernel..." -ForegroundColor Cyan
try {
    Invoke-Expression "& '$envPath\Scripts\activate'; python -m ipykernel install --user --name=nba_dev_env --display-name='NBA API Dev (uv)'"
    
    # Verify kernel installation
    $kernelPath = "$env:APPDATA\jupyter\kernels\nba_dev_env"
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

Write-Host "Development environment setup completed successfully!" -ForegroundColor Green
Write-Host "To activate the development environment, run: .\$envPath\Scripts\activate" -ForegroundColor Cyan
Write-Host "IMPORTANT: Do NOT use Import-Module with the virtual environment directory" -ForegroundColor Yellow
Write-Host "When using Jupyter, select the 'NBA API Dev (uv)' kernel" -ForegroundColor Cyan 