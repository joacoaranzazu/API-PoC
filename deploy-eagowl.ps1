# EAGOWL POC - PowerShell Deployment Script
# Automated deployment for Fleet Intelligence Platform on Windows

param(
    [switch]$SkipDocker,
    [switch]$SkipNode,
    [switch]$SkipPython,
    [string]$Environment = "development"
)

Write-Host "🚀 EAGOWL POC Fleet Intelligence Platform Deployment" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# Check if running as administrator
if (-NOT ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "❌ Please run this script as Administrator" -ForegroundColor Red
    exit 1
}

# Configuration
$PROJECT_ROOT = $PSScriptRoot
$SERVICES_DIR = "$PROJECT_ROOT\services"
$WEB_DIR = "$PROJECT_ROOT\web-ui"
$DOCKER_COMPOSE_FILE = "$PROJECT_ROOT\docker-compose.prod.yml"
$ENV_FILE = "$PROJECT_ROOT\.env"

Write-Host "📁 Project Root: $PROJECT_ROOT" -ForegroundColor Green

# Function to check if a command exists
function Test-Command($Command) {
    try {
        Get-Command $Command -ErrorAction Stop | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

# Function to install Chocolatey if not present
function Install-Chocolatey {
    if (-not (Test-Command choco)) {
        Write-Host "📦 Installing Chocolatey..." -ForegroundColor Yellow
        Set-ExecutionPolicy Bypass -Scope Process -Force
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
        iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
        refreshenv
    } else {
        Write-Host "✅ Chocolatey already installed" -ForegroundColor Green
    }
}

# Function to install Docker Desktop
function Install-Docker {
    if (-not (Test-Command docker)) {
        Write-Host "📦 Installing Docker Desktop..." -ForegroundColor Yellow
        choco install docker-desktop -y
        Write-Host "⚠️  Docker Desktop installed. Please restart and start Docker Desktop manually." -ForegroundColor Yellow
        Write-Host "   Then run this script again with -SkipDocker flag." -ForegroundColor Yellow
        return $false
    } else {
        Write-Host "✅ Docker already installed" -ForegroundColor Green
        return $true
    }
}

# Function to install Python
function Install-Python {
    if (-not (Test-Command python)) {
        Write-Host "📦 Installing Python..." -ForegroundColor Yellow
        choco install python311 -y
        refreshenv
    } else {
        $pythonVersion = python --version 2>&1
        Write-Host "✅ Python already installed: $pythonVersion" -ForegroundColor Green
    }
}

# Function to install Node.js
function Install-NodeJs {
    if (-not (Test-Command node)) {
        Write-Host "📦 Installing Node.js..." -ForegroundColor Yellow
        choco install nodejs -y
        refreshenv
    } else {
        $nodeVersion = node --version
        Write-Host "✅ Node.js already installed: $nodeVersion" -ForegroundColor Green
    }
}

# Function to create .env file
function Create-EnvironmentFile {
    if (-not (Test-Path $ENV_FILE)) {
        Write-Host "📝 Creating environment file..." -ForegroundColor Yellow
        $envContent = @"
# EAGOWL POC Environment Configuration
JWT_SECRET_KEY=eagowl-poc-secret-key-2024
WALKIEFLEET_URL=http://poc1.eagowl.co:9998
WALKIEFLEET_USER=10000
WALKIEFLEET_PASS=1948

# Service URLs
AI_ANALYTICS_URL=http://ai-analytics:5001
SMART_MAP_URL=http://smart-map:5002
FLEET_OPTIMIZER_URL=http://fleet-optimizer:5003
PREDICTIVE_ALERTS_URL=http://predictive-alerts:5004

# Database Configuration (if needed)
DATABASE_URL=postgresql://eagowl:eagowl123@localhost:5432/eagowl_poc

# Redis Configuration (if needed)
REDIS_URL=redis://localhost:6379

# Frontend Configuration
NEXT_PUBLIC_API_URL=http://localhost:5000
NEXT_PUBLIC_MAP_API_KEY=your-map-api-key-here

# Debug Settings
DEBUG=false
NODE_ENV=production
"@
        $envContent | Out-File -FilePath $ENV_FILE -Encoding UTF8
        Write-Host "✅ Environment file created" -ForegroundColor Green
    } else {
        Write-Host "✅ Environment file already exists" -ForegroundColor Green
    }
}

# Function to install Python dependencies
function Install-PythonDependencies {
    Write-Host "📦 Installing Python dependencies..." -ForegroundColor Yellow
    
    $services = @("api", "ai-analytics", "smart-map", "fleet-optimizer", "predictive-alerts")
    
    foreach ($service in $services) {
        $serviceDir = "$SERVICES_DIR\$service"
        $requirementsFile = "$serviceDir\requirements.txt"
        
        if (Test-Path $requirementsFile) {
            Write-Host "   Installing dependencies for $service..." -ForegroundColor Cyan
            Push-Location $serviceDir
            python -m pip install -r requirements.txt
            if ($LASTEXITCODE -ne 0) {
                Write-Host "❌ Failed to install dependencies for $service" -ForegroundColor Red
                Pop-Location
                return $false
            }
            Pop-Location
        } else {
            Write-Host "⚠️  Requirements file not found for $service" -ForegroundColor Yellow
        }
    }
    
    Write-Host "✅ Python dependencies installed" -ForegroundColor Green
    return $true
}

# Function to install Node.js dependencies
function Install-NodeDependencies {
    if (Test-Path $WEB_DIR) {
        Write-Host "📦 Installing Node.js dependencies..." -ForegroundColor Yellow
        Push-Location $WEB_DIR
        npm install
        if ($LASTEXITCODE -ne 0) {
            Write-Host "❌ Failed to install Node.js dependencies" -ForegroundColor Red
            Pop-Location
            return $false
        }
        Pop-Location
        Write-Host "✅ Node.js dependencies installed" -ForegroundColor Green
        return $true
    } else {
        Write-Host "⚠️  Web UI directory not found" -ForegroundColor Yellow
        return $true
    }
}

# Function to build Docker images
function Build-DockerImages {
    Write-Host "🐳 Building Docker images..." -ForegroundColor Yellow
    
    Push-Location $PROJECT_ROOT
    
    # Check if docker-compose file exists
    if (Test-Path $DOCKER_COMPOSE_FILE) {
        docker-compose -f $DOCKER_COMPOSE_FILE build
        if ($LASTEXITCODE -ne 0) {
            Write-Host "❌ Failed to build Docker images" -ForegroundColor Red
            Pop-Location
            return $false
        }
    } else {
        Write-Host "⚠️  Docker Compose file not found" -ForegroundColor Yellow
        Pop-Location
        return $true
    }
    
    Pop-Location
    Write-Host "✅ Docker images built successfully" -ForegroundColor Green
    return $true
}

# Function to start services
function Start-Services {
    Write-Host "🚀 Starting EAGOWL services..." -ForegroundColor Yellow
    
    Push-Location $PROJECT_ROOT
    
    if (Test-Path $DOCKER_COMPOSE_FILE) {
        docker-compose -f $DOCKER_COMPOSE_FILE up -d
        if ($LASTEXITCODE -ne 0) {
            Write-Host "❌ Failed to start services" -ForegroundColor Red
            Pop-Location
            return $false
        }
        
        Write-Host "✅ Services started successfully" -ForegroundColor Green
        
        # Wait for services to be ready
        Write-Host "⏳ Waiting for services to be ready..." -ForegroundColor Yellow
        Start-Sleep -Seconds 30
        
        # Check service health
        Check-ServiceHealth
    } else {
        Write-Host "⚠️  Docker Compose file not found" -ForegroundColor Yellow
    }
    
    Pop-Location
    return $true
}

# Function to check service health
function Check-ServiceHealth {
    Write-Host "🔍 Checking service health..." -ForegroundColor Yellow
    
    $services = @(
        @{Name="API Gateway"; Port=5000; Path="/health"},
        @{Name="AI Analytics"; Port=5001; Path="/health"},
        @{Name="Smart Map"; Port=5002; Path="/health"},
        @{Name="Fleet Optimizer"; Port=5003; Path="/health"},
        @{Name="Predictive Alerts"; Port=5004; Path="/health"},
        @{Name="Web UI"; Port=3000; Path="/"}
    )
    
    foreach ($service in $services) {
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:$($service.Port)$($service.Path)" -TimeoutSec 10 -ErrorAction Stop
            if ($response.StatusCode -eq 200) {
                Write-Host "✅ $($service.Name) is healthy" -ForegroundColor Green
            } else {
                Write-Host "⚠️  $($service.Name) returned status code $($response.StatusCode)" -ForegroundColor Yellow
            }
        }
        catch {
            Write-Host "❌ $($service.Name) is not responding" -ForegroundColor Red
        }
    }
}

# Function to show access information
function Show-AccessInfo {
    Write-Host ""
    Write-Host "🎉 EAGOWL POC Platform Deployment Complete!" -ForegroundColor Green
    Write-Host "===========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "📱 Access Points:" -ForegroundColor Cyan
    Write-Host "   🌐 Web UI:         http://localhost:3000" -ForegroundColor White
    Write-Host "   🔗 API Gateway:    http://localhost:5000" -ForegroundColor White
    Write-Host "   🤖 AI Analytics:   http://localhost:5001" -ForegroundColor White
    Write-Host "   🗺️  Smart Map:      http://localhost:5002" -ForegroundColor White
    Write-Host "   🚚 Fleet Optimizer: http://localhost:5003" -ForegroundColor White
    Write-Host "   🚨 Predictive Alerts: http://localhost:5004" -ForegroundColor White
    Write-Host ""
    Write-Host "🔐 Default Login Credentials:" -ForegroundColor Cyan
    Write-Host "   👤 Username: admin" -ForegroundColor White
    Write-Host "   🔑 Password: admin123" -ForegroundColor White
    Write-Host ""
    Write-Host "   👤 Username: fleet_manager" -ForegroundColor White
    Write-Host "   🔑 Password: fleet123" -ForegroundColor White
    Write-Host ""
    Write-Host "📋 Management Commands:" -ForegroundColor Cyan
    Write-Host "   🐳 View logs:       docker-compose -f $DOCKER_COMPOSE_FILE logs -f" -ForegroundColor White
    Write-Host "   🛑 Stop services:   docker-compose -f $DOCKER_COMPOSE_FILE down" -ForegroundColor White
    Write-Host "   🔄 Restart:         docker-compose -f $DOCKER_COMPOSE_FILE restart" -ForegroundColor White
    Write-Host ""
}

# Main deployment flow
try {
    # Install dependencies
    if (-not $SkipPython) {
        Install-Chocolatey
        Install-Python
    }
    
    if (-not $SkipNode) {
        Install-Chocolatey
        Install-NodeJs
    }
    
    if (-not $SkipDocker) {
        Install-Chocolatey
        $dockerInstalled = Install-Docker
        if (-not $dockerInstalled) {
            Write-Host "⚠️  Please start Docker Desktop and run script again with -SkipDocker" -ForegroundColor Yellow
            exit 1
        }
    }
    
    # Create environment file
    Create-EnvironmentFile
    
    # Install dependencies
    if (-not $SkipPython) {
        $pythonSuccess = Install-PythonDependencies
        if (-not $pythonSuccess) {
            Write-Host "❌ Failed to install Python dependencies" -ForegroundColor Red
            exit 1
        }
    }
    
    if (-not $SkipNode) {
        $nodeSuccess = Install-NodeDependencies
        if (-not $nodeSuccess) {
            Write-Host "❌ Failed to install Node.js dependencies" -ForegroundColor Red
            exit 1
        }
    }
    
    # Build and start services
    if (Test-Command docker) {
        $buildSuccess = Build-DockerImages
        if ($buildSuccess) {
            $startSuccess = Start-Services
            if ($startSuccess) {
                Show-AccessInfo
            } else {
                Write-Host "❌ Failed to start services" -ForegroundColor Red
                exit 1
            }
        } else {
            Write-Host "❌ Failed to build Docker images" -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "⚠️  Docker not available. Please install Docker and run again." -ForegroundColor Yellow
        Write-Host "   You can run services individually using Python/Node.js" -ForegroundColor Yellow
    }
}
catch {
    Write-Host "❌ Deployment failed with error:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

Write-Host "✅ Deployment script completed" -ForegroundColor Green