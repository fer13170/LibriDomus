# Genera la versión portable de Bibliotecario Virtual.
#
# Uso (desde la carpeta del proyecto, en PowerShell):
#     .\build\build.ps1
#
# Resultado:
#     build\salida\BibliotecarioVirtual\          <- carpeta portable lista para usar
#     build\salida\BibliotecarioVirtual-X.Y.Z.zip <- la misma carpeta comprimida
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
    --name BibliotecarioVirtual `
    --icon (Join-Path $raiz "build\icono.ico") `
    --add-data "$(Join-Path $raiz 'bibliotecario\recursos');bibliotecario\recursos" `
    --distpath $salida `
    --workpath (Join-Path $raiz "build\work") `
    --specpath (Join-Path $raiz "build\work") `
    (Join-Path $raiz "BibliotecarioVirtual.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller ha fallado." }

Write-Host "== 3/4 Autoprueba del ejecutable" -ForegroundColor Cyan
$carpetaApp = Join-Path $salida "BibliotecarioVirtual"
$exe = Join-Path $carpetaApp "BibliotecarioVirtual.exe"
$datosPrueba = Join-Path $env:TEMP "bv_autoprueba"
Remove-Item -Recurse -Force $datosPrueba -ErrorAction SilentlyContinue
$env:BV_DATOS = $datosPrueba
$proceso = Start-Process -FilePath $exe -ArgumentList "--autoprueba" -Wait -PassThru
Remove-Item Env:\BV_DATOS
Get-Content (Join-Path $datosPrueba "autoprueba.txt") -Encoding UTF8
if ($proceso.ExitCode -ne 0) { throw "La autoprueba del ejecutable ha fallado." }

Write-Host "== 4/4 ZIP" -ForegroundColor Cyan
$version = & $python -c "import bibliotecario; print(bibliotecario.VERSION)"
$zip = Join-Path $salida "BibliotecarioVirtual-$version.zip"
Remove-Item $zip -ErrorAction SilentlyContinue
Compress-Archive -Path $carpetaApp -DestinationPath $zip
$tamano = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Host "Listo: $zip ($tamano MB)" -ForegroundColor Green
