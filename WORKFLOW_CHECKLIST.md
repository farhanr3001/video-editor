# Kinetic Cut workflow follow-up

## Implemented

- [x] Offline Google Noto colour emoji picker: 3,953 Unicode 17 entries,
  searchable names/categories, skin tones, flags and joined sequences.
- [x] Emoji insertion button at the bottom-right of title/subtitle text editors.
- [x] Colour emoji in preview and export, including ordinary captions.
- [x] Google emoji in the editable rich-text box; Windows glyph spacing fixed;
  original Unicode text, selection, copy/paste and undo retained.
- [x] Headline inspector: Color, Size, Duration, position-only Transform.
- [x] New headlines centred at project dimensions / 2 (540, 960 by default).
- [x] Playhead snaps to media/subtitle edges when snapping is enabled.
- [x] Media Pool / Power Bin marquee selection, ordered batch timeline insertion,
  folder exclusion and batch removal of unused pool / Power Bin entries.
- [x] Alt+V / context-menu Paste Attributes: compatible video/audio/text sources,
  initially unchecked properties, group/master toggles and multi-target support.
- [x] Removed Hook Card, Caption Pop and Lower Third from the effects catalogue;
  existing project data remains supported.
- [x] Slightly reduced fast numeric scrubbing acceleration.
- [x] Grey Alt-drag duplicate preview and temporary new track before drop;
  moving back or cancelling removes the provisional track without project edits.
- [x] Startup subprocess policy loaded before bundled dependency runtime hooks.
- [x] Window title and executable product description are Kinetic Cut.
- [x] Defaults verified: 1080 × 1920, 60 fps.

## Verification and delivery

- [x] All 3,953 catalogue entries shape to available Google colour glyphs.
- [x] Real 60 fps H.264 emoji export and preview/export pixel comparison.
- [x] Existing real-media playback/timeline and render-queue checks passed.
- [x] Previous packaged check passed: assets, rendering, title, defaults and
  Windows helper console handle = 0, even when a new console was requested.
- [x] Full regression suite: 96 tests passed and process exited cleanly (code 0),
  with deterministic Qt test-window and queued-worker cleanup.
- [x] Rebuilt dist/KineticCut/KineticCut.exe with the rich-text emoji fix.
- [x] Final packaged smoke check exited 0; inspected the final workspace capture
  showing colour emoji inside Rich Text and in the preview. Report and images:
  build/desktop-final-check/. Native Windows text rendering was checked separately
  in build/windows-rich-text-fixed.png.

## Next follow-up — media bins, timeline and captions

- [x] Aspect-preserving transparent image thumbnails; refresh old cached JPGs.
- [x] Media Pool / Power Bin display rename and Open File Location.
- [x] Drag timeline clips into Power Bins without moving their originals;
  save/reload their attributes and restore them on later timeline insertion.
- [x] Snapping on clip/caption edge trims, frame-step arrow keys and playback loop.
- [x] Cut/Split naming and white razor cursor; swap link/snapping button positions.
- [x] Correct open/closed lock icons, locked-lane insertion guards and hidden images.
- [x] Paint selected transform controls above every preview layer.
- [x] Obvious caption font dropdown, cyan text / black outline defaults, and
  active-word background highlighting in preview and export.
- [x] Regression tests, visual checks and updated executable.

## Urgent batch-deletion follow-up

- [x] Reproduced multi-decoder teardown freeze with Delete and undo/redo.
- [x] Queue native decoder stop/disposal outside the Python edit callback;
  remove retired decoders from preview immediately and keep child outputs alive
  until player disposal. Sample latest frames without queuing every video frame.
- [x] Linear linked-selection expansion and generator-safe linked batch split.
- [x] One undoable delete for a mixed media/title/caption selection; locked tracks
  are protected from deletion and ripple movement. Preserve mixed marquee selection.
- [x] 116 unit tests pass with process exit 0. Eight-decoder watchdog passes
  Delete/Backspace, Cut/Paste, overwrite, undo/redo, track removal, hiding, seeking
  and mixed caption deletion; no retired players leaked; process exit 0.
  Report: build/batch-delete-check/report.json. The test's offscreen clipboard is
  cleared before Qt shutdown; the real Windows system clipboard is unchanged.
- [x] Existing real-media UI/playback regression passes after the decoder changes.
  Image/caption visual checks and real 60 fps word-highlight export pass; preview
  versus exported-frame mean error stays below 1.1/255 per colour channel.
- [x] Finished watchdog stress checks, clean-exit validation and package rebuild.
- [x] Updated dist/KineticCut/KineticCut.exe (8 September 2026, 21:21 local).
  Frozen package self-test exited 0: 3,953 emoji, saved-bin attribute roundtrip,
  word-highlight export, caption defaults, loop/razor controls, 1080×1920 at
  60 fps, Kinetic Cut title/product metadata and hidden helper console handle 0.
  Report/screenshots: build/bins-package-check/.

The preceding follow-up is complete. Verification is bounded
to the cases above; it is not a guarantee that every possible media/driver/input
combination is free of defects.

## Preview, bin separation and incoming drag follow-up — 9 September

- [x] Reproduced one-frame preview while the timeline clock advanced; stop
  resetting the active frame timer on every clock tick.
- [x] Real-media test compares changing preview pixels on V1 and V3 with V2 empty.
- [x] Keep saved Power Bin attribute records separate from Master source media;
  selection and cancelled drags do not import media or preset wrappers.
- [x] Enable drops on the Power Bin grid viewport, including empty space and
  folder tiles; saving a timeline preset leaves original timeline clips unchanged.
- [x] Grey incoming-media previews, sequential batch placement and provisional
  linked video/audio lanes; preview and committed insert share one placement plan.
- [x] Extend horizontal zoom-out from 12 to 0.6 pixels/second (20× wider);
  logarithmic slider midpoint is 12, maximum remains 240. Adaptive ruler spacing.
- [x] Supply the missing palette SVG for the Inspector's Colours tab.
- [x] Final full regression: 128 tests, process exit 0. Real pixel-hash playback
  checks pass across empty/hidden layers, cut boundaries, loop and beyond-end
  black preview. Eight-decoder batch edits and prior real-media UI checks pass.
  Reports: build/playback-progress-check/ and build/batch-delete-check/.
- [x] Inspected incoming grey ghosts, provisional lanes, the outlined Power Bin
  grid and palette icon in build/incoming-visual-check/.
- [x] Rebuilt dist/KineticCut/KineticCut.exe. Frozen self-test exited 0 and recorded
  six distinct video frames on each occupied lane around an empty middle lane.
  Power Bin grid drop acceptance, attribute roundtrip, emoji, word-highlight
  export, 1080×1920 at 60 fps and hidden helper consoles also passed.
  Report/screenshots: build/preview-package-check/. No remaining items in this
  follow-up checklist; verification remains bounded to the recorded cases.

Test artifacts are under build/. Package self-tests use isolated application data
and do not touch the user's projects. Existing pinned Windows shortcut labels may
be cached; the new executable's FileDescription and ProductName are Kinetic Cut.

## Timeline, captions and audio follow-up — 9 September

- [x] Timeline PNG thumbnails preserve transparency and aspect ratio, including old projects.
- [x] Group-safe multi-layer movement; middle-button preview pan suppresses wheel zoom.
- [x] Live auto-caption style/animation preview; conditional colour rows; optional curse-word censorship.
- [x] Cut curse words audio action with timestamped recognition and non-ripple cuts.
  Real offline faster-whisper recognition detected both test words with actual
  timestamps; three retained audio segments preserved source offsets. English
  vocabulary and speech recognition are not exhaustive; review results.
- [x] Remove Silence as an audio drop action with aligned linked-video validation and local packing.
  Original files, unrelated clips and later groups stay unchanged. Entire edits
  are undoable. Instant Package waits for silence processing before captioning.
- [x] Edit > Delete gaps: narrative gaps close in order, preserving later relative timing.
  The lowest story-video lane (content lane preferred) guides gaps. Long still/
  title overlays shorten across cuts; non-music audio protects audible material.
  All later clips/captions shift together. Locked affected lanes reject the edit.
- [x] Explorer-to-timeline import, Master deduplication and incoming placement ghosts.
  Durations are probed asynchronously; provisional ghosts say they are reading
  duration until metadata arrives. Only a committed drop adds Master media.
- [x] Chroma Key / Green Screen, preview/export parity and scrub-able colour sampling dialog.
  Key alpha matches FFmpeg exactly on the test fixture; composition, grading
  and circular-mask export checks pass. Sampler shows the original selected
  clip, with its full timeline duration; main playhead remains unchanged.
- [x] Assess vocal isolation dependencies; defer heavyweight installation pending user choice.
  No vocal-separation dependency/model installed. Demucs-style local separation
  needs additional ML dependencies/models: https://github.com/facebookresearch/demucs
- [x] User subsequently approved the optional Vocal Only component; see the
  current follow-up below. The initial deferral above is historical.
- [x] Regression tests, visual checks, updated executable and frozen-package verification.
  150 unit/UI tests pass, exit 0. Forced Qt cleanup check: 20 tests pass. Fixed a
  test spy retaining a native QPainter after widget destruction; draw-order
  checking no longer holds native painter arguments. No app crash was suppressed.
  Live multi-decoder Delete/Backspace, undo/redo, cut/paste, overwrite, track
  removal and visibility checks pass; measured deletion calls 16–62 ms.
  Actual frame-hash playback passes with empty/hidden layers, cuts and looping.
  Visuals and key-alpha/export evidence: build/followup-visual-check/.
  Real offline word-timestamp evidence: build/word-cuts-check/report.json.
  Rebuilt dist/KineticCut/KineticCut.exe (9 September, 14:12 local).
  Frozen check exited 0: six distinct frames per occupied lane around an empty
  middle lane, new caption/audio/keying/Explorer controls, emoji, Power Bin
  roundtrip, hidden helper consoles and Kinetic Cut product title all passed.
  Packaged report: build/followup-package-check/report.json.

## Optional vocals, editor ergonomics and projects — 9 September evening

- [x] First-use optional Vocal Only download; isolated CPU worker, progress and
  cancellation, MP3 destination and optional undoable audio replacement. No
  upload or model import on normal startup. Real download/install/separation
  check passes. Measured installation: 1,214,059,629 bytes (about 1.2 GB).
  The test-only installation under build/vocal-component-check/runtime was
  removed after verification to reclaim space; reports and MP3 results remain.
  Runtime files can be downloaded again; first-use installation is still opt-in.
  Both standalone WAV and a 3-second trim from the supplied MP4 pass, producing
  3.030-second MP3s. MP4 source offset: 175.520079 seconds. Base bundle remains
  approximately 364 MiB; the AI component is not bundled or loaded by default.
- [x] Table-style lane headers; names above controls; audio Mute instead of eye,
  applied to playback and export. Existing hidden audio lanes migrate to mute.
- [x] Interior slider defaults centred, endpoint defaults preserved.
- [x] Position to Top, Mark as Webcam, Position Below Webcam; cropped/centred
  framing, persistent metadata and undo. Locked clips protected.
- [x] Video Inspector Background Blur toggle and strength; disabled when off.
- [x] Reproduced cinema/feels alignment failure from the supplied source.
  Separate speech-region transcription places Feels at 12.248–12.768 seconds.
  Two-word groups no longer cross the long pause. Recognition is approximate.
- [x] TestEdit.kcut export measured at 98.44 seconds before and 22.43 seconds
  after optimization for its 10.16-second 1080×1920/60fps NVIDIA output.
  Opaque video avoids needless RGBA conversions; broad blur uses reduced working
  resolution. Checked-frame mean RGB difference: 1.74/255. Source/project untouched.
  Final end-to-end Auto export (subtitle switch off, headline retained) selected
  NVIDIA and completed in 15.28 seconds; timings vary with system load.
- [x] Auto probes actual NVIDIA/Intel/AMD encoding and falls back to CPU.
  Fixed minimum-frame-size probing; NVIDIA is selected on this PC. Subtitle
  burn is disabled with no actual subtitle items; video titles always render.
- [x] New Project uses a supported settings dialog and clears workspace/history.
  Save/Discard/Cancel guards project switching. Project Manager offers persistent
  folder, thumbnails, search, gallery/list and New Project first. Open/Delete
  menus; deletion is a recoverable .kcut-only move, never source-media deletion.
- [x] Header context menus contain only lane actions; Duplicate Layer inserts
  above source with independent IDs/links, preserved properties and undo.
- [x] 163 unit/UI regression tests pass; real caption alignment and keying/export
  checks pass. Evidence: build/final-current-tests.log and
  build/current-followup-check/report.json.
- [x] Updated dist/KineticCut/KineticCut.exe, 9 September 2026 at 19:59 local.
  Final frozen check: build/current-package-check/report.json. Gallery/list,
  header layout and disabled Background Blur visuals inspected. Optional AI
  stays unloaded; changing frames on V1/V3 with empty V2, hidden helper consoles,
  emoji, Power Bins, caption and new project controls verified.
- [x] Assessed (discussion only): person-background removal and tracked face
  filters are feasible, neither implemented. Official MediaPipe model-only
  sizes checked via HTTP HEAD: SelfieSegmenter 249,537 bytes; FaceLandmarker
  bundle 3,758,596 bytes. Runtime and filter artwork add to these figures.
  Main concerns: per-frame processing/cache, hair and motion-edge quality,
  tracking loss/occlusion and identical preview/export behaviour. Recommend
  optional background removal first, then a small tracked-filter catalogue.
  Sources: https://developers.google.com/edge/mediapipe/solutions/vision/image_segmenter
  and https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker

## 10 September follow-up (supersedes the discussion-only entry above)

- [x] Remove automatic audio-processing controls from New Project; new projects
  leave normalization, noise reduction and ducking off. Existing saved settings
  are preserved and remain available through Project Settings.
- [x] Reproduce updated TestEdit.kcut stalling at frame 710 / 11.783 seconds with
  captions. NVIDIA buffering fixed using zero delay/lookahead. Same project
  completed in 28.31 seconds in direct render and 44 seconds through the queue.
  Final queue recheck completed in 18.015 seconds at 100%, with captions enabled.
  Timings vary with system load. Evidence: build/export-queue-stall-check/report.json.
- [x] Add Cancel Render, progress watchdog, child-process lifetime ownership,
  finalization feedback and atomic output publication. Cancel/failure preserves
  an existing output; no source/project file is changed.
- [x] Optional person-background removal, tracked Party Hat, Face Mask and Big
  Eyes. Analyse current crop off-thread, cache landmarks/masks, hide missing-face
  filters, validate source/crop/coverage, and offer Re-analyse. Preview/export
  share effects; lossless alpha-bearing render caches retain original sources.
- [x] First-use consent, download/install/analysis progress, cancellation and
  undetected-subject feedback. Measured installation 345,539,680 bytes, separate
  from the base app. Real supplied webcam: face/person detected in all 60 frames.
- [x] 16 added tests cover corrupt/missing caches, crop and trim safety, face
  loss, segmentation alpha/stack order, cancellation, stall detection, process
  ownership, original-output preservation, first-use decline and undo.
- [x] Full 185-test suite passes; real no-face/person test passes. Cropped real
  webcam previews and stacked-effect export inspected. Evidence:
  build/sept10-final-tests.log, build/vision-render-tests.log,
  build/vision-component-check/absent-report.json, build/vision-visual-check/.
- [x] Final requested addition: content-anchored box-selection autoscroll/wheel
  scrolling across offscreen video/audio lanes and media-pool/Power Bin items.
  Five dedicated UI tests cover both directions, offscreen selection retention,
  horizontal anchor stability, no timeline edits and release/Escape/clear safety.
- [x] Rebuilt dist/KineticCut/KineticCut.exe on 10 September 2026 at 15:33 local.
  Packaged self-test passed: lossless alpha/effect export, simplified New Project,
  unloaded optional AI, changing video frames across an empty middle lane,
  Power Bin attributes, captions/emoji and hidden helper processes.
  Evidence: build/sept10-package-check/report.json. New Project screenshot inspected.
  Removed only the temporary optional test runtime (about 346 MB); retained
  reports, masks and screenshots. User TestEdit.kcut remains 59,163 bytes with
  original 9 September 22:19:26 modification time. All current requested tasks done.

## Continuous timeline selection correction

- [x] Reproduce split selection outlines and premature scrolling handoff when
  crossing subtitle/video/audio dividers.
- [x] Draw one overlay above all section dividers. Keep the original content
  anchor; retain selected items that scroll out of view.
- [x] Scroll the active section to its directional limit before crossing to the
  next section, including stationary-pointer continuation, wheel input, rapid
  multi-section moves and reversing direction. No timeline media is moved.
- [x] Verified continuous fill over dividers with pixel assertions and inspected
  screenshots. All ten scrolling UI tests and the complete 190-test suite pass.
  Rebuilt dist/KineticCut/KineticCut.exe; packaged checks pass, including scrolling
  through subtitle/video/audio in both directions. Evidence:
  build/selection-boundary-full-tests.log and
  build/selection-boundary-package-check/report.json, with continuous-selection
  screenshots alongside the report. Saved user project/source media unchanged.

## Title fades, Deliver controls and startup follow-up

- [x] Title and Headline fades/opacity wired into preview and all export parts,
  including background cards, outlines/shadows, emoji and animated segments.
  Actual Text and Headline exports brighten/dim correctly at both edges.
- [x] Editable Location dropdown stores the latest five unique successful export
  folders. Fixed-width Deliver settings, disabled left splitter, wrapped estimate
  and vertically scrollable form tested at 1100px through 1920px window widths.
- [x] Per-job elapsed timer starts only on its turn and freezes at its terminal
  state. Queue × removes waiting jobs by identity; active jobs are protected.
  Completed-job context menu opens its folder; no output files are deleted.
- [x] Isolated source startup trace recorded no subprocess launches. Added direct
  FFmpeg/ffprobe resolution around the installed Chocolatey wrappers, retained
  hidden-process policy and added frozen multiprocessing guard. Background import
  loading keeps the splash event loop responsive; source startup self-test passes.
- [x] All 199 regression tests passed. Rebuilt EXE (2026-09-10 16:44:28) passed
  packaged title/export/queue/layout checks and actual startup checks. Evidence:
  `build/title-delivery-final-package-check/report.json`,
  `build/startup-final-package-check/report.json`, and
  `build/delivery-final-tests.log`. Final layout screenshots inspected.
  TestEdit.kcut remains unchanged. The reported startup flashes were not directly
  reproduced: both scoped startup audits observed no subprocess launches.

## MCP, gestures, filters and cut-transition follow-up

- [x] AI Assistant is connection setup/status only. Loopback authenticated MCP
  exposes 15 editor tools, revision-checked undoable edits, UI workflows,
  previews, import and export. Codex configuration registered with backup.
  Native `mcp__kinetic_cut__get_state` and `get_preview` succeeded against the
  installed running editor on 2026-09-11 (not only a helper-client test).
- [x] Failed queue cards show RENDER FAILED; Render All only starts queued jobs.
- [x] Move/Alt-drag edge-scrolls its source section. Middle drag pans the
  starting section. Shared boundaries offer green linked rolling edits;
  independent trims show the neighbour's overwritten portion immediately.
- [x] Trim/fade/roll/retime handles never scroll, including incidental wheel
  input. Existing and Alt-duplicated clips can create a highest video lane.
  Pool drags recover after entering over the fixed track headers.
- [x] Party Hat and Face Mask removed from the library (legacy projects remain
  compatible). Big Nose, Big Lips and Face Twist reuse face tracking; missing
  tracking hides distortions. No replacement 3D accessory claimed or included.
- [x] Red playhead, dark fade triangles, rounded black thumbnail/clip borders.
  Visual evidence: `build/gesture-visual-check/fade-borders-playhead.png`.
- [x] Nearby video decoders prepare both sides of cuts with bounded resources.
  Packaged playback and forward/reverse scrubbing show no missing picture at
  adjacent different-source or source-jump cuts. Incoming frames actually decode;
  genuine gaps remain blank. Evidence: `build/timeline-cut-package-check/report.json`.
- [x] All 220 regression tests pass (`build/timeline-regressions-full-tests.log`);
  extra wheel/fade gesture assertions pass in `build/gesture-regression-tests.log`.
  Packaged MCP, editing/export/workflow and startup checks pass in
  `build/timeline-assistant-package-check/report.json`,
  `build/timeline-workflow-package-check/report.json`, and
  `build/timeline-startup-package-check/report.json` (no startup subprocesses).
- [x] Installed EXE: 2026-09-11 05:20:10, 7,495,512 bytes, SHA256
  `3556EBD37FB47C8F24A79CF9B1ED1EA3B679C895E6E22E780D553948366877A3`.
  Previous EXE retained at `build/KineticCut-before-timeline-regressions.exe`.
  User TestEdit.kcut was not saved or changed; SHA256 remains
  `2FE7352BB391D31FABC28F5C40862D3FF5E59396BCDFD841BED6F14EBEFD3502`.

## Caption layout and creative styles — 2026-09-11

- [x] Compact, stable Caption header with customization expanded below it,
  including short Inspectors; Aa text-case button beside emoji, batch/undo.
- [x] Generated trailing-period removal; persisted recognized word timings;
  word fade, sparse editable Word Highlight 2, Punch, colour-following glow.
- [x] Timings colour-codes highlighted words and offers per-word context actions.
- [x] Curated font picker, downward compact popup, hover preview, legacy font
  preservation and seven OFL families (3,396,535 bytes including licenses).
  Geometos Soft is available only if separately installed; see CAPTION_STYLES.md.
- [x] 252 tests pass (`build/caption-style-release-tests.log`); packaged subtitle,
  workflow, assistant and startup checks pass. Actual FFmpeg frames and preview
  glyph bounds verified; visuals in `build/caption-style-subtitle-package-check`.
  Packaged 1,000-caption typing average 9.94 ms/character, maximum 12.06 ms.
- [x] Installed and reopened EXE: 2026-09-11 17:50:07, 7,525,480 bytes; SHA256
  `E19924C0AC0BD884CF4FC70D37ADA7100519F843F750C55D14A47FABFE1022DE`.
  Previous executable: `build/KineticCut-before-caption-style-update.exe`.
  Native MCP get_state succeeded after installation. No user project was edited.

## Detailed waveforms, MCP status and subtitle parity

- [x] Streamed/cached signed stereo peaks at 1 ms, multi-resolution aggregation,
  no fixed full-recording point cap or artificial 2.8x clipping. Clear centre
  split, source-time/trim/speed/gain/fade mapping. Real recording sample inspected
  in `build/waveform-source-visual/waveform.png`; original source only read.
- [x] Shift+wheel changes height only within the pointed audio/video/subtitle
  section, without changing horizontal zoom or divider resizing semantics.
- [x] MCP enablement never opens its panel automatically. Green toolbar/panel
  check requires authenticated client activity; idle/last-request information is
  retained. Verified against the installed running app using native MCP state
  and workspace-preview tools: toolbar green, connection dialog closed.
- [x] Subtitle cutting includes one-word captions. Group drag, Alt-drag copies,
  Escape rollback, live overwrite previews, trim/placement overlap subtraction,
  preserved tails/styles and one-step undo. Pasting/generation share overwrite
  semantics. Overlapping newly placed subtitles are resolved deterministically.
- [x] Separate editable Timings tab with multi-row selection and input validation.
  Custom styling immediately follows Customize Caption. Cursor starts at text
  end when a different item is loaded; typing does not reset it. Y positioning
  scrubs in pixel units in Track and custom controls. Locked values stay visible
  while edits are prevented. Same-type bulk styles/text/common effects supported.
- [x] Inspector slider groove clicks jump to the clicked value and remain
  draggable; existing press/release history grouping is preserved.
- [x] Measured 1,000-subtitle typing hot path: profiled mean 741 ms -> 17 ms.
  Removed per-key serialization/deep-copy/table rebuild and off-screen painting.
  Immutable unchanged history records are shared without aliasing live objects;
  text edits update immediately and group undo after a pause. Packaged benchmark
  around 10 ms/character. Evidence: `build/caption-performance-before.json`,
  `build/caption-performance-final.json`, `build/final-subtitle-package-check/report.json`.
- [x] 242 tests pass (`build/subtitle-final-tests.log`). All final packaged
  subtitle, waveform, MCP/edit/import/export, broader workflow, cut-transition
  and startup checks pass (`build/final-*-package-check/report.json`). Inspector
  layouts inspected in `build/subtitle-source-check/custom-caption.png` and
  `build/subtitle-source-check/timings.png`.
- [x] Installed EXE: 2026-09-11 11:19:51, 7,511,341 bytes; SHA256
  `BAD0B8977438DD5A3DC3CF68A362BDAB09B76F022F43F376E55C05D77538909D`.
  Previous EXE backed up at `build/KineticCut-before-subtitle-update.exe`.
  TestEdit.kcut SHA256 remains
  `2FE7352BB391D31FABC28F5C40862D3FF5E59396BCDFD841BED6F14EBEFD3502`.
