# Kinetic Cut — risk-based testing policy

Effective 26 September 2026. Applies to every coding agent. This replaces older
blanket instructions to run the complete suite after **every** change. It does
not weaken saved-project safety, package verification, or honest reporting.

## 1. Decision rule

Run tests for the behavior changed and its affected neighbors, not every feature
in the editor just because a new EXE is requested. Assess the actual changed
functions, shared callers, signals and data, not only filenames. A small local
change in `ui.py` or `workspace.py` does not automatically require the full suite.

| Change risk | Required verification |
| --- | --- |
| Documentation only; no runtime/build/dependency changes | Check instructions, paths and examples. No application tests, build or installation. |
| Isolated wording, icon, layout or local style | Affected UI module tests; inspect the changed control/dialog at ordinary and small sizes. For themed UI inspect all three themes. No full suite unless shared behavior is changed. |
| Isolated feature/bug fix | Reproduce the report; run the relevant modules below plus affected neighboring behavior. Add/extend behavioral coverage when existing tests do not cover the failure. Run a relevant real-media/native check if applicable. |
| Shared/high-risk change | Focused tests first, then the complete isolated module suite and affected integration/native checks. See mandatory full-suite triggers below. |
| New executable | The applicable source checks above, staged packaged startup and affected packaged workflow checks; installed startup after safe replacement. An EXE build alone does **not** trigger the complete suite. |

Before editing, record the chosen scope and why in `ACTIVE_TASKS.md` or the task's
working notes. Select the union when a change touches several areas. Do not omit
a relevant expensive test to meet a time target. If impact cannot be bounded,
use the full suite. Existing unaffected tests remain available for full checkpoints.

## 2. When the full suite MUST run

- Changes to generic project/media/timeline serialization, legacy loading,
  shared source-time mapping, IDs/links/track semantics, or common edit operations.
- Changes to shared undo/redo snapshot creation/restoration, project replacement,
  autosave/recovery publication, or common mutation/locking/transaction guards.
- Changes to the transport clock, seek/cut state machine, decoder sharing or
  teardown, native frame ownership, shared worker scheduling/lifecycle, or
  shutdown. Real/native checks are also required; unit passes cannot prove these.
- Changes to the common preview/compositor or export graph/batching/publication
  pipeline. An isolated effect implementation with bounded callers can instead
  use its focused tests and preview/export parity check.
- Global theme application, icon engine or broadly applied Qt stylesheet changes;
  common controls whose interaction changes affect multiple inspectors/dialogs.
  Local styling that does not change these systems can use focused checks.
- Dependency/runtime updates, Python/Qt/FFmpeg changes, PyInstaller/runtime hooks,
  build configuration or bundled dependency changes.
- Broad refactors, changes spanning unrelated feature areas, an unknown impact
  boundary, or a focused failure revealing an unexpected cross-feature effect.
- A milestone release containing multiple features; or before the **fifth
  code-bearing installation** since the last complete passing suite. Documentation
  changes and repeated builds of identical already-tested code do not count.
  Record the checkpoint count in the ledger; reset only after a complete pass.

Run the full suite once on the final code state, not after every intermediate
edit. During iteration rerun affected modules. If code changes after the full
pass, rerun the changed scope; repeat the full suite if the new change meets a
trigger above. A subsequent full checkpoint must include all accumulated changes.

## 3. Required coverage map for focused changes

Names below are actual files under `tests/`. Run the modules relevant to the
specific behavior; conditional additions are mandatory when their stated path
is touched. Inspect test bodies: historical catch-all modules contain unrelated
features, and names alone are not a dependency map. Full-suite triggers override
this focused map.

| Area changed | Required focused modules / conditional additions |
| --- | --- |
| Media splitting, trimming, retiming, links, locks, overwrite or batch edits | `test_core.py`, `test_nle.py`, `test_timeline_editing.py`, `test_batch_edit_safety.py`, `test_history_safety.py`. Add `test_new_edit_actions.py` for gap removal, silence/censor and audio edit actions; `test_editor_refinements.py` for clipboard/copy-paste; `test_keyframes.py` for animated cuts. Generic implementation changes require full suite. |
| Timeline drag, scroll, marquee, snapping, mixed selections | `test_timeline_gestures.py`, `test_selection_scroll.py`, `test_mixed_subtitle_move.py`. Add `test_gta_regressions.py` for blade/wheel/locks, `test_pool_monitor_polish.py` for sticky snaps/fade corners/playhead-preserving cuts, `test_ui_followup.py` for additive selection/drop behavior, `test_sept8_workflow.py` for Alt ghosts/provisional lanes. |
| Timeline painting, overlay-only damage, playhead appearance | `test_layered_playback.py`, `test_playback_scheduling.py`; `test_playhead_handle.py` for scrubber geometry. Add gesture/selection suites if hit testing or selection changes. A purely isolated silhouette change can use `test_playhead_handle.py` and its visual/drag check alone. |
| Preview/playback/seek/proxy behavior | `test_layered_playback.py`, `test_playback_scheduling.py`, `test_preview_seek_gate.py`, `test_caption_focus.py`. Add `test_preview_bins_drag.py` and `test_batch_edit_safety.py` for frame timer/decoder retirement; `test_av1_preview.py` for codec/proxy behavior; `test_worker_lifecycle.py` for jobs. Shared transport/lifecycle changes require full suite. |
| Download Media | `test_downloader_dialog.py`; add `test_av1_preview.py` for codec preference/preparation, `test_missing_media.py` for source availability/path changes, and `test_worker_lifecycle.py` for generic background-job changes. Add `test_assistant.py` only if the MCP download entry point changes. |
| Media Pool / Power Bins / import and external drops | `test_bins_timeline_caption.py`, `test_preview_bins_drag.py`, `test_pool_monitor_polish.py`; add `test_nle.py` for bin persistence, `test_new_edit_actions.py` for async Explorer drops, `test_sept8_workflow.py` for batch selection/attributes, `test_missing_media.py` for remove/relink/offline behavior. |
| Missing media / replacement / source-folder relink | `test_missing_media.py`, `test_history_safety.py`; add `test_compounds_performance.py`, `test_compound_waveforms.py`, `test_av1_preview.py` and `test_vision_and_render.py` when nested sources or their caches/analysis are affected. |
| Captions: editing, timing, style, inspector, focus | `test_subtitle_editing.py`, `test_caption_styles.py`, `test_bins_timeline_caption.py`; add `test_caption_focus.py` for focused playback/navigation, `test_mixed_subtitle_move.py` for mixed dragging, `test_history_safety.py` for text batching/undo, `test_sept8_workflow.py` for emoji/attributes. Shared timing/serialization changes require full suite. |
| Inspector transform/crop/fit/attribute controls | `test_ui_followup.py`, `test_viewer_width_fit.py`; add `test_current_followup.py` for alignment/blur/default sliders, `test_editor_refinements.py` for scrub gestures/clipboard, `test_professional_polish.py` for color dialogs/enablement/guards, `test_sept8_workflow.py` for attribute type safety. Run only relevant families, not all four catch-all modules automatically. |
| Keyframes / procedural VFX / transitions | `test_keyframes.py`, `test_visual_fx.py`, or `test_transitions.py` respectively. Run both keyframes and VFX if curves/baking are shared. Add relevant timeline/inspector suites if their interaction changes. Shared transform sampling/composition/export changes require full suite. |
| Face customization / AR / vision | `test_custom_face.py`, `test_vision_and_render.py`; `test_face_filter_categories.py` when the catalogue/grouping changes. A catalogue-only change need not run pixel-morph tests. Add history/worker/preview suites when those paths change. |
| Graphics, titles, emoji, text drawing | `test_graphics.py`, `test_title_delivery.py`, `test_caption_styles.py` as relevant; `test_sept8_workflow.py` for emoji/editor operations, `test_editor_refinements.py` for headline geometry/output resizing. Shared text render changes require all consumers and may trigger full suite. |
| Waveforms, audio meters, gain/fades/mute, processed audio | `test_waveforms.py`, `test_audio_project_safety.py`, `test_pool_monitor_polish.py` as relevant; `test_compound_waveforms.py` for mixed/child waveform jobs, `test_nle.py` for exported audio settings, `test_new_edit_actions.py` / `test_current_followup.py` for separation/replacement/actions. |
| Compounds / nested navigation and render caches | `test_compounds_performance.py`, `test_compound_waveforms.py`, `test_history_safety.py`, `test_missing_media.py`; add audio/export/vision suites for affected child content. Generic nesting/model or root-save changes require full suite. |
| Themes and local themed UI | `test_theme_contrast.py` plus the changed UI's suite. Catalogue/chooser/global theme changes also require `test_ui_themes.py`, `test_theme_and_ui.py`, `test_layered_playback.py` and full suite. Inspect all three themes; don't recolor media/caption pixels. |
| Phone page / transfer / mirror | `test_phone_connect.py`, `test_phone_backends.py`; add theme tests for appearance, `test_worker_lifecycle.py` for shared jobs. Simulated-device tests are not proof of a hardware transfer. Shared process policy changes require full suite. |
| Recovery / project versions / collection / save/load | `test_crash_recovery_and_tts.py`, `test_audio_project_safety.py`, `test_core.py`, `test_history_safety.py`; `test_current_followup.py` for project discovery/deletion. Common persistence/recovery changes require full suite. |
| TTS / dialogue generation | `test_crash_recovery_and_tts.py`; add `test_new_edit_actions.py`, `test_history_safety.py`, `test_assistant.py` if timeline insertion/undo/MCP changes. Do not download models or call paid services just for a unit test. |
| Caches / resource retention / cancellation | `test_image_cache.py`, `test_cache_manager.py`, `test_worker_lifecycle.py`, `test_history_safety.py` according to the changed cache/owner; add owning feature suite such as AV1, vision, compounds or waveforms. Shared lifecycle changes require full suite. |
| Export/queue/Deliver | `test_title_delivery.py`, `test_vision_and_render.py`, `test_gta_regressions.py`, `test_current_followup.py`, `test_nle.py` as relevant; effect-specific suites for affected graphs. Shared export pipeline changes require full suite and real output verification. |
| MCP / auth / tool schema / commands | `test_assistant.py` plus the feature suites for commands changed. Do not run MCP networking tests for unrelated cosmetic changes. |
| Search/timecode copy/effect-category preference | `test_small_controls.py` or `test_effects_category_persistence.py` respectively, plus affected UI/theme checks. These isolated preferences must not dirty edit history. |

When new modules/features are added, extend this map. Never freeze the required
suite to a historical test count: it is evidence, not a target to preserve.

`test_oct3_editing.py` covers exact move-release adjacency across media types and
captions, same-lane snap priority, contextual track insertion/undo, compact attribute
groups/session memory, linked zoom ratios, numeric type-to-drag and live linked blur.
Use it with affected timeline/inspector/attribute neighbors for those paths.
`--editing-selftest <output> [project]` exercises native Qt interactions and captures
the affected dialog in all three themes at ordinary/compact sizes. An optional
project is loaded into disposable copies, decoded and hash-checked without saving.

`test_native_editing_followup.py` covers real spin-box keyboard targets, all eight
graphic resize/rotate/move paths, independent side grips/inspector/reset, export
transform tags and Windows shared-handle replacement/seek/rename/delete behavior.
`--editing-followup-selftest <output>` adds native focused-widget input, three-theme
graphic handles, live video/audio/source-preview removal and decoded export bounds.
It generates disposable fixtures under output; on Windows it deliberately recycles
only its own generated playing-recycle.mp4 to verify the Explorer deletion path.

## 4. Integration, visual and performance checks

`test_caption_emojis.py` covers sparse semantic selection, contextual single-word
cards, repeat suppression, cache invalidation, selected-word preview/export timing
and the full ASS exporter route for both emoji animations with arbitrary fonts.
Use caption/style/emoji neighbors for selection changes. `--caption-emoji-selftest
<output> <project> [--regenerate]` uses a disposable project copy, three native
themes and decoded FFmpeg exports. Regeneration requires an existing local base.en
model and clears only the disposable subtitle lane; it never downloads a model.

`test_caption_followup.py` covers static single-word emphasis through speech hold,
multiword karaoke for 2–12 words, full-block emoji centering, normalized glyph
geometry across viewer scales and native spinner/theme interaction. Shared caption
geometry changes require a complete checkpoint. `--caption-followup-selftest
<output> <project>` verifies the actual Komika font and fixture, 1–12 word cards
at 180/360/1080 preview widths, setup dialogs/spin arrows in all themes and decoded
export colours for initial/held text. The source fixture is hash-checked unchanged.

Use the smallest diagnostic that covers the real path, with an isolated home and
disposable output. Read its implementation/fixture requirements before execution.

| Changed path | Appropriate additional evidence |
| --- | --- |
| Decoder/cuts/audio handoff | `--cut-selftest`; real reported codec/source when relevant; compare cold and cached paths. |
| Playback/timeline responsiveness | `--playback-selftest <output> <media>` and/or `--timeline-selftest <output> <project>`; native timing on the affected composition. Do not benchmark concurrently with builds/full tests. |
| AV1 preparation | `scripts/av1_timeline_check.py <media>` with a fresh isolated home, then cached reuse; original source unchanged and original audio retained. |
| Captions, focus, keyframes, pool, compounds, missing media | Matching `--subtitle-selftest`, `--focus-selftest`, `--keyframe-selftest`, `--pool-selftest`, `--compound-selftest`, `--missing-selftest`. Run only the affected workflow(s). |
| Global themes | `--theme-selftest` matrix, inspect affected images and unchanged content pixels. Local dialog/style fixes: three-theme focused visual check; do not regenerate all 61 matrix images automatically. |
| Waveforms | `--waveform-selftest`, including source-time/zoom mapping when changed. |
| Phone protocols | `--phone-selftest` plus actual-device transfer/mirror checks when available; state unverified hardware clearly. |
| MCP | `--assistant-selftest` when tools/wiring/auth are affected. |
| Export/effect pixels | Short real export with representative effects/times and boundaries. Probe streams/duration, decode the result, inspect frames and compare preview/export. A full user project render is needed for a project-specific stall or when a short fixture cannot exercise the cause, not every slider/layout update. |

Do not change saved user projects/media or normal settings during verification.
Do not treat a mock pass, static screenshot or startup check as proof of actual
playback, transfer, smoothness or correct exported pixels.

## 5. Commands and isolation

Focused modules can use the existing Qt-cleanup runner. No new runner is required.
Run each module in its own process/home so theme/windows/worker state cannot leak.
Example selection for an isolated downloader/AV1 fix (expand for actual scope):

```powershell
$testOutput = Join-Path $PWD 'build/my-task-focused'
$previousTestHome = $env:KINETIC_CUT_HOME
try {
    foreach ($module in @('test_downloader_dialog.py', 'test_av1_preview.py')) {
        $moduleName = [IO.Path]::GetFileNameWithoutExtension($module)
        $env:KINETIC_CUT_HOME = Join-Path $testOutput $moduleName
        & .\.venv\Scripts\python.exe scripts\unit_tests.py $module
        $testExit = $LASTEXITCODE
        if ($testExit -ne 0) { throw "$module failed with exit $testExit" }
    }
} finally {
    $env:KINETIC_CUT_HOME = $previousTestHome
}
```

Complete checkpoint:

```powershell
.\.venv\Scripts\python.exe scripts\test_modules.py --output build/my-task-full
# Preserve/check $LASTEXITCODE immediately; read report.json and failing logs.
```

Use `--retry-failed` only after investigating the failure. Keep the prior attempt
and explanation. Do not rerun until a flaky result disappears, weaken assertions,
raise timeouts, or report “OK” if Qt teardown crashes afterward. Avoid the legacy
monolithic all-tests invocation: isolated modules prevent accumulated Qt cleanup
stalls. Keep two-worker concurrency unless separately measured and verified.

## 6. Build/install gates still required

For every requested runtime release: stage with `build.ps1`, run packaged startup
and the affected workflow(s), confirm closure freshly, preserve rollback, install
non-destructively, compare EXE hashes, and run installed startup. Check new assets
and dependencies when present. Quote paths containing spaces in `Start-Process`
arguments; a malformed selftest command can open the normal editor instead.

Do not rebuild for this policy/documentation change. Source tests, staged build,
packaged workflow and installed verification are separate claims in the ledger.
For a focused release report the modules/count actually run and explicitly say
“focused checks; full suite not run (policy: isolated change).” Keep the latest
full-suite baseline and code-bearing install count visible for checkpoint selection.

## 7. Redundancy review and current evidence

Reviewed 26 September: 53 modules / 503 methods. An AST comparison of test bodies
(ignoring source locations and method names) found **no exactly repeated bodies**.
This is not proof that every assertion is unique, nor a reason to delete fixtures.
Theme modules have some overlapping palette/style assertions, but the structure,
real MainWindow application and contrast/live-icon tests serve different layers.
CurrentModel/Core/NLE/UI checks similarly protect different entry points and edges.

The latest full report `build/av1-faster-regression/report.json` passed 503 tests;
its module durations total 437.72 process-seconds, with two concurrent workers.
That sum is **not wall-clock elapsed time** and includes imports, Qt setup and
teardown. The largest modules were professional polish (37.53s), subtitle editing
(31.92s), pool/preview drag (25.53s), MCP (24.66s) and VFX (24.23s). These historical
times are not future guarantees. Packaging and real-media checks cost time too.

No test was deleted or disabled by this policy. Delete/merge a test only after
demonstrating identical fixtures, entry points and failure coverage in a retained
test; preserve its regression rationale. Candidate future improvements are
topic-based splitting of catch-all modules and measured fixture setup/cleanup
optimization—not removing teardown, async safety, native checks or assertions.
Those changes are separate tasks and must not be bundled into unrelated updates.
