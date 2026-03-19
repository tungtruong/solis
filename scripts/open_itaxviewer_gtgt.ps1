Param(
    [string]$BaseUrl = "https://tt133-mvp-api-639731818835.asia-southeast1.run.app",
    [string]$Email = "demo@wssmeas.local",
    [string]$Password = "demo123",
    [string]$CompanyId = "COMP-WS-001",
    [string]$Period = "2026-03",
    [string]$ReportId = "gtgt",
    [string]$OutputDir = "d:/Repos/WSSMEAS/.local-dev",
    [string]$ITaxViewerPath = "C:/Program Files (x86)/iTax Viewer/iTaxViewer.exe"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ITaxViewerPath)) {
    throw "Khong tim thay iTaxViewer tai duong dan: $ITaxViewerPath"
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$loginBody = @{
    email = $Email
    password = $Password
} | ConvertTo-Json

$login = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/auth/login-demo" -ContentType "application/json" -Body $loginBody
if (-not $login.token) {
    throw "Dang nhap that bai: khong nhan duoc token"
}

$xmlPayload = @{
    email = $Email
    company_id = $CompanyId
    period = $Period
    report_id = $ReportId
    submitted_by = $Email
} | ConvertTo-Json

$xmlResp = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/demo/compliance/export-xml" -ContentType "application/json" -Body $xmlPayload
if (-not $xmlResp.content_base64) {
    throw "Khong nhan duoc noi dung XML"
}

$periodToken = ($Period -replace "[^0-9Q-]", "")
$fileName = if ($xmlResp.file_name) { [string]$xmlResp.file_name } else { "tokhai_${ReportId}_${periodToken}.xml" }
$xmlPath = Join-Path $OutputDir $fileName

[System.IO.File]::WriteAllBytes($xmlPath, [System.Convert]::FromBase64String([string]$xmlResp.content_base64))
Write-Host "Da luu XML:" $xmlPath

# Mo truc tiep bang iTaxViewer de xem dung giao dien/chuan in cua app tong cuc thue.
Start-Process -FilePath $ITaxViewerPath -ArgumentList $xmlPath
Write-Host "Da mo iTaxViewer voi file XML."
