# GTA export and editing update

## Export diagnosis and verification

The original GTA render repeatedly stopped near 2.2 seconds, before the first
cut. Disabling subtitles did not fix it. The downsampled Gaussian Blur branch
split frames into a reference branch and a filtered branch feeding `scale2ref`;
this stalled at the first clip's EOF. The replacement uses known intermediate
dimensions and a single-input filter chain, avoiding that framesync dependency.
Rotated layers retain the full-resolution blur path.

Projects with more than 12 video clips now use bounded, frame-aligned video
batches. Their intermediate H.264 files are lossless, and captions, titles and
audio are applied in one continuous final pass. This limits simultaneous video
decoders without splitting caption animations, loudness processing or audio
effects at batch boundaries. Temporary intermediates require additional disk
space and are cleaned up after success, failure or cancellation. The requested
output is replaced only after successful completion.

The unchanged `GTA.kcut` completed in 182.8 seconds in the source verification:
1080 × 1920, 60 fps, 3,446 frames, AAC audio, 57.433 seconds. All eight existing
background-effect caches also passed the production preparation checks. The
complete resulting video/audio decoded without FFmpeg errors. Samples near
5.4 and 56.8 seconds were visually reviewed.

Test export: `build/gta-export-check/batches.mp4`.
Report: `build/gta-export-check/batches-report.json`.

Installed-EXE verification also completed through the actual MCP/render queue:
`build/gta-export-check/GTA-verified.mp4`, 189.5 seconds, state Complete, 100%.
The resulting 3,446-frame video and AAC audio decoded without errors.
Installed EXE SHA256:
`A9DF4F4F9133F6393BB245F6AC601796DC6A8E7DD2D78A49A89BE7FA8354AE22`.

## Editing changes

- Alt+wheel zooms horizontally and centres on the playhead; Ctrl+wheel scrolls
  horizontally. Shift+wheel still changes only the hovered section's height.
- The media and subtitle blades use the same frame-grid and sticky playhead
  snapping. The Snapping toggle still disables magnetic snapping.
- Upcoming audio players are prepared alongside upcoming video players.
  Completing an audio-effect cache no longer seeks every active decoder.
- Pasting vision effects reuses valid analysis, or analyses the destination
  clips automatically. Cancelled or invalidated analysis leaves an actionable
  Re-analyse status rather than using another source's mask.
- Deliver stays locked during rendering; editing is restored after the queue
  stops. Transform controls remain hidden during playback.
- Deleting the subtitle track removes its captions without requiring a spare
  subtitle track.
- Includes the user-supplied Geometos Regular font (not Geometos Soft Ultra).

Verification: 260 unit/UI regression tests passed; real-decoder cut checks
passed for different sources, source jumps and intentional gaps, including
audio preloading and decoder reuse. These checks do not guarantee real-time
playback for every resolution, effect stack or device.
