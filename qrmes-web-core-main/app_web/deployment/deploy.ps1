# MES应用PowerShell部署脚本
# 适用于Windows环境

param(
    [string]$NasHost = "172.16.30.2",
    [string]$NasUser = "panovation",
    [string]$NasAppDir = "/volume2/MES/app_web",
    [string]$NasDataDir = "/volume2/MES/data",
    [string]$NasFilesDir = "/volume2/MES/files",
    [switch]$AllowLegacyDeploy,
    [switch]$SkipDeps,
    [switch]$SkipService,
    [switch]$Help
)

# 颜色输出函数
function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

function Write-Info {
    param([string]$Message)
    Write-ColorOutput "[INFO] $Message" "Green"
}

function Write-Warning {
    param([string]$Message)
    Write-ColorOutput "[WARN] $Message" "Yellow"
}

function Write-Error {
    param([string]$Message)
    Write-ColorOutput "[ERROR] $Message" "Red"
}

function Write-Step {
    param([string]$Message)
    Write-ColorOutput "[STEP] $Message" "Cyan"
}

# 显示帮助信息
function Show-Help {
    Write-Host @"
MES应用PowerShell部署脚本

用法: .\deploy.ps1 [选项]

选项:
  -NasHost <地址>      NAS服务器地址（默认: 172.16.30.2）
  -NasUser <用户名>    SSH用户名（默认: panovation）
  -NasAppDir <路径>    应用目录（默认: /volume2/MES/app_web）
  -AllowLegacyDeploy   明确确认执行历史独立/生产部署流程
  -SkipDeps            跳过依赖安装
  -SkipService         跳过服务配置
  -Help                显示此帮助信息

示例:
  .\deploy.ps1 -AllowLegacyDeploy
  .\deploy.ps1 -NasHost 192.168.1.100 -NasUser admin
  .\deploy.ps1 -AllowLegacyDeploy -SkipDeps

注意:
  0. 当前 NAS 测试环境 172.16.30.2:8891 不使用本脚本；请改用 docs/skills/mes-update-nas-sync/SKILL.md
  1. 需要安装SSH客户端（Windows 10/11自带）
  2. 需要安装SCP工具或使用WinSCP
  3. 建议使用Git Bash或WSL执行Shell脚本
"@
}

# 显示标题
function Show-Header {
    Write-Host "=========================================" -ForegroundColor Cyan
    Write-Host "  MES应用部署 (PowerShell历史流程)" -ForegroundColor Cyan
    Write-Host "=========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "目标服务器: $NasHost"
    Write-Host "部署目录: $NasAppDir"
    Write-Host ""
}

function Assert-LegacyDeployAcknowledged {
    if (-not $AllowLegacyDeploy) {
        Write-Error "此脚本属于历史独立服务器/生产部署流程，不适用于当前 NAS 测试环境 172.16.30.2:8891。"
        Write-Error "当前测试环境请使用 docs/skills/mes-update-nas-sync/SKILL.md，并部署到 /volume2/MES/test/app_web。"
        Write-Error "如确需执行历史 /volume2/MES/app_web 流程，请显式传入 -AllowLegacyDeploy。"
        return $false
    }

    if ($NasAppDir -eq "/volume2/MES/test/app_web") {
        Write-Error "此历史脚本不支持测试环境目录 $NasAppDir。"
        Write-Error "测试环境请改用 docs/skills/mes-update-nas-sync/SKILL.md。"
        return $false
    }

    return $true
}

# 检查SSH连接
function Test-SshConnection {
    Write-Step "检查SSH连接..."
    
    try {
        $result = ssh -o ConnectTimeout=5 "$NasUser@$NasHost" "echo 'Connection OK'" 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Info "✓ SSH连接正常"
            return $true
        } else {
            Write-Error "✗ SSH连接失败"
            Write-Error "请检查："
            Write-Error "  1. SSH服务是否启用"
            Write-Error "  2. 用户名和密码是否正确"
            Write-Error "  3. 网络连接是否正常"
            return $false
        }
    } catch {
        Write-Error "✗ SSH连接异常: $_"
        return $false
    }
}

# 检查必要工具
function Test-RequiredTools {
    Write-Step "检查必要工具..."
    
    $tools = @("ssh", "scp")
    $allFound = $true
    
    foreach ($tool in $tools) {
        if (Get-Command $tool -ErrorAction SilentlyContinue) {
            Write-Info "✓ 找到 $tool"
        } else {
            Write-Error "✗ 未找到 $tool"
            $allFound = $false
        }
    }
    
    if (-not $allFound) {
        Write-Warning "缺少必要工具，请安装："
        Write-Warning "  - OpenSSH Client (Windows 10/11自带)"
        Write-Warning "  - 或使用 Git Bash"
        Write-Warning "  - 或使用 WSL"
        return $false
    }
    
    return $true
}

# 创建远程目录
function New-RemoteDirectories {
    Write-Step "创建远程目录结构..."
    
    $script = @"
sudo mkdir -p $NasAppDir/static
sudo mkdir -p $NasAppDir/templates
sudo mkdir -p $NasAppDir/deployment
sudo mkdir -p $NasDataDir
sudo mkdir -p $NasFilesDir/projects
sudo mkdir -p $NasFilesDir/record
sudo mkdir -p $NasFilesDir/photos
sudo mkdir -p /volume2/MES/backups
sudo chown -R $NasUser:users /volume2/MES
sudo chmod -R 755 /volume2/MES
echo "目录创建完成"
"@
    
    try {
        ssh "$NasUser@$NasHost" $script
        if ($LASTEXITCODE -eq 0) {
            Write-Info "✓ 远程目录创建完成"
            return $true
        } else {
            Write-Error "✗ 远程目录创建失败"
            return $false
        }
    } catch {
        Write-Error "✗ 创建目录异常: $_"
        return $false
    }
}

# 上传文件
function Copy-ApplicationFiles {
    Write-Step "上传应用文件..."
    
    $projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    $appWebDir = Join-Path $projectRoot "app_web"
    
    Write-Info "项目根目录: $projectRoot"
    Write-Info "应用目录: $appWebDir"
    
    # 检查目录是否存在
    if (-not (Test-Path $appWebDir)) {
        Write-Error "✗ 找不到应用目录: $appWebDir"
        return $false
    }
    
    # 上传Python文件
    Write-Info "上传Python模块..."
    $pythonFiles = @(
        "mesapp.py", "config.py", "auth.py",
        "data_access_layer.py", "permission_service.py",
        "user_management_service.py", "synology_auth_client.py",
        "photo_api.py", "process_config_api.py",
        "project_config_manager.py", "config_history_manager.py",
        "h2_api.py", "error_handler.py", "security_validator.py",
        "webdav_client_v2.py", "smb_client.py"
    )
    
    foreach ($file in $pythonFiles) {
        $filePath = Join-Path $appWebDir $file
        if (Test-Path $filePath) {
            try {
                scp $filePath "$NasUser@${NasHost}:$NasAppDir/" 2>&1 | Out-Null
                if ($LASTEXITCODE -eq 0) {
                    Write-Info "  ✓ $file"
                } else {
                    Write-Warning "  ✗ $file (失败)"
                }
            } catch {
                Write-Warning "  ✗ $file (异常: $_)"
            }
        } else {
            Write-Warning "  ✗ $file (文件不存在)"
        }
    }
    
    # 上传requirements.txt
    $reqFile = Join-Path $appWebDir "requirements.txt"
    if (Test-Path $reqFile) {
        scp $reqFile "$NasUser@${NasHost}:$NasAppDir/" 2>&1 | Out-Null
        Write-Info "  ✓ requirements.txt"
    }
    
    Write-Info "✓ 应用文件上传完成"
    Write-Warning "注意: static/ 和 templates/ 目录需要手动使用WinSCP上传"
    
    return $true
}

# 初始化数据库
function Initialize-Database {
    Write-Step "初始化数据库..."
    
    $deploymentDir = $PSScriptRoot
    $sqlFile = Join-Path $deploymentDir "database_setup.sql"
    
    if (-not (Test-Path $sqlFile)) {
        Write-Error "✗ 找不到数据库初始化脚本: $sqlFile"
        return $false
    }
    
    # 上传SQL文件
    scp $sqlFile "$NasUser@${NasHost}:$NasAppDir/deployment/" 2>&1 | Out-Null
    
    # 执行初始化
    $script = @"
cd $NasAppDir/deployment
sqlite3 $NasDataDir/users.db < database_setup.sql
echo "数据库初始化完成"
"@
    
    try {
        ssh "$NasUser@$NasHost" $script
        if ($LASTEXITCODE -eq 0) {
            Write-Info "✓ 数据库初始化完成"
            return $true
        } else {
            Write-Error "✗ 数据库初始化失败"
            return $false
        }
    } catch {
        Write-Error "✗ 数据库初始化异常: $_"
        return $false
    }
}

# 安装依赖
function Install-Dependencies {
    if ($SkipDeps) {
        Write-Warning "跳过依赖安装"
        return $true
    }
    
    Write-Step "安装Python依赖..."
    
    $script = @"
cd $NasAppDir
if [ -f requirements.txt ]; then
    pip3 install -r requirements.txt --user
    echo "依赖安装完成"
else
    echo "警告: requirements.txt 不存在"
fi
"@
    
    try {
        ssh "$NasUser@$NasHost" $script
        if ($LASTEXITCODE -eq 0) {
            Write-Info "✓ Python依赖安装完成"
            return $true
        } else {
            Write-Warning "✗ 依赖安装失败（可能需要手动安装）"
            return $true  # 不阻止继续
        }
    } catch {
        Write-Warning "✗ 依赖安装异常: $_"
        return $true  # 不阻止继续
    }
}

# 配置服务
function Set-SystemdService {
    if ($SkipService) {
        Write-Warning "跳过服务配置"
        return $true
    }
    
    Write-Step "配置systemd服务..."
    
    $serviceContent = @"
[Unit]
Description=MES Application Service
After=network.target

[Service]
Type=simple
User=$NasUser
WorkingDirectory=$NasAppDir
Environment="PYTHONUNBUFFERED=1"
Environment="FLASK_ENV=production"
ExecStart=/usr/bin/python3 $NasAppDir/mesapp.py
Restart=always
RestartSec=10
StandardOutput=append:/var/log/mesapp.log
StandardError=append:/var/log/mesapp.log

[Install]
WantedBy=multi-user.target
"@
    
    # 创建临时文件
    $tempFile = [System.IO.Path]::GetTempFileName()
    $serviceContent | Out-File -FilePath $tempFile -Encoding UTF8
    
    # 上传服务文件
    scp $tempFile "$NasUser@${NasHost}:/tmp/mesapp.service" 2>&1 | Out-Null
    Remove-Item $tempFile
    
    # 安装服务
    $script = @"
sudo mv /tmp/mesapp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable mesapp
echo "服务配置完成"
"@
    
    try {
        ssh "$NasUser@$NasHost" $script
        if ($LASTEXITCODE -eq 0) {
            Write-Info "✓ systemd服务配置完成"
            return $true
        } else {
            Write-Error "✗ 服务配置失败"
            return $false
        }
    } catch {
        Write-Error "✗ 服务配置异常: $_"
        return $false
    }
}

# 启动服务
function Start-MesService {
    Write-Step "启动服务..."
    
    $script = @"
sudo systemctl start mesapp
sleep 3
sudo systemctl status mesapp --no-pager
"@
    
    try {
        ssh "$NasUser@$NasHost" $script
        if ($LASTEXITCODE -eq 0) {
            Write-Info "✓ 服务启动完成"
            return $true
        } else {
            Write-Error "✗ 服务启动失败"
            return $false
        }
    } catch {
        Write-Error "✗ 服务启动异常: $_"
        return $false
    }
}

# 验证部署
function Test-Deployment {
    Write-Step "验证部署..."
    
    Start-Sleep -Seconds 5
    
    $healthUrl = "http://${NasHost}:8891/api/h2/health"
    Write-Info "检查健康端点: $healthUrl"
    
    $maxRetries = 5
    $retryCount = 0
    
    while ($retryCount -lt $maxRetries) {
        try {
            $response = Invoke-WebRequest -Uri $healthUrl -TimeoutSec 5 -ErrorAction Stop
            if ($response.StatusCode -eq 200) {
                Write-Info "✓ 健康检查通过 (HTTP 200)"
                return $true
            }
        } catch {
            $retryCount++
            if ($retryCount -lt $maxRetries) {
                Write-Warning "健康检查失败，重试 $retryCount/$maxRetries..."
                Start-Sleep -Seconds 3
            } else {
                Write-Error "✗ 健康检查失败"
                return $false
            }
        }
    }
    
    return $false
}

# 显示部署摘要
function Show-DeploymentSummary {
    Write-Host ""
    Write-Host "=========================================" -ForegroundColor Green
    Write-Host "  部署完成" -ForegroundColor Green
    Write-Host "=========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "应用信息:"
    Write-Host "  地址: http://${NasHost}:8891"
    Write-Host "  健康检查: http://${NasHost}:8891/api/h2/health"
    Write-Host ""
    Write-Host "服务管理:"
    Write-Host "  启动: sudo systemctl start mesapp"
    Write-Host "  停止: sudo systemctl stop mesapp"
    Write-Host "  重启: sudo systemctl restart mesapp"
    Write-Host "  状态: sudo systemctl status mesapp"
    Write-Host ""
    Write-Host "日志查看:"
    Write-Host "  应用日志: sudo tail -f /var/log/mesapp.log"
    Write-Host ""
    Write-Host "下一步:"
    Write-Host "  1. 使用WinSCP上传 static/ 和 templates/ 目录"
    Write-Host "  2. 访问 http://${NasHost}:8891 测试系统"
    Write-Host "  3. 查看文档: app_web/docs/"
    Write-Host ""
}

# 主函数
function Main {
    if ($Help) {
        Show-Help
        return
    }
    
    Show-Header

    if (-not (Assert-LegacyDeployAcknowledged)) {
        return
    }
    
    # 检查工具
    if (-not (Test-RequiredTools)) {
        Write-Error "缺少必要工具，部署终止"
        Write-Info "建议使用 Git Bash 或 WSL 运行 deploy.sh 脚本"
        return
    }
    
    # 检查连接
    if (-not (Test-SshConnection)) {
        Write-Error "SSH连接失败，部署终止"
        return
    }
    
    # 执行部署步骤
    if (-not (New-RemoteDirectories)) { return }
    if (-not (Initialize-Database)) { return }
    if (-not (Copy-ApplicationFiles)) { return }
    if (-not (Install-Dependencies)) { return }
    if (-not (Set-SystemdService)) { return }
    if (-not (Start-MesService)) { return }
    
    # 验证部署
    if (Test-Deployment) {
        Show-DeploymentSummary
    } else {
        Write-Error "部署验证失败"
        Write-Error "请检查日志: ssh $NasUser@$NasHost 'sudo tail -f /var/log/mesapp.log'"
    }
}

# 执行主函数
Main
