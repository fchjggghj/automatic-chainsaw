# 一键查看所有爬虫实例的下载进度
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "    快穿小说下载器 - 总进度查看" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$ports = @(8765, 8766, 8767, 8768, 8769)
$totalDownloaded = 0
$totalSearched = 0
$totalFailed = 0
$runningCount = 0

foreach ($port in $ports) {
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/progress" -TimeoutSec 3
        $stats = $r.stats
        $dl = $stats.downloaded
        $searched = $stats.searched
        $failed = $stats.failed
        $isRunning = $r.running
        
        $totalDownloaded += $dl
        $totalSearched += $searched
        $totalFailed += $failed
        if ($isRunning) { $runningCount++ }
        
        $statusColor = if ($isRunning) { "Green" } else { "Gray" }
        $statusText = if ($isRunning) { "运行中" } else { "空闲" }
        
        Write-Host ""
        Write-Host "[$port] $statusText" -ForegroundColor $statusColor
        Write-Host "  搜索: $searched | 下载: $dl | 失败: $failed" -ForegroundColor White
        if ($r.current_keyword) {
            Write-Host "  当前: $($r.current_keyword) @ $($r.current_site)" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "[$port] 无法连接" -ForegroundColor Red
    }
}

# 统计文件数
$files = Get-ChildItem -Path "C:\Users\Administrator\Desktop\books\books\novel_crawler\downloads" -Recurse -File -ErrorAction SilentlyContinue
$fileCount = $files.Count
$totalSize = ($files | Measure-Object -Property Length -Sum).Sum / 1MB

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "总统计" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "运行中实例: $runningCount / 5" -ForegroundColor Green
Write-Host "总搜索: $totalSearched" -ForegroundColor White
Write-Host "总下载(API): $totalDownloaded" -ForegroundColor Green
Write-Host "总失败: $totalFailed" -ForegroundColor Red
Write-Host "文件数: $fileCount" -ForegroundColor Cyan
Write-Host "总大小: $([math]::Round($totalSize, 2)) MB" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
