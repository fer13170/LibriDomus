# Genera la versión portable de LibriDomus.
#
# Uso (desde la carpeta del proyecto, en PowerShell):
#     .\build\build.ps1
#
# Resultado:
#     build\salida\LibriDomus\          <- carpeta portable lista para usar
#     build\salida\LibriDomus-X.Y.Z.zip <- la misma carpeta comprimida
#     build\salida\LibriDomus-X.Y.Z-instalador.exe <- instalador (si Inno Setup 6 está instalado)
#
# Pasos: pruebas automáticas -> PyInstaller (modo carpeta) -> autoprueba del .exe -> ZIP -> instalador.

# "Continue": PyInstaller escribe su registro por stderr y PowerShell 5.1 lo trataría
# como error. Los fallos reales se detectan con $LASTEXITCODE tras cada paso.
$ErrorActionPreference = "Continue"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
$python = Join-Path $raiz ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "No existe .venv. Créalo con:  py -3.13 -m venv .venv ; .venv\Scripts\python -m pip install -r requirements-dev.txt"
}

Write-Host "== 1/5 Pruebas automáticas" -ForegroundColor Cyan
& $python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Las pruebas han fallado. No se genera el ejecutable." }

Write-Host "== 2/5 PyInstaller" -ForegroundColor Cyan
$salida = Join-Path $raiz "build\salida"
# Datos de versión del .exe (Propiedades > Detalles). Sin ellos los antivirus desconfían más.
$versionInfo = Join-Path $raiz "build\work\version_info.txt"
& $python (Join-Path $raiz "build\version_info.py") $versionInfo
if ($LASTEXITCODE -ne 0) { throw "No se ha podido crear la información de versión." }
# --noupx: los ejecutables comprimidos con UPX son los que más falsos positivos dan.
& $python -m PyInstaller --noconfirm --clean --windowed --onedir --noupx `
    --name LibriDomus `
    --icon (Join-Path $raiz "build\icono.ico") `
    --version-file $versionInfo `
    --add-data "$(Join-Path $raiz 'libridomus\recursos');libridomus\recursos" `
    --distpath $salida `
    --workpath (Join-Path $raiz "build\work") `
    --specpath (Join-Path $raiz "build\work") `
    (Join-Path $raiz "LibriDomus.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller ha fallado." }

$carpetaApp = Join-Path $salida "LibriDomus"
$exe = Join-Path $carpetaApp "LibriDomus.exe"

Write-Host "== Dependencias: todo debe ir dentro del paquete (el equipo final no tiene Python)" -ForegroundColor Cyan
& $python (Join-Path $raiz "build\verificar_dependencias.py") $carpetaApp
if ($LASTEXITCODE -ne 0) { throw "Faltan dependencias en el paquete." }

Write-Host "== 3/5 Autoprueba del ejecutable (con un PATH mínimo, sin Python)" -ForegroundColor Cyan
$datosPrueba = Join-Path $env:TEMP "libridomus_autoprueba"
Remove-Item -Recurse -Force $datosPrueba -ErrorAction SilentlyContinue
$pathOriginal = $env:PATH
$env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$env:SystemRoot\System32\Wbem"
Remove-Item Env:\PYTHONHOME, Env:\PYTHONPATH -ErrorAction SilentlyContinue
$env:LIBRIDOMUS_DATOS = $datosPrueba
$proceso = Start-Process -FilePath $exe -ArgumentList "--autoprueba" -Wait -PassThru
Remove-Item Env:\LIBRIDOMUS_DATOS
$env:PATH = $pathOriginal
Get-Content (Join-Path $datosPrueba "autoprueba.txt") -Encoding UTF8
if ($proceso.ExitCode -ne 0) { throw "La autoprueba del ejecutable ha fallado." }

Write-Host "== Manual de usuario (PDF)" -ForegroundColor Cyan
& $python (Join-Path $raiz "build\generar_manual.py") $carpetaApp
if ($LASTEXITCODE -ne 0) { throw "No se ha podido generar el manual." }

Write-Host "== 4/5 ZIP" -ForegroundColor Cyan
$version = & $python -c "import libridomus; print(libridomus.VERSION)"
$zip = Join-Path $salida "LibriDomus-$version.zip"
Remove-Item $zip -ErrorAction SilentlyContinue
Compress-Archive -Path $carpetaApp -DestinationPath $zip
$tamano = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Host "ZIP: $zip ($tamano MB)" -ForegroundColor Green

Write-Host "== 5/5 Instalador (Inno Setup 6)" -ForegroundColor Cyan
$iscc = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    Write-Host "Inno Setup 6 no está instalado: se omite el instalador (el ZIP sí está listo)." -ForegroundColor Yellow
    Write-Host "Para instalarlo:  winget install --id JRSoftware.InnoSetup --exact --source winget --scope user"
} else {
    & $iscc /Q "/DVersion=$version" (Join-Path $raiz "build\instalador.iss")
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup ha fallado al crear el instalador." }
    $instalador = Join-Path $salida "LibriDomus-$version-instalador.exe"
    $tamano = [math]::Round((Get-Item $instalador).Length / 1MB, 1)
    Write-Host "Instalador: $instalador ($tamano MB)" -ForegroundColor Green
}
Write-Host "Listo." -ForegroundColor Green
