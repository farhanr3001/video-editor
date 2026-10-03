# Playback responsiveness investigation — 21 September 2026

## What was expensive

The unchanged `LagTest.kcut` has three crops of a 1920×1080/60fps source,
Gaussian blur on the lowest video layer, and a separate audio item. Shared
source-time mappings already reuse one video decoder. The regression was not
three independent decoders, a theme recolour every frame, or the red cursor itself.

An instrumented native 1900×1032 window showed average GUI work of 11.10ms for
frame readback, 22.40ms for preview painting, and 13.51ms for timeline painting.
Selection calculation was only 0.50ms. Native frame conversion, CPU effects and
unnecessary track repainting competed with input on the same Qt event loop.

## Open-source references actually inspected

Repository popularity was observed during this investigation, not a quality or
performance guarantee. No external implementation was copied or dependency added.

- [Shotcut](https://github.com/mltframework/shotcut), approximately 15.3k stars:
  [videowidget.cpp](https://github.com/mltframework/shotcut/blob/master/src/videowidget.cpp).
  Its consumer-side frame preparation, bounded semaphore admission and queued
  presentation informed our bounded CPU-image work queue. Native ownership differs
  from PySide/Qt Multimedia; its C++ texture handoff cannot simply be transplanted.
- [Kdenlive](https://github.com/KDE/kdenlive), approximately 5.7k stars:
  [Timeline.qml](https://github.com/KDE/kdenlive/blob/master/src/timeline2/view/qml/Timeline.qml).
  Its separately represented rubber selection and playhead informed separating our
  dynamic overlay from unchanged track pixels. We retained Kinetic Cut's existing
  continuous live-selection semantics and cross-section scrolling.
- [Olive](https://github.com/olive-editor/olive), approximately 9.1k stars (the
  current development version identifies itself as alpha):
  [renderprocessor.cpp](https://github.com/olive-editor/olive/blob/master/app/render/renderprocessor.cpp).
  Render tickets, cancellation, decoder reuse and texture-versus-CPU return paths
  illustrate why GPU decode alone does not make CPU readback/composition free.

Qt's [threaded painting documentation](https://doc.qt.io/qt-6/threads-modules.html)
permits painting on independent QImages, not QWidgets. The worker handoff follows
that distinction; it does not move the canvas or live decoder frames to a worker.

## Implemented

1. Timeline static pixels no longer include the marquee. Its previous/current
   bounds and playhead/timecode use a separate damage path. Selection membership,
   edits, scrolls, themes, hover and geometry still invalidate ordinary content.
2. Detached CPU QImages and copied filter/geometry/settings snapshots prepare
   eligible static pixel-effect layers off the UI thread. At most two work items
   exist; decoders receive rotating admission. No widget or decoder-owned frame
   is accessed by a worker.
3. Raw source image and its prepared effects publish together. Duplicate webcam,
   gameplay and background crops therefore reference the same source image.
   Seek/decoder generations and publication sequence reject stale/out-of-order
   work. Failure falls back to the established synchronous renderer.
4. Effect keys still validate source image, crop, properties, geometry, motion
   state and DPR. Pausing retains the prior full-quality path; export code and
   originals are unchanged. Tests compare worker and synchronous pixels exactly.
5. Keyframed, procedural animated, vision and transition layers retain their
   established time-dependent path. They are NOT advertised as fully asynchronous.

Rejected experiment: even copying native planes before worker QVideoFrame
conversion stalled native Windows shutdown. That implementation and its helper
were removed. Only CPU-image effect work is shipped. Do not reintroduce native
frame conversion workers based solely on synthetic/offscreen tests.

## Measured evidence and limits

Baseline: `build/lagtest-marquee-diagnosis/report.json`.
New comparable no-waveform run: `build/lagtest-overlay-cpu-effects/report.json`.
Selection repaints during playback: **19.21 → 82.49/sec**; mean preview painting:
**22.40 → 2.22ms**. New native run with real waveform content:
`build/lagtest-final-waveforms/report.json`: 78.11 selection repaints/sec,
2.09ms preview paint, 0.71ms timeline paint. In 3.99 seconds it published 149 video
frames and the audio decoder advanced 4010ms. Live video was not disabled for
these reported playback figures. Diagnostic ablations are labelled separately.

This is not guaranteed 144Hz interaction or 60fps delivery. Native frame-to-image
readback/conversion remains a measured UI bottleneck (~9ms per actual conversion
in the waveform run). A GPU-resident compositor requires a separately tested
renderer/texture-lifetime design, not a fake GPU checkbox or unsafe thread move.
Qt's decode backend may use hardware, but the current QPainter/Pillow effects are
not a GPU-resident effects graph. Export-quality changes were not used to obtain
these improvements. Waveform generation itself is completed before measurement.

Project SHA256 is unchanged:
`281bf55853651db33bdfbe3be7b53a9a9d8ef608b6ba3d63e45a8e9b46c3285c`.
The task ledger records source, regression, package and installed milestones
separately. Always rerun native tests after scheduling changes.

Release verification: 446 tests / 43 modules passed. Frozen native LagTest run
(`build/responsive-package-timeline/report.json`) passed with 68.91 selection
paints/sec, 1.91ms preview paint, 131 video frames/4.02s and 4054ms audio progress.
Installed startup and all four cut-boundary cases passed. Installed bundle:
`dist/KineticCut/`; full previous bundle: `build/responsive-before-install-20260921/`.
EXE SHA256: `005B798C3B9C4D5DBA0B216BF70FE759897B0A9F1893D2D75F761B3C5043DE68`.
