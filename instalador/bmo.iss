; Instalador do BMO (Inno Setup 6)
#define Nome "BMO"
#define Versao "1.0.0"
#define Editor "Projeto BMO"
#define ExeNome "BMO.exe"

[Setup]
AppId={{7B3E8F04-52A1-4D21-9C55-E10B45D2A7C3}
AppName={#Nome}
AppVersion={#Versao}
AppPublisher={#Editor}
DefaultDirName={autopf}\BMO
DefaultGroupName=BMO
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=saida
OutputBaseFilename=BMO-Setup-{#Versao}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#Nome} — Assistente Virtual

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "..\dist\BMO\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\BMO"; Filename: "{app}\{#ExeNome}"
Name: "{autodesktop}\BMO"; Filename: "{app}\{#ExeNome}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"

[Run]
Filename: "{app}\{#ExeNome}"; Description: "Abrir o BMO agora"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\.env"
