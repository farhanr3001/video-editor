# September workspace rehaul — acceptance record

## Implementation sequence

1. Model/transport and editing invariants.
2. Timeline/viewer interaction and rendering.
3. Workspace panels, inspector routing, media/effects organization.
4. Subtitle styling and export/queue consistency.
5. Real input/render tests, screenshots, fixes, standalone package.

## Implemented and exercised

- [x] Playback clock independent from decoder callbacks; native playback crosses
  cuts and survives Media Pool selection. Windows software-decoding default avoids
  the reproduced D3D frame-conversion deadlock.
- [x] Marquee/multi-selection; Link selection toggle; context link/unlink;
  linked split/trim/move/delete; Alt-drag duplication; new V/A lanes.
- [x] One V1/A1 on fresh projects, subtitle lane, thumbnails, volume-scaled
  waveforms, draggable audio fades, bounded horizontal/vertical timeline zoom.
- [x] Viewer output mask, pointer-centred view zoom, middle-button pan, Fit,
  transform handles; removed redundant I/O and Select/Crop toolbar controls.
- [x] Independent stacked Media Pool/Effects toggles and Inspector visibility;
  selected filename and contextual icon tabs; project title; Edit/Deliver footer.
- [x] Media thumbnail grid/search; persistent Power Bin folder/reference storage.
- [x] Categorized/searchable effect list, real effect drop onto clips;
  enabled-only Effects tab; Gaussian Blur controls.
- [x] Video Transform/Cropping/Composite; Audio Volume/Pan/Pitch with mixed-value
  relative adjustments; irrelevant tabs disabled; wheel-safe numeric controls.
- [x] ST1 caption selection, Caption/Track routing, text/timing, inherited/custom
  style, colour/sliders/reset controls, split/merge, visible native text fill.
- [x] Separate Deliver workspace, shared viewer/timeline, immutable job snapshots,
  sequential rendering, completed-job phone/wireless actions.
- [x] Existing timeline cuts receive Vertical Layout without deleting/recreating
  source audio; occupied lanes are preserved.
- [x] Undo/redo, ruler dragging, viewer pan, and compact 1366×768 layout regression.
- [x] Standalone executable opens the actual editor window; packaged local
  faster-whisper transcription ran offline against xqc_royalty.mp4.

## Tests and evidence

- 19 unit tests pass: persistence, track order, linking, split behavior, subtitle
  inheritance, ASS controls, Power Bins, audio filters, silence ranges, and LAN serving.
- scripts/sept_regression_test.py: real native Windows Qt input and supplied media.
- scripts/sept_render_test.py: queued real-media 720×1280 render, preserved opening
  gap, cropped layout, blur, captions, independent pan/pitch/fades/audio.
- scripts/render_modes_test.py: Normal/Add/Multiply/Screen, Reflect/Replicate blur
  borders, softness, rotated/perspective layer, subtitle background/shadow, music
  ducking, and export without audio.
- scripts/smoke_test.py: synthesized footage/image/audio → vertical MP4 → ffprobe
  → project save/load.
- scripts/package_check.py: inspect the packaged process's actual window title;
  detect and report packaged startup dialogs instead of mistaking them for success.
- Packaged --caption-selftest: faster-whisper tiny.en, network disabled, 10 captions.
- Final standalone startup: editor window responsive; approximately 111 MB idle
  working set on this Windows machine (not a playback/4K memory measurement).
- Native screenshots: build/sept-edit-workspace.png, sept-video-inspector.png,
  sept-audio-inspector.png, sept-subtitle-inspector.png, sept-deliver-workspace.png,
  sept-compact-workspace.png, and sept-preview-caption.png.

## Bugs found during the loop and corrected

- Native D3D/CPU-frame conversion deadlock, masked by offscreen-only testing.
- Existing-content Vertical Layout no-op.
- Lost track ordering, recreated deleted audio, and right-hand split link groups.
- Caption fill obscured by its outline at reduced viewer sizes.
- Effect preview strength scaling and source-trim waveform alignment.
- Compact viewer minimum size overlapping playback controls.
- Undo/redo Inspector selection diverging from the timeline/viewer.
- PyInstaller collecting an incompatible ICU DLL from an unrelated Poppler tool
  on the host PATH. build.ps1 now isolates DLL collection and restores PATH.

## Validation boundaries / follow-up requiring hardware

- [ ] Physical Pixel USB/MTP/ADB copy with an unlocked, connected phone.
- [ ] macOS native run and platform-specific packaging.
- [ ] Broad GPU/driver and sustained 4K performance coverage.

The native UI follows the supplied panel organization and editing interactions;
it is not a pixel-identical Resolve clone. Preview blur is resolution-reduced,
and Qt/libass text rasterization can differ. Preview pan/pitch processing builds
an audio cache; the first change may take a moment. Render-time estimates are
heuristic. Hardware export encoders depend on the machine's FFmpeg build/driver.

The supplied screenshots are visual references, not embedded instructions.
The optional videos were not needed to establish the described toggle and pan
interactions. Original media was not modified.
