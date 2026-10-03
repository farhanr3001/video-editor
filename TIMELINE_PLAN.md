# Timeline interaction follow-up

1. Restore media-grid → timeline drag initiation and Add to Timeline context actions;
   test the entire native mouse gesture, including Power Bin items.
2. Put viewer/Inspector together above a full-width timeline, with bounded vertical
   splitter travel; clear all properties and disable tabs when selection is empty.
3. Model source-aware trims, still-image extension, video/audio fade handles,
   release-time same-lane overwrite edits, and constant-speed retiming.
4. Implement Ctrl+R timeline retime overlays, drag-to-stretch, speed presets/reset,
   linked video/audio behavior, and matching preview/export timing and fades.
5. Separate lower Power Bins navigation with its own splitter/header, persistent
   folders, folder-drop organization, and reusable media drag/drop.
6. Verify model edge cases, native input, source-frame/audio output, screenshots,
   packaged build and startup. Record evidence and any hardware-only limits.

Overwrite edits are committed on release, not while dragging. Only destination
lanes are overwritten; they do not ripple later items. Retime changes preserve the
selected source range, changing timeline duration instead of its source trim.

## Acceptance record — 4 September 2026

- [x] Full native mouse drag from Media Pool to timeline, playback, Power Bin
  item → folder, persistence reload, fresh-project Power Bin → timeline, and
  context-menu Add to Timeline. The static icon grid explicitly remains drag
  enabled. Native input tests keep their temporary window unobscured.
- [x] Timeline spans the viewer and Inspector width. Splitter extremes preserve
  minimum viewer/timeline heights; Inspector sections scroll without squeezing
  controls. No selection hides property bodies and disables all tabs.
- [x] Added media becomes the active selection; linked AV selects video as
  primary, audio-only additions open Audio, and the Inspector is shown on Edit.
- [x] Native still-image extension from either edge, source-bounded footage
  trims, video/audio fade handles with red active state and seconds feedback.
- [x] Ctrl+R, linked edge retiming, percentage preset menu/reset, independent
  retiming, and release-only overwrite edits. Uncovered source pieces survive.
- [x] Retimed playback verified against actual decoded frames, player rate,
  and source timestamps. Paused speed changes prime a muted decoder frame
  without starting the timeline clock.
- [x] 34 unit tests passed, including source mapping after split/trim/overwrite,
  retimed silence ranges, linked fragment handling, locked lanes and save/load.
- [x] Controlled FFmpeg renders at 50%, 200%, 800%: output durations, red/blue
  source-frame timing, alpha fades and preserved 440 Hz audio pitch passed.
- [x] Earlier editor native regression suite and actual render-queue integration
  passed; Normal/Add/Multiply/Screen modes and silent export passed.
- [x] Final packaged executable rebuilt, including automatic added-clip selection;
  its native editor window opened successfully and the test instance closed cleanly.

Evidence scripts: `native_media_drag_test.py`, `timeline_interaction_test.py`,
`retime_render_test.py`, `sept_regression_test.py`, `sept_render_test.py`, and
`render_modes_test.py` in `scripts/`. Reviewed screenshots are under `build/`:
`retime-workspace.png`, `video-fade-drag.png`, and `full-width-timeline.png`.

Bounds: constant-speed retiming is supported (10–800%), not variable speed ramps,
reverse playback or optical-flow interpolation. Power Bins persist references;
source files must remain available. This is Resolve-inspired behavior/layout,
not a claim of complete or pixel-identical Resolve parity.
