# Distribution and updates — implementation plan

Status: staged/installed package and installer install/upgrade/uninstall verified;
source/release publication in progress. The owner explicitly resumed the task
for personal use and device transfer on 3 October. Existing notices are retained;
unestablished provenance is recorded rather than presented as an invented license.
See ACTIVE_TASKS.md for completed checks and package/publication gates.

Owner-authorized scope: clean redundant builds first; preserve personal Power Bin,
projects and session assets; create a self-contained Windows installer with optional
packs; add startup/manual update checks; publish application source to
https://github.com/farhanr3001/video-editor. No editing behavior changes.

1. Cleanup complete: removed 39,573,649,284 logical bytes from 58 approved paths.
   Current dist, caption-followup-stage and one verified rollback remain. The
   machine reported 69.83 GB free immediately afterward. Evidence is retained in
   build/approved-cleanup-result.json. AGENTS.md now requires bounded retention.
2. Keep source/assets/tests and distribution specifications in Git. Exclude user
   projects, Power Bin, machine settings, media libraries, vendor binaries and
   generated releases. Preserve local source and private fonts.
3. Include FFmpeg/FFprobe, English base caption model and existing caption resources
   in standard installation. Optional phone mirroring, vision and vocal separation
   components use app-owned storage and remain available from inside the app.
4. Add a versioned GitHub Releases update channel. Checks are asynchronous; startup
   offers OK/Cancel/Don't show again for a particular version. Manual File > Check
   for updates is above UI Themes and overrides a dismissed startup notice. Offline
   errors must not claim that the application is up to date. Preserve editing state.
5. Installer provides optional component checkboxes, installed-size totals, Windows
   Apps registration, upgrade support and cleanup of app-owned optional downloads.
   Preserve Power Bin metadata and every source it references. Never remove
   externally saved projects/media or shared global model caches.
6. Verification scope: complete isolated module suite because dependency/build
   handling changes; three-theme update UI; offline/no-release/new-release cases;
   component integrity/cancellation; staged and installed startup, captions/export;
   isolated real installer upgrade/uninstall with Power Bin survival.
7. Push reviewed source and publish verified release assets. Record source tests,
   package build, installation and remote publication separately in ACTIVE_TASKS.

Build retention: one staging directory and one rollback. Keep small reports/logs.
Compiler and packaging inputs can be reused under ignored build/tools and
build/distribution-inputs; avoid retaining a full bundle per verification attempt.
Store downloadable components in app-owned roots so both installer-preselected and
later downloads can be removed by the same uninstaller. Installer size labels must
distinguish exact packaged sizes from estimated runtime downloads.

## Building and publishing later updates

The verified build uses CPython 3.10 and PyInstaller 6.22.2. Install
requirements-build.txt into a virtual environment; build.ps1 prevents collection
of unrelated host DLLs and user-site packages. Save the resolved dependency list
with the small release evidence rather than retaining another full bundle.

Increment kinetic_cut/version.py and assets/windows-version.txt together. Reuse
the prepared pinned runtime sources under build/distribution-inputs/components,
or prepare them with vision_component.install / vocal_component.install into
those explicit staging roots. Phone archives originate from the upstream vendor
packages described in THIRD_PARTY_NOTICES. Source history excludes owner-supplied
font binaries and personal downloaded music. Personal-transfer installers include
the supplied fonts and their available notices. FFmpeg's upstream license/README
accompany the shipped tools.

Prepare payloads with scripts/prepare_distribution.py --model <base.en snapshot>
--ffmpeg-bin <FFmpeg bin>. Set KINETIC_CUT_ASSETSPATH to
build/distribution-inputs/assets and KINETIC_CUT_DISTPATH to
build/distribution-stage, then run build.ps1. Run scripts/build_installer.py
--compiler <ISCC.exe>, verify the staged and installed package and installer, and
push the tested source to main. scripts/publish_release.py uploads the installer,
component packs and manifests into a draft release; --publish makes it public.
GitHub supplies the installer SHA-256 digest used by the update checker. Sign-in
is only needed by the maintainer publishing releases; never embed credentials.
Future updates replace app files and retain settings, Power Bin and installed
components. A stable installer AppId supports upgrades and Windows Apps removal.

The installer can use verified pack ZIPs placed beside it for offline preselection.
Without those ZIPs it downloads the checked components. In-app first-use downloads
always use the same SHA-256 manifest and component roots. Remove installed optional
packs from Cache Manager; their effect download buttons and phone overlay return.

## Transfer to another personal device

Run KineticCut-Setup-1.1.0.exe. The editor and base.en caption model work without
optional packs or a model download. For an offline transfer, copy the four pack
ZIPs beside the installer before selecting their checkboxes. For an online
transfer, optional selections download from the release; they can also be added
later inside the app. Copy your .kcut projects and their referenced media separately;
they and Power Bin data are personal data, never installer/repository payloads.

Standard app files: 803.9 MB; installer: 341.8 MB. All four optional packs add
1,688.9 MB installed (528.5 MB download). These are decimal sizes from the verified
package; Windows reports different numbers when displaying binary units. Models
chosen later beyond the standard caption model and working caches add their own data.
