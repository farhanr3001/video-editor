# Kinetic Cut

A native Windows video editor inspired by DaVinci Resolve, focused on a compact
workflow for short-form video while retaining general video editing tools.
Python/PySide6 provides the interface, Qt decodes previews and FFmpeg renders
exports. Projects and media stay local.

## Install and transfer

Download the installer from [GitHub Releases](https://github.com/farhanr3001/video-editor/releases).
Editing, FFmpeg/FFprobe, caption templates, emoji resources and the default English
base.en caption model are included. Caption generation works offline after installation.
The standard app files occupy about 804 MB; the installer is about 342 MB.

Optional checkboxes show the total installed size and download size:

| Optional tools | Added installed size | Download |
| --- | ---: | ---: |
| Vocal separation | 1,098.6 MB | 296.9 MB |
| Face/background analysis and tracked effects | 297.2 MB | 109.4 MB |
| iPhone mirroring | 266.9 MB | 110.9 MB |
| Android mirroring | 26.2 MB | 11.3 MB |

These decimal sizes describe version 1.1.0. Working caches and additional caption
models can add data. For an offline transfer, place the optional ZIPs beside the
installer before selecting their checkboxes. Otherwise they download from the
release. Copy your projects and media separately using **File > Collect project
and media**. Projects, Power Bin data and personal media libraries are excluded
from the installer and source repository.

## Editing and downloads

The editor supports layered video/audio timelines, crops and transforms, linked
media, graphics and titles, effects, animated properties, captions, Power Bins,
compound clips and export queues. Three themes are available. An MCP connection
panel lets an external assistant work with the editor when authorized.

Use **File > Optional downloads** to add tools later. Missing effects show a
Download button; an unavailable phone page displays a blurred download gate.
Downloads show size, confirmation, percentage progress and cancellation.
**File > Cache Manager** removes selected installed optional packs and restores
their download controls. Windows Apps uninstall removes application-owned packs,
settings and caches, while preserving Power Bin metadata and the media it references.
External projects and media are preserved.

Startup offers new releases with OK, Cancel and a version-specific Don't show again.
**File > Check for updates**, immediately above UI Themes, checks manually even
after dismissal. Offline checks report a connection error. Installer and component
downloads verify SHA-256 before use; update checks do not upload projects or media.

## Run and build from source

Windows 10/11 x64 and Python 3.10+ are required. The verified packaging environment
uses CPython 3.10 and PyInstaller 6.22.2.

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements-build.txt
.venv\Scripts\python main.py
```

For source execution, provide FFmpeg/FFprobe on PATH or in app settings.
Use pythonw.exe for a console-free source launch. A packaged EXE needs its
_internal directory beside it.

Run isolated regression modules with:

```powershell
.venv\Scripts\python scripts/test_modules.py --output build/regression
```

For a standalone installer, prepare the baseline caption model, FFmpeg binaries
and optional runtimes with scripts/prepare_distribution.py. Phone binaries and
owner-supplied font files are outside source history; include their local copies
when preparing a personal-transfer package. Set KINETIC_CUT_ASSETSPATH to the
prepared assets and KINETIC_CUT_DISTPATH to build/distribution-stage, then run
build.ps1. Compile with scripts/build_installer.py and an Inno Setup compiler.
scripts/verify_installer.ps1 checks real install, upgrade and uninstall using a
disposable profile; never run data-cleanup tests against normal user data.

For future updates, increment kinetic_cut/version.py and assets/windows-version.txt,
rebuild and verify the staged/installed package, push source, and upload a draft
with scripts/publish_release.py. Add --publish after verification. Credentials
come from the maintainer's Git credential helper and are never embedded in the app.
Keep only one current staged build and one verified rollback; retain small reports.

See [release notes](RELEASE_NOTES.md) and [third-party notices](THIRD_PARTY_NOTICES.md).
Personal engineering context, task ledgers and historical plans remain local.
