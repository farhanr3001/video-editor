# Kinetic Cut

## For AI maintainers

Read [AI_PROJECT_CONTEXT.md](AI_PROJECT_CONTEXT.md) and
[ACTIVE_TASKS.md](ACTIVE_TASKS.md) before making changes. They contain the
model-independent engineering contract, architecture and interaction rules,
MCP/snapshot workflow, regression and EXE release procedures, and unresolved work.
`AGENTS.md` points coding agents to these instructions automatically.

Native Qt desktop editor for vertical livestream shorts. Python/PySide6 provides
the application and widgets; Qt decodes previews and FFmpeg renders exports.
There is no browser, webview, Electron runtime, or required cloud account.

## Run on Windows

Install the current Windows release from
[GitHub Releases](https://github.com/farhanr3001/video-editor/releases).
The installer includes FFmpeg/FFprobe and the default base.en caption model.
Optional tools can be selected during installation or added from File > Optional
downloads. File > Check for updates is above UI Themes. Dismissed startup notices
apply to that version only; a manual check still offers it. Normal update checks
never upload a project or media.

Windows Apps uninstall removes app-owned downloads/settings/caches while preserving
Power Bin metadata and its referenced media. Original external projects and exports
are untouched. Use File > Collect project and media before moving projects.
Personal .kcut files, session assets, downloaded music and user-provided private
fonts are excluded from Git/releases. The repository includes a small sanitized
caption fixture so regression tests do not require the owner's private project.

Release procedure is in [DISTRIBUTION.md](DISTRIBUTION.md). Keep only one current
staged bundle and one verified rollback; keep small regression reports, not old
complete application copies.

Open `dist/KineticCut/KineticCut.exe` after building. Keep its `_internal`
directory beside it. FFmpeg and ffprobe must be on PATH or beside the executable.

To run the source:

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

For a console-free source launch, use `.venv\Scripts\pythonw.exe main.py`.
The packaged executable is windowed; its startup splash reports actual loading
stages before the editor appears. Windows media helpers and Python dependency
subprocesses are launched without console windows. Diagnostic errors go to
`application.log` in the KineticCut data directory (logs rotate automatically).

## Professional polish pass

- Deliver is a review-only workspace: scrub or play the timeline, but return to
  Edit to trim, move, split, drop effects/media, transform footage, or edit text.
  Edit shortcuts and context menus are locked too; overlay preferences return
  when switching back to Edit. Queued renders remain independent snapshots.
- Compatible effect drop targets shade grey and display the effect name;
  incompatible/locked clips reject the drop. Applied clips show an `fx` badge.
- The library adds Warm Tone, Cool Tone, Sepia and Channel Swap with adjustable
  strength; Voice Clarity and Low Cut work in prepared audio previews and exports.
  Noise Clean now applies to the chosen audio clip. Auto Duck remains explicitly
  project-wide and affects music-role tracks while source speech plays.
- Caption Pop, Lower Third and Headline are editable title presets. Inspector
  colour swatches open a dark colour dialog; cancelling leaves colours unchanged.
- Headline uses bold black text on a fitted, stepped white background. Explicit
  newlines and automatic wrapping are supported; its focused Inspector has a
  text editor and a uniform Size slider. Preview and export share vector geometry.
- Clips have subtle rounded corners and remain clipped to their own timeline
  section while scrolling, including thumbnails, labels and selection borders.
- Inspector values use cursor-captured, speed-sensitive dragging independent of
  decimal precision. Shift makes fine adjustments; Ctrl makes coarse adjustments;
  double-click to type. A complete drag is one undo step. Drop Shadow has paired
  X/Y offsets and a header enable toggle.
- Cut/Copy/Paste work for media, titles and subtitles. Paste is an undoable,
  non-ripple overwrite at the playhead, preserving relative timing, lanes and
  linked AV pairs. Locked destinations reject the edit. Text-field shortcuts
  still operate on text, and Deliver remains read-only.
- The playhead can travel beyond the final clip into a black preview without
  increasing the project/export duration. The empty preview prompt stays inside
  the canvas, and a multi-resolution Kinetic Cut icon identifies the application.
- Render jobs retain failures and diagnostic details. Double-click a failed job
  for details; Retry Failed requeues it after the underlying issue is corrected.
- Background-task activity, clearer hover/focus/disabled states, colour-coded
  effect categories and useful empty-state prompts keep the existing layout.
- File → Project Settings changes the canvas/aspect ratio and project frame rate,
  plus existing audio defaults. New projects remain 1080 × 1920 at 60 fps.
  Deliver follows the project format; settings changes are undoable.
- Hold the scrubber near either timeline edge to scroll continuously. Playback
  and explicit seeks reveal an off-screen playhead. Video-wheel up reveals higher
  lanes; down returns towards V1. Audio keeps its normal top-origin direction.

Requirements: Python 3.10+, Windows 10/11, FFmpeg 6+ with libass. macOS source
support has not been verified in this Windows test environment.

## September editing workspace

- Fresh projects contain one empty video track and one empty audio track.
  Tracks are generic ordered lanes, not fixed “facecam” or “gameplay” categories.
- Media Pool and Effects are independent, vertically stacked left panels.
  Their toolbar toggles reclaim the unused space. Inspector also hides completely.
- Media Pool uses a wrapping thumbnail grid with filenames and a search toggle.
  Power Bins / Master and user-created subfolders persist across projects.
  Files remain at their original locations; Power Bins remember references.
- Effects are grouped by category, searchable, and can be dragged onto a clip.
  The last selected category (for example, Open FX / Blur) is restored when the
  app next opens; a removed category falls back to All Effects.
- The project title is above the viewer. A fixed footer switches between Edit
  and Deliver, which share the same viewer and timeline.
- The Inspector displays the selected filename and context-enabled Video, Audio,
  and Effects tabs. Video contains Transform, Cropping, and Composite sections.
  Audio contains Volume, Pan, and Pitch. Gaussian Blur has independent linked
  horizontal/vertical strengths, border mode, blend, enable, and removal controls.
- Numeric fields do not respond to the wheel; scrolling over them scrolls the
  surrounding Inspector. Sliders and reset buttons accompany relevant values.
- A detected unclean shutdown offers the latest recovery autosave on next launch.
  Normal projects are saved explicitly with Ctrl+S. Each overwrite of an existing
  `.kcut` retains its previous state under `.KineticCut Versions/<name>.kcut/`
  (up to 20 versions). Use **File → Restore saved version…** to open one as an
  unsaved edit; saving it cannot silently overwrite the current project.
- **File → Collect project and media…** copies the project and its media pool
  sources, including nested compound sources, into a separate portable folder.
  The open project and source files are unchanged. Missing media stops collection
  before a usable `.kcut` is published; relink it first.
- Audio track headers show live left/right preview peaks and a latched clipping
  indicator. Select an audio clip and open **Inspector → Audio → Levels** for
  dBFS readouts and reset. Its mix-headroom warning is a conservative sum of
  track peaks, not an exact sample-mixed export measurement.

## Editing gestures

| Action | Gesture |
| --- | --- |
| Import | Ctrl+I, drop local files, or Media Pool context menu |
| Add a clip | Drag its thumbnail onto a timeline lane |
| Audio-only from a video | Drag the thumbnail onto an audio lane |
| Select several clips | Drag a rectangle through empty timeline space; Ctrl-click adds/removes |
| Linked selection | Timeline **Link** toggle; Ctrl+Shift+L |
| Link/unlink selected clips | Right-click → Link Clips; Ctrl+Alt+L |
| Duplicate | Alt-drag; copies trims, transforms, audio settings, and effects |
| Create another lane | Drag above the top video lane or below the bottom audio lane; track context menu also works |
| Split | B for Blade, or Ctrl+B at the playhead |
| Cut / Copy / Paste clips | Ctrl+X / Ctrl+C / Ctrl+V, or clip context menu; paste overwrites at the playhead |
| Inspector numeric adjustment | Drag; Shift for fine / Ctrl for coarse; double-click to type |
| Select / Trim | A / T |
| Lift / Ripple Delete | Backspace / Delete |
| Undo / Redo | Ctrl+Z / Ctrl+Shift+Z |
| Play / Pause / Stop | Space / K |
| Timeline horizontal zoom | Slider or Alt+wheel (centred on playhead) |
| Timeline horizontal scroll | Ctrl+wheel |
| Timeline track-height zoom | Shift+wheel; height is clamped |
| Viewer zoom / pan | Wheel / middle-button drag |
| Viewer Fit | Fit button or middle-button double-click |
| Crop selected media | Crop toolbar button or C; draw/move/resize, wheel zoom, middle pan |
| Video / audio fades | Drag the upper corner handles; the active handle turns red and shows seconds |
| Extend / trim | Drag a clip edge; stills extend freely and footage stops at its source limits |
| Retime controls | Ctrl+R, then stretch an edge or use the speed-percentage menu; Ctrl+R closes controls |
| Frame a source crop | Viewer context menu → source crop, or Inspector crop values |

Imported video/audio pairs are linked automatically. With Link enabled, editing
operations include the linked members; disable it to cut or manipulate one
component. A cut's right-hand pieces form their own link group.

Moving or stretching a clip over another on the same lane overwrites only the
covered interval when the mouse is released. Uncovered portions remain, with
correct source trims. Slowing down is an overwrite edit, not a ripple edit.
Retime controls preserve the source range and support 10–800% speed, including
linked video/audio and pitch-preserving audio export.

The timeline spans underneath both the viewer and Inspector. Drag the horizontal
splitter to change their relative height; minimum sizes protect both sections.
With no selection, the Inspector is empty and its tabs are disabled.

Media Pool and Power Bin thumbnails can be dragged directly to timeline lanes.
Newly added media becomes the active timeline selection and opens its Inspector
properties. Video is primary for linked video/audio pairs; audio-only additions
open Audio. The Link toggle controls whether linked companions are selected.
Right-click a thumbnail → Add to Timeline appends to the last appropriate lane.
The lower Power Bins section has a separate resizable tree: right-click to create
folders and drag thumbnails into them. These are persistent references to source
files, not copies; moving a reference does not move or delete the original file.

Waveforms reflect source trims, fades, and volume. Multiple selected audio clips
with different values show an ellipsis; relative adjustments preserve their
level differences, bounded by each control's range.

Viewer zoom/pan affects only the view, never the output transform. The output
remains masked to the project frame. Clip handles change the actual layer.

Inspector numeric fields follow an NLE scrub model: single-click and drag left or
right to adjust, double-click to type, Enter to commit. Wheel input scrolls the
Inspector without changing numbers, combos or sliders. The movable red anchor in
the viewer controls the selected layer's transform pivot.

Effects lists every attached clip effect, including effects without parameters;
use its bin icon to remove the selected effect. Colours provides Neutral, HD Pop,
Cinematic and B&W presets plus grayscale, brightness, contrast, saturation and
sharpen controls, consistently applied to preview and export.

Generate Captions first opens the track-style setup, then shows extraction/model/
transcription progress. The first result is selected on ST1 and revealed in the
viewer. Caption and Track controls include typography, alignment, position, zoom,
opacity, outline, shadow, background, animation and clickable colour swatches.

## Fast vertical-short workflow

1. Import footage, then drag it to V1.
2. Select the video and apply **Vertical Layout**. Existing cuts retain their
   timing and source audio; the preset adds background and facecam layers.
3. Use source crop rectangles to select gameplay and webcam, then adjust their
   positions, independent X/Y zoom, flips, or rotation.
4. Remove Silence on the desired section and generate local captions.
5. Captions occupy ST1 above the video lanes. Select a caption to edit its text
   and timing in Video → Caption. Track styles apply globally unless Customize
   Caption is enabled. Subtitle context menus provide split, merge, and delete.
6. Add a logo, music, or SFX by dragging media onto the appropriate lane.
7. Switch to **Deliver**, choose MP4 codec, resolution, fps, bitrate, captions,
   and audio options, then **Add to Render Queue**.
8. Each job captures a project/settings snapshot. **Render All** processes the
   queued snapshots in order; further editing does not change a queued job.
9. Select a completed job and use Send Completed Video to Phone or Wireless
   Download.

USB delivery supports Android ADB and Windows MTP. The phone must be unlocked,
connected in File Transfer mode for MTP, or authorized for USB debugging for ADB.
Actual physical-device delivery requires a connected phone and was not verified
during this UI rehaul. Wireless sharing uses a temporary local server; close its
dialog to stop sharing.

## Captions and performance

Local speech recognition supports faster-whisper, whisper.cpp, and Windows
Speech. The first faster-whisper use downloads the selected model once; subsequent
use can be offline. Choose tiny.en for speed or base.en/small.en for accuracy.
Model downloads and media caches are not bundled into the editor executable.

The timeline clock is independent of decoder callbacks. Windows uses software
preview decoding by default because the CPU-frame QWidget compositor encountered
a D3D frame-conversion deadlock on this machine. Export encoding is independent;
CPU and available hardware encoders can be selected in Deliver. Automatic 4K
proxies use the source file only for export.

Blur previews are resolution-reduced CPU approximations; FFmpeg renders at output
resolution. Qt and libass font rasterization can differ slightly. Pan/pitch and
positive-volume preview audio is cached in the background, so the first change
may take a moment to prepare. Render-time and file-size figures are estimates.
This is a focused editor inspired by Resolve's organization, not a pixel-identical
or feature-complete Resolve replacement.

## Editing refinements

The text inspector includes a searchable offline Google Noto emoji picker with
3,953 Unicode 17 emoji, including skin tones, flags and joined sequences. Colour
artwork is shared by the picker, preview and burned-in export. Headline controls
are Color, Size, Duration and Transform (position); new headlines start centred.

Media Pool and Power Bin support marquee selection, batch removal of bin entries,
and sequential timeline insertion of selected media. Folders are ignored when
dragging media to the timeline. Source files are never deleted by these actions.

Copy a timeline clip, then use Alt+V or Paste Attributes in its target's context
menu. All properties start unchecked; video, audio and text sources are matched
to compatible targets. Pasting attributes preserves timing, source media and text.
The snapping toggle also controls playhead snapping. Alt-drag shows a grey copy
and provisional new lanes, committed only on drop; Escape cancels the drag.

Image thumbnails preserve transparency and proportions on a black matte. Use a
media item's context menu to Rename its display label or Open File Location;
renaming does not change the source file. Drag timeline clips onto a Power Bin
folder or its item grid to save reusable clips with their trims, transform,
effects and linked media. The timeline originals stay in place. These presets
persist across sessions; source media files must remain available at their paths
(Power Bins save references and attributes, not duplicate source files).
The Master pool contains source files, not saved attribute presets. Selecting or
starting a drag from a Power Bin does not import anything; actual insertion adds
only missing source files, reusing existing paths. Old unused preset wrappers in
Master are cleaned up on project load without deleting any source files.
Timeline presets can be dropped onto the Power Bin's main item grid (empty space
or folder tiles) as well as its folder tree. The grid outlines an accepted drop.

Dragging from either bin into the timeline displays grey placement previews,
including sequential selections and provisional linked video/audio lanes. These
are visual only until drop; cancellation does not import files or create tracks.
The horizontal zoom slider is logarithmic: 0.6–240 pixels/second, with the previous
12 pixels/second zoom-out limit at its midpoint. Alt+wheel centres the playhead;
Ctrl+wheel scrolls horizontally without changing zoom.

Snapping also applies to all clip/caption trim edges. Left/Right steps one project
frame while the timeline has focus; the repeat button after the preview transport
buttons toggles playback looping. Cut/Split keeps shortcut B. Locked tracks reject
insertion and edits, and hidden tracks hide images as well as video and text.

Auto Caption Style uses an installed-font dropdown and defaults to cyan #55ffff
text with a black #000000 outline. Word highlight gives each word a timed,
configurable background card in multi-word captions, matching preview and export.
The word intervals are evenly distributed across each caption's duration; this
does not claim individual speech-alignment timestamps. Saved styles stay intact.

## Build

```powershell
.venv\Scripts\python -m pip install pyinstaller
.\build.ps1
```

Output: `dist/KineticCut/KineticCut.exe`. The package includes Qt, the Python
runtime, local speech-recognition dependencies, Google Noto emoji and Lucide SVG icons.
FFmpeg/ffprobe remain external to avoid adding their distribution size.
See THIRD_PARTY_NOTICES.md for icon attribution.

The optional `--workflow-selftest OUTPUT_DIRECTORY` executable argument runs an
isolated, offscreen package check and writes a JSON report and screenshots. It
checks the bundled emoji renderer, FFmpeg output and hidden Windows subprocesses;
it does not open or modify your existing projects or settings.

## Verification

```powershell
$env:KINETIC_CUT_HOME = "$PWD\build\test-home"
.venv\Scripts\python scripts/unit_tests.py
.venv\Scripts\python scripts/smoke_test.py
.venv\Scripts\python scripts/render_modes_test.py
.venv\Scripts\python scripts/sept_render_test.py
.venv\Scripts\python scripts/batch_delete_check.py
.venv\Scripts\python scripts/bins_visual_check.py
.venv\Scripts\python scripts/playback_progress_check.py
.venv\Scripts\python scripts/incoming_visual_check.py
$env:QT_QPA_PLATFORM = "windows"
.venv\Scripts\python scripts/sept_regression_test.py
.venv\Scripts\python scripts/native_media_drag_test.py
.venv\Scripts\python scripts/timeline_interaction_test.py
.venv\Scripts\python scripts/retime_render_test.py
.venv\Scripts\python scripts/crop_inspector_test.py
.venv\Scripts\python scripts/caption_workflow_test.py
.venv\Scripts\python scripts/colour_render_test.py
```

The last two scripts use the supplied xqc_royalty.mp4 locally. Native input tests
cover linked cuts, marquee, duplication/new tracks, volume multi-edit, fades,
wheel-safe inputs, panel toggles, caption inheritance and visible text pixels,
effect drop, immutable render snapshots, viewer zoom, and playback across cuts.
Tests also cover Power Bin persistence, track ordering/save/load, ASS styles,
all four exposed composite modes, audio filters, silent exports, and LAN download.
The batch-delete watchdog exercises eight live decoders with Delete/Backspace,
Cut/Paste, overwrite, undo/redo, track removal, visibility and seeking, and checks
that retired player objects are released. Mixed media/caption deletion is one
undoable edit and preserves locked lanes. Latest-frame sampling bounds preview
work instead of accumulating queued native frames from multiple 60 fps layers.
The frame sampler is not restarted by clock ticks. The playback-progress check
compares actual changing pixel hashes across occupied and empty layers, visibility
changes, cut boundaries, looping and empty space beyond the timeline end. The
frozen-package self-test also renders moving video across an empty middle lane.
See REHAUL_PLAN.md for the acceptance record and validation boundaries.
See TIMELINE_PLAN.md for the timeline interaction follow-up and its test evidence.

### Caption, audio and keying workflow

Auto Caption Style includes a live style preview and a play/stop animation
preview. Background Colour is shown only for a background card; Word Highlight
Colour is shown only for that animation. Censor curse words masks common English
profanity in generated text without changing timestamps. Always review generated
captions: recognition and vocabulary matching are not perfect.

Audio effects **Cut curse words** and **Remove Silence** are editing actions:
drag them onto a timeline audio clip. Cut curse words uses the existing local
faster-whisper engine/model for actual word timestamps, asks before applying,
and leaves gaps without moving video. It does not use guessed sentence timings.
Remove Silence requires linked video/audio with identical timeline start and
duration, then packs retained sections of those linked clips only. Other clips
stay fixed. Cancel discards background analysis results; Undo restores the whole
edit. Original source files are never modified. Instant Package sequences silence
processing before caption generation.

Edit > Delete gaps uses the lowest story-video lane (preferring a content lane),
not long still/title overlays, to find narrative gaps. Non-music audio protects
audible content inside a gap. Later clips, captions and sound effects move by one
common time map, keeping their offsets. Still/title overlays crossing a removed
interval shorten. Affected locked layers block the operation to prevent drift.

Explorer files can be dropped directly onto the timeline. Muted placement ghosts
appear immediately; duration analysis runs in the background. The final insert
uses measured durations and imports each source into Master once. Cancelled drags
do not add Master records. PNG timeline thumbnails use source alpha, including
projects whose old cached thumbnails were flattened JPEGs.

Keying > Chroma Key / Green Screen provides a colour swatch, eyedropper,
similarity and edge softness. The eyedropper opens the original selected clip
before effects, with a scrubber covering its timeline duration. Click a pixel and
Apply; the main playhead is not moved. Key transparency uses matching Qt/FFmpeg
math and preserves pre-existing alpha. Preview pan ignores wheel events while
the middle button is held.

Vocal Only is an optional local audio action. Drop it onto an unlocked audio
clip, approve the first-use download, and choose an output MP3. A progress
dialog covers download, setup, separation and export, with cancellation and
error feedback. On completion, choose whether to replace that timeline audio;
video and timing stay unchanged, and replacement is undoable. Video-file audio
and standalone audio files are supported. Nothing is uploaded.

The CPU component is downloaded separately (roughly 250–450 MB; measured
installation about 1.2 GB, requiring 2 GB free during setup). It never loads at
normal editor startup. Separation is not perfect and does not guarantee a
copyright-free result. Long clips can take significant CPU time; review the
saved sound before using it. Demucs is archived upstream; this optional backend
is version-pinned, and its model and Python downloads are SHA-256 checked.

### Project browser, framing and export follow-up

File > Project Manager provides gallery/list views, search, a New Project tile,
and a persistent project folder. The default save folder is Documents/Kinetic
Cut/Projects; opening a project establishes its folder if none is configured.
The browser also includes recent opened/saved projects. Double-click to open.
Deletion moves only the selected .kcut into `.KineticCut Trash` beside it;
source media is untouched, and the open project cannot be deleted. Save a
project to cache a thumbnail of its current composition. New/Open protect
unsaved work with Save/Discard/Cancel.

Layer headers use a bordered table layout, with names above controls. Audio
lanes have Mute rather than visibility; mute affects preview and export.
Layer-header menus contain lane actions only, including Duplicate Layer above
the source. Duplicated media has independent IDs/links and preserves properties.

Preview context menus offer Position to Top, Mark as Webcam, and Position Below
Webcam for visible cropped media. The Video inspector has a quick Background
Blur toggle and strength, applying a normal Gaussian Blur effect. Interior
numeric defaults sit at the centre of sliders; endpoint defaults stay at ends.

Auto export tests NVIDIA, Intel and AMD encoders and falls back to CPU. This
selects a working hardware encoder, not a promise that every GPU effect runs
on the GPU. Strong-blur filtering uses a reduced working resolution, while
opaque video avoids unnecessary RGBA conversions. On the supplied 10.16-second
TestEdit.kcut, isolated 1080x1920/60fps NVIDIA export improved from 98.44 seconds
to 22.43 seconds. Actual time depends on hardware, layers and effects. Titles
always render; Burn Subtitles is disabled unless real subtitle items exist.

Caption recognition transcribes separate speech regions instead of joining
silence-separated regions before alignment. The reported “feels” word now
starts at 12.248 seconds in the supplied recording; multi-word caption groups
also break across long pauses. Speech recognition remains approximate.

Additional checks:

```powershell
.venv\Scripts\python scripts/followup_visual_check.py
.venv\Scripts\python scripts/word_cuts_check.py
.venv\Scripts\python scripts/qt_cleanup_check.py
```

The word-cut check uses a generated local Windows speech fixture and an already
cached Whisper model; it explicitly disables network downloads. The cleanup
check forces garbage collection after each UI test. Its overlay test records
draw order without retaining a live native QPainter beyond the paint event.

### September 10 updates

New Project now asks only for name, canvas and frame rate. Audio keeps its
source level by default: no automatic normalization, noise reduction or music
ducking. Saved projects retain their existing settings; optional audio
processing remains available in Project Settings and individual effects.

The updated 12.07-second TestEdit export with generated captions exposed a
NVIDIA final-frame buffering stall. Zero delay/lookahead fixes that case.
Deliver now has Cancel Render, finalization feedback and a 90-second
no-progress watchdog. Render logs live in the application cache. A failed or
cancelled export leaves any previous output intact; only a completed render
is published to the chosen filename. Owned encoder processes close with the
application rather than remaining as orphaned renders.

In Effects, **Person / Background → Remove Person Background** removes the
person's surroundings. **Face Filters** offers Big Eyes, Big Nose, Big Lips
and Face Twist. Crop the webcam first, then drop an effect onto its video/image clip.
First use asks before downloading an isolated optional component (about
350 MB installed; the tested installation measured 346 MB). It is not loaded
at editor startup. Download/setup and clip analysis show progress and Cancel.

Analysis follows one face through the current cropped clip. Filters disappear
when no face is detected; a clip with no detection gets an explanatory prompt
and no effect. Effects can be stacked, bypassed, removed or undone. Changing
the crop/source, or extending beyond analysed footage, requires **Re-analyse
current crop** in the Effects inspector. Trimming within the analysed range
or repositioning the clip does not require another model run. These are
practical lightweight filters, not guaranteed studio-quality rotoscoping:
review hair edges, fast movement, occlusions and shots with multiple people.

Playback uses cached landmarks/masks, not live AI inference. Export prepares
a lossless alpha-bearing cache using the same drawing operations as preview.
This preparation can take time and additional disk space, especially for long
or high-resolution clips; subsequent unchanged exports reuse it. Original
video and audio files are never overwritten by analysis or effects.

While box-selecting timeline clips, hold the pointer near the top/bottom edge
of a layer section to scroll through hidden lanes, or use the mouse wheel
without releasing the selection. Selection stays anchored to the original
timeline content. The media pool and Power Bin grid support the same edge and
wheel scrolling, retaining items that move out of view. Release or Escape
stops selection scrolling.

Timeline box selection is a single continuous overlay across subtitle, video
and audio dividers. When dragging beyond a section that still has hidden lanes
in that direction, it scrolls that section to its end before passing into the
next one. This works downwards and upwards, even when the pointer moves across
several sections at once. The mouse wheel follows the same active section.

Text and Headline timeline objects support their clip fade-in/out handles in
preview and export, including backgrounds, outlines, shadows and emoji.
Clip opacity and simultaneous fades multiply together; title styling remains
editable and is not rewritten by the fade controls.

Deliver has an editable Location dropdown containing the last five successful
export folders. Its settings column stays fixed-width, with vertical scrolling
when needed, and cannot be narrowed with the splitter. Each queue card displays
its own elapsed render time, starting on that job's turn and stopping on
completion/failure/cancellation. Pending jobs have a removal ×; removing a queue
entry never deletes an output file. Completed jobs offer Open file location in
their right-click menu.

Startup imports run off the GUI thread so the splash continues processing
events. Python subprocesses remain hidden, multiprocessing workers use the
frozen-app guard, and installed Chocolatey FFmpeg wrappers are bypassed in favour
of their actual binaries. This avoids a wrapper creating its own console child.
# MCP connection and timeline gesture update

The top-right **AI Assistant** button is an MCP connection/status panel, not a
built-in chatbot. See [MCP_CONNECTION.md](MCP_CONNECTION.md) for setup and tools.

Failed renders now display **RENDER FAILED** and are never retried by Render All;
add a fresh job after correcting the problem. Moving/Alt-dragging clips edge-scrolls
the source section, including when the pointer crosses into an incompatible
section. Middle-button drag pans the timeline horizontally and the starting
section vertically; the time axis remains synchronized across all sections.
At an adjoining clip boundary, the narrow centre hit zone performs a linked
rolling trim with a green indicator. Just to either side, normal single-edge
trimming remains available and previews the neighbour's overwritten range.

The Face Filters library now offers Big Eyes, Big Nose, Big Lips and Face Twist.
Party Hat and Face Mask are removed from the library; saved projects containing
those old effects remain readable. New distortions reuse existing face analysis
and disappear when tracking is lost. These are distortions, not 3D accessories.

Adjacent-cut playback prepares nearby video decoders in both directions, so
the viewer can cross source changes without temporarily losing the picture.
If a decoder is still catching up, an adjacent outgoing frame can be held for
at most half a second; genuine empty timeline gaps are not filled. Preparation
is bounded to eight additional decoders and only nearby visible video lanes.

Clip trims, rolling edits, fades and retiming do not scroll the viewport while
their handles are held. Move/Alt-drag still edge-scrolls and can create a new
highest video lane. Incoming media drags may enter over the track headers and
continue into valid placement space. Locked/read-only targets remain protected.
Timeline clips have dark fade shading and thin rounded black borders, with a
red playhead.

Audio waveforms now use cached signed peaks at one-millisecond resolution,
rather than a fixed 1,000 points for an entire recording. Zoom-aware aggregation
retains short transients, combines stereo peaks without phase cancellation,
and draws a split centre line without artificially boosting/clipping the display.
Trim/source offsets, speed, volume and fades are reflected in the waveform.
Shift+wheel changes track height only in the audio, video or subtitle section
under the pointer; other sections and horizontal zoom stay unchanged.

Automatic MCP enablement is silent. The panel opens only from AI Assistant.
A green check in the toolbar/panel means a client has made a verified handshake
or authenticated request this session; last-request and idle status are shown.

Subtitles support single-word cutting, group moves/Alt-drag duplication and
overwrite trimming with previews/undo. Unaffected subtitle tails are retained.
The Inspector's Timings tab contains navigation and an editable timing/text
table. Customize Caption controls sit directly below the checkbox. Caption/title
styles and text apply to all selected unlocked items of the same type; matched
effect controls update the corresponding effects on selected clips. Group timing
edits preserve relative offsets instead of stacking subtitles at one timestamp.
Inspector slider-track clicks jump directly to the clicked value.

Typing updates the live text and preview immediately, grouping history snapshots
after a short pause. History reuses immutable unchanged records, hidden timing
tables are not rebuilt per keystroke, and off-screen clips/captions are culled
before painting. These changes avoid project-size-dependent typing stalls.
