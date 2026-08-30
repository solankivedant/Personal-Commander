; Inno Setup script — Phase 8 (docs/ROADMAP.md).
; Source guidance: munshiji-full-report.md §12, and
; .claude/agents/packaging-release-engineer.md before editing.
;
; Reminders baked into this stub, don't drop them when filling it in:
;   - Ship the base installer only (~180MB target): app, wake word, grammars,
;     TTS engine. Model weights are downloaded on first run, never bundled
;     (see docs/LICENSING-AUDIT.md) — do not add a [Files] entry for weights.
;   - Built from PyInstaller --onedir output, not --onefile.
;   - Sign the EXE before this step, and sign the installer this script
;     produces afterward. Unsigned installers trigger SmartScreen warnings
;     that measurably kill conversion (§18 risk #6).
;   - Uninstall must remove models, the Chroma index, and config — a
;     multi-GB orphan directory after uninstall generates support tickets.

#define MyAppName "Munshiji"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Munshiji"
#define MyAppExeName "munshiji.exe"

[Setup]
AppId={{REPLACE-WITH-GENERATED-GUID}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputBaseFilename=munshiji-setup
Compression=lzma2
SolidCompression=yes
; SignTool=... configured at release time, not committed here.

[Files]
; Source=dist\munshiji\* populated by scripts/package.py (PyInstaller --onedir).
; Source: "..\dist\munshiji\*"; DestDir: "{app}"; Flags: recursesubdir

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[UninstallDelete]
; Remove downloaded models, the Chroma index, and user config on uninstall —
; see the reminder above. Fill in real paths once data/ layout is finalized.
Type: filesandordirs; Name: "{userappdata}\{#MyAppName}\data"
Type: filesandordirs; Name: "{userappdata}\{#MyAppName}\models"
