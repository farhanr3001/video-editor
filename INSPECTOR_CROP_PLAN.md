# Crop, Inspector and caption follow-up

- [x] Restore Crop near the front of the timeline toolbar and bind `C`.
- [x] Decode the selected clip's raw source frame at the playhead. The modal Crop
  canvas supports new rectangle drawing, in-box movement, eight-handle resizing,
  wheel zoom, middle-button pan, Fit, reset, dimmed exclusion and live dimensions.
- [x] Show every clip-attached effect in Effects, including no-parameter effects;
  add an icon-only bin action and restore changed state on removal.
- [x] Make Inspector number fields single-drag scrub controls, double-click keyboard
  editors, and route wheel events from numbers, lists and sliders to panel scrolling.
- [x] Snap both leading and trailing selection edges to the playhead, zero and all
  other clip boundaries, with magnetic snapping on by default and a visible guide.
- [x] Add an on-canvas anchor/pivot and use it for transform rotation/scale geometry.
- [x] Add per-clip Colours with Neutral, HD Pop, Cinematic and B&W presets plus
  brightness, contrast, saturation, sharpen and grayscale preview/export support.
- [x] Add pre-generation auto-caption styling and determinate extraction/model/
  transcription progress. Select and reveal the first generated caption on ST1.
- [x] Verify caption typography, colour picker, alignment, position, shadow,
  background settings, visible viewer text and actual offline tiny.en transcription.
- [x] Native crop/Inspector/effect/colour/snap/anchor test, 35 unit tests, prior UI
  regression, composite-mode renders, caption render and real colour render passed.
- [x] Rebuild and launch-check the packaged Windows application.

Constant clip colour controls are implemented; this does not add a node graph,
secondary colour keys, colour-managed grading, tracking or variable keyframes.
