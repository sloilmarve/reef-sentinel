# 珊瑚哨兵 Reef Sentinel —— 两个一键脚本（本地预览 / 一键刷新）的实际逻辑
#
# 为什么中文横幅不在 .bat 里：
#   cmd.exe 按字节偏移读取批处理文件；在 chcp 65001 之后，UTF-8 多字节字符
#   一旦跨过读取缓冲区边界，解析就会失步并把一行切成两半。第 48 轮实测
#   （Windows 11 26100 / cmd 10.0）控制台会打出：
#     '口即可停止服务。' is not recognized as an internal or external command,
#   —— 服务照旧起得来，但那是一行红字错误，评委双击时看得见。UTF-8 加 BOM
#   也一样；GBK 不报错，但项目约定所有文本文件都是 UTF-8。因此两个 .bat
#   只留纯 ASCII，把控制权交给本脚本。
#
# 本文件用 UTF-8 with BOM 保存：Windows PowerShell 5.1 在没有 BOM 时会按 ANSI
# 代码页解码，中文会变成乱码。
#
# 第 49 轮起：解释器不再只看「能不能跑」，而是真的问一遍环境。
#   py 启动器 / PATH 里的 python / python3 三个候选依次用 tools/check_env.py 探一次，
#   挑第一个「版本齐全」的；本机实测 py -> Python 3.13.9 + numpy 2.3.5，
#   而钉住的 numpy==2.2.6 装在 PATH 的 python（3.10.11）上 —— 旧版按 py 优先会
#   默默用漂移的解释器刷新，浮点末位可能与已冻结材料不同。刷新前还缺依赖时，
#   不再抛 ImportError 回溯，而是打出「缺什么 + 一条能直接复制的安装命令」，
#   并问一句要不要现在装。
#
# 用法（.bat 已经封装好，一般不用手敲）：
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\launch.ps1 -Mode preview
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\launch.ps1 -Mode refresh

param(
  [ValidateSet('preview', 'refresh')]
  [string]$Mode = 'preview',
  # 非交互（脚本 / CI / 自动测试）时用：缺依赖就直接装，不再等按键。
  # 第 50 轮加的：只靠 [Console]::IsInputRedirected 判断会把「回答 Y」也一起吞掉，
  # 安装这条路就永远测不到、脚本里也永远装不上。
  [switch]$Yes
)

$ErrorActionPreference = 'Stop'

# tools/ 的上一层就是项目根目录
$root = Split-Path -Parent $PSScriptRoot
$check = Join-Path $root 'tools\check_env.py'

function Say([string]$Text = '') { Write-Host $Text }

function Wait-Key {
  # 双击时等一个回车，窗口不要一闪而过。
  # stdin 被重定向（管道 / 自动测试）时 Read-Host 不会抛错而是永久阻塞，
  # 所以先看 [Console]::IsInputRedirected —— 第 49 轮实测：不加这一句，
  # 干净解压包里的自动测试会一直挂在这个函数上不退出。
  if ([Console]::IsInputRedirected) { Start-Sleep -Seconds 3; return }
  try { [void](Read-Host '  按回车键关闭这个窗口') } catch { Start-Sleep -Seconds 3 }
}

# 候选解释器：py 启动器（Windows 官方安装自带）-> PATH 里的 python -> python3，去重。
# 注意 Windows 应用商店的 python.exe 占位符也在 PATH 里，它只会弹商店、并不执行代码，
# 所以候选一定要真的跑一次才算数（见 Probe-Env）。
function Get-PythonCandidates {
  $seen = @{}
  $out = @()
  foreach ($name in @('py', 'python', 'python3')) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($null -eq $cmd) { continue }
    $exe = $cmd.Source
    if (-not $exe) { $exe = $cmd.Definition }
    if (-not $exe) { continue }
    $key = $exe.ToLower()
    if ($seen.ContainsKey($key)) { continue }
    $seen[$key] = $true
    $out += $exe
  }
  return ,$out
}

# 用 tools/check_env.py --json 真探一次，返回 @{state='ready'|'drift'|'incomplete'; json=...}
#   ready      = 解释器够新、要求的包都在且版本与 requirements.txt 一致
#   drift      = 能跑，但某个包与钉住的版本不同（浮点末位可能漂）
#   incomplete = 解释器太旧或缺包/装坏 —— 这个候选要给出安装指引
#   返回 $null  = 这个解释器根本执行不了代码（例如商店占位符）
# 没有 check_env.py 时退回最朴素的版本判断（旧行为），保证脚本不会因为缺文件而失效。
function Probe-Env([string]$exe, [string[]]$req = @()) {
  if (-not (Test-Path $check)) {
    try { $null = & $exe -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>$null } catch { return $null }
    if ($LASTEXITCODE -ne 0) { return $null }
    if ($req.Count -gt 0) { return @{ state = 'incomplete'; json = $null } }
    return @{ state = 'ready'; json = $null }
  }
  $argv = @($check, '--json')
  if ($req.Count -gt 0) { $argv += @('--require', ($req -join ',')) }
  $raw = $null
  try { $raw = & $exe @argv 2>$null } catch { return $null }
  if ($null -eq $raw) { return $null }
  $obj = $null
  try { $obj = ($raw -join "`n") | ConvertFrom-Json } catch { $obj = $null }
  if ($null -eq $obj) { return $null }
  # check_env.py 给的是布尔量（PowerShell 5.1 里空 JSON 数组的 .Count 不稳）
  if ($obj.needs_install) { return @{ state = 'incomplete'; json = $obj } }
  if ($obj.drifted) { return @{ state = 'drift'; json = $obj } }
  return @{ state = 'ready'; json = $obj }
}

# 注意：Get-PythonCandidates 用 return ,$out 已经保证返回数组；这里若再套一层 @()，
# 会变成「只有一个元素的数组，而那个元素本身是数组」——后面 foreach 只跑一次，
# $c 变成三条路径拼成的一整串，Probe-Env 拿它当可执行文件自然全部失败。
# 第 49 轮在干净解压包里实测踩到过：预览脚本报「找到的 Python 都跑不起来」。
$cands = Get-PythonCandidates
if ($cands.Count -eq 0) {
  Say ''
  Say '  没有找到 Python 3.10 以上版本。'
  Say '  ① 装一个 Python 3.10+（python.org，安装时勾上 Add python.exe to PATH），或者'
  Say '  ② 直接双击 demo\index.html 看成品页：单文件、无需 Python、无需联网。'
  Say ''
  Wait-Key
  exit 1
}

if ($Mode -eq 'preview') {
  # 本地预览只用标准库的 http.server：只要有一个能跑代码的 Python 3.10+ 就够
  $py = $null
  foreach ($c in $cands) {
    if ($null -ne (Probe-Env -exe $c)) { $py = $c; break }
  }
  if ($null -eq $py) {
    Say ''
    Say '  找到的 Python 都跑不起来（可能是 Windows 应用商店的占位符）。'
    Say '  直接双击 demo\index.html 也能看成品页：单文件、无需 Python、无需联网。'
    Say ''
    Wait-Key
    exit 1
  }
  try { $Host.UI.RawUI.WindowTitle = '珊瑚哨兵 Reef Sentinel - 本地预览' } catch { }
  $url = 'http://127.0.0.1:8788/'
  Say ''
  Say '  ============================================================'
  Say '   珊瑚哨兵 Reef Sentinel  -  仙本那珊瑚礁气候预警台'
  Say '  ============================================================'
  Say "   预览地址 : $url   （2 秒后自动打开浏览器）"
  Say '   数据窗口 : 见页面顶部（最新一天由流水线写入，本脚本不写死日期）'
  Say "   项目目录 : $root"
  Say '  ------------------------------------------------------------'
  Say '   看完后关闭这个窗口即可停止服务。'
  Say '  ============================================================'
  Say ''
  Start-Process -FilePath 'powershell' -WindowStyle Hidden -ArgumentList @(
    '-NoProfile', '-WindowStyle', 'Hidden', '-Command',
    "Start-Sleep -Seconds 2; Start-Process '$url'"
  ) | Out-Null
  & $py -m http.server 8788 --bind 127.0.0.1 --directory (Join-Path $root 'demo')
  $code = $LASTEXITCODE
  Say ''
  Say '  服务已停止。'
  Say ''
  Wait-Key
  exit $code
}

try { $Host.UI.RawUI.WindowTitle = '珊瑚哨兵 Reef Sentinel - 一键刷新' } catch { }
Say ''
Say '  ============================================================'
Say '   珊瑚哨兵 Reef Sentinel  -  一键刷新（重新取数并重画成品页）'
Say '  ============================================================'
Say '   这一步会访问 Open-Meteo 公开 API 取最新数据，然后重算指标与模型，'
Say '   最后重画 demo\index.html。全程约 1 到 3 分钟（上游响应快时约 40 秒），'
Say '   请勿关闭本窗口。'
Say '  ------------------------------------------------------------'
Say ''

# 刷新要跑 pipeline/refresh.py，标准库之外只依赖 numpy（见 requirements.txt）。
# 在三个候选里挑第一个「版本齐全」的；没有齐全的，优先留一个能跑的（漂移 > 缺东西）。
$req = @('numpy')
$py = $null
$probe = $null
$fallback = $null
foreach ($c in $cands) {
  $r = Probe-Env -exe $c -req $req
  if ($null -eq $r) { continue }
  if ($r.state -eq 'ready') { $py = $c; $probe = $r; break }
  if ($null -eq $py) { $py = $c; $probe = $r }
  if ($null -eq $fallback) { $fallback = @{ exe = $c; probe = $r } }
}

if ($null -eq $py) {
  if ($null -ne $fallback) {
    $py = $fallback.exe
    $probe = $fallback.probe
  } else {
    Say '  找到的 Python 都跑不起来（可能是 Windows 应用商店的占位符）。'
    Say '  ① 装一个 Python 3.10+（python.org，勾上 Add python.exe to PATH），或者'
    Say '  ② 直接双击 demo\index.html 看成品页：单文件、无需 Python、无需联网。'
    Say ''
    Wait-Key
    exit 1
  }
}

if ($probe.state -eq 'drift') {
  foreach ($row in @($probe.json.rows)) {
    if ($row.state -eq 'drift') {
      Say "  注意：本机 $($row.name) $($row.found)，requirements.txt 钉的是 $($row.pin)。"
    }
  }
  Say '  刷新照常能跑，但浮点末位可能与已冻结材料不同（想逐位复现请装 numpy==2.2.6）。'
  Say ''
}

if ($probe.state -eq 'incomplete') {
  # 缺依赖时给「缺什么 + 怎么办」，而不是让 pipeline/refresh.py 抛一段 ImportError 回溯
  Say "  一键刷新需要 numpy，当前的 Python（$py）还不满足："
  Say ''
  if (Test-Path $check) { & $py $check --require numpy }
  else { Say "      $py -m pip install -r requirements.txt" }
  Say ''
  Say '  要不要现在装？按 Y 回车自动执行安装，其它键退出。'
  $ans = ''
  if ($Yes) {
    Say '  （-Yes：非交互模式，直接安装）'
    $ans = 'Y'
  } elseif ([Console]::IsInputRedirected) {
    # 输入被重定向时不能等按键（等下去就是永久阻塞），按「不装」处理，
    # 并告诉调用方非交互安装的正确姿势是 -Yes。
    Say '  （输入被重定向，按「不装」处理；非交互安装请加 -Yes）'
    $ans = 'N'
  } else {
    try { $ans = Read-Host '  安装依赖？(Y/N)' } catch { $ans = 'N' }
  }
  if ($ans -notmatch '^[Yy]') {
    Say ''
    Say '  已取消。装好之后再双击一次 更新数据.bat 即可。'
    Say ''
    Wait-Key
    exit 1
  }
  Say ''
  Say '  正在安装（python -m pip install -r requirements.txt）...'
  & $py -m pip install -r (Join-Path $root 'requirements.txt')
  if ($LASTEXITCODE -ne 0) {
    Say ''
    Say '  安装失败。请手动执行下面这一条（需要联网）：'
    Say "      $py -m pip install -r requirements.txt"
    Say '  只想看成品页的话不需要装任何东西：双击 demo\index.html。'
    Say ''
    Wait-Key
    exit 1
  }
  Say '  安装完成，继续刷新。'
  Say ''
}

& $py (Join-Path $root 'pipeline\refresh.py')
$code = $LASTEXITCODE
Say ''
Say "  刷新结束。成品页：$(Join-Path $root 'demo\index.html')"
Say '  直接双击该文件即可查看最新版本，或运行 启动预览.bat 在浏览器里看。'
Say ''
Wait-Key
exit $code
