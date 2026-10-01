; Instalador de LibriDomus (Inno Setup 6).
;
; No se ejecuta a mano: lo compila build.ps1 después de crear la carpeta portable, con
;     ISCC.exe /DVersion=1.3.0 build\instalador.iss
;
; Decisiones:
; - Se instala SOLO PARA EL USUARIO (no pide permisos de administrador) en
;   %LOCALAPPDATA%\Programs\LibriDomus. Así la subcarpeta «datos» junto al programa se puede
;   escribir igual que en la versión portable y el programa no necesita ningún cambio.
; - Al actualizar (instalar una versión nueva encima) los datos se conservan: el instalador
;   solo sustituye los archivos del programa.
; - Al desinstalar, la carpeta «datos» NO se borra (son los datos del usuario); se avisa de dónde queda.

#ifndef Version
  #define Version "0.0.0"
#endif
#define Nombre "LibriDomus"
#define Exe "LibriDomus.exe"
#define Origen "salida\LibriDomus"

[Setup]
; AppId identifica la aplicación para las actualizaciones y la desinstalación: no cambiarlo nunca.
AppId={{96094149-BED6-40C1-92AE-89063D29AD3A}
AppName={#Nombre}
AppVersion={#Version}
AppVerName={#Nombre} {#Version}
AppPublisher=LibriDomus
; Datos de versión del instalador (Propiedades > Detalles): ayudan a que el antivirus no desconfíe.
VersionInfoVersion={#Version}
VersionInfoCompany={#Nombre}
VersionInfoProductName={#Nombre}
VersionInfoProductVersion={#Version}
VersionInfoDescription=Instalador de {#Nombre}
VersionInfoCopyright=© 2026 {#Nombre}
DefaultDirName={localappdata}\Programs\{#Nombre}
DefaultGroupName={#Nombre}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=salida
OutputBaseFilename={#Nombre}-{#Version}-instalador
SetupIconFile=icono.ico
UninstallDisplayIcon={app}\{#Exe}
UninstallDisplayName={#Nombre}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
; Si el programa está abierto, el instalador pide cerrarlo (gestor de reinicio de Windows).
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[InstallDelete]
; Se borran las bibliotecas de la versión anterior para que no queden archivos viejos mezclados.
; La carpeta «datos» no se toca.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#Origen}\*"; DestDir: "{app}"; Excludes: "datos\*"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#Nombre}"; Filename: "{app}\{#Exe}"
Name: "{autoprograms}\Manual de usuario de {#Nombre}"; Filename: "{app}\Manual de usuario.pdf"
Name: "{autodesktop}\{#Nombre}"; Filename: "{app}\{#Exe}"; Tasks: escritorio

[Run]
Filename: "{app}\{#Exe}"; Description: "Abrir {#Nombre} ahora"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and DirExists(ExpandConstant('{app}\datos')) then
    // SuppressibleMsgBox: en una desinstalación silenciosa (/SUPPRESSMSGBOXES) no se queda esperando.
    SuppressibleMsgBox('Tus datos (colección, portadas, copias de seguridad y preferencias) se han conservado en:' + #13#10 +
           ExpandConstant('{app}\datos') + #13#10#13#10 +
           'Si vuelves a instalar LibriDomus en la misma carpeta, los encontrará. ' +
           'Si ya no los necesitas, puedes borrar esa carpeta.', mbInformation, MB_OK, IDOK);
end;
