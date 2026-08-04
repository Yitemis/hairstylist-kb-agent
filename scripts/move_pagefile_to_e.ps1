# 把 C 盘 pagefile.sys 移到 E 盘 + 减小大小
# 用法：右键 PowerShell → 用管理员身份运行 → 执行此脚本 → 重启

$ErrorActionPreference = 'Stop'
Write-Host '=== 移动 pagefile 到 E 盘 ===' -ForegroundColor Green

# 1. 创建 E 盘 pagefile 目录
New-Item -ItemType Directory -Path 'E:\pagefile' -Force | Out-Null

# 2. 设置 E 盘 pagefile（系统管理大小 4-16GB）
Write-Host '[1/3] 设置 E 盘 pagefile（4-16GB 自动）...' -ForegroundColor Cyan
& wmic pagefileset where "name='E:\pagefile\pagefile.sys'" create 2>&1 | Out-Null
& wmic pagefileset where "name='E:\pagefile\pagefile.sys'" set InitialSize=4096,MaximumSize=16384 2>&1 | Out-Null

# 3. 删除 C 盘 pagefile
Write-Host '[2/3] 删除 C 盘 pagefile...' -ForegroundColor Cyan
& wmic pagefileset where "name='C:\pagefile.sys'" delete 2>&1 | Out-Null

# 4. 提示重启
Write-Host '[3/3] 完成！请手动重启电脑' -ForegroundColor Yellow
Write-Host '重启后 C 盘 pagefile.sys (~22GB) 会自动删除' -ForegroundColor Yellow
