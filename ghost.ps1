<#
  ghost.ps1 - the Casperr hook for Windows PowerShell 5.1 (PSReadLine 2.0).

  LOAD IT (note the dot and the space before the path - this matters):
      . D:\ghost\ghost.ps1

  USE IT:
      casperr summon     starts the floating ghost and turns on Alt+G
      (type a command, DON'T press Enter, press Alt+G, look at the ghost)
      casperr status     shows whether the ghost and the key are active
      casperr release    turns Alt+G off and sends Casperr home
      casperr summon -Key 'Alt+Shift+G'     use a different key if Alt+G is taken

  WHAT IT DOES (and nothing more):
    * Adds ONE key binding to THIS terminal session only.
    * When you press that key it reads the text you have typed so far and sends
      it, as a small message, to the ghost window on THIS computer (127.0.0.1).
    * It never runs your command, never changes what you typed, and does not
      touch Enter, your other keys, your $PROFILE, the registry, PATH or any
      PowerShell setting.
    * Closing the terminal removes everything. If the ghost is closed, the key
      simply does nothing. Any error inside the key handler is swallowed so it
      can never break your prompt.
#>

# Must be loaded with ". " (dot-source), otherwise the 'ghost' command would
# disappear again as soon as this file finishes.
if ($MyInvocation.InvocationName -ne '.') {
    Write-Host "Please load Ghost with a dot and a space before the path, like this:" -ForegroundColor Yellow
    Write-Host "    . $PSCommandPath" -ForegroundColor Yellow
    return
}

$script:GhostDir  = $PSScriptRoot
$script:GhostPort = 47321
$script:GhostKey  = 'Alt+g'


function Test-GhostRunning {
    # If we can NOT take the ghost's port, somebody (the ghost) already has it.
    try {
        $ep = New-Object System.Net.IPEndPoint -ArgumentList ([System.Net.IPAddress]::Loopback), $script:GhostPort
        $c  = New-Object System.Net.Sockets.UdpClient -ArgumentList $ep
        $c.Close()
        return $false
    } catch {
        return $true
    }
}


function Send-GhostMessage {
    param([string]$Json)
    $udp = New-Object System.Net.Sockets.UdpClient
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Json)
        [void]$udp.Send($bytes, $bytes.Length, '127.0.0.1', $script:GhostPort)
    } finally {
        $udp.Close()
    }
}


function Start-GhostWindow {
    # pythonw.exe = Python without a black console window. Prefer the project's own venv.
    $py = Join-Path $script:GhostDir '.venv\Scripts\pythonw.exe'
    if (-not (Test-Path -LiteralPath $py)) {
        $found = Get-Command pythonw.exe -ErrorAction SilentlyContinue
        if ($found) { $py = $found.Source } else { $py = $null }
    }
    if (-not $py) {
        Write-Host "Could not find pythonw.exe. Activate your venv or check your Python install." -ForegroundColor Red
        return $false
    }
    $window = Join-Path $script:GhostDir 'ghost_window.py'
    Start-Process -FilePath $py -ArgumentList ('"{0}"' -f $window) -WorkingDirectory $script:GhostDir
    Start-Sleep -Milliseconds 700
    return $true
}


function Enable-GhostKey {
    param([string]$Key)

    $port = $script:GhostPort

    # GetNewClosure() freezes $port inside the handler so it keeps working later.
    $handler = {
        param($k, $a)
        try {
            $line = $null
            $cursor = $null
            # READ-ONLY look at what is typed on the prompt. Nothing is changed.
            [Microsoft.PowerShell.PSConsoleReadLine]::GetBufferState([ref]$line, [ref]$cursor)

            $loc = Get-Location
            if ($loc.Provider.Name -eq 'FileSystem') { $cwd = $loc.ProviderPath } else { $cwd = $env:USERPROFILE }

            $json  = ConvertTo-Json -Compress -InputObject @{ line = [string]$line; cwd = [string]$cwd }
            $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
            $udp   = New-Object System.Net.Sockets.UdpClient
            try { [void]$udp.Send($bytes, $bytes.Length, '127.0.0.1', $port) } finally { $udp.Close() }
        } catch {
            # Deliberately silent: Ghost must never disturb your prompt.
        }
    }.GetNewClosure()

    Set-PSReadLineKeyHandler -Chord $Key `
        -BriefDescription 'GhostCheck' `
        -LongDescription 'Ask the Ghost about the line you are typing (never runs it)' `
        -ScriptBlock $handler
}


function Get-GhostKeyBinding {
    param([string]$Key)
    Get-PSReadLineKeyHandler -Bound | Where-Object { $_.Key -ieq $Key }
}


function casperr {
    param(
        [Parameter(Position = 0)]
        [ValidateSet('summon', 'release', 'status', 'help')]
        [string]$Action = 'help',
        [string]$Key
    )

    if ($Key) { $script:GhostKey = $Key }
    $k = $script:GhostKey

    switch ($Action) {

        'summon' {
            if (-not (Get-Module PSReadLine)) {
                Write-Host "PSReadLine is not loaded in this terminal, so Alt+G can't be added here." -ForegroundColor Red
                return
            }
            $existing = Get-GhostKeyBinding -Key $k
            if ($existing -and ($existing.Function -ne 'GhostCheck')) {
                Write-Host "$k is already used for '$($existing.Function)'. I won't touch it." -ForegroundColor Yellow
                Write-Host "Pick another key, for example:  casperr summon -Key 'Alt+Shift+G'" -ForegroundColor Yellow
                return
            }
            if (-not (Test-GhostRunning)) {
                if (-not (Start-GhostWindow)) { return }
            }
            Enable-GhostKey -Key $k
            Write-Host "Casperr has been summoned! He is haunting this shell now. Type a command (don't press Enter), then press $k." -ForegroundColor Green
        }

        'release' {
            $existing = Get-GhostKeyBinding -Key $k
            if ($existing -and ($existing.Function -eq 'GhostCheck')) {
                Remove-PSReadLineKeyHandler -Chord $k
                Write-Host "$k released." -ForegroundColor Green
            }
            if (Test-GhostRunning) {
                Send-GhostMessage -Json '{"cmd":"quit"}'
                Write-Host "Casperr has returned to the ghost realm!" -ForegroundColor Green
            }
        }

        'status' {
            $existing = Get-GhostKeyBinding -Key $k
            $keyOn = [bool]($existing -and ($existing.Function -eq 'GhostCheck'))
            Write-Host ("Ghost window running : {0}" -f (Test-GhostRunning))
            Write-Host ("{0} bound to Ghost : {1}" -f $k, $keyOn)
        }

        default {
            Write-Host "casperr summon    summon Casperr and turn on $k"
            Write-Host "casperr status    show what is active"
            Write-Host "casperr release   turn $k off and send Casperr home"
            Write-Host "casperr summon -Key 'Alt+Shift+G'   use another key"
        }
    }
}

Write-Host "Casperr is ready. Type:  casperr summon" -ForegroundColor Cyan