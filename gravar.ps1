<#
    Compila e grava o firmware do botao no Arduino Nano.

        .\gravar.ps1              detecta a porta sozinho
        .\gravar.ps1 -Porta COM7  forca uma porta
        .\gravar.ps1 -SoCompilar  so compila, nao grava

    Sobre o bootloader: quase todo Nano clone vem com o bootloader antigo, que
    fala a 57600 baud em vez de 115200. O FQBN padrao (arduino:avr:nano) assume
    o novo e falha com "stk500_recv(): programmer is not responding". Este
    script tenta o novo e, se levar esse erro, repete com o antigo - entao voce
    nao precisa saber qual dos dois tem em maos.
#>

param(
    [string]$Porta,
    [switch]$SoCompilar
)

$ErrorActionPreference = "Stop"

$SKETCH = Join-Path $PSScriptRoot "botao_interrogacao"

# Placa nao plugada nao e bug do script - nao merece stack trace na cara.
function Erro($msg) {
    Write-Host "`n$msg" -ForegroundColor Red
    exit 1
}

# VIDs de chips USB-serial comuns em placas Arduino (mesma lista do daemon)
$VIDS = @("0x1A86", "0x0403", "0x2341", "0x2A03", "0x1B4F", "0x10C4")

function Get-ArduinoCli {
    $cmd = Get-Command arduino-cli -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($p in @("C:\Program Files\Arduino CLI\arduino-cli.exe",
                     "$env:LOCALAPPDATA\Programs\Arduino CLI\arduino-cli.exe")) {
        if (Test-Path $p) { return $p }
    }
    Erro "arduino-cli nao encontrado. Instale com: winget install ArduinoSA.CLI"
}

function Find-Porta($cli) {
    $json = & $cli board list --format json 2>$null | Out-String
    if (-not $json.Trim()) { return $null }
    $portas = (ConvertFrom-Json $json).detected_ports
    if (-not $portas) { return $null }

    # 1a escolha: placa que o proprio arduino-cli reconheceu
    foreach ($p in $portas) {
        if ($p.matching_boards) {
            Write-Host ("  detectado: {0} em {1}" -f $p.matching_boards[0].name, $p.port.address)
            return $p.port.address
        }
    }
    # 2a escolha: clone com CH340/FTDI - o cli nao identifica, o VID entrega
    foreach ($p in $portas) {
        if ($p.port.protocol -eq "serial" -and $VIDS -contains $p.port.properties.vid) {
            Write-Host ("  detectado: clone (VID {0}) em {1}" -f $p.port.properties.vid, $p.port.address)
            return $p.port.address
        }
    }
    return $null
}

$cli = Get-ArduinoCli
Write-Host "arduino-cli: $cli"

Write-Host "`nCompilando..."
& $cli compile --fqbn arduino:avr:nano $SKETCH
if ($LASTEXITCODE -ne 0) { Erro "falhou compilar - veja os erros acima." }
Write-Host "compilou ok" -ForegroundColor Green

if ($SoCompilar) { Write-Host "`n-SoCompilar: parando aqui."; exit 0 }

if (-not $Porta) {
    Write-Host "`nProcurando a placa..."
    $Porta = Find-Porta $cli
}
if (-not $Porta) {
    Erro "nenhuma placa encontrada. Pluga o Nano no USB, ou passa -Porta COM3."
}

# O daemon segura a porta COM aberta; o avrdude precisa dela livre.
$daemon = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
          Where-Object { $_.CommandLine -like "*tecla_fantasma*" }
if ($daemon) {
    Write-Host "`n  [!] tecla_fantasma.py esta rodando (PID $($daemon.ProcessId))." -ForegroundColor Yellow
    Write-Host "      Ele segura a $Porta aberta e o upload vai falhar. Fecha ele antes." -ForegroundColor Yellow
}

foreach ($fqbn in @("arduino:avr:nano", "arduino:avr:nano:cpu=atmega328old")) {
    Write-Host "`nGravando em $Porta  [$fqbn]"
    & $cli upload -p $Porta --fqbn $fqbn $SKETCH
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`ngravado com sucesso [$fqbn]" -ForegroundColor Green
        Write-Host "Agora: botao entre D2 e GND, e roda  python tecla_fantasma.py"
        exit 0
    }
    Write-Host "  falhou com $fqbn" -ForegroundColor Yellow
}

Erro "nao gravou com nenhum dos dois bootloaders. Confere o cabo (tem cabo USB que so da carga, sem dados) e se a $Porta esta livre."

