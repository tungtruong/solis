Param(
    [string]$BaseUrl = "https://tt133-mvp-api-639731818835.asia-southeast1.run.app",
    [string]$Email = "demo@wssmeas.local",
    [string]$Password = "demo123",
    [string]$CompanyId = "COMP-WS-001",
    [string]$Period = "2026-03",
    [string]$ReportId = "gtgt",
    [string]$OutputDir = "d:/Repos/WSSMEAS/.local-dev",
    [string]$ITaxViewerPath = "C:/Program Files (x86)/iTax Viewer/iTaxViewer.exe",
    [switch]$ConvertToPdf,
    [string]$PdfPath = "",
    [int]$StartupDelaySeconds = 5,
    [int]$DialogDelaySeconds = 2
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
$viewerProcess = Start-Process -FilePath $ITaxViewerPath -ArgumentList $xmlPath -PassThru
Write-Host "Da mo iTaxViewer voi file XML."

if ($ConvertToPdf) {
    $resolvedPdfPath = if ([string]::IsNullOrWhiteSpace($PdfPath)) {
        Join-Path $OutputDir (([System.IO.Path]::GetFileNameWithoutExtension($fileName)) + ".pdf")
    }
    else {
        $PdfPath
    }

    New-Item -ItemType Directory -Path (Split-Path -Path $resolvedPdfPath -Parent) -Force | Out-Null

    $previousDefaultPrinter = Get-CimInstance Win32_Printer | Where-Object { $_.Default -eq $true } | Select-Object -First 1
    $pdfPrinter = Get-CimInstance Win32_Printer -Filter "Name='Microsoft Print to PDF'"
    if (-not $pdfPrinter) {
        throw "Khong tim thay may in 'Microsoft Print to PDF'."
    }

    $null = Invoke-CimMethod -InputObject $pdfPrinter -MethodName SetDefaultPrinter

    Start-Sleep -Seconds $StartupDelaySeconds
    $shell = New-Object -ComObject WScript.Shell
    $activated = $shell.AppActivate($viewerProcess.Id)
    if (-not $activated) {
        $activated = $shell.AppActivate("iTax Viewer")
    }
    if (-not $activated) {
        throw "Khong the focus cua so iTaxViewer de auto print."
    }

    $shell.SendKeys("^p")
    Start-Sleep -Seconds $DialogDelaySeconds
    $shell.SendKeys("{ENTER}")
    Start-Sleep -Seconds $DialogDelaySeconds

    Set-Clipboard -Value $resolvedPdfPath
    $shell.SendKeys("^v")
    Start-Sleep -Milliseconds 300
    $shell.SendKeys("{ENTER}")
    Start-Sleep -Seconds 4

    if (Test-Path $resolvedPdfPath) {
        Write-Host "Da convert PDF bang iTaxViewer:" $resolvedPdfPath
    }
    else {
        Write-Warning "Khong tim thay file PDF sau auto print. Kiem tra hop thoai Save As va thu lai."
    }

    if ($previousDefaultPrinter -and $previousDefaultPrinter.Name -ne $pdfPrinter.Name) {
        $restorePrinter = Get-CimInstance Win32_Printer -Filter "Name='$($previousDefaultPrinter.Name.Replace("'", "''"))'"
        if ($restorePrinter) {
            $null = Invoke-CimMethod -InputObject $restorePrinter -MethodName SetDefaultPrinter
        }
    }
}
