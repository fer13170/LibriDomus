# Genera la versión portable de LibriDomus.
#
# Uso (desde la carpeta del proyecto, en PowerShell):
#     .\build\build.ps1
#
# Resultado:
#     build\salida\LibriDomus\          <- carpeta portable lista para usar
#     build\salida\LibriDomus-X.Y.Z.zip <- la misma carpeta comprimida
#
# Pasos: pruebas automáticas -> PyInstaller (modo carpeta) -> autoprueba del .exe -> ZIP.

# "Continue": PyInstaller escribe su registro por stderr y PowerShell 5.1 lo trataría
# como error. Los fallos reales se detectan con $LASTEXITCODE tras cada paso.
$ErrorActionPreference = "Continue"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
$python = Join-Path $raiz ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "No existe .venv. Créalo con:  py -3.12 -m venv .venv ; .venv\Scripts\python -m pip install -r requirements-dev.txt"
}

Write-Host "== 1/4 Pruebas automáticas" -ForegroundColor Cyan
& $python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Las pruebas han fallado. No se genera el ejecutable." }

Write-Host "== 2/4 PyInstaller" -ForegroundColor Cyan
$salida = Join-Path $raiz "build\salida"
& $python -m PyInstaller --noconfirm --clean --windowed --onedir `
    --name LibriDomus `
    --icon (Join-Path $raiz "build\icono.ico") `
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

Write-Host "== 3/4 Autoprueba del ejecutable (con un PATH mínimo, sin Python)" -ForegroundColor Cyan
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

Write-Host "== 4/4 ZIP" -ForegroundColor Cyan
$version = & $python -c "import libridomus; print(libridomus.VERSION)"
$zip = Join-Path $salida "LibriDomus-$version.zip"
Remove-Item $zip -ErrorAction SilentlyContinue
Compress-Archive -Path $carpetaApp -DestinationPath $zip
$tamano = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Host "Listo: $zip ($tamano MB)" -ForegroundColor Green
