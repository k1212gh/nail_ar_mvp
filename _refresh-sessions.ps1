# =====================================================================
#  대화목록 정상화 스크립트  (nail_ar_mvp)
#  - .jsonl 원본 transcript 들을 스캔해서:
#      1) 프로젝트 루트에 _대화목록.md  (항상 보이는 세션 목록/인덱스)
#      2) 대화복원\<날짜>_<id8>_<제목>.md  (각 세션 전체 대화)
#  - 세션이 늘어나면 이 스크립트만 다시 실행하면 자동 반영됨.
#  실행: PowerShell 에서  ./_refresh-sessions.ps1
# =====================================================================

$ErrorActionPreference = 'Stop'
$JsonlDir = "C:\Users\k1212\.claude\projects\c--Users-k1212-AppData-Local-Packages-Claude-pzs8sxrjxfjjc-LocalCache-Roaming-Claude-local-agent-mode-sessions-e09da062-dfa9-4cf7-a52c-504d5ae18918-be0f4f74-2505-4b1a-a0e2-fc77097d2f44-local-51d6b6ba--1qn84o"
$ProjRoot  = "C:\Users\k1212\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\local-agent-mode-sessions\e09da062-dfa9-4cf7-a52c-504d5ae18918\be0f4f74-2505-4b1a-a0e2-fc77097d2f44\local_51d6b6ba-fabe-4dac-9c35-b1fe5d4107b8\outputs\nail_ar_mvp"
$RestoreDir = Join-Path $ProjRoot "대화복원"
if (-not (Test-Path $RestoreDir)) { New-Item -ItemType Directory -Path $RestoreDir | Out-Null }

function Get-Text($content) {
  if ($null -eq $content) { return "" }
  if ($content -is [string]) { return $content }
  $parts = @()
  foreach ($b in $content) {
    if ($b.type -eq 'text' -and $b.text) { $parts += $b.text }
  }
  return ($parts -join "`n")
}
function Clean-Title($t) {
  if (-not $t) { return "(제목없음)" }
  $t = ($t -split "`n")[0].Trim()
  $t = $t -replace '[\\/:\*\?"<>\|]', ' '
  if ($t.Length -gt 50) { $t = $t.Substring(0,50) }
  if (-not $t) { $t = "(제목없음)" }
  return $t
}

$sessions = @()
foreach ($f in (Get-ChildItem "$JsonlDir\*.jsonl" | Sort-Object LastWriteTime)) {
  $id = $f.BaseName
  $lines = Get-Content $f.FullName -Encoding utf8
  $userMsgs = @(); $asstCount = 0; $toolNames = @{}
  $firstTitle = $null; $firstTs = $null; $lastTs = $null
  $transcript = New-Object System.Text.StringBuilder
  foreach ($l in $lines) {
    try { $o = $l | ConvertFrom-Json } catch { continue }
    if ($o.timestamp) { if (-not $firstTs) { $firstTs = $o.timestamp }; $lastTs = $o.timestamp }
    if ($o.type -eq 'user' -and $o.message.role -eq 'user') {
      $txt = Get-Text $o.message.content
      if ($txt -and $txt.Trim() -and $txt -notmatch '^\s*<(system-reminder|command|local-command)' ) {
        $userMsgs += $txt
        if (-not $firstTitle) { $firstTitle = $txt }
        [void]$transcript.AppendLine("### 🧑 나"); [void]$transcript.AppendLine($txt.Trim()); [void]$transcript.AppendLine("")
      }
    }
    elseif ($o.type -eq 'assistant' -and $o.message.role -eq 'assistant') {
      $asstCount++
      $txt = Get-Text $o.message.content
      $tools = @()
      foreach ($b in $o.message.content) { if ($b.type -eq 'tool_use') { $tools += $b.name; $toolNames[$b.name] = $true } }
      if ($txt.Trim()) { [void]$transcript.AppendLine("### 🤖 Claude"); [void]$transcript.AppendLine($txt.Trim()); [void]$transcript.AppendLine("") }
      if ($tools.Count) { [void]$transcript.AppendLine("> 🔧 도구: " + (($tools | Group-Object | ForEach-Object { $_.Name + "×" + $_.Count }) -join ", ")); [void]$transcript.AppendLine("") }
    }
  }
  $title = Clean-Title $firstTitle
  $dateStr = if ($firstTs) { ([datetime]$firstTs).ToLocalTime().ToString("yyyy-MM-dd HH:mm") } else { $f.LastWriteTime.ToString("yyyy-MM-dd HH:mm") }
  $fileDate = if ($firstTs) { ([datetime]$firstTs).ToLocalTime().ToString("yyyy-MM-dd") } else { $f.LastWriteTime.ToString("yyyy-MM-dd") }
  $mdName = "$fileDate" + "_" + $id.Substring(0,8) + "_" + ($title -replace '\s+','_') + ".md"
  $mdPath = Join-Path $RestoreDir $mdName

  $header = "# $title`n`n- 세션 ID: ``$id```n- 시작: $dateStr`n- 내 메시지 $($userMsgs.Count)개 / Claude 응답 $asstCount개`n- 이어하기: ``claude --resume $id```n`n---`n`n"
  Set-Content -Path $mdPath -Value ($header + $transcript.ToString()) -Encoding utf8

  $sessions += [pscustomobject]@{
    Id=$id; Id8=$id.Substring(0,8); Title=$title; Date=$dateStr; SortKey=$firstTs
    UserCount=$userMsgs.Count; AsstCount=$asstCount; SizeKB=[math]::Round($f.Length/1KB,0)
    MdRel="대화복원/$mdName"
  }
}

# ---- 인덱스 생성 ----
$sorted = $sessions | Sort-Object SortKey -Descending
$idx = New-Object System.Text.StringBuilder
[void]$idx.AppendLine("# 💬 대화 목록 (nail_ar_mvp)")
[void]$idx.AppendLine("")
[void]$idx.AppendLine("> 이 파일을 탭 고정(Pin)해 두면 왼쪽 패널 대신 항상 과거 대화를 볼 수 있습니다.")
[void]$idx.AppendLine("> 갱신: PowerShell 에서 ``./_refresh-sessions.ps1`` 다시 실행.")
[void]$idx.AppendLine("> 원본 세션 직접 복귀: 외부 터미널에서 ``claude --resume <세션ID>``")
[void]$idx.AppendLine("")
[void]$idx.AppendLine("| 날짜 | 제목 | 내용 | 전체보기 | 이어하기(ID) |")
[void]$idx.AppendLine("|---|---|---|---|---|")
foreach ($s in $sorted) {
  $link = "[열기](" + ($s.MdRel -replace ' ','%20') + ")"
  [void]$idx.AppendLine("| $($s.Date) | $($s.Title) | 💬$($s.UserCount) / 🤖$($s.AsstCount) ($($s.SizeKB)KB) | $link | ``$($s.Id)`` |")
}
[void]$idx.AppendLine("")
[void]$idx.AppendLine("---")
[void]$idx.AppendLine("총 $($sessions.Count)개 세션 · 마지막 갱신 시각은 이 파일 수정시각 참조")
Set-Content -Path (Join-Path $ProjRoot "_대화목록.md") -Value $idx.ToString() -Encoding utf8

Write-Output ("완료: $($sessions.Count)개 세션 인덱싱")
Write-Output ("인덱스: " + (Join-Path $ProjRoot "_대화목록.md"))
Write-Output ("복원본 폴더: " + $RestoreDir)
