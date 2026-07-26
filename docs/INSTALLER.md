# Windows one-click installer

## What to send

Send only `dist\ReelsBuilderSetup.exe`. Do not send `.env`, `.venv`, output videos,
job databases, or the full development folder.

The matching SHA-256 checksum is written beside it as
`dist\ReelsBuilderSetup.exe.sha256`.

## Friend installation flow

1. Double-click `ReelsBuilderSetup.exe`.
2. Keep **Create a desktop shortcut** selected.
3. Wait while Python, FFmpeg, and the isolated Python environment are prepared.
4. Leave **Launch History Reels Builder** selected and finish setup.
5. Enter personal API keys in the dashboard's API settings.

Internet access is required for the first setup. Subsequent launches use the
**History Reels Builder** Desktop or Start Menu shortcut.

The application is installed under:

```text
%LOCALAPPDATA%\Programs\History Reels Builder
```

Generated videos remain outside the application under:

```text
%USERPROFILE%\Pictures\history videos
```

Setup and dashboard logs are stored under the installed application's
`runtime\logs` directory.

## Safety and updates

- The installer contains a blank `.env.example`, never the developer's `.env`.
- Existing user `.env` values are preserved when setup is run again as an update.
- Generated videos and job history are not bundled.
- The installer is currently unsigned, so Windows SmartScreen may show
  **More info → Run anyway**.

## Rebuilding

From the project root:

```powershell
.\installer\build_installer.ps1
```

If Inno Setup is not yet installed on the build machine:

```powershell
.\installer\build_installer.ps1 -InstallCompiler
```

The build script audits the package manifest before compilation and writes the
final SHA-256 checksum after a successful build.
