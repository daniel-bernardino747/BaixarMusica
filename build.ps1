# Gera dist\BaixarMusica.exe e, opcionalmente, publica o release.
#
#   powershell -ExecutionPolicy Bypass -File build.ps1
#   powershell -ExecutionPolicy Bypass -File build.ps1 -Versao 1.1.0 -Publicar
#
# O executavel sai SEM assinatura digital -- o SmartScreen vai avisar na primeira
# abertura de quem baixar. Ver README, secao "O Windows vai reclamar".

param(
    [string]$Versao = "1.0.0",
    [switch]$Publicar
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ($Versao -notmatch '^\d+\.\d+\.\d+$') {
    throw "Versao precisa ser no formato X.Y.Z (recebi '$Versao')"
}
$partes = $Versao.Split('.')
$tupla = "$($partes[0]), $($partes[1]), $($partes[2]), 0"

# Metadados no binario. Executavel sem nenhum metadado pontua pior nas
# heuristicas de antivirus -- e barato, entao preenchemos.
$versionInfo = @"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($tupla), prodvers=($tupla),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)
  ),
  kids=[
    StringFileInfo([StringTable('041604B0', [
      StringStruct('CompanyName', 'BaixarMusica'),
      StringStruct('FileDescription', 'Baixa musicas do Spotify e do YouTube em mp3'),
      StringStruct('FileVersion', '$Versao'),
      StringStruct('InternalName', 'BaixarMusica'),
      StringStruct('OriginalFilename', 'BaixarMusica.exe'),
      StringStruct('ProductName', 'BaixarMusica'),
      StringStruct('ProductVersion', '$Versao')
    ])]),
    VarFileInfo([VarStruct('Translation', [1046, 1200])])
  ]
)
"@
Set-Content -Path "version.txt" -Value $versionInfo -Encoding utf8

# Publicar um binario que nao passa nos testes seria mandar o defeito para
# a maquina dos outros -- e la nao da para depurar.
python -m pytest -q
if (-not $?) { throw "Os testes falharam; nao vou buildar." }

# --noupx de proposito: binario comprimido com UPX e um gatilho heuristico
# classico de antivirus, e os poucos MB economizados nao valem o falso positivo.
# O .exe fica travado enquanto uma copia dele estiver rodando, e o PyInstaller
# falha com "Acesso negado". Onefile sobe um processo filho, entao fechar a
# janela nem sempre basta.
$rodando = Get-Process -Name BaixarMusica -ErrorAction SilentlyContinue
if ($rodando) {
    Write-Host "Fechando $($rodando.Count) instancia(s) de BaixarMusica..."
    $rodando | Stop-Process -Force
    Start-Sleep -Milliseconds 500
}

python -m PyInstaller `
    --onefile --windowed --clean --noconfirm --noupx `
    --name BaixarMusica `
    --icon icone.ico `
    --version-file version.txt `
    app.py

# $ErrorActionPreference nao pega codigo de saida de executavel nativo: sem esta
# checagem o script seguiria e publicaria o binario velho como se fosse novo.
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou (codigo $LASTEXITCODE)." }

$exe = Join-Path $PSScriptRoot "dist\BaixarMusica.exe"
if (-not (Test-Path $exe)) { throw "PyInstaller terminou sem gerar $exe." }
$hash = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLower()
$mb = [math]::Round((Get-Item $exe).Length / 1MB, 1)

Write-Host ""
Write-Host "Pronto: $exe  ($mb MB)"
Write-Host "SHA256: $hash"

if ($Publicar) {
    $notas = @"
Baixe o **BaixarMusica.exe** aqui embaixo e clique duas vezes. Nao precisa
instalar mais nada -- na primeira vez o proprio programa busca o que falta.

Na primeira abertura o Windows mostra uma tela azul dizendo que protegeu o seu PC.
Clique em **Mais informacoes** e depois em **Executar assim mesmo**. Isso acontece
porque o programa nao tem assinatura digital paga, nao porque ele seja perigoso.

SHA256 do executavel: ``$hash``
"@
    gh release create "v$Versao" $exe --title "v$Versao" --notes $notas
    if ($?) {
        Write-Host ""
        $repo = (gh repo view --json nameWithOwner -q .nameWithOwner)
        Write-Host "Link para mandar aos amigos:"
        Write-Host "  https://github.com/$repo/releases/latest/download/BaixarMusica.exe"
    }
}
