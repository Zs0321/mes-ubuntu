# Quick Fix Script - Remove Synology Dependency and Fix Database Persistence
# PowerShell Script

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Database Fix and Synology Removal Tool" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check Python
Write-Host "[1/6] Checking Python..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "OK Python installed: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "ERROR Python not found" -ForegroundColor Red
    exit 1
}

# 2. Find database
Write-Host ""
Write-Host "[2/6] Finding database..." -ForegroundColor Yellow

$dbPaths = @("..\app\files\users.db", "app\files\users.db", "users.db")
$dbPath = $null

foreach ($path in $dbPaths) {
    if (Test-Path $path) {
        $dbPath = $path
        Write-Host "OK Found database: $dbPath" -ForegroundColor Green
        break
    }
}

if (-not $dbPath) {
    Write-Host "WARN Database not found" -ForegroundColor Yellow
    $createNew = Read-Host "Create new database (y/N)"
    if ($createNew -eq 'y') {
        $dbPath = "..\app\files\users.db"
        New-Item -ItemType Directory -Force -Path "..\app\files" | Out-Null
        Write-Host "OK Will create: $dbPath" -ForegroundColor Green
    } else {
        exit 1
    }
}

# 3. Backup
Write-Host ""
Write-Host "[3/6] Backing up..." -ForegroundColor Yellow

if (Test-Path $dbPath) {
    $backupPath = "$dbPath.backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    Copy-Item $dbPath $backupPath
    Write-Host "OK Backed up to: $backupPath" -ForegroundColor Green
} else {
    Write-Host "WARN Database does not exist yet" -ForegroundColor Yellow
}

# 4. Migrate
Write-Host ""
Write-Host "[4/6] Running migration..." -ForegroundColor Yellow

$adminPassword = Read-Host "Enter admin password (default: admin123)"
if ([string]::IsNullOrWhiteSpace($adminPassword)) {
    $adminPassword = "admin123"
}

Write-Host "Database path: $dbPath" -ForegroundColor Gray
Write-Host "Admin password: $adminPassword" -ForegroundColor Gray
Write-Host ""

python migrate_database.py "$dbPath" "$adminPassword"

if ($LASTEXITCODE -eq 0) {
    Write-Host "OK Migration successful" -ForegroundColor Green
} else {
    Write-Host "ERROR Migration failed" -ForegroundColor Red
    Write-Host "Try manually: python migrate_database.py `"$dbPath`" `"$adminPassword`"" -ForegroundColor Yellow
    exit 1
}

# 5. Check files
Write-Host ""
Write-Host "[5/6] Checking files..." -ForegroundColor Yellow

$files = @("local_auth_service.py", "user_management_service_v2.py", "migrate_database.py")
foreach ($file in $files) {
    if (Test-Path $file) {
        Write-Host "OK $file" -ForegroundColor Green
    } else {
        Write-Host "ERROR $file missing" -ForegroundColor Red
    }
}

# 6. Next steps
Write-Host ""
Write-Host "[6/6] Done!" -ForegroundColor Yellow
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Update mesapp.py:" -ForegroundColor White
Write-Host "   Replace:" -ForegroundColor Gray
Write-Host "     from synology_auth_client import SynologyAuthService" -ForegroundColor DarkGray
Write-Host "   With:" -ForegroundColor Gray
Write-Host "     from user_management_service_v2 import UserManagementService" -ForegroundColor DarkGray
Write-Host ""
Write-Host "2. Restart app: python mesapp.py" -ForegroundColor White
Write-Host ""
Write-Host "3. Login with:" -ForegroundColor White
Write-Host "   Username: admin" -ForegroundColor Gray
Write-Host "   Password: $adminPassword" -ForegroundColor Gray
Write-Host ""
Write-Host "4. Change password after first login!" -ForegroundColor Yellow
Write-Host ""
Write-Host "See IMPLEMENTATION_GUIDE.md for details" -ForegroundColor Cyan
Write-Host ""
Write-Host "Script completed!" -ForegroundColor Green
