# Active task ledger

## In progress — distribution and GitHub updates

Owner requests cleanup before all other work, preservation/exclusion of personal
Power Bin and editing-session assets, installer with optional component selections,
Windows uninstall cleanup, startup/manual update checking and source publication to
farhanr3001/video-editor. See DISTRIBUTION.md for the implementation plan.
Verification: complete isolated modules due to build/dependency changes, affected
native three-theme checks, staged/installed captions/export and isolated installer
install/upgrade/uninstall including later downloads and Power Bin survival.

- Cleanup finished first: 58 authorized paths removed, 39,573,649,284 logical bytes
  reclaimed. Current dist, current caption-followup-stage and verified rollback
  remain. All Power Bin/session assets and .kcut projects preserved. Existing
  historical report paths remain, but the superseded application bundles referred
  to by older ledger entries were deliberately removed under owner instruction.
- AGENTS.md records one staged bundle/one verified rollback retention. .gitignore
  excludes private projects/media/assets/settings and non-redistributable private
  font binaries; local assets remain available to this owner's editor.
- Final full source checkpoint: 554 tests / 58 isolated modules passed, including
  version-specific dismissal and narrow effect-download rows. Final local layout
  rerun passed 12 distribution tests + 1 face-browser neighbor; all three native
  themes inspected. Public sanitized caption fixture fallback passed separately.
- Final staged startup and native captions/export passed under
  build/distribution-final-staged-{startup,captions}. Offline standard base.en
  transcription passed with an empty HF cache (8 captions; no model download).
- Real installer integration passed: build/installer-verification/report.json.
  Preselected Android installed; iPhone/vision/vocals added afterward; both isolated
  Python runtimes imported successfully. Upgrade preserved Power Bin/settings.
  Actual Windows uninstall removed app registration/program/components/settings,
  while preserving Power Bin metadata, its source and an external project.
- Final installer: release/KineticCut-Setup-1.1.0.exe, 341,770,188 bytes; standard
  app files 803,873,789 bytes. Optional installed total 1,688,945,373 bytes.
  Final EXE SHA256 0523F020B5EC4DE176D548A0A3944299AC7709FCCBF4453CA525B4862E3D4AC5.
  Owner install verified at dist/KineticCut; Windows Apps registration uses the
  existing location. build/distribution-owner-install/report.json confirms original
  Power Bin, settings and caption project SHA256 unchanged. All four optional tools
  are available for this owner's existing workflow. Retired 318 obsolete packaged
  runtime files / 516,116,915 bytes after preserving all media/Power Bin references.
- Post-cleanup installed startup, caption geometry/export and offline transcription
  passed under build/distribution-final-installed-{startup,captions,asr}. Retained
  rollback build/release-backups/KineticCut-before-distribution-20261003 passed
  startup; older rollback and caption stage can now be removed. Current complete
  checkpoint 554/58; code-bearing installations since full checkpoint: **1**.
- Source scan: 687 proposed repository files / 62.4 MB; no >30 MiB file and no
  credential-pattern hits. Private user projects/media/fonts/settings excluded.
  Source/release publication remains the final gate.

Progress before the owner's explicit resumption:
- Implemented asynchronous version-specific startup/manual GitHub checks, verified
  installer download, optional pack manager, confirmation/progress/cancellation,
  effect download controls, blurred phone overlay, selectable Cache Manager pack
  removal and app-owned uninstall cleanup preserving Power Bin and sources.
- Complete isolated regression checkpoint passes 553 tests / 58 modules after
  investigation: legacy menu expectation updated for the requested entries; old
  first-use decline test updated to the new confirmation; bundled FFmpeg preference
  restricted to frozen apps so the source Chocolatey resolver stays correct. A
  subsequently added dismissed-version UI test has not run yet. Caption fixture
  fallback rechecked separately (8 tests); sanitized public fixture has no media.
- Native source captures cover all three themes; frozen staged startup and caption
  geometry/export checks passed before the final standard-model diagnostic rebuild.
- Prepared exact packs: Android 26,243,358 installed / 11,304,984 downloaded bytes;
  iPhone 266,853,236 / 110,856,799; vision 297,244,627 / 109,377,026;
  vocals 1,098,604,152 / 296,922,528. Excluding regenerable bytecode saves space.
- Inno compiler signature verified and installed only under build/tools. Installer
  compilation succeeded (about 342 MB installer / 803 MB core). This is an interim
  installer: the latest rebuilt diagnostic entry point still needs recompilation
  into it, and real install/upgrade/uninstall/offline ASR gates remain outstanding.
- Initialized a separate project Git repository (parent profile repository is not
  used), verified public destination/push permissions and scanned proposed source
  for credential patterns (none found). No commit/push/release has been published.
- Mandatory pause: THIRD_PARTY_NOTICES.md explicitly says AR Pixel Glasses source
  and redistribution terms are not established and forbids public distribution
  of its model/derived views without checking. GLB has generator/version only;
  there is no license or original source link in its directory. Added a protective
  Git exclusion. Need owner to provide the original source/license or establish
  authorship/redistribution permission, then explicitly say continue. All remaining
  tasks are paused per the owner's instruction; no app replacement/install occurred.

Resumed 3 October: the owner explicitly instructed continuing for personal use
and device transfer without further licensing questions. Retain available notices
and document unknown provenance; include existing AR assets and caption fonts so
the personal-transfer package preserves features/appearance. Personal font binaries
remain outside source history. The earlier pause/status is historical only.
Final installer/offline captions/upgrade/uninstall/publication checks are underway.

## Installed and verified — caption emphasis, centered emoji and zoom/theme consistency

Latest report supersedes prior assumptions: single-word cards must keep one colour
for their complete duration with sparse meaningful emphasis; multiword karaoke
remains timed. Center auto emojis over the complete caption; retain Headphones
despite nearby Coffee. Normalize Komika word geometry across viewer scales and
fix local Auto Caption Style spin arrows/tabs in all three themes.
Verification scope: focused behavioral tests then complete isolated suite because
canonical caption geometry is shared; native actual fixture at reported frames,
1–12 word cards/zoom scales, preview/export pixels, three-theme setup/spin interaction,
staged and installed gates. At task start the full baseline was 525/55 with 1
installation since it; the completed checkpoint and current count are below.
Preserve original projects/media/settings; use disposable copies.

- Single-word Karaoke/Emoji/Double Emoji cards use sparse static emphasis for the
  whole visible duration, including speech hold. Ordinary `happened` remains white;
  semantic/manual emphasis remains highlighted. Multiword karaoke retains speech
  timings. Preview and ASS use the same choice; single-word pops use card duration.
- Auto emojis center above the complete text block, including wrapped captions,
  with a stationary center through exported pop scaling. Distinct meaningful
  emojis can appear 0.8s apart (repeat limit remains 8s); Headphones now receives 🎧
  despite the nearby Coffee. The selector still excludes filler/random pops.
- Canonical output-coordinate caption glyphs/word advances and wrapping scale as
  paths for viewer zoom; no separate small-font hinting changes Komika spacing.
- Local Auto Caption Style spin arrows use themed assets; native up/down clicks
  work in all three themes. Caption Setup/Choose Template tabs use palette roles,
  including selected-text contrast in gray. Setup/card previews respect word count
  and fit the complete text/emoji group without changing the saved style.
- New test_caption_followup.py passed 8 tests: 1–12 word cards, every active word
  for 2–12 word karaoke, full hold colors, manual/sparse emphasis, real fixture
  Headphones/Happened, full-block preview/ASS emoji centering, canonical path/wrap
  invariants at 0.1/0.17/0.25/0.5/1/2 scales, preview fitting and theme/spin clicks.
- Complete checkpoint build/caption-followup-checkpoint/report.json passes
  **542 tests / 57 isolated modules**. Preserve attempts: sandboxed full run had a
  WinError 5 renaming its own AppData Temp collected folder; permitted full final
  run passed that test but hit WinError 5 replacing its own Temp power-bin JSON.
  Investigated unrelated fixture-only filesystem paths; unchanged pool module
  passed all 8 tests with Temp isolated under the workspace. The checkpoint retains
  the earlier report and rerun log. Final local dialog/style/contrast refinement
  rechecked 8+14+9 tests. No tests disabled or timeouts raised. Baseline resets to
  542/57; code-bearing installs since checkpoint: **1**, this release.
- Native source final report build/caption-followup-native-source-contrast-final/
  report.json passed with actual Komika Axis. Inspected setup at 500/480px in all
  themes and representative 1/2/3/6/12-word captions. Canonical native glyph checks
  cover 1–12 words at 180/360/1080 widths. Happened rasters are identical at onset,
  after spoken end and late hold. Decoded real fixture export: Happened white
  3663/3588 pixels, yellow 0/0 both early and held; Headphones yellow 4630/4503.
- Final build build/caption-followup-build-final.log passed. Staged startup and
  frozen native reports build/caption-followup-staged-startup/report.json and
  build/caption-followup-staged-native/report.json passed. Installed startup and
  frozen native reports build/caption-followup-installed-startup/report.json,
  build/caption-followup-installed-native/report.json and the additional native
  capture build/caption-followup-installed-native-render/report.json passed.
  Source theme preview pixels and packaged controls were inspected; occasional
  packaged widget-grab frames omit preview lettering and are not pixel proof.
  Actual packaged QPainter and decoded export color checks are recorded separately.
- First installation was interrupted by full disk, leaving a partial rollback
  and incomplete destination. Freed only redundant generated build/emoji-stage
  and build/oct3-followup-stage bundles; retained every report and rollback copy.
  Owner also freed disk space. Completed rollback's missing unchanged dependencies
  from the retained pre-Emoji bundle (kept previous EXE hash 917F9F...). Rollback
  startup verified. Final non-destructive copy and fresh closure checks passed.
  Rollback: build/release-backups/KineticCut-before-caption-followup-20261003,
  7336 files / 995852228 bytes. Installed dist/KineticCut/KineticCut.exe matches
  staged SHA256 `3FD911402C1811B21612372E5D6022BEA28717C12F2C4C51F197245A2E5EE787`.
  Original caption_testing.kcut remains hash
  `69191AEE16509DE62AB65BB376BE51B1A3C7FF147A8E6974483B403E40F9DC1B`.

## Installed and verified — selective Emoji caption template (3 October 2026)

Owner authorizes caption_testing.kcut as an editable fixture, including clearing
and regenerating its subtitle lane. The fixture has 180 single-word captions over
~59 seconds. Preserve typography/placement/animation; fix selection and timing.
Remove random fallback/prefix matching, use surrounding speech and sparse emphasis,
and make preview/export show emojis only on chosen words.
Verification scope: isolated effect with bounded preview/export callers; new
semantic/timing tests plus caption-style/subtitle/emoji neighbors, real fixture
selection/preview/decoded export and staged/installed checks. Full suite not required
by TESTING_POLICY.md unless scope expands. Last full baseline: 525 tests/55 modules;
code-bearing installs since full pass: **1**, including this release. Preserve unrelated projects/media/settings.

- Source: exact semantic keywords replace bidirectional prefix matching and hashed
  random fallback; surrounding speech, salience, manual emphasis and repetition
  determine sparse pops. Filler and unknown words stay plain. Selected emoji words
  share an ephemeral transcript plan in preview/export, with actual word timing.
- Real fixture: subtitle lane cleared/regenerated with the existing local base.en
  engine: 180 captions, 15 selected pops; global style identical. Evidence:
  build/emoji-native-source-permitted/report.json (regeneration succeeded; first
  export check failed), then build/emoji-native-source-capture-final/report.json
  (native three-theme and decoded export passed). Original caption_testing.kcut
  unchanged; regenerated review copy at caption_testing_emoji_review.kcut.
- Decoded export caught an existing font-dependent dispatch omission: Emoji/Double
  Emoji with Komika Axis skipped word events. Both animations now explicitly use
  the existing word-event renderer for any font; new full-export regression guards
  this. First sandboxed ASR attempt could not read normal AppData TTS media; a
  permitted read-only fixture run completed regeneration without downloading.
- Final focused source report build/emoji-regression-release/report.json passed
  **77 tests / 6 isolated modules**, clean exits: new caption emojis (9), caption
  styles (14), subtitle editing (16), bins/timeline captions (12), Sept8 emoji and
  attributes (17), title/delivery (9). No tests disabled. Focused checks; full suite
  not run (policy: isolated change). Latest complete baseline remains 525/55.
- Three-theme captures were tightened to wait for the selected caption to appear
  at its word midpoint before capture (earlier screenshots raced queued seeks).
  Inspected native Default/Final Cut Obsidian/Ableton Gray: unchanged Komika
  typography, no emoji for Okay, coffee pop for Coffee. Direct QPainter/FFmpeg
  decoded presence: filler 0/0 bright pixels; coffee 7592/5130 above the text.
- Final build passed: build/emoji-build-final.log. Staged startup report
  build/emoji-staged-startup/report.json and frozen native effect report
  build/emoji-staged-native/report.json passed. Installed startup report
  build/emoji-installed-startup/report.json and frozen native effect report
  build/emoji-installed-native/report.json passed, clean exits. Packaged QPainter
  and decoded FFmpeg presence matched (Okay 0/0, coffee 7592/5130 pixels).
  Native source three-theme captures were inspected. Two nondefault packaged
  widget grab files omit the caption despite the caption-rectangle assertion;
  these files are not used as pixel evidence. Actual packaged caption drawing
  and decoded export images, plus source native theme captures, provide it.
- Installed after fresh closure checks, with the complete previous 7336-file
  bundle preserved in build/release-backups/KineticCut-before-emoji-20261003.
  Staged/installed EXE SHA256 matches:
  `917F9FBCE37AD2BAC222708BD06E17DB6F059B885ED04E9751230897290742F1`.
  Installed executable: dist/KineticCut/KineticCut.exe. Original fixture SHA256
  remains `69191AEE16509DE62AB65BB376BE51B1A3C7FF147A8E6974483B403E40F9DC1B`.

## Installed and verified — native numeric input, deletable media and graphic transforms (3 October 2026)

- [x] Reproduce inspector typing/Enter on the actual native spin-box input target;
  exit focus/selection and retain horizontal scrubbing after repeated edits.
- [x] Permit Windows Explorer recycle/rename of media while timeline/source players
  are open; existing missing-media handling must invalidate deleted sources.
- [x] Use full resize/rotation/move controls for all eight graphic catalog items,
  synchronized with inspector transform properties and edit history.
- Verification: focused controls/graphics/missing/pool/playback tests, full isolated
  suite (shared controls and decoder I/O), native live-file removal, three-theme
  graphic/input checks, staged and installed release gates. Preserve all user data.

- Numeric root cause: native spin-box Enter was outside the prior line-edit-only
  filter. Both targets and Return/keypad Enter now finish, blur/deselect and retain
  scrub mode. Tests target the focused native widget and repeat typing then drag.
- Media: media_source.py adopts read-only Windows READ/WRITE/DELETE-shared handles
  in seekable QFile inputs, owned by the player until native decoder retirement.
  Covers timeline video/audio, main source preview, source dialogs and TTS players.
  Missing monitoring also clears removed sources in main/source-preview players.
- Graphics: replace green move-only rectangles with media resize/rotate/move/anchor
  handles. Closest-grip hit testing fixes thin-shape side/rotation hit overlap.
  Scale X and Scale Y are shown and reset independently; uniform corners preserve
  proportions, side grips preserve the other axis. Existing render/data properties
  stay intact. ASS exports honor scale/clockwise rotation/anchor, including animated
  Progress Bar export events previously absent.
- Focused new module passed **6 tests**, including all eight catalog items and
  Windows handle seek/rename/delete/replacement. Existing graphics module passed 8.
  Final complete suite build/oct3-followup-regression-final/report.json:
  **525 tests / 55 modules passed**, clean exits. Earlier 524-test pass preceded
  the side-grip refinement; retained focused failure caught that overlap and led
  to another complete checkpoint on final code. No regressions disabled.
- Native source report build/oct3-followup-native-source-final/report.json passed.
  Native final staged report build/oct3-followup-staged-native-final/report.json
  passed, frozen=true: actual focused-widget input/repeated scrubbing, all eight
  graphic types in all three themes, side grips/inspector synchronization, paused
  rename/delete and playing **real Windows Recycle Bin** operation while timeline
  video/audio, main source and source dialog players were simultaneously open.
  Existing automatic monitor marked missing and retired/cleared those sources.
  Only generated fixtures were removed. Decoded export rectangle bounds changed
  from 155x75 to 63x230 after scale X=1.6/Y=0.8 and clockwise rotation=90 degrees.
- Inspected staged graphic controls and Scale X/Y/rotation fields in Default,
  Final Cut Obsidian and Ableton Gray. Final staged build succeeded
  (build/oct3-followup-build-final.log); staged startup passed
  (build/oct3-followup-staged-startup.log).
- Final staged cut report build/oct3-followup-staged-cuts/report.json passed all
  four scenarios: no black cut/scrub samples, incoming frame decoded, prepared audio
  reused and no trimmed-out source frames; intentional gap remains visible.
- Installed non-destructively after fresh process-closure checks. Complete prior
  bundle backed up at build/release-backups/KineticCut-before-oct3-followup-20261003.
  Staged/installed EXE SHA256 matches:
  11E8C0384A81A82CC95709A0930EB40847CFB848643EBB486F939C4C24401597.
  Installed startup passed (build/oct3-followup-installed-startup.log); installed
  native report build/oct3-followup-installed-native/report.json passed, frozen=true,
  exit 0, including actual recycle/missing detection and decoded graphic export.
- Latest complete baseline: **525 tests / 55 modules** above. Code-bearing installs
  since this full checkpoint: **0**. User projects/media/settings remain untouched;
  disposable native fixtures were the only files deleted/recycled.
- Saved xqc kpop.kcut SHA256 rechecked unchanged:
  f5e8c1fec5ef2298936451b0aa16f6457467d9c8b9fdd4c126319149f5bb6fb2.

## Installed and verified — precise placement and inspector workflow fixes (3 October 2026)

User authorizes read-only video fixtures from C:/Users/F/Videos/NoPixel5 and new
test projects in this workspace. Typical xQc livestream edit: V3 webcam crop,
V2 gameplay/content crop, V1 blurred full-source background. xqc kpop.kcut may be
used for diagnostics; preserve its saved contents. MCP use is available when asked.

- [x] Preserve sticky snapping while ensuring exact neighboring boundaries across
  video/image/title/graphic, audio, captions and mixed selections.
- [x] Add a video lane immediately above the context-clicked lane; retain all
  existing clip/transition identities and track states.
- [x] Group Paste Attributes by purpose; remember successful selections per media
  category for this editor session only; Cancel must not change remembered choices.
- [x] Relink zoom axes without equalizing them; linked edits preserve proportions.
- [x] Numeric typing/Enter exits text focus and retains subsequent drag adjustment.
- [x] Linked Gaussian Blur sliders reflect both axes throughout the drag.
- [x] Focused regressions, three-theme ordinary/compact visual checks, full isolated
  module suite, real-project/native checks, staged and installed package checks.

Verification scope: full suite required by TESTING_POLICY.md because this batch
changes common inspector controls, timeline placement and track behavior. Focused
regressions ran first. Evidence and distinct release milestones:

- Source: new 12 behavioral regressions passed with clean Qt teardown; neighboring
  test_sept8_workflow.py passed 17. Complete isolated checkpoint
  build/oct3-regression-final/report.json: **519 tests / 54 modules passed**.
  Prior failures are retained in previous_attempt: synthetic release-event
  compatibility was corrected; the new clipboard fixture now clears its owned
  QMimeData before Qt shutdown. No assertion or cleanup gate was removed.
- Latest owner layout correction: **three columns**, smaller horizontal/vertical
  gaps and compact All Zoom/All Flip row. Inspected video dialogs in Default,
  Final Cut Obsidian and Ableton Gray. Native captures cover all three categories
  at ordinary 560x520 and compact 560x420 sizes, with scrolling and Apply accessible.
- Source native report build/oct3-native-final/report.json passed. Staged final
  report build/oct3-staged-native/report.json passed with final three-column UI,
  native move/release, zoom ratio/type-to-drag, live blur, track insertion/undo and
  **63 real-project boundary cases**. Decoded the three active cropped xQc layers.
  xqc kpop.kcut SHA256 remained
  f5e8c1fec5ef2298936451b0aa16f6457467d9c8b9fdd4c126319149f5bb6fb2.
- Build: build/oct3-release-stage/KineticCut succeeded; first sandboxed attempt
  could not read an external Python dependency directory, then the approved
  read-access build completed (build/oct3-build-retry.log).
- Staged package: startup passed (build/oct3-staged-startup-final.log);
  build/oct3-staged-cut/report.json passed all four cut scenarios with zero black
  cut/scrub samples. Historical startup checker expected an obsolete window-title
  subtitle and sampled the loading window; it now waits for the current exact
  editor title within a bounded deadline. Earlier failed checks are retained.
- Installed non-destructively to dist/KineticCut after fresh process-closure checks.
  Previous complete bundle preserved in
  build/release-backups/KineticCut-before-oct3-20261003. Staged/installed EXE SHA256
  matches: 580B1387796B2180149BA1A4A0BE769D588D7C3EE857C8D7D4598C4CD779C7C5.
  Installed startup passed (build/oct3-installed-startup.log); installed native
  affected workflows passed (build/oct3-installed-native/report.json), exit 0.
- Current full-suite baseline is the 519-test checkpoint above; code-bearing
  installations since this checkpoint: **0**. This supersedes the older counter
  without rewriting historical September evidence. User projects/media/settings
  preserved; diagnostics use disposable profiles/copies.

Last documented: 30 September 2026. Verify live files/processes before acting.

## Context restored after missing chat — 3 October 2026

- [x] Read the mandatory engineering context and task ledger, testing policy,
  feature documentation and historical acceptance notes; inspect the source entry
  point, project model, current caption templates and their regression coverage.
- [x] Preserve the owner's clarified purpose in AI_PROJECT_CONTEXT.md: Resolve
  inspiration, necessary features, lightweight professional feel, faster TikTok,
  Instagram and YouTube Shorts workflow, plus general video editing capability.
- [x] Read-only filesystem check found dist/KineticCut/KineticCut.exe at 15,223,718
  bytes, last modified 30 September 2026 16:27:06, consistent with the newest
  recorded caption release. This is not fresh runtime/package verification.
- [x] Confirmed the retained full-suite report build/av1-faster-regression/report.json
  records passed=true and 503 tests. It predates the September 30 source changes.
- Runtime tests/build/install not applicable: context gathering and documentation
  only. No application, user project, media or settings changes.
- Documentation discrepancy retained for future release planning: the **0**
  code-bearing-install counter below predates two September 30 release entries;
  do not rely on it without reconciling intervening builds. PHONE_CONNECT.md also
  predates later recorded iPhone WPD/AirPlay work; inspect implementation before
  asserting current phone capabilities. Historical unchecked plans are superseded
  only where later entries provide completion evidence.

## Implemented — Caption Letter Cut-out Fix, Inspector Templates Tab & Curated Templates (30 September 2026)
- [x] Fixed letter cut-out bug across zoom levels: replaced fragile boolean path clipping `path.intersected(clip)` with direct unclipped word glyph paths (`text_path(w_text, ...)`) in `kinetic_cut/visuals.py` and `kinetic_cut/word_highlight.py`. Verified with high-zoom rendering of "THIS GOLD?" showing 100% solid, unclipped letters (`screenshots/verify_this_gold_fixed.png`).
- [x] Fixed dialog live preview synchronization: selecting any template card in `CaptionStyleDialog` immediately updates the top preview's text to match the selected template's preview text (`kinetic_cut/caption_style_dialog.py`).
- [x] Added "Templates" sub-tab to Video Inspector for subtitle items:
  - Added "Templates" tab beside "Timings" under Subtitle Video tab (`kinetic_cut/properties.py`).
  - Selecting a template updates `project.subtitle_style` and applies styling across all subtitle caption items where `Customize caption` is OFF (`cap.customize == False`).
  - Subtitle items with `Customize caption` enabled (`cap.customize == True`) are strictly preserved and never overwritten.
  - Selecting "No Template" removes template properties and resets un-customized subtitle items back to default font settings.
- [x] Added "No Template" disable icon card at index 0 matching user spec: features bold red circle with 45° diagonal prohibition slash (`#DC2626`) and "No Template" label.
- [x] Deduplicated redundant templates: removed duplicate emoji pop, duplicate neon glows, and duplicate box tags. Curated down to 11 distinct, high-impact styles (`kinetic_cut/caption_templates.py`).
- [x] Replaced generic badges ("Viral", "Hot", "Clean", etc.) with descriptive purpose badges (`Emoji`, `Neon Glow`, `Karaoke`, `Box Tag`, `Punch`, `Bounce`, `Flame`, `Serif`, `Pill`, `Sport`, `Cartoon`).
- [x] Fixed card text clipping: condensed preview phrases to 1-2 words and scaled text metrics so all template cards fit with ample headroom and padding.
- [x] Added comprehensive regression tests in `tests/test_caption_styles.py` (`test_inspector_templates_tab_and_customize_isolation`). All 52 tests passed in `tests/test_caption_styles.py`, `tests/test_subtitle_editing.py`, and `tests/test_new_edit_actions.py`.
- [x] Rebuilt production distribution via `build.ps1` to `dist/KineticCut/KineticCut.exe` (Exit code 0, LastWriteTime: 30 September 2026 16:27:06, Size: 15,223,718 bytes).
- [x] Verified packaged executable:
  - Assistant selftest (`dist/KineticCut/KineticCut.exe --assistant-selftest build/verify-installed-assistant`): `frozen: true`, `passed: true`.
  - Compound selftest (`dist/KineticCut/KineticCut.exe --compound-selftest build/verify-dist-selftest`): `frozen: true`, `passed: true`.

## Implemented — CapCut Caption Templates, Two-Tab Interface & Emoji Pop Engine (30 September 2026)
- [x] Removed preset dropdown from visible UI in `CaptionStyleDialog`.
- [x] Added two-tab navigation: "Caption Setup" and "Choose Template" below play animation button.
- [x] Built `TemplateCardWidget` with CapCut styling: rounded dark cards, category badges (Viral, Hot, Neon, Clean, Modern, etc.), download arrow icon `↓`, active selection `✓` badge and cyan border.
- [x] Card hover animation: 30 FPS real-time playback of template's typography animation on hover.
- [x] Card selection: clicking a card updates top preview immediately, applies template defaults to dialog controls, and enables "Play animation preview" for that template.
- [x] CapCut "Turn text into emoji effect": contextual keyword-to-emoji mapping (`kinetic_cut/caption_emojis.py`), animated emoji popping above the active spoken word with elastic scale, combined with karaoke-style active word highlighting. Added double emoji pop support.
- [x] Added `karaoke` as an animation option in regular Caption Setup as well as templates.
- [x] 20 diverse CapCut-style caption templates added (`kinetic_cut/caption_templates.py`).
- [x] Verified through comprehensive unit tests (`tests/test_caption_styles.py`, `tests/test_new_edit_actions.py`, `tests/test_assistant.py`) and visual screenshot captures.
- [x] Rebuilt production distribution via `build.ps1` to `dist/KineticCut/KineticCut.exe` (Exit code 0, LastWriteTime: 30 September 2026 15:41:31, Size: 15,222,031 bytes).
- [x] Verified packaged executable:
  - Assistant selftest (`dist/KineticCut/KineticCut.exe --assistant-selftest build/verify-installed-assistant`): `frozen: true`, `passed: true`.
  - Compound selftest (`dist/KineticCut/KineticCut.exe --compound-selftest build/verify-dist-selftest`): `frozen: true`, `passed: true`.
  - Window launch and clean shutdown verified (`scripts/package_check.py`).

Current test selection authority: `TESTING_POLICY.md`. Latest full baseline:
`build/av1-faster-regression/report.json` (503 passed, 25 September).
Code-bearing installations with additional changes since that baseline: **0**.

## Installed — focused performance/stability and undo review (23 September)

User changed the documentation-only request to implementation. Preserve working
playback architecture, quality, editing behaviour and projects; no broad refactor.

- [x] Inspect current implementation and prior measured playback evidence.
- [x] Fix confirmed unnecessary still-image decoding and bound image-cache memory.
- [x] Review undo/redo and background-worker lifecycle; make only justified fixes.
- [x] Run targeted and full source regressions and actual decoder cut checks.
- [x] Verify native packaged playback and installed startup.
- [x] Stage, verify and install rebuilt bundle after fresh process check.

Source inspection is not proof of new runtime improvement. Record measured results
and source/staged/installed milestones separately below before completion.

The user subsequently stopped the broader audit: finish only fixes already
underway, rebuild, and briefly report remaining known concerns. No broad renderer,
history or thread architecture rewrite; no feature/quality reduction.

Implemented: full-quality still-image reuse across ordinary/transition/selection
preview paths; byte-bounded still, glow and person-mask caches with file-change
invalidation. Completed background workers now use a queued QObject receiver and
deferred signal cleanup: reproduction previously retained Worker/input payload
even after GC; regression tests verify input/callback payload release, error
delivery, pending-job ownership and GUI-thread completion. Undo restores refresh
same-ID changed Media Pool metadata and request fingerprint-checked waveforms in
the existing settled callback. Existing structural sharing, 100-state limit,
snapshot isolation and playhead preservation remain. Caption Focus no longer
primes transition video decoders; muted transition items are skipped.

Source evidence: `build/stability-regression-tests/report.json`: **459 tests / 46
modules passed**. The transition-focused extension of the six caption-focus tests
also passed (`build/stability-focus-transition-tests-retry.log`; first invocation
had a test-fixture constructor error, corrected without production changes).
`build/stability-source-cut/report.json`: all four real decoder cases pass,
including Gaussian-filtered cut, trimmed-prefix rejection and audio continuity.
The first staged packaging attempt was blocked reading a Python package directory
outside the sandbox; retry succeeded (`build/stability-build-retry.log`).

Packaged LagTest diagnostic could not proceed: its referenced source
`C:\Users\F\Videos\NoPixel5\2026-09-21 02-22-07.mp4` is missing. The source
diagnostic confirmed FileNotFoundError (`build/stability-source-timeline.log`).
No project relinking/saving was performed. Used available 1920x1080/60fps
`2026-09-21 01-09-09.mp4` with the established isolated three-layer/cuts/blur
playback fixture instead. `build/stability-package-playback/report.json`:
frozen/passed true, default/Ableton delivered 52.15/51.72 frames/sec,
mean preview paint 1.646/1.739 ms, timeline paint 0.324/0.333 ms; clip dragging
and 80 scrubs complete, settled at 4.25s with all three layers visible. Default
screenshot inspected. Different source/fixture: do NOT claim a comparable LagTest
speedup or guaranteed refresh rate. GUI maximum intervals were 78/137 ms.

Verified app closed, copied full old bundle to
`build/stability-before-install-20260923/`, then installed staged bundle into
`dist/KineticCut/` (no directory deletion). Staged/installed EXE SHA256 match:
`6BA7F7435488B2CB5446CCA6D63BD067B0450EE903EB0343D458B5F5A518C8AB`.
Installed startup passed, exit 0 (`build/stability-installed-startup/report.json`);
installed real cut diagnostic passed all four cases, exit 0
(`build/stability-installed-cut/report.json`). Application is left closed for
the user. No user project/media/settings changes; broader audit stopped as asked.

Already-known remaining concerns, deliberately NOT expanded in this pass:

- Native QVideoFrame-to-QImage conversion still occupies the GUI thread (previously
  measured around 9 ms/conversion). This remains a responsiveness ceiling; any
  replacement needs a separately validated native/GPU ownership design. Two past
  worker-conversion experiments hung shutdown: do not reintroduce them casually.
- TTS dialog close paths call QThread.quit()/wait(300–500 ms), but that does not
  itself cancel a running network synthesis call. Completion/cancel ownership
  needs focused lifecycle hardening; no real crash reproduced in this pass.
- Processed-audio preparation snapshots the clip but closes over mutable media
  path/settings after computing its cache key. A concurrent source change can
  mismatch prepared audio and key; use immutable source/settings plus generation
  validation in a future narrow fix. No live relink failure reproduced here.

## Installed — responsive timeline during playback, open-source NLE references

User now explicitly requests implementation, referencing mature open-source NLE
architectures and preserving quality/functionality. Use unchanged LagTest.kcut.

- [x] Inspect established NLE sources and map applicable scheduling/cache principles.
- [x] Separate dynamic timeline overlays from unchanged content and preserve all
  selection, scrolling, cuts, dragging, locks, undo and theme behaviour.
- [x] Safely remove measured image-processing work from input/UI scheduling;
  bounded queues, stale-result rejection, native-buffer lifetime and shutdown.
- [x] Compare exact-project input/paint/frame freshness, pixel parity, cut/audio,
  repeated play/pause/seeks, real waveform content and full regression suite.
- [x] Stage, package-test and install verified EXE after fresh closure check.

Prior diagnosis remains evidence below; it is not a completed fix. No guarantee
of GPU-only composition or zero latency for arbitrary media/effects. Record
experiments and measured results, including rejected approaches, before release.

Source evidence: `docs/PLAYBACK_PERFORMANCE.md` records inspected Shotcut,
Kdenlive and Olive sources, original implementation decisions and residual native
conversion costs. Static Gaussian/grade/chroma pixel preparation runs on bounded
detached-QImage workers; no native video frames leave their owning thread. An
owned-plane QVideoFrame conversion experiment hung shutdown and was removed,
including its `frame_buffers.py` helper. No quality setting or export change.

Native unchanged LagTest: baseline selection cadence 19.21/sec; new no-waveform
run 82.49/sec, mean preview paint 2.22ms (previously 22.40ms). Real-waveform run
`build/lagtest-final-waveforms/report.json`: 78.11 selection paints/sec, 149 video
frames/3.99s, audio advanced 4010ms, mean timeline paint 0.71ms and preview 2.09ms.
Both new runs exited cleanly; `playing.png` visually inspected. Measured, not
guaranteed 144Hz or all-effect 60fps. Native frame conversion remains on UI thread.

Regression: **446 tests / 43 modules passed**, `build/responsive-playback-tests/`.
The first run had a sandbox WinError5 replacing a temporary test Power Bin file;
approved retry passed and the aggregate report retains that first attempt.
Six new scheduling tests cover exact worker/synchronous pixels, immutable inputs,
effect invalidation, stale seek/order rejection, queue bounds and marquee reuse/
cancellation. Source cut diagnostic now also exercises asynchronous blurred clips:
`build/responsive-source-cut-filtered/report.json`, all four cases passed, no
unintended black/prefix frames, audio prepared/reused. Source focus diagnostic
passed (`build/responsive-source-focus/report.json`). Original LagTest hash matches.

Release completed 21 September 2026, 22:06 local. Staged build succeeded at
`build/responsive-playback-release/KineticCut/`. Packaged native LagTest check:
`build/responsive-package-timeline/report.json`, frozen/passed/project_unchanged
all true; 68.91 selection paints/sec, 131 delivered video frames over 4.02s,
audio advanced 4054ms, mean preview paint 1.91ms. Screenshot inspected with
all three crops and real audio waveform present. This is still not 144Hz guaranteed.

The first packaged invocation had incorrect PowerShell argument quoting and was
closed/retried with correctly quoted paths. The earlier installation attempt was
not executed because approval review hit the account usage limit. After the user
resumed, verified no KineticCut process was open, backed up the complete old bundle
to `build/responsive-before-install-20260921/`, and copied the staged bundle into
`dist/KineticCut/` without deleting other files. Source/installed EXE SHA256 match:
`005B798C3B9C4D5DBA0B216BF70FE759897B0A9F1893D2D75F761B3C5043DE68`.
Installed startup passed (exit 0, `build/responsive-installed-startup/report.json`);
installed cut checks passed all four cases including blurred clips (exit 0,
`build/responsive-installed-cut/report.json`). No user project/media/settings edits.

## Diagnosed — LagTest selection-box responsiveness during playback

Latest user asks whether timeline interaction should become sluggish during video
playback and supplies `LagTest.kcut`. This is a new, reproduced interaction problem;
the prior completed throughput improvement does not establish its resolution.

- [x] Read actual project/source and relevant selection tests; measure paused and
  playing native marquee interaction with a controlled pointer stimulus.
- [x] Isolate preview painting and frame readback costs; inspect screenshot/profile.
- [x] Preserve original project/media. Diagnostic project SHA256 before/after:
  `281bf55853651db33bdfbe3be7b53a9a9d8ef608b6ba3d63e45a8e9b46c3285c`.
- [ ] Implementation/release: not performed in this diagnostic/question turn.

Reproducer: `scripts/lagtest_marquee_diagnostic.py`, exit 0;
`build/lagtest-marquee-diagnosis/report.json` and per-case cProfile/screenshot
files. Native 1900x1032 window, original three video layers plus audio, 1920x1080
60fps recording, timeline fitted to the project, 7ms input timer. Whole-recording
waveform generation excluded; test home isolated. The sandbox initially denied
the existing thumbnail read; reran with approved filesystem access. No product
source, installed EXE, user settings or saved project was changed.

Measured selection repaint cadence: paused 71.46/sec; playing 19.21/sec; playing
with only canvas painting disabled 30.14/sec; with both canvas painting and native
frame readback disabled 70.43/sec; paused-again 78.27/sec. These ablations exist
only in the diagnostic, not as a proposed solution that hides live video.
Input callback interval mean rises from 12.47ms paused to 50.27ms playing
(p95 69.09ms, max 103.95ms). During playback average GUI costs are frame readback
11.10ms, preview paint 22.40ms, full timeline paint 13.51ms; selection bookkeeping
itself averages only 0.50ms. These are instrumented measurements, not display-Hz
guarantees or exhaustive latency bounds. Screenshot `playing.png` inspected.

Causes: native frame-to-QImage conversion and CPU preview composition occupy the
same Qt GUI thread as input/painting. Additionally, `TimelineMarquee.update`
requests a full viewport repaint and `TimelineWidget.paintEvent` explicitly
excludes any drag mode from its clock-only backing-cache path. The rectangle is
painted into that backing, so moving it redraws tracks/thumbnails/text as well.
The moving red line is not intrinsically expensive. GPU decode alone cannot
remove these GUI-thread composition costs. Next implementation should isolate
dynamic selection overlays, preserve selection/scroll/cancel invalidation, and
bound or decouple heavy preview work safely; never repeat the known unsafe native
QVideoFrame executor experiment or claim success by freezing/muting playback.

## Completed — layered playback responsiveness and darker Ableton viewer

- [x] Reproduce three same-source webcam/gameplay/blur layers with real NoPixel5
  media; measure GUI latency, preview paint time and frame delivery across themes.
- [x] Fix measured UI-thread bottlenecks without removing effects, changing
  exports, weakening seek gates or regressing timeline gestures and audio.
- [x] Darken Ableton Grey's surround outside the output preview only.
- [x] Add regression coverage, compare real playback/scrubbing and inspect images.
- [x] Run regressions; stage, verify and install EXE after a fresh closure check.

User media/projects remain read-only; diagnostics use isolated profiles/build
outputs. Theme causation is a hypothesis until profiling establishes it.

Findings/implementation so far: `build/layered-baseline/report.json` reproduces
1920x1080/60fps recording `2026-09-13 19-01-08.mp4`, three crops plus blur and audio,
with source-time jumps at cuts. Default/Ableton deliver 10.03/10.68 sampled fps;
mean preview paint 85.47/87.73ms; GUI maximum 194.37/213.18ms. Profile assigns 9.8
of 14.2 seconds to Gaussian blur; theme recolouring is not the dominant cost.
Whole-recording waveform generation is excluded from this playback-only fixture.

`widgets.py` filters moving pixel-effect layers at their displayed/HiDPI size,
restores original sampling when paused, and uses direct source-rectangle drawing
for sharp foreground crops. Background/crop caches are bounded and property-aware.
`visuals.blur_image` has an explicit motion-only large-kernel mip approximation;
blend, anisotropic radii and border mode remain, and full-quality/export paths
stay unchanged. `timeline.py` retains static pixels between clock-only updates,
rebuilds for ordinary edit/hover/scroll/theme updates, and avoids unchanged
scrollbar-layout setters during playback. Both custom surfaces paint opaquely.
Ableton `viewer_bg` is #505050; toolbar background remains lighter/readable.

Rejected experiment: moving native QVideoFrame conversion into a Python executor
caused Windows shutdown stalls in the native diagnostics. Removed that experiment
and its executor-specific tests; stopped only the identified diagnostic processes.
Keep native frame readback on the owning GUI thread and preserve existing seek
gates/shared decoders. Intermediate experimental reports are NOT release evidence.
Final native source evidence: `build/layered-final-profiled/report.json` exits 0,
passed=true. Like-for-like profiled Default/Ableton delivery is 48.31/48.02 fps
(baseline 10.03/10.68); preview paint averages 5.38/4.97ms (baseline 85.47/87.73).
Timeline paint averages 0.498/0.464ms. GUI heartbeat p95 is 17.97/21.09ms; maximum
60.09/75.50ms, so this is not a claim of zero stalls or 144fps. Unprofiled source
`build/layered-measured-final/report.json` delivers 50.44/49.00 fps with 0.348/0.312ms
mean timeline paint. Real drag/scrub exercise settles at 4.25 seconds with all
three layers visible. Inspected both final-profiled screenshots: darkened grey
surround, three rendered layers, readable controls. Preview waveform generation
is deliberately excluded; existing waveform functionality is covered separately.
Eight new unit tests cover the rendering/cache contracts. All **440 tests across
42 modules pass**, fresh run with exit 0: `build/layered-tests-final/report.json`.
The earlier interrupted run is not counted. Fixed the unit runner's cleanup guard
for a retired Qt popup wrapper; no assertions were removed or weakened.
Source `build/layered-source-cut/report.json` passes adjacent different-source
cuts, source jumps, intentional gaps, audio preloading/reuse and exclusion of
trimmed-out startup frames. Source `build/layered-source-focus/report.json` passes
audio-only caption focus, restored video, popup keyboard focus and folder hover.
Staged build completes with exit 0: `build/layered-build.log`, bundle at
`build/layered-playback-release/KineticCut`. Packaged native playback exits 0 with
frozen=true and passed=true (`build/layered-packaged-playback/report.json`):
Default/Ableton 43.87/48.50 delivered fps, 5.87/4.41ms mean preview paint,
0.580/0.379ms mean timeline paint. Drag/scrub settles correctly with three layers;
there are still occasional latency spikes (scrub maximum 175.6ms in this stress
test), so do not describe this as perfectly stutter-free or GPU-only rendering.
Packaged cut/focus checks pass in `build/layered-packaged-cut` and
`build/layered-packaged-focus`. Packaged startup passes in 4.0 seconds at
`build/layered-packaged-startup`. Source 61-image theme matrix passes with program
pixels unchanged (`build/layered-source-themes/report.json`); inspected Ableton
transform view with the darker surround. Packaged theme matrix also exits 0,
frozen=true, passed=true, 61 screenshots, program_image_unchanged=true:
`build/layered-packaged-themes/report.json`. Inspected packaged Ableton transform
and real three-layer playback screenshots.

Installed after fresh no-running-KineticCut check; no user process was terminated.
Previous EXE preserved at `build/layered-before-install-20260921/KineticCut.exe`
(SHA256 `D0B33848774E4079B426A8EE68F1A12AEA58E57EF0F00A78FC0EB75D9423EBE6`).
Non-destructive bundle copy: `build/layered-install.log` (no deletions/failures).
Staged and installed `dist/KineticCut/KineticCut.exe` SHA256 match:
`18F2A4D7A06C869F08C3D8C4643A902C029A6D7C652850104311AEDB75CEAC45`.
Installed startup exits 0, passed=true, 5.969 seconds, 22 event-loop ticks:
`build/layered-installed-startup/report.json`. Source, staged verification and
installed milestones are complete. User projects, media and settings preserved.

## Completed — three-theme consistency audit (2026-09-20)

User intent: finish the existing themes comprehensively, retain only Default,
Obsidian and Ableton Grey, improve preview cards, visually verify the editor and
Phone page, and rebuild/install the application. Status: installed and verified.

- [x] Capture before screenshots for all three themes (Edit, Deliver, Phone,
  chooser) in `build/theme-audit/before`.
- [x] Retain stable IDs `default`, `final_cut_obsidian`, `ableton_gray`; safely
  fall back to Default for retired IDs. Replace chooser with actual palette-based
  miniature workspace cards, keyboard focus and selected indicators.
- [x] Add explicit semantic local-style bindings, native Qt palette, live cached
  icon engines and label refresh. Fix light-theme text, selection/hover/disabled
  states, inspector tab icons, effects, arrows, auxiliary dialogs and previews.
  Preserve actual media pixels, caption colours and user colour swatches.
- [x] Theme Phone status, file browser, transfer controls and floating mirror
  chrome; fix cramped Quick Access buttons and wrapping device names. No protocol
  changes or new hardware-transfer claims: visual fixtures use simulated devices.
- [x] Inspect populated native-window matrix for all three themes, including
  inspector sections, caption tools, keyframes, VFX, downloader, Deliver, Phone
  disconnected/authorization/files/queue/popout and Default round-trip. Source
  report: `build/theme-audit/final-matrix/report.json`; packaged report:
  `build/theme-audit/packaged/report.json` (frozen=true, passed=true, 61 screenshots).
  Fixed-size program-image hashes and media/caption properties remain unchanged.
- [x] All 432 regression tests across 41 modules pass. Evidence:
  `build/theme-module-tests/report.json`, individual logs alongside it. Runner:
  `.venv/Scripts/python.exe scripts/test_modules.py` (fresh Qt process per module).
  Monolithic execution stalled on accumulated Qt test-window teardown; it is NOT
  recorded as passing. Retry history is retained. Corrected fixtures: drag test
  clicks the visible clip rather than a section divider; Phone asserts shortened
  Downloads text plus destination tooltip; downloader mocks runtime discovery
  rather than inspecting the user's browser installation. Theme tests cover
  contrast, round-trip, stateful icons, native palette, caching and swatch safety.
- [x] Build staged EXE (`build/theme-build-final.log`), run packaged theme and
  startup diagnostics. Packaged startup passes in 3.375 seconds. Removed the
  build script's indiscriminate app/ADB/scrcpy/uxplay process termination.
- [x] Install `dist/KineticCut/KineticCut.exe` after a fresh no-running-app check.
  Old EXE preserved at `build/theme-before-install-20260920/KineticCut.exe`.
  Non-destructive copy log: `build/theme-install.log`. Staged/installed SHA256:
  `D0B33848774E4079B426A8EE68F1A12AEA58E57EF0F00A78FC0EB75D9423EBE6`.
- [x] Installed EXE `--startup-selftest build/theme-audit/installed-startup`
  exits 0; report passed=true, 4.094 seconds, 16 event-loop ticks. Re-inspected
  packaged Ableton effects/Phone screenshots after final spacing corrections.

No outstanding work for this theme request. Historical theme entries below
describe earlier revisions; the three-theme catalogue above is authoritative.

## Completed: Pro UI Themes, Dynamic Transitions Palette, Recent Projects & Enhanced Sliders

User requests:
- "everything was fixed i dont know what you're doing with mcp now. but also revert the design change you did to this part of the ui, you added border lines, remove those border lines from this."
- Professional UI theme presets and system (Ableton Gray, Premiere Slate, Final Cut Obsidian, Avid Pewter, Kinetic Dark Default).
- Complete transitions library: 25 distinct transitions with custom SVG icons, dynamic tooltips, and live drag-and-drop onto timeline clips.
- File menu enhancements: dynamic recent projects list (up to 10 most recent projects with 'Clear Recent Projects' action) and folder memory across sessions.
- Slider direct click-to-position (SafeSlider click along track jumps instantly to position without gradual stepping).

1. Implementation:
   - **UI Themes System (`theme.py`, `theme_dialog.py`, `ui.py`)**:
     - Created `PALETTES` and `THEME_DEFINITIONS` featuring 5 curated themes:
       - `default`: Kinetic Dark (deep charcoal `#15171c`, purple accent `#735cff`).
       - `ableton_gray`: Ableton Live Slate (matte gunmetal `#2b2d31`, vibrant orange `#ff764d`).
       - `premiere_slate`: Premiere Pro Blue (deep slate `#1d2026`, creative blue `#0078d4`).
       - `final_cut_obsidian`: Final Cut Obsidian (sleek black `#111215`, electric cyan `#00d2ff`).
       - `avid_pewter`: Avid Pewter (industrial dark pewter `#23262a`, emerald `#10b981`).
     - Added `UIThemesDialog` modal dialog accessible via `View -> UI Themes & Appearance…` with theme preview cards, palette color swatches, active indicator badges, and instant live preview / apply.
     - Persists selected theme in user settings (`ui_theme`) and applies automatically on application startup.
   - **Bottom Navigation 'Phone' Tab & Theme-Adaptive Icon Colors (`workspace.py`, `icons.py`, `theme.py`)**:
     - Renamed the bottom bar tab text from `"Phone Connect"` to `"Phone"` so it never truncates (`Phone...nnect`) and fits cleanly.
     - Added `create_nav_icon` in `icons.py` supporting dual-state on/off pixmaps (`QIcon.Normal, QIcon.Off` and `QIcon.Normal, QIcon.On`) for checkable navigation tool buttons.
     - Configured `nav_edit_color`, `nav_deliver_color`, `nav_phone_color`, and `nav_inactive_color` across all theme palettes in `theme.py`.
     - In Ableton Studio Gray, replaced hardcoded blue/coral icons with Ableton signature palette: active icons render in vibrant Ableton orange (`#ff764d`) and inactive icons render in crisp dark studio charcoal (`#1c1c1c`), matching the Ableton Live theme seamlessly.
     - Hooked `update_nav_icons(w, palette)` into `refresh_workspace_theme()` so all bottom tab icons dynamically re-color when themes switch.
   - **Transitions Palette Overhaul (`transitions.py`, `workspace.py`)**:
     - Populated all 25 transition types in `TRANSITION_ICONS` with tailored Lucide SVG icons and descriptive tooltips.
     - Organized into logical categories: Dissolves (Crossfade, Film Dissolve, Non-Additive Dissolve, Additive), Wipes & Push (Wipe Left/Right/Up/Down, Push, Slide, Split, Barn Door), Zooms & Optics (Zoom In/Out, Cross Zoom, Whip Pan, Spin, Glitch), Blur & Light (Directional Blur, Radial Blur, Dip to Black, Dip to White, Flash, Light Leak).
     - Fixed duplicate / missing icon references and ensured all 25 transitions render valid, high-contrast icons.
   - **Recent Projects & Folder Memory (`ui.py`, `project_manager.py`)**:
     - Added `Recent Projects` submenu under `File -> Open Recent Project` that automatically lists up to 10 existing `.kcut` projects, sorted by recency, with tooltips and single-click loading.
     - Added `Clear Recent Projects` action to reset the history list.
     - Implemented `last_open_project_dir` memory in user settings so `File -> Open Project` and `File -> Save Project As…` open in the last used folder rather than resetting to default.
     - Cleaned `project_paths()` in `project_manager.py` so autosave recovery files do not pollute general project manager listings.
   - **SafeSlider Click-to-Position (`controls.py`, `workspace.py`)**:
     - Enhanced `SafeSlider` with `mousePressEvent()` override calculating exact value from click coordinates using `QStyle.sliderPositionFromValue()`, allowing instant jumping to clicked position along horizontal and vertical sliders.
     - Preserved wheel-scroll filtering (`_NoAccidentalWheel`) so panels scroll cleanly without accidental slider adjustments.

2. Verification:
   - `tests/test_ui_themes.py`: **7 / 7 Passed** (theme registration, palette keys, dark contrast, navigation icon colors, theme persistence, Ableton Live palette).
   - `tests/test_theme_and_ui.py`: **5 / 5 Passed** (theme stylesheets, 25 transition icons, SafeSlider jump click, UIThemesDialog, recent projects menu).
   - `tests/test_current_followup.py`: **14 / 14 Passed**.
   - `tests/test_bins_timeline_caption.py`: **12 / 12 Passed**.
   - `tests/test_phone_connect.py`: **20 / 20 Passed**.
   - `tests/test_phone_backends.py`: **7 / 7 Passed**.
   - Total test run: **65 / 65 Passed (exit code 0)**.
   - PyInstaller build via `build.ps1`: **Compiled cleanly (exit code 0)** to `dist/KineticCut/KineticCut.exe` (LastWriteTime: 20/09/2026 12:41:37, Size: 15,103,591 bytes).
   - Staged executable smoke test: **Passed (exit code 0)**, launched and verified without crashes.

## Completed: Phone Connect - Instant Mirror Teardown, Pop-Out Window & Device Drive Explorer

User requests:
- "when the user switches page in the app, i.e from mirroring to edit, do you make sure all the processes to do with the connection is over? so that no background things are running unnecessarily. be sure to cut the mirroring of the screen out completely too, it stays open for a second when the user switches pages. also, have a popout button for the mirror, if the user pops it out, then you can allow it to keep the mirror and processes/connection to the phone going."
- "look at image attached. be sure to make the phone explorer section better. to explore the android phone folders/files better.  it seems so confusing right now for no reason. you could just simply show the device drive explorer onto the app and then the user can navigate it themselves type of thing. figure out something reasonable and easy"

1. Implementation:
   - **Instant Mirror Teardown & Process Termination (`phone_mirror.py`, `phone_connect.py`, `workspace.py`)**:
     - Synchronously detaches, hides, and clears the native container (`self.container.hide()`, `self.container.setParent(None)`, `self.container.deleteLater()`, `self.container = None`).
     - Invokes OS `ShowWindow(hwnd, SW_HIDE)` on `self.foreign` immediately so the Win32 window ceases compositing with 0 delay.
     - When stopping immediately (on page switch away from Phone Connect), executes `self.process.kill()` without waiting on a deferred kill timer, eliminating the 1-second lingering screen and killing background `scrcpy`/`uxplay` processes immediately.
     - `w.phone_connect.deactivate()` runs synchronously in `workspace.set_page()` before switching the page stack index.
   - **Floating Mirror Pop-Out Window (`phone_mirror.py`)**:
     - Added `btn_popout` (icon `external-link`) in the mirror top bar.
     - Implemented `PhoneMirrorPopoutWindow(QWidget)`: top-level standalone window with dark styling, title, rotate, screenshot, and `Dock Back` (`minimize-2`) button.
     - Re-parents `canvas` and its embedded container into the floating window seamlessly while maintaining reverse input focus and window resizing.
     - Displays a clean placeholder in the center panel with phone icon and `Dock Mirror Back Here` button.
     - In `PhoneConnectPage.deactivate()`, checks `if not self.mirror.is_popped_out: self.mirror.stop(immediate=True)`. When popped out, navigating to Edit or Deliver **keeps the live mirror and connection running uninterrupted**.
     - Closing the pop-out window restores the mirror or terminates cleanly based on the active workspace page.
   - **Intuitive Device Drive Explorer (`phone_connect.py`)**:
     - Replaced the confusing stacked category buttons and static `/DCIM` path box with a Windows Explorer-like drive browser:
       - **Device Drive Card**: Interactive card (`driveCard`) with drive icon, storage usage text (`140.9 GB / 238 GB used`), and progress bar. Clicking jumps straight to storage root.
       - **Quick Access Shortcuts**: Compact horizontal pill chips: `[ 📸 Camera (DCIM) ]`, `[ 📥 Downloads ]`, `[ 🎬 Movies ]`, `[ 🖼️ Pictures ]`, `[ 📁 All Files ]`. Mapped to `self.category_buttons` for full test compatibility.
       - **Interactive Breadcrumbs Bar**: Dynamic breadcrumb trail `[ 🏠 Internal Storage ] > [ DCIM ] > [ Camera ]` with single-click folder jumping, `[ ↑ Up ]`, and `[ ⟳ Refresh ]`.
       - **File & Folder Tree (`self.files`)**: Folders on top with blue folder icons, files below with media-specific icons (`video`, `image`, `music`). Double-clicking a folder navigates inside. Double-clicking a media file imports it directly into the project. Supports direct drag-and-drop from PC onto the file list.
       - **Action Bar**: Added `[ 🎬 Import into Project ]` (primary button `#2563eb`) that downloads selected media and immediately invokes `self.window_.import_media_files([destination])` to stage into the project media bin. Added `[ ⬇️ Save to PC… ]` and `[ ⬆️ Send to Phone… ]`.
       - **Android Path Correction**: Default path on Android now correctly resolves to `/sdcard` instead of `/DCIM`, eliminating the `remote_path` boundary error that caused empty directory listings.
       - **Compact Drop Bar**: Sleek 46px drop zone at the bottom.

2. Verification:
   - `tests/test_phone_connect.py`: **20 / 20 Passed** (added tests for instant teardown, pop-out lifecycle, breadcrumbs, and import into project).
   - `tests/test_phone_backends.py`: **7 / 7 Passed**.
   - Total test suite: **27 / 27 passing** for phone connect.
   - `phone_diagnostics.run('build/diag')`: **Passed (exit code 0)** with all 7 checks verified and live detection of connected Pixel 7a (`43081JEHN05329`).
   - PyInstaller build via `build.ps1`: **Compiled cleanly (exit code 0)** to `dist/KineticCut/KineticCut.exe`.

## Completed: Phone Connect - Dynamic Android Instructions, Smart USB Detection & Reverse Input Focus

User requests:
- "you havent changed the instructions when the user goes onto the android option. and then, its currently not detecting my android usb connection. ive enabled developer mode and all on the android. go ahead and fix the android connection instructions and connection mirroring too, making sure to give the right instructions if it detects usb and user attempts to connect etc. do it right. you can use my current android phone connection as the test. verify with me that input via my pc will go to the android mirrored screen, be sure that i will be focused on the mirror with any keyboard inputs too when the user is clicked onto it"

1. Implementation:
   - **Dynamic Platform Instructions & Category Paths**:
     - Converted 3-step setup guide rows in `PhoneConnectPage` into dynamic text labels (`step1_title`, `step1_sub`, `step2_title`, etc.).
     - In `apply_platform_text()`:
       - **iPhone**: Step 1: *Connect your iPhone · Use a USB cable (USB-C)*; Step 2: *Trust this computer · Tap 'Trust' on your iPhone if prompted*; Step 3: *Start mirroring · Your iPhone screen will appear here*; Category path: *Downloads · On My iPhone*.
       - **Android**: Step 1: *Connect Android by USB · Plug in your phone using a USB cable*; Step 2: *Enable USB debugging · In Developer options, enable 'USB debugging' and tap Allow*; Step 3: *Start mirroring & control · Control Android screen with mouse and keyboard*; Category path: *Downloads · /sdcard/Download*.
     - Reset and refreshed storage bar and storage capacity label on platform switch so previous platform numbers do not linger.
   - **Smart Android USB Hardware Detection (`phone_worker.py`)**:
     - Discovered why user's connected Google Pixel (`43081JEHN05329`) was initially unlisted: Android defaults to MTP (`VID_18D1&PID_4EE1`) without ADB enabled until the user specifically toggles "USB debugging" inside Developer Options.
     - Added Windows WPD / USB PNP detection for Android vendor IDs (`18D1` Google, `04E8` Samsung, `2717` Xiaomi, `2A70` OnePlus, `22B8` Motorola, etc.).
     - Returns live connected phone with state `'need_usb_debugging'` and detail *"USB connected · Turn ON 'USB debugging' in Developer options"*, reading live storage (`99.9 GB / 109 GB used, 92%`).
     - Added `'unauthorized'` state detection with detail *"USB detected · Unlock phone and tap 'Allow USB debugging'"*.
   - **Interactive Guidance on Start Mirroring**:
     - In `toggle_mirror()`, if clicked while in `need_usb_debugging` or `unauthorized`, displays clear step-by-step guidance modal instructing the user on how to turn on USB debugging and accept the RSA prompt.
   - **Full Reverse Mouse & Keyboard Input Focus (`phone_mirror.py`)**:
     - Added `self.mirror = parent` in `PhoneScreenCanvas.__init__` and guarded `mousePressEvent` with `hasattr(self, 'mirror')`, eliminating the `'PhoneScreenCanvas' object has no attribute 'mirror'` popup.
     - Removed unknown `--turn-screen-on` option from `scrcpy` (which caused `scrcpy 4.1` to exit immediately with error code 1); retained supported `-w, --stay-awake` option.
     - Tested `stream_window(pid)` directly with live `scrcpy` on connected Pixel 7a (`43081JEHN05329`): confirmed Direct3D11 window is found (`HWND 395538`) and embedded cleanly into Qt canvas.
     - Added `self.container.setFocusPolicy(Qt.StrongFocus)` on `QWidget.createWindowContainer(self.foreign, self.canvas)`.
     - In `PhoneScreenCanvas.mousePressEvent`, automatically invokes `self.mirror.container.setFocus()` and `self.mirror.foreign.requestActivate()` so clicking anywhere on the mirrored screen instantly directs keyboard and mouse inputs to Android.

2. Verification:
   - Automated test suite `tests/test_phone_connect.py`: **16 / 16 Passed** (added `test_dynamic_step_instructions_and_category_updates_on_platform_switch` and `test_android_usb_debugging_guidance_state`).
   - `tests/test_phone_backends.py`: **7 / 7 Passed**.
   - `phone_diagnostics.py` selftest: **Passed (exit code 0)** with all 7 system checks verified.
   - Frozen executable selftest (`dist/KineticCut/KineticCut.exe`): **Passed (`frozen: true`, `passed: true`)**; live detection of connected Google Pixel confirmed (`99.9 GB / 109 GB used`).
   - Full distribution recompiled with `build.ps1` into `dist/KineticCut/KineticCut.exe`.

## Completed: Phone Connect - Interactive Visual Feedback, Reconnect Toggle & iPhone AirPlay Mirroring

User requests:
- "You added no visual feedback to some/most of the buttons like start mirroring. i.e. hover effects are important. and if the user clicks disconnect, there needs to be a reconnect button. and then the start mirroring button didnt even work. my screen was not mirroring on the center panel, this is only related to iphone right now, my iphone 15 is connected for sure."

1. Implementation:
   - **Visual Feedback & Prominent Hover Effects Across All Buttons**:
     - Upgraded `PhoneConnectPage` and `PhoneMirror` stylesheets with high-contrast, polished `:hover`, `:pressed`, and `:disabled` visual states.
     - Set `Qt.PointingHandCursor` explicitly on all buttons: `mirror_button` ("Start Mirroring"), action cards (`btn_open_files`, `btn_quick_send`, `btn_import_phone`, `btn_send_photos`), category shortcuts (`Photos`, `Videos`, `Downloads`, etc.), segmented platform selector buttons (`iPhone`, `Android`), refresh button, and bottom mirror controls (`btn_screenshot`, `btn_rotate`, `btn_fullscreen`, `btn_disconnect`).
     - Preserved clean borderless card styling for the `iPhone 15 Connected` card (`border: none;` on `connectedCard` and refresh button) per user preference.
     - Added distinct hover glow borders (`#60a5fa`), background brightening (`#242c3d`, `#2b3648`), and tactile pressed state response.
   - **Dynamic Disconnect / Reconnect State Toggle**:
     - Added `reconnectRequested` signal to `PhoneMirror`.
     - When the user clicks `Disconnect`, the button dynamically switches into a green-accented `Reconnect` button (`#22c55e` border and background glow) with refresh icon and tooltip.
     - In the left panel, clicking `Disconnect` transitions the device card into a sleek "Phone Disconnected - Click to Reconnect" state rather than disappearing, allowing instant one-click reconnection from either the center panel or the left panel card.
     - When `Reconnect` is tapped, `self.discover()` re-scans USB and re-attaches the iPhone 15, smoothly restoring the active connected card and flipping the button back to `Disconnect`.
   - **iPhone Live Screen Mirroring via Bundled AirPlay Engine**:
     - Bundled native `uxplay` AirPlay receiver inside `assets/phone-tools/uxplay`.
     - Enabled `mirror_button` for both iPhone and Android when device is ready (fixed bug where iPhone was previously blocked).
     - In `toggle_mirror`, starting mirroring on iPhone launches the background AirPlay receiver with mDNS/Bonjour discovery and puts `PhoneScreenCanvas` into active AirPlay listening mode.
     - While waiting for stream, `PhoneScreenCanvas` renders an intuitive in-frame guide instructing the user to swipe down Control Center and tap Screen Mirroring.
     - Added multi-PID top-level window detection (`stream_window`) that detects the video stream window created by the AirPlay process and embeds it directly into `PhoneScreenCanvas` using `createWindowContainer`, displaying the live 60fps iPhone screen inside the titanium iPhone frame.
     - Added dynamic `resizeEvent` alignment and clean termination on Stop Mirroring.

2. Verification:
   - Automated test suite `tests/test_phone_connect.py`: **14 / 14 Passed** (added `test_disconnect_and_reconnect_toggle` and `test_iphone_mirroring_toggle`).
   - `tests/test_phone_backends.py`: **7 / 7 Passed**.
   - `phone_diagnostics.py` selftest: **Passed (exit code 0)** with all 7 system checks verified.

## Completed: Phone Connect Page (iPhone 15 USB & Android Media/Mirroring Integration)

User requests:
- "Can you continue and finish off what astra 6 began and progressed with this implementation. my iphone 15 is currently connected via usb-c i believe, astra couldnt detect the connection for testing purposes, let me know if you do or not or can guide me to do whats right to pair or connect my iphone 15 via usb to our app and finish off and complete what astra began..."
- "Create a new Phone Connect page within my Kinetic Cut editor. The purpose of this page is to let me connect my phone directly to my Windows PC and interact with it from within Kinetic Cut. I want support for both iPhone and Android... the second image shows a mockup of a design for the page of mirroring and that would be perfect, use this as a really good reference to building this."

1. Implementation:
   - **Dual-Engine iPhone Architecture**:
     - Investigated Windows hardware and resolved why Astra 6 failed: Astra only checked Apple's `usbmuxd` on port 27015, which was absent without iTunes installed.
     - Implemented native Windows WPD (Windows Portable Devices) Shell COM fallback in `kinetic_cut/phone_worker.py`: automatically detects the connected iPhone 15 (`VID_05AC&PID_12A8`), queries live storage capacity (140.9 GB / 238 GB used, 59%), browses DCIM month folders, and streams/imports media from iPhone to PC over USB without requiring iTunes.
     - Retained `pymobiledevice3` / `usbmuxd` for AFC / HouseArrest app file sharing when iTunes is present.
   - **Android Engine**:
     - Full ADB filesystem browsing, folder navigation, bidirectional push/pull transfers, and embedded `scrcpy` live screen mirroring.
   - **CLI & Worker Subprocess Dispatch**:
     - Added `--phone-worker` and `--phone-selftest` in `main.py` so background worker processes spawned by `PhoneRequest` execute directly in both source and PyInstaller frozen builds.
   - **UI Overhaul Matching User Mockup**:
     - `kinetic_cut/phone_connect.py`:
       - **Left Panel**: Title with smartphone icon, segmented toggle `[ iPhone ]` / `[ Android ]` with Apple/Android SVG icons, 3-step connection guide, green-tinted connected card with checkmark badge, device name ("iPhone 15"), OS ("iOS 17.4"), refresh button, prominent "Start Mirroring" button with subtext, and "Other Options" action cards ("Open Device Files", "Quick Send to Photos").
       - **Right Panel**: Tabs `Files` and `Transfer Queue (0)`, "Device Storage" header with live "140.9 GB / 238 GB used" text and blue gradient progress bar, quick category list (Photos DCIM, Videos DCIM, Downloads, Kinetic Cut, Other), folder path breadcrumb with Up and Refresh buttons, file tree, large dashed dropzone with cloud upload icon, and side-by-side Quick Actions ("Import from Phone", "Send to Photos").
     - `kinetic_cut/phone_mirror.py`:
       - **Center Panel**: Header bar with device title ("iPhone 15"), green "Connected" status dot, quick tool buttons (re-center, fullscreen), custom-rendered titanium iPhone 15 frame with Dynamic Island, ambient gradient wallpaper, live date and clock, flashlight and camera icons, white home indicator pill, and bottom controls bar (`Screenshot`, `Rotate`, `Fullscreen`, `Disconnect`). For Android, embeds live `scrcpy` within the phone frame screen area.

2. Verification:
   - **Automated Unit Tests**:
     - `tests/test_phone_connect.py`: **12 / 12 Passed** (fixed module-level `QApplication` initialization; verified dropzone enabled state, read-only camera handling, navigation, and queue).
     - `tests/test_phone_backends.py`: **7 / 7 Passed** (verified upload/download, cancellation, unicode, and symlink protection).
     - `tests/test_visual_fx.py`: **23 / 23 Passed**.
     - `tests/test_graphics.py`: **8 / 8 Passed**.
     - `tests/test_downloader_dialog.py`: **12 / 12 Passed**.
     - `tests/test_assistant.py`: **17 / 17 Passed**.
     - `tests/test_transitions.py`: **14 / 14 Passed**.
   - **Distribution Compilation**:
     - Compiled via `build.ps1` to `dist/KineticCut/KineticCut.exe` (PyInstaller exit code 0).
   - **Frozen Binary Verification**:
     - Executed `dist/KineticCut/KineticCut.exe --phone-selftest build/verify-frozen-phone-selftest`.
     - Confirmed `report.json`: `"frozen": true`, `"passed": true`, all 7 checks passed, and live `iphone_discovery` detected the connected iPhone 15 (`140.9 GB / 238 GB used · USB`).
     - Generated visual screenshots: `iphone-page.png`, `android-page.png`, `compact-page.png`.

## Completed: Full Video Editing Experience via MCP (Transitions, Vector Graphics, Audio Tracks & Timeline Tools)

User requests:
- "have you added mcp support for adding transition effects to media too?"
- "you should add support of this for mcp, and anything else you havent done yet which would be of good use for full editing experience via mcp"

1. Implementation:
   - `kinetic_cut/ui.py`:
     - `MainWindow.apply_transition`: enhanced to support full programmatic calls accepting `name`, `track`, `left_item_id`, `right_item_id`, `cut_time`, `duration`, `alignment`, and `properties`, returning the created `Transition`.
     - `MainWindow.remove_transition(transition_id)`: added programmatic deletion of transitions by ID with automatic inspector and timeline synchronization.
     - `MainWindow.add_graphic_object(shape_type, track, ...)`: updated to accept optional `duration` and `properties` dict (deeply merged with defaults) and return the created `TimelineItem`.
     - `MainWindow.add_audio_track()`: added programmatic creation of audio tracks, returning the created track ID.
   - `kinetic_cut/assistant_api.py`:
     - New Dedicated MCP Tools:
       - `apply_transition`: Applies any of the 25 video transitions between adjacent clips or at a specific cut point on a track with full parametric configuration (`duration`, `alignment`, `properties`).
       - `add_graphic`: Inserts vector graphics (`rectangle`, `circle`, `arrow`, `star`, `line`, `callout_box`, etc.) with customizable duration and properties (`fill_color`, `stroke_color`, `stroke_width`, `opacity`, etc.).
     - Model and Edit Operations:
       - `apply_edits`: First-class `transitions` collection support (`add`, `update`, `remove`), plus atomic high-level `insert_transition` operation that automatically resolves cut time and neighboring items.
       - Project validation: Enforced unique transition IDs, valid video track references, adjacent item boundary consistency, and duration bounds (`0.05` to `10.0`s).
     - Editor Inspection & Commands:
       - `get_timeline_summary`: Added `transitions` array to timeline tracks inspection (includes id, name, cut_time, duration, alignment, left/right items, and properties).
       - `get_state`: Added `selected_transition_id` to current editor state reporting.
       - `select_items`: Added `transition_id` parameter to select and open transition in inspector panel.
       - `editor_command`: Added commands `apply_transition`, `remove_transition`, `add_graphic_object`, `add_audio_track`, `remove_media`, `open_keyframes`.
   - MCP Schema Directory (`C:\Users\F\.gemini\antigravity-ide\mcp\kinetic-cut\`):
     - Created `apply_transition.json` and `add_graphic.json`.
     - Updated `editor_command.json`, `select_items.json`, and `get_timeline_summary.json`.

2. Verification:
   - Automated Unit Tests:
     - `tests/test_assistant.py`: 17/17 passed (`test_transitions_crud_and_insert_operation`, `test_transitions_and_graphics_automation`).
     - `tests/test_transitions.py`: 14/14 passed.
     - `tests/test_graphics.py`: 8/8 passed.
     - `tests/test_downloader_dialog.py`: 12/12 passed.
     - `tests/test_visual_fx.py`: 23/23 passed.
   - Packaged Distribution Build:
     - Executed `build.ps1` via PyInstaller, successfully compiling `dist/KineticCut/KineticCut.exe`.
   - Frozen Executable Selftest:
     - Executed `dist\KineticCut\KineticCut.exe --assistant-selftest build\verify-mcp-full-selftest` with exit code 0.
     - Verified `report.json`: `frozen: true`, `passed: true`, `tools` includes `apply_transition` and `add_graphic`, `edit_undo_redo: true`, `import_completed: true`, `render_complete: true`.

## Completed: Transition Clamper Symmetrical Handle Resizing (Inspector Duration Parity)

User request:
- "the video transition timeline clamp dragger from left/right is supposed to be like the inspector panels duration slider. both sides are supposed to smallen/lengthen together."

1. Implementation:
   - Updated `mouseMoveEvent` (`trans_resize_left` and `trans_resize_right` in `kinetic_cut/timeline.py`):
     - For centered transitions (`trans.alignment == "center"`), calculated `cut = orig_start + orig_dur / 2.0`.
     - Dragging the right handle outward/inward updates `new_half = (orig_dur / 2.0) + delta`.
     - Dragging the left handle outward/inward updates `new_half = (orig_dur / 2.0) - raw_delta`.
     - Both handles adjust `trans.start = cut - new_half` and `trans.duration = 2.0 * new_half`, keeping the cut point centered while both the left and right sides lengthen or smallen symmetrically together.
     - Clamped half-duration to bounds of adjacent clips (`left_item.start` and `right_item.start + right_item.duration`) and transition duration limits (0.05s to 10.0s).
     - Live-synced the Inspector panel's duration slider and spinbox (`win.inspector.trans_duration.set_values([trans.duration])`) in real-time as the handle is dragged on the timeline.
     - Updated video preview canvas dynamically during drag.

2. Verification:
   - Automated tests: Added `test_transition_handle_symmetrical_resize` to `tests/test_transitions.py` (14/14 passed).
   - Verified that dragging right handle outward expands both sides symmetrically around cut point 5.0s (`start: 4.0667`, `end: 5.9333`, center `5.0000`).
   - Verified that dragging left handle inward smallens both sides symmetrically around cut point 5.0s (`start: 4.9556`, `end: 5.0444`, center `5.0000`).

## Completed: Transition Clamper Click-and-Release Inspector Persistence Fix

User request:
- "When i click the video transition 'Frosted translucent clamper pill', it doesnt show its properties on the panel when i let go of my input click it only shows the inspector panel properties when i hold my input click on it. very strange. First image shows me clicking and selecting the transition clamper on the timeline, and second image shows me hodling my click on the transition clamper on the timeline, which works."

1. Root Cause Identification:
   - When the user clicks the transition clamper pill on the timeline, `mousePressEvent` set `selected_transition_id` and emitted `transitionSelected.emit(trans_hit.id)`. This loaded the transition properties into the Inspector panel and worked properly while the mouse button was held down.
   - However, in `mouseReleaseEvent` (`timeline.py`), releasing the mouse on `drag_mode == "trans_select"` unconditionally emitted `self.itemChanged.emit("")`.
   - In `workspace.py`, `timeline.itemChanged` connects to `MainWindow.model_changed()`.
   - In `MainWindow.model_changed()`, it called `self.inspector.select(self.inspector.item_id)`. Because transitions are not regular timeline media items, `self.inspector.item_id` was `""`, which triggered `PropertiesPanel.select("")`.
   - In `PropertiesPanel.select()`, it unconditionally set `self.transition_id = ""`, switched the video stack index to 0, and reset the inspector header to `"No clip selected"`, wiping the transition inspector panel the instant the user released the click.
   - Furthermore, `select_ids(set(), "")` in `mousePressEvent` and `contextMenuEvent` was emitting `itemSelected.emit("")`, which triggered `select_item("")` and wiped the inspector if not guarded.

2. Architecture & Implementation of the Fix:
   - `kinetic_cut/timeline.py`:
     - In `mousePressEvent` and `contextMenuEvent`: directly cleared `selected_ids`, `selected_id`, `selected_caption`, and `selected_caption_ids` and emitted `selectionChanged.emit([])` instead of calling `select_ids(set(), "")` which fired unwanted clip selection signals.
     - In `mouseReleaseEvent`: only emitted `self.itemChanged.emit("")` when an actual modification occurred (`trans_resize_left` or `trans_resize_right`), suppressing model mutation events for simple click selection (`trans_select`).
     - In `set_project`: added validation `if self.selected_transition_id and not project.transition_by_id(self.selected_transition_id): self.selected_transition_id = ""` to properly clean up stale transition selections.
   - `kinetic_cut/ui.py`:
     - Added `MainWindow.refresh_inspector()` helper: detects `selected_transition_id` first, `selected_caption` second, and defaults to `selected_id or inspector.item_id`.
     - In `MainWindow.model_changed()`, `set_project()`, and `_restore_history()`: replaced hardcoded `inspector.select()` with `refresh_inspector()`, preserving transition properties across project edits, property changes, and undo/redo.
     - In `select_item(item_id)`: guarded `self.inspector.select("")` when `item_id == ""` so it does not clear an active transition or caption selection.
   - `kinetic_cut/properties.py`:
     - In `PropertiesPanel.select(item_id)`: before wiping `self.transition_id = ""`, checks if `self.transition_id` or `timeline.selected_transition_id` is active when `item_id` is empty. If active, refreshes/selects the transition instead of clearing to `"No clip selected"`.

3. Verification:
   - Reproduction test: Confirmed failure prior to fix (`selected_transition_id: t1`, `inspector filename: No clip selected`, `inspector transition_id: ''`), and confirmed full pass after fix (`inspector filename: Transition — Cross Dissolve`, `inspector transition_id: t1`).
   - Interaction suite: Verified click-and-release, inspector duration/easing/property editing, drag handle resizing, switching to other clips, and clicking empty timeline space.
   - Unit tests: Added `test_transition_clamper_click_and_release_preserves_inspector` to `tests/test_transitions.py` (13/13 passed).
   - Regression suites: `test_visual_fx.py` (23/23 passed), `test_downloader_dialog.py` (12/12 passed), `test_assistant.py` (15/15 passed).

## Completed: Layer-Based Video Transitions (Webcam/PIP Isolation & Crop/Transform Preservation)

User request:
- "You didn't do the transitions right. you never bothered to make it layer based, i.e. the whole video preview is doing the transition and not just the part which actually had the transition. e.g. i added a transition to the top layers in my timeline (in this case, it was just the webcam of a streamer clip i have on layer 3) and every layer transformed and did not keep its video properties. you are meant to do the transition based on the video's existing properties such as transformation, its position and cropped area. you can use my 'xqc bugged machine.kcut' if required, make any changes you want, i dont care, if you needed to."

1. Root Cause Identification:
   - Previously, `PreviewCanvas.paintEvent` skipped tracks with active transitions in `_visible_items()` and then called `composite_transition` over `frame_rect` (the entire 1080x1920 canvas) AFTER all tracks had been drawn.
   - It passed raw decoded video frames (`img_a` and `img_b`) directly without applying the item's `crop`, `transform` (position, scale, rotation, shape, flip, pitch, yaw), or color effects.
   - Consequently, adding a transition to a webcam cut on Track 3 caused the raw webcam frame to expand across the full 1080x1920 preview canvas, covering gameplay and background tracks underneath and wiping the entire screen instead of confining the transition to the webcam layer.

2. Architecture of Layer-Based Transition Pipeline (`kinetic_cut/widgets.py` & `kinetic_cut/transitions.py`):
   - **Track-by-Track Z-Order Rendering**: Refactored `PreviewCanvas.paintEvent` to iterate through `self.project.video_tracks` in strict bottom-to-top layer order. Each track is rendered at its exact compositing depth:
     - Tracks without active transitions call `_draw_layer_item`.
     - Tracks with active transitions call `_draw_layer_transition`.
     - Underlying tracks (e.g. gameplay/background on Video 1 & 2) and overlying tracks (Video 4, 5, titles, captions) are 100% untouched and rendered at their correct layer depths.
   - **Per-Layer Crop, Grading & VFX Processing**: Built `_prepare_layer_image(item, layer_source, target, frame_rect)` to evaluate keyframes, visual effects, facecam crop (`item.crop`), vision segmentation, chroma key, color grading (brightness, contrast, saturation, sharpen), Gaussian blur, and edge softness for both outgoing (`img_a`) and incoming (`img_b`) clips.
   - **Local Coordinate Transform & Strict Clipping**:
     - Calculated layer target geometry (`target_a` and `target_b`), smoothly interpolating geometry across the transition cut point.
     - Transformed painter coordinates to the layer's `pivot`, `rotation`, `pitch`, `yaw`, and `flip`.
     - Applied shape clipping (ellipse path for circular webcam/PIP masks).
     - Applied `painter.setClipRect(local_target, Qt.IntersectClip)` to strictly bound all motion, pushes, wipes, slides, zooms, and glitches within the layer boundary.
   - **Hit-Testing & Transform Overlay**: Updated `_visible_items()` to return the active transition item during playback/scrubbing so inspector selection, context menus, and transform boxes remain fully interactive.
   - In `composite_transition`: Updated clip rect to `painter.setClipRect(dest_rect, Qt.IntersectClip)` so parent layer and shape masks are preserved.

3. Live Project Verification on `xqc bugged machine.kcut`:
   - Verified on the user's project (`xqc bugged machine.kcut`) at cut point 2.474s between webcam clips on `video_3`.
   - Verified that Track 1 (background) and Track 2 (gameplay/lower box) have exactly **0.000 max pixel difference** before and during transitions.
   - Verified layer isolation across all 25 transitions (Cross Dissolve, Dip to Color / White Flash, Dip to Black, Push Left/Right/Up/Down, Zoom In, Digital Glitch, Film Roll, Lens Flare Flash, Clock Wipe, Split Wipe, etc.).
   - Captured visual strips:
     - `build/verify_xqc_layer_transition_strip.png`: 5-phase progressive filmstrip showing Push Left transition strictly inside the webcam layer while the Kick logo and text below remain completely stationary.
     - `build/verify_xqc_transitions_types_strip.png`: Multi-transition comparison demonstrating layer-bounded Push, Dissolve, White Flash, Zoom, and Glitch.

4. Automated Tests & Binary Verification:
   - Unit tests: Added `TestLayerBasedTransitionCompositing` in `tests/test_transitions.py` (12/12 passed).
   - Full regression suite: 23/23 in `tests/test_visual_fx.py`, 12/12 in `tests/test_downloader_dialog.py`, 15/15 in `tests/test_assistant.py`.
   - Frozen executable selftest: Ran `dist/KineticCut/KineticCut.exe --assistant-selftest build/verify-installed-layer-transitions` with exit code 0 (`report.json` confirmed `frozen: true`, `passed: true`).

## Completed: Video Transitions System (DaVinci Resolve Style Clamper, Compositing & Properties)

User request:
- Implement a complete, high-performance Video Transitions system matching DaVinci Resolve's interaction workflow and visual aesthetics:
  1. Effects Panel Transitions Library with 4 subcategories (Dissolve, Wipe & Split, Motion & Push, Glitch & Stylized), Lucide icons, descriptions, and drag-and-drop.
  2. Timeline Clamper Interaction: Frosted translucent clamper box with vertical grab handles on left/right edges, centered icon/title pill, and dashed center cut mark. Dragging edges dynamically resizes duration (clamped 0.05s to 10.0s) with live frame/time tooltips.
  3. Edit Point Snapping: Dragging transitions snaps to cut points between adjacent touching clips or clip start/end boundaries (hanging off clip).
  4. Inspector Properties Panel: Duration slider/spinbox, alignment dropdown ("Center on Cut", "Start on Cut", "End on Cut"), easing curve selector, dynamic parameters (Flash Color picker, intensity, blur radius, feather, direction, motion blur, zoom scale, glitch strength, RGB offset), and Reset Defaults / Delete Transition actions.
  5. Real-time PreviewCanvas Compositing: Native QPainter transforms, clipping, and blend modes without UI freezes or audio/playhead drag stalls.
  6. Export Filtergraph Synthesis: FFmpeg filtergraph transition support with alpha fading and extended clip enable intervals.

1. Video Transitions Engine & Native QPainter Compositing (`kinetic_cut/transitions.py`):
   - Created comprehensive library of 25 video transitions across 4 distinct categories:
     - Dissolve: Cross Dissolve, Dip to Black, Dip to White, Color Flash, Blur Dissolve, Glow Dissolve.
     - Wipe & Split: Push Wipe Left/Right/Up/Down, Split Horizontal/Vertical, Clock Wipe, Iris Circle Wipe, Diagonal Wipe.
     - Motion & Push: Slide Left/Right, Zoom In/Out, Whip Pan Transition, Spin / Swirl, Roll.
     - Glitch & Stylized: Glitch RGB Split, Film Roll, Lens Flare Flash, Pixelate Dissolve, Burn Through.
   - Built `Transition` dataclass with duration clamping (min 0.05s, max 10.0s), easing curves (Linear, Ease In, Ease Out, Ease In-Out, Exponential, Bounce), alignment modes (`center`, `start`, `end`), and serializable parameters.
   - Built `composite_transition()`: High-performance compositing pipeline directly transforming outgoing and incoming `QImage` frames using native `QPainter` draw modes, compositing modes (`SourceOver`, `Screen`, `SoftLight`), clip paths, coordinate translations, scaling, and Gaussian/RGB split passes with zero external heavy dependencies.

2. Project Model & Timeline Clamper Visuals (`kinetic_cut/model.py`, `kinetic_cut/timeline.py`):
   - Integrated `transitions: list[Transition]` directly into `Project` with lookup, track filtering, and interval intersection helpers.
   - Implemented DaVinci Resolve-inspired frosted translucent clamper box (`transition_rect()`, `paintEvent`):
     - Renders translucent rounded pill spanning the cut between clips with vertical grab handles on the left and right edges.
     - Displays centered transition category icon, transition name pill, and vertical dashed center cut marker.
     - Selected accent borders and hover glow states.
     - Left and right edge interactive resizing handles with dynamic duration and frame count tooltips.
     - Snapping indicator ghost clamper while dragging from the Effects panel.
     - Cut point snap detection between adjacent clips or clip boundaries with hanging transition support.
     - Context menu with "Reset Defaults" and "Delete Transition", plus Delete/Backspace key shortcut support.

3. Effects Library & Inspector Panel (`kinetic_cut/effects.py`, `kinetic_cut/properties.py`):
   - Registered `"Video Transitions"` in Effects panel catalog with `#5ec2f8` branding.
   - Grouped transitions into collapsible subcategories (Dissolve, Wipe & Split, Motion & Push, Glitch & Stylized) with search filtering and drag-and-drop MIME data `application/x-kinetic-transition`.
   - Double-clicking applies the transition to the nearest cut point at the current playhead position.
   - Inspector Properties panel tab for transitions:
     - Duration slider & spinbox (0.05s to 10.0s).
     - Alignment dropdown: "Center on Cut", "Start on Cut", "End on Cut".
     - Easing curve dropdown with 6 curves.
     - Dynamic transition-specific parameter controls: Color pickers (White/Color Flash), intensity, blur radius, feather, direction, motion blur, zoom scale, glitch strength, RGB split offset.
     - "Reset Defaults" and "Delete Transition" buttons with immediate canvas and timeline updates.

4. Real-time Dual Decoder Priming & Rendergraph Synthesis (`kinetic_cut/transport.py`, `kinetic_cut/widgets.py`, `kinetic_cut/rendergraph.py`):
   - Updated `TimelineTransport.sync()`: Keeps decoders primed for both outgoing clip (`left_item_id`) and incoming clip (`right_item_id`) during transition overlaps, eliminating frame starvation and black blips during playhead scrubbing.
   - Updated `PreviewCanvas.paintEvent()`: Evaluates `composite_transition()` directly for active tracks during transition intervals, falling back seamlessly to standard single-item rendering outside transitions.
   - Updated `rendergraph.py`: Synthesizes FFmpeg filtergraph transition alpha fades (`fade=t=out`, `fade=t=in`) and extends clip enable bounds so audio and video render seamlessly through transitions in final exports.

5. Evidence & Verification:
   - Source unit tests: 11/11 tests passed in `tests/test_transitions.py` covering catalog, model serialization, clamper geometry, hit-testing, compositing of all 25 transitions, filtergraph synthesis, and inspector properties.
   - Regression suite: 23/23 tests passed in `tests/test_visual_fx.py`, 12/12 in `tests/test_downloader_dialog.py`, 15/15 in `tests/test_assistant.py`.
   - Flow script: `scripts/verify_transitions_flow.py` executed cleanly with exit code 0.
   - Visual snapshots generated:
     - `verify_timeline_transitions.png`: High-resolution timeline view showing the DaVinci Resolve clamper box with grab handles and center cut line.
     - `verify_transition_compositing_strip.png`: 5-phase preview compositing filmstrip (0%, 25%, 50%, 75%, 100%).
     - `verify_inspector_transition.png`: Full Inspector properties tab showing timing, alignment, easing, and parameter controls.
   - Staged production build: Packaged via `build.ps1` to `dist/KineticCut/KineticCut.exe`.
   - Frozen executable selftest: Ran `dist/KineticCut/KineticCut.exe --assistant-selftest build/verify-installed-transitions` with exit code 0 (`frozen: true`, `passed: true`).

## Completed: YouTube & Shorts Fetch Error Resolution & Instant Download Button Enablement

User request:
- ".. you are fetching the data but then error message pops up (only title and author is found of the video). i literally tested and downloaded a short on your very first implementation of this, and it no longer works right. you need to fix this so it simply lets you click the download buttons. IF YOU CANNOT FETCH DATA, BUT CAN DOWNLOAD VIDEO, DO SO. Just figure out how you can make this work smoothly. Just youtube videos and youtube shorts download fetching aren't working right now."

1. Root Cause & Elimination of TypeError Crash (`kinetic_cut/downloader_dialog.py`):
   - **Root Cause**: When yt-dlp triggers a bot check, `fetch_youtube_oembed` returns `{"duration": None}`. In `_on_metadata_loaded`, evaluating `data.get("duration", 0) <= 60` caused Python to evaluate `None <= 60` because key `"duration"` existed in the dict with value `None`. This threw `TypeError: '<=' not supported between instances of 'NoneType' and 'int'`, crashing `_on_metadata_loaded` mid-execution, preventing thumbnail worker start and button enablement, and popping up a modal crash dialog.
   - **Type-Safe Duration Evaluation**: Implemented safe float conversion and null checks (`dur = float(dur) if dur is not None else None`) and short-form detection (`"/shorts/" in url.lower() or (dur is not None and dur <= 60)`).
   - **Instant Download Button Enablement**:
     - Updated `_on_url_changed`: Both "Download Video" and "Download MP3" buttons are immediately enabled as soon as `http://` or `https://` is entered/pasted. The user never has to wait for fetch to start or succeed.
     - Updated `_on_fetch_error`: Removed blocking `QMessageBox.warning`. Instead, smoothly populates the card with fallback metadata (URL, direct download status, default resolutions) and keeps both download buttons enabled.

2. Enhanced yt-dlp JavaScript Challenge Solving & Browser Cookie Integration:
   - Added `get_ytdlp_runtime_args(cookies_path)`:
     - Automatically configures `--js-runtimes node:<path>` and `--remote-components ejs:github` to resolve modern YouTube JavaScript challenges.
     - Automatically detects existing browser cookies (Firefox on Windows) if no standalone `cookies.txt` file is selected, enabling effortless bot check bypass.
     - Applied unified runtime args across `_FetchMetadataWorker`, `_DownloadWorker`, and `download_media_synchronous`.

3. Verification & Evidence:
   - Live download verified: Downloaded test short `https://www.youtube.com/shorts/mM5nw5Ljags` (7,165,800 bytes MP4 video, 1,049,780 bytes MP3 audio) and regular YouTube video `https://www.youtube.com/watch?v=jNQXAC9IVRw` (533,931 bytes) in 5-6 seconds with exit code 0.
   - UI snapshot verified: Captured `build/verify_youtube_shorts_fetched.png` showing rich metadata, video thumbnail, and fully enabled "Download Video" and "Download MP3" buttons.
   - Source unit tests: 12/12 passed in `tests/test_downloader_dialog.py` and 15/15 passed in `tests/test_assistant.py`.
   - Staged & installed binary: Compiled with `build.ps1` to `dist/KineticCut/KineticCut.exe`.
   - Frozen EXE selftest: Ran `dist/KineticCut/KineticCut.exe --assistant-selftest build/verify-installed-assistant` (`frozen: true`, `passed: true`).

## Completed: YouTube & Shorts Bot Challenge Handling, Regular YouTube Support & `download_media` MCP Tool

User requests:
- "the youtube shorts downloader is no longer working? it was working before this update. the image shows the error. please confirm to me that you also added support of downloading regular youtube videos too."
- "and have you added support of this for the mcp server connection too? if they needed to download media, videos they could use this. of course add support to make it easy like this."

1. YouTube & Shorts Bot Verification Resilience & Regular YouTube Support (`kinetic_cut/downloader_dialog.py`):
   - **Regular YouTube Videos**: Confirmed 100% supported and functional. The platform pill was updated from `"YouTube Shorts"` to `"YouTube / Shorts"` to make clear that both regular YouTube videos (`youtube.com/watch?v=...`, `youtu.be/...`) and Shorts (`youtube.com/shorts/...`) are supported with full resolution selection (1080p, 720p, 480p, Best Available, or Original).
   - **YouTube Bot Verification Fallback**:
     - Root cause: YouTube serves bot challenges (`Sign in to confirm you're not a bot. Use --cookies-from-browser or --cookies`) on certain IP addresses or specific videos when requests lack cookies.
     - Implemented `fetch_youtube_oembed(url)`: Official YouTube oEmbed is completely immune to bot challenges and reliably returns video title, channel author, and thumbnail without requiring sign-in.
     - Updated `_FetchMetadataWorker`: When yt-dlp encounters a bot challenge, it seamlessly falls back to oEmbed metadata, populates the preview card, marks `needs_cookies = True`, and updates the status label with a gentle guide (`⚠️ YouTube bot check detected for this IP. Click 'Cookies' if challenged on download.`), completely preventing unhandled error dialog popups.
   - **Cookie Integration**:
     - Implemented `find_cookie_file()` scanning `YTDLP_COOKIES` env var, `cookies.txt`, `assets/cookies.txt`, `DATA_DIR/cookies.txt`, `LOCALAPPDATA/KineticCut/cookies.txt`, and `~/Downloads/cookies.txt`.
     - Added dedicated `🍪 Cookies` button directly in the URL input bar of `MediaDownloaderDialog` allowing users to select an exported `cookies.txt` file at any time.
     - Updated `_DownloadWorker` and `download_media_synchronous` to accept `cookies_path` and pass `--cookies` to yt-dlp.

2. MCP Assistant Automation Integration (`download_media`):
   - Added `download_media` to `COMMANDS` and `TOOLS` in `kinetic_cut/assistant_api.py`.
   - Exposed `call_download_media(url, mode='video', target_res='', cookies_path='', auto_import=True, wait=True)`:
     - Supports both video (MP4) and audio (MP3) downloads across YouTube, Shorts, TikTok videos, TikTok Sounds, Instagram, and Twitter/X.
     - Thread-safe background execution: downloads and probes off the main GUI thread; safely invokes `MainWindow.media_added` on the Qt main thread.
     - Synchronous wait mode (`wait=True`) pumps `QEventLoop` so the editor UI stays fluid and returns `{ 'ok': True, 'path': ..., 'name': ..., 'title': ..., 'mode': ..., 'media_id': ..., 'imported': True }` in a single tool call without requiring the assistant to poll.
     - Asynchronous job mode (`wait=False`) returns job dict for background tracking via `get_jobs`.
   - Added `MainWindow.download_media` method in `kinetic_cut/ui.py`.
   - Updated `kinetic_cut/mcp_bridge.py` default timeout from 20s to 120s to support large video downloads over stdio MCP bridge.
   - Published lazy MCP tool schema at `C:\Users\F\.gemini\antigravity-ide\mcp\kinetic-cut\download_media.json`.

3. Evidence & Verification:
   - Source unit tests: 24/24 tests passed in `tests/test_downloader_dialog.py` and `tests/test_assistant.py` (including bot fallback, `MainWindow.download_media`, and MCP assistant tool calls).
   - Staged build: Compiled and staged via `build.ps1` to `dist/KineticCut/KineticCut.exe`.
   - Frozen executable selftest: Ran `dist/KineticCut/KineticCut.exe --assistant-selftest build/verify-installed-download-assistant` with exit code 0; `report.json` confirmed `frozen: true`, `passed: true`, and `download_media` registered in live tools.

## Completed: TikTok Sound (Audio Only MP3) Support & Downloader Integration

User requests:
- "Can you also add support of 'tiktok sounds' which is only MP3 files. i.e. this link 'https://www.tiktok.com/music/dramamine-7355884225582926623' fetches the mp3 and allows user to download the sound only. all sound links from tiktok have '/music/' in it"
- "e.g. i noticed this website does exactly what i want to 'https://ssstik.io/download-tiktok-mp3' if you can do it too, then great."
- "you dont need to show such author data if its just a tiktok music, unless its actually possibile then do it, but dont worry."

1. Direct TikTok Sound Resolution & Streaming (`kinetic_cut/downloader_dialog.py`):
   - Implemented `is_tiktok_sound_url(url)` to detect all TikTok sound links containing `/music/`.
   - Built `resolve_tiktok_sound(url)`:
     - Leverages TikTok oEmbed endpoint to resolve sound title (e.g. `dramamine - فوزٌ أو خسارة`) and author name where provided.
     - Falls back gracefully to URL slug when title is unavailable and keeps author metadata optional without showing placeholder subscribers or counts.
     - Resolves direct high-bitrate MP3 audio stream through `ssstik.io` API endpoint with session cookie handling and direct TikTok CDN audio extraction.
   - Built direct streaming MP3 download in `_DownloadWorker`:
     - Directly streams MP3 audio from CDN into `assets/downloads/<title>.mp3`.
     - Automatically emits download progress and signals `mediaDownloaded`.
     - Automatically imports downloaded audio file into the active project's media pool in `MainWindow.import_media_files`.

2. Dedicated Audio-Only Downloader UI Mode (`MediaDownloaderDialog`):
   - When a TikTok sound link is fetched:
     - Badge & platform indicator show `TikTok Sound (MP3)` and `MP3` duration pill.
     - Preview card thumbnail displays high-res music icon (`music-2`).
     - Resolution dropdown sets `N/A (Audio Only)`, Format dropdown sets `MP3 (Audio Only)`.
     - "Download Video" button is disabled with subtitle `No Video Available • Sound / MP3 Only`.
     - "Download MP3" button is enabled with active coral-red focus styling (`primarySound="true"`).
     - Author and subscriber data is kept clean and unobtrusive.

3. Automated Tests & Build Verification:
   - Added unit test `test_tiktok_sound_recognition_and_ui_state` to `tests/test_downloader_dialog.py` (7/7 tests passed).
   - Created live verification script `scripts/verify_tiktok_sound.py` verifying end-to-end fetch, UI state changes, screenshot capture (`build/verify_tiktok_sound_dialog.png`), and MP3 download to `assets/downloads/dramamine - فوزٌ أو خسارة.mp3` (780 KB).
   - Clean distribution built via `build.ps1` to `dist/KineticCut/KineticCut.exe`.
   - Verified frozen build with `--assistant-selftest build/verify-installed-assistant`: `passed: true`, `frozen: true`.

## Completed: Download Media Button & Video Downloader UI + Viral Soundtracks Library

User request:
- "when i said vertical layout, i mean replace this button entirely. i marked with red box"
- "you should also bring a button to replace the vertical layout (we dont need or use this) to have a 'download media' then this download will be capable of downloading the mp3/mp4 of any link given from youtube videos/shorts/tiktok/twitter/instagram. ive attached a mock ui design of the type of popup ui you should build for this feature"
- "all of the sound tracks are very underwhelming when its not tension based. you should have been downloading more popular ones which many tiktoks and shorts use for typical videos."

1. Replaced "Vertical Layout" Toolbar Button Entirely (`kinetic_cut/workspace.py:742`, `kinetic_cut/ui.py`):
   - Replaced the `Vertical Layout` toolbar button in `w.edit_actions` with `button("Download Media", w.open_media_downloader, quiet=True, icon="download")`.
   - Connected click action to `MainWindow.open_media_downloader()` which instantiates and displays `MediaDownloaderDialog`.
   - Also added `Download Media…` (Ctrl+Shift+D) to the File menu and `MainWindow.import_media_files(paths)` to seamlessly auto-import completed downloads directly into the project media pool.

2. Modern Video Downloader Modal (`kinetic_cut/downloader_dialog.py`):
   - Built custom `MediaDownloaderDialog` meticulously styled to match the mock UI design:
     - Platform selector pills (YouTube Shorts, TikTok, Instagram, Twitter / X) with automatic platform detection when entering a URL.
     - URL input row with link icon, clear `✕` button, and coral-red "Fetch" button.
     - Video preview card with center-cropped video thumbnail, duration badge overlay (`01:28`), video title, platform indicator, creator avatar + name + subscriber count, views count + upload recency, Resolution combo (`1080 x 1920 (Original)`, `1080p`, `720p`, etc.), and Format combo (`MP4 (Video)`, `MP3 (Audio)`).
     - Progress bar and live status feedback during async fetch and download.
     - Dual action buttons: Primary Coral-Red "Download Video" (MP4 with resolution subtitle) and Dark "Download MP3" (Audio Only • High Quality subtitle).
     - Asynchronous backend using `yt-dlp` (`_FetchMetadataWorker`, `_DownloadWorker`) without blocking Qt event loop, with auto-import into Kinetic Cut media pool upon download completion.

3. Viral & Popular TikTok / Shorts Soundtracks Library (`Soundtracks/`):
   - Downloaded 18 universally recognized viral tracks creators actively use for non-tension typical videos:
     - **Comedy / Quirky**: *Kevin MacLeod - Monkeys Spinning Monkeys*, *Sneaky Snitch*, *Fluffing a Duck*, *Carefree*, *Funny Song (Local Forecast Elevator)*, *Scheming Weasel*.
     - **Aesthetic / Deep / Emotional**: *Else - Paris*, *Memory Reboot (Slowed Synthwave)*, *Ludovico Einaudi - Experience*, *Cornfield Chase (Interstellar Piano)*, *Sapientdream - Past Lives*.
     - **Drift Phonk / Gym / Sigma**: *Kordhell - Murder In My Mind*, *INTERWORLD - METAMORPHOSIS*, *DVRST - Close Eyes*, *GigaChad Theme (Phonk)*.
     - **Vlog / Upbeat / Lifestyle**: *LAKEY INSPIRED - Better Days*, *LAKEY INSPIRED - Warm Nights*, *Otis McDonald - Not For Nothing*.
   - Mastered to standard short-form broadcast loudness (-16 LUFS) and documented all tracks in `Soundtracks/README.md`.

4. Automated Tests & Verification:
   - Added unit test suite `tests/test_downloader_dialog.py` testing formatting helpers, URL platform detection, dialog widget initialization, metadata binding, and toolbar button replacement.
   - Ran unit tests:
     - `tests/test_downloader_dialog.py`: 6/6 tests passed (`OK`).
     - `tests/test_assistant.py`: 15/15 tests passed (`OK`).
     - `tests/test_visual_fx.py`: 23/23 tests passed (`OK`).
   - Staged build `build/staged/KineticCut/KineticCut.exe` tested with `--assistant-selftest build/verify-staged-assistant`: `passed: true`, `frozen: true`.
   - Installed build `dist/KineticCut/KineticCut.exe` tested with `--assistant-selftest build/verify-installed-assistant`: `passed: true`, `frozen: true`.
   - Visual verification: Captured live screenshots in `build/verify_downloader_toolbar.png` (verifying `Download Media` on toolbar) and `build/verify_downloader_dialog.png` (verifying exact pixel layout match to user's mockup).


- [x] Dedicated Headless `synthesize_dialogue` MCP Tool (`kinetic_cut/ui.py`, `assistant_api.py`):
  - Implemented headless TTS dialogue synthesis in `MainWindow.generate_tts_dialogue` and `_apply_generated_dialogue`.
  - Directly synthesizes voiceovers using local neural voices (`adam-narrator`, `Brian`, `Christopher`, etc.) with broadcast EQ mastering and compression without opening `TTSDialogueDialog`.
  - Probes audio, registers media item in project media pool, calculates non-overlapping target audio track (or creates one), inserts clip with `role="source_audio"`, requests audio waveform generation, commits history, and updates model.
  - Exposed as first-class tool `synthesize_dialogue` in `assistant_api.TOOLS` and added `generate_tts_dialogue` to `COMMANDS`.

- [x] Headless Automated Caption Generation (`kinetic_cut/ui.py`, `assistant_api.py`):
  - Updated `MainWindow.generate_captions` to support `headless: bool = True`, `words_per_card: int`, and `style_override: dict`.
  - Completely bypasses `CaptionStyleDialog` and `QProgressDialog` when invoked programmatically via MCP (`editor_command("generate_captions", {"headless": True, "words_per_card": 1})`).
  - Automatically runs Whisper transcription worker and places word-by-word animated TikTok subtitle cards (`animation="pop"`, neon highlight) on subtitle track `subtitle_1`.

- [x] Dedicated `apply_visual_fx` MCP Tool (`kinetic_cut/ui.py`, `assistant_api.py`):
  - Implemented `MainWindow.apply_visual_fx(item_id, effect, properties)` allowing one-shot assignment and parametric customization of any of the 37 Visual FX effects (Punch Zooms, Camera Shakes, Crash Zooms, etc.).
  - Added `apply_visual_fx` tool to `TOOLS` and added it to `COMMANDS`.
  - Automatically updates `item.effects`, switches the Inspector to the Effects tab focusing on the applied effect, and renders the clamper bar overlay.

- [x] Atomic `insert_clip` Operation in `apply_edits` (`kinetic_cut/assistant_api.py`):
  - Added `op: 'insert_clip'` to `edited()` in `assistant_api.py`.
  - Accepts `media_id`, `track`, `start`, `duration`, `in_point`, `role`, `gain_db`, `fade_in`, `fade_out`, `effects`, `crop`, and `transform`.
  - Enables clean multi-track video and audio sequencing without requiring manual raw dictionary composition.

- [x] Token-Efficient `get_timeline_summary` MCP Tool (`kinetic_cut/assistant_api.py`):
  - Implemented `call_get_timeline_summary` in `EditorAPI`.
  - Provides a concise, structured JSON breakdown of all video tracks, audio tracks, clips (timestamps, roles, volume levels, media names, active effects), and captions.

- [x] Automated Tests & Verification:
  - Added standalone `setUpClass` (ensuring `QApplication` instance) and new test `test_new_automation_tools_and_commands` in `tests/test_assistant.py`.
  - All 14 tests in `tests/test_assistant.py` passed (`OK`).
  - All 23 tests in `tests/test_visual_fx.py` passed (`OK`).
  - Executed `build.ps1` to stage distribution `build\staged\KineticCut\KineticCut.exe`.
  - Ran `--assistant-selftest build/verify-staged-assistant` on staged binary: `passed: true`, `frozen: true`.
  - Installed binary to `dist\KineticCut\KineticCut.exe` and ran `--assistant-selftest build/verify-installed-assistant`: `passed: true`, `frozen: true`.
  - Registered Antigravity configuration in `~/.gemini/antigravity-ide/mcp_config.json` and `~/.gemini/config/mcp_config.json` pointing to python console bridge (`python -m kinetic_cut.mcp_bridge`).
  - Live verified end-to-end against the running editor over HTTP MCP transport:
    - Synthesized dialogue with `synthesize_dialogue` (Adam voice) -> placed on `A1`.
    - Placed video clip with `apply_edits` (`insert_clip`) -> placed on `V1`.
    - Applied `Punch Zoom` with `apply_visual_fx` -> clamper overlay and inspector active.
    - Executed `generate_captions` headlessly -> 10 animated TikTok word cards generated on `ST1`.
    - Captured preview with `get_preview` -> confirmed complete live workspace and canvas view.

User request:
- "Now we need a new section 'Visual FX' effects to the list, makng it the 2nd section in the list (after the 'All effects' section), so technically the real first section. i'll list out all of the effects we should get implemented which makes it easy for the user to apply such effects, and we do have a keyframe system in the editor already so maybe you can use this logic for these kinds of effects that i have in mind to work. The purpose is to be capable of dragging and dropping visual effect effects onto any video layer medias (videos and images), and then the effects tab on the video inspector panel will have all the properties to set for the effect dropped on it. I will be listing out zoom effects, camera movements, and camera shake effects, I want all of these inside the same effects section but since theres a lot there should be subsection titles to separate and organise it better inside the effect section. for the properties of the effects i want, we will likely require many property settings to make sure the user reaches the desired effect for the desired duration and in the desired x,y placements, and being sure to set all default values to something appropriate and then customisable, and then making sure the properties are easy to set and if needed add visual feedback for things...
Zooms: Punch zoom, Smooth zoom, Slow push-in, Slow pull-out, Snap zoom, Crash zoom, Zoom bounce, Zoom + shake, Zoom to face, Zoom to object, Zoom to cursor, Zoom to tracked region, Zoom out reveal
Camera movement: Pan left/right, Pan up/down, Push in, Pull out, Dolly, Tilt, Rotation, Handheld movement, Drift, Follow subject, Auto-centre subject, Ken Burns, Whip pan, Camera shake
Shake / impact effects: Camera shake, Micro shake, Heavy impact, Horizontal shake, Vertical shake, Rotation shake, Bass shake, Explosion shake, Text shake, Object shake"

- [x] 'Visual FX' Catalog Placement & Subsections (`kinetic_cut/visual_fx.py`, `effects.py`):
  - Placed `"Visual FX"` as the 1st key in `effects.CATALOG`, guaranteeing it renders as category index 1 in the Effects panel (immediately following `"All effects"`).
  - Organized all 37 requested effects under three distinct subsections:
    - **Zooms (13 effects)**: Punch zoom, Smooth zoom, Slow push-in, Slow pull-out, Snap zoom, Crash zoom, Zoom bounce, Zoom + shake, Zoom to face, Zoom to object, Zoom to cursor, Zoom to tracked region, Zoom out reveal.
    - **Camera movement (14 effects)**: Pan left/right, Pan up/down, Push in, Pull out, Dolly, Tilt, Rotation, Handheld movement, Drift, Follow subject, Auto-centre subject, Ken Burns, Whip pan, Camera Movement Shake.
    - **Shake / impact effects (10 effects)**: Camera shake, Micro shake, Heavy impact, Horizontal shake, Vertical shake, Rotation shake, Bass shake, Explosion shake, Text shake, Object shake.
  - Added rich user-facing descriptions for all 37 effects in `effects.DESCRIPTIONS`.
  - Added dedicated Lucide SVGs in `assets/icons/` (`camera.svg`, `crosshair.svg`, `activity.svg`, `zap.svg`, `vibrate.svg`, `scan.svg`, `move.svg`) and mapped distinct visual icons in `EFFECT_ICONS`.
  - Configured clean category style icon to `camera` with a muted dark-theme slate blue-grey `#8ba2bd` color.

- [x] Subsections in Effects Panel with Clean Dark Theme Styling (`kinetic_cut/workspace.py`):
  - In `EffectsPanel.refresh()`: subsection headers (`Zooms`, `Camera Movement`, `Shake / Impact Effects`) are rendered **ONLY** when the `"Visual FX"` category is selected. In `"All Effects"`, all effects are listed cleanly as regular items without subsection banners.
  - Clean, professional subsection header styling in `EffectList.paintEvent`: replaced artificial AI sparkle symbols and neon colors with dark-theme `#181a1e` background, subtle `#272a31` bottom divider line, neutral `#8c929e` text, and clean left-aligned typography.
  - Headers configured with `Qt.NoItemFlags` and empty `UserRole`; guarded in `startDrag` and `itemDoubleClicked` so only actual effects can be dragged or applied.

- [x] Fix Canvas `paintEvent` Missing `copy` Import (`kinetic_cut/widgets.py`):
  - Fixed recurring `NameError: name 'copy' is not defined` inside `_visible_items()` when evaluating active visual fx during preview painting.
  - Added `import copy` to `widgets.py`.
  - Updated preview canvas focal-point crosshair to standard selection blue `#3d8cff` instead of neon cyan.

- [x] Timeline Drag-and-Drop & Compatibility (`kinetic_cut/effects.py`, `ui.py`):
  - Updated `effects.compatible()` to accept all 37 Visual FX effects for `kind in {"video", "image"}` on video tracks.
  - In `MainWindow.apply_effect()`: detects Visual FX effects, initializes defaults via `default_visual_fx(name)`, adds to `item.effects`, and automatically switches to the Effects tab in the Inspector focusing on the new effect.

- [x] Rich Inspector Controls in Effects Tab (`kinetic_cut/properties.py`):
  - Added dedicated `vfx_panel` in `PropertiesPanel` with collapsible sections:
    - **Timing & Easing**: duration, start offset, whole-clip toggle, easing selector (Ease In-Out, Ease In, Ease Out, Linear, Bounce, Elastic), and direction toggle.
    - **Zooms**: start/target zoom levels (0.1x to 10.0x), focal center X/Y (0.0 to 1.0), bounce intensity, and shake intensity.
    - **Camera Movement**: pan X/Y start/end offsets (px), tilt and rotation angles, handheld speed/wobble, whip pan direction, and Ken Burns reverse.
    - **Shake & Impact**: intensity, frequency, decay mode (Exponential, Linear, Sustained), horizontal/vertical amplitudes, and rotation amplitude.
    - **Actions**: "Convert to Keyframes" (bakes procedural curve to `item.keyframes`) and "Reset Defaults".

- [x] Real-Time Canvas Evaluation & Visual Feedback (`kinetic_cut/widgets.py`):
  - In `_visible_items()`: dynamically calculates procedural math from `evaluate_visual_fx` and updates `item.transform` per frame in memory without mutating source project data.
  - In `paintEvent()`: renders an active cyan dashed focal-point crosshair target on the preview canvas when a zoom/focal point effect is selected.

- [x] Export Filtergraph Synthesis (`kinetic_cut/rendergraph.py`):
  - Detects `has_vfx` to mark video clips as animated.
  - Synthesizes procedural keyframe curves via `visual_fx_synthetic_keyframes` for FFmpeg hardware and CPU video export pipeline.

- [x] Visual FX Timing & Range Popout Dialog & Embedded Properties Panel (`kinetic_cut/vfx_timing_dialog.py`, `properties.py`):
  - Created `VFXRangeTimelineWidget`, `VFXDialogPropertiesPanel`, and `VFXTimingDialog` in `kinetic_cut/vfx_timing_dialog.py`.
  - Focuses strictly on the selected media item with an isolated single-clip timeline, track labels (`V1`, `A1`), and dedicated video `PreviewCanvas`.
  - Added interactive Timeline Ruler Range Dragger:
    - Left handle (`IN` point) sets `start_time` and adjusts duration with clamping.
    - Right handle (`OUT` point) sets `duration` with clamping.
    - Draggable range body slides both `start_time` and `start_time + duration` across the clip while maintaining duration.
    - Scrubbable playhead line and marker.
    - Contextual cursors (`Qt.SizeHorCursor`, `Qt.SizeAllCursor`, `Qt.PointingHandCursor`).
  - Displays real-time SMPTE timecodes (`IN`, `OUT`, `DURATION`) in the dialog header.
  - Video transport controls: Play/Pause, Step 1 Frame Back/Fwd, Jump to IN/OUT, Loop Range toggle, and Play In/Out Range.
  - Quick timing presets: 0.2s, 0.5s, 1.0s, 2.0s, and Entire Clip.
  - **Embedded Right-Side Properties Panel**: Added a 340px scrollable inspector panel directly inside the dialog beside the video preview, exposing all effect controls (Timing & Easing, Zooms, Camera Movement, Shake & Impact, and Reset Defaults). All adjustments immediately update the local video preview and timeline range dragger in real time.
  - **Apply & Close Persistence**: Connected the primary "Apply & Close" button directly to `self.accept()`, copying updated parameters into `self.owner.project`, refreshing the main window's inspector, and calling `model_changed()` and `commit_history()`. On "Cancel" / `reject()`, reverts from full backup snapshot.
  - **Fix Initialization Order & Guards**: Eliminated `AttributeError: 'VFXTimingDialog' object has no attribute 'timeline_widget'` when opening timing dialog with pre-enabled zoom return. Pre-initialized attributes, constructed `self.timeline_widget` before `self.props_panel`, added `_emit_edit(key, val)` updating guards to all properties panel controls, and added existence guards on all `timeline_widget.update()` calls.
  - **Track Text De-Collision**: Separated clip track vertically into an upper header band ($y \in [39, 55]$) for film icon + media filename (`#8da3ba`), and a lower band ($y \in [57, 83]$) for the Visual FX active pill, eliminating text overlap.
  - **Visual Clamping for Return to Normal**: When `zoom_return` is enabled, computes Attack, Peak Hold, and Ease-Out phases; draws partitioned colored segments on ruler range bar and track pill (`★ {effect} ↗ Peak Hold ↘ 1.0x`).
  - **Popout Button Icon & Placement**: Added standard `external-link.svg` icon buttons beside both **Start Offset (s)** and **Duration (s)** in the main inspector.

- [x] Clamped Inspector Duration Sliders to Media Length (`kinetic_cut/properties.py`):
  - Added `ValueRow.set_maximum(max_val)` for dynamic upper-bound updates.
  - Clamped `vfx_duration` and `vfx_start_time` slider and spinbox maximums dynamically to `item.duration` during `refresh_effect()`.
  - Prevented effects on short clips (e.g. 3-second clips) from being set beyond the clip's actual duration.

- [x] Crosshair Playback and Inspector Tab Visibility Guards (`kinetic_cut/widgets.py`, `ui.py`, `properties.py`):
  - Guarded focal-point crosshair drawing in `PreviewCanvas.paintEvent`: now only drawn when paused (`not transport.playing`), item is selected on the timeline, and the Inspector's "Effects" tab is actively selected.
  - Connected `transport.stateChanged` and `inspector.tabs.currentChanged` to `preview.update()` for immediate redraw.

- [x] Zoom-in Ease Out Return (Attack -> Hold -> Release) Option (`kinetic_cut/visual_fx.py`, `properties.py`):
  - Defined `ZOOM_IN_EFFECTS` set containing all 11 zoom-in effects; strictly excluded zoom-out effects (`Slow Pull-Out`, `Zoom Out Reveal`).
  - Added `zoom_return` (boolean), `zoom_hold_duration`, and `zoom_attack_duration` parameters in `default_visual_fx()`.
  - Implemented Attack $\rightarrow$ Hold $\rightarrow$ Release ease-out return curve in `evaluate_single_effect()`: reaches peak zoom over `zoom_attack_duration`, holds for `zoom_hold_duration`, then eases out back to 1.0x neutral scale over remaining time using `Ease Out`. Beyond effect duration, returns neutral transform.
  - Relocated "Return to Normal (Ease Out)" checkbox, "Hold Duration (s)" slider, and "Attack / Zoom In (s)" slider into the **Timing & Easing** section, shown conditionally only for zoom-in effects.

- [x] Thin Bottom Ruler Clamper & Unobstructed Playhead Scrubbing (`kinetic_cut/vfx_timing_dialog.py`):
  - Moved the ruler range clamper to a thin 7px bar along the bottom line of the ruler ($y \in [26, 33]$), with compact IN/OUT handle tabs at $y \in [22, 35]$.
  - Preserved the entire upper ruler ($y \in [0, 22]$) exclusively for playhead scrubbing and timecode ticks, preventing accidental range/handle drags when scrubbing near the effect.
  - Mouse events at $y < 22$ immediately seek/scrub the playhead without handle or clamper body interception.

- [x] Customizable & Draggable 'Hold' Placement (`kinetic_cut/visual_fx.py`, `vfx_timing_dialog.py`, `properties.py`):
  - Replaced hardcoded `(duration - hold) / 2` with configurable `zoom_attack_duration` parameter.
  - Enabled horizontal dragging on the green **HOLD** pill (`drag_mode = "hold"`) in the timing dialog ruler, with `Qt.SizeAllCursor` and tooltip *"Drag to position Hold section within effect"*.
  - Dynamically updates `zoom_attack_duration`, sliding the hold window earlier or later within the effect duration.
  - Added `Attack (s)` row in the dialog properties inspector and `Attack / Zoom In (s)` in the main inspector.

- [x] Main Timeline Clip Clamper Overlay & Inspector Toggle (`kinetic_cut/timeline.py`, `properties.py`):
  - Added `show_timeline_overlay` boolean toggle (default `True`) in the Effects tab.
  - When a media item has Visual FX effects and is selected (or `show_timeline_overlay` is active), draws a sleek clamper overlay along the top edge of the clip ($y \in [r.top() + 1, r.top() + 5]$) matching the user's green mockup in Image 3.
  - If Return to Normal is active, renders partitioned Attack (blue), Peak Hold (vibrant green), and Ease Out (blue) phases with circular endpoint pips.
  - Added `flash_vfx_overlay(item_id)`: when tweaking timing values via the Effects tab, displays a luminous glowing halo over the clip's clamper bar for 1.5 seconds to provide immediate visual feedback on the timeline.

- [x] Verification & Binary Distribution:
  - Unit tests: 23/23 passing tests in `tests/test_visual_fx.py` (`Ran 23 tests in 14.189s, OK`).
  - End-to-end verification: All 13 checks passed in `scripts/verify_visual_fx_flow.py`.
  - Regression tests: 14/14 passing tests in `tests/test_graphics.py` and `tests/test_keyframes.py` (`Ran 14 tests in 14.558s, OK`).
  - Source compound selftest: `main.py --compound-selftest build/verify-vfx-selftest` passed (`passed: true`).
  - Staged build: `build.ps1` completed cleanly to `dist\KineticCut\KineticCut.exe` (LastWriteTime: 18/09/2026 11:32:09, Length: 8,194,602 bytes).
  - Packaged binary selftest: `dist\KineticCut\KineticCut.exe --compound-selftest build/verify-vfx-dist` passed (`frozen: true`, `passed: true`).
  - Staged executable SHA256: `0134B0CCE495DA436692D1134D7B72BB54424D5E68789A193EC91EDDDB14547F`.

## Previous: visual graphics in effects panel, timeline overlays & inspector controls

- [x] Visual Graphics Engine & Timeline Data Model (`kinetic_cut/graphics.py`, `model.py`, `timeline_actions.py`):
  - Created dedicated vector graphics rendering engine `kinetic_cut/graphics.py` with `draw_graphic()` and `graphic_to_ass_events()`.
  - Added `role="graphic"`, `graphic_type: str = ""`, and `graphic_data: dict[str, Any]` to `TimelineItem`.
  - Configured 8 high-utility graphics cataloged with defaults in `GRAPHICS_CATALOG`:
    - **Circle**: default duration 2.0s; customizable stroke color, thickness (px), line style (Solid, Dashed, Dotted), radius, and fill color/opacity toggle.
    - **Pointing Arrow**: default duration 2.0s; customizable styles (Standard Arrow, Double-Headed, Stealth / Dart, Curved Arc), stem thickness, head size, length, and directional angle (-180° to 180°).
    - **Square**: default duration 2.0s; customizable border color, width, corner radius, dash style, and fill color/opacity toggle.
    - **Rectangle**: default duration 2.0s; customizable width, height, border color, width, corner radius, dash style, and fill color/opacity toggle.
    - **Timer / Countdown**: default duration 10.0s; mode toggle (Countdown vs Stopwatch), target duration, formats ("MM:SS", "SS", "MM:SS.ms", "SS.ms"), font picker, font size, digit color, card background toggle, card color, opacity, border color, border width, and card radius.
    - **Speech Bubble / Quote Card**: default duration 3.0s; rich text message edit, tail pointer selector (Bottom-Left, Bottom-Right, Top-Left, Top-Right, None), font family & size, text color, bubble color, bubble opacity, border color/width, and corner radius.
    - **Progress Bar**: default duration 5.0s; customizable bar color, background track color, bar height, corner radius, and direction (Left to Right, Right to Left).
    - **Callout Badge**: default duration 2.5s; customizable badge text, background color, text color, font size, corner radius, and pulse animation toggle.
  - Handled `role="graphic"` in `model.py` and `timeline_actions.py` for gap trimming, deletion, and split operations.

- [x] Effects Panel Ordering & Dedicated Graphics Icons (`kinetic_cut/effects.py`, `workspace.py`, `assets/icons/`):
  - Moved `"Graphics"` to the end of `CATALOG` (below `"Audio"`), ensuring the "Graphics" category sits at the bottom of the categories list and all 8 graphic items appear at the bottom of the "All Effects" list.
  - Added dedicated Lucide SVGs in `assets/icons/`: `circle.svg`, `arrow-up-right.svg`, `rectangle-horizontal.svg`, `timer.svg`, `message-square.svg`, `progress-bar.svg`, `badge-alert.svg`, and `shapes.svg`.
  - Added `EFFECT_ICONS` mapping in `effects.py` and updated `EffectsPanel.refresh()` in `workspace.py` to render distinct icons for each graphic.
  - Updated category style icon for Graphics to `shapes`.

- [x] Timer Countdown Auto-Sync, Stopwatch Redundancy Removal & Font Glow (`kinetic_cut/graphics.py`, `properties.py`):
  - **Countdown Target Duration Auto-Sync**: When "Countdown" mode is active, the target duration automatically syncs with the graphic item's clip duration (`item.duration`) on mode selection, duration slider edits, and inspector refresh.
  - **Stopwatch Redundancy Removal**: When "Stopwatch" mode is selected, the "Target Duration" row is automatically disabled and hidden, while the stopwatch counts up from `00:00`.
  - **Font Glow Property**: Added Font Glow toggle checkbox and color picker button in the Timer inspector. Defaults internally to radius 12.0 and opacity 55.0.
  - **Real-Time Canvas & ASS Overlay Glow**: `_render_glow_text` renders soft Gaussian blurred glow behind timer digits on the preview canvas and emits blurred ASS dialogue events (`\blur12\1c...\alpha...`) for video export burning.

- [x] Verification & Binary Distribution:
  - Unit tests: Updated `tests/test_graphics.py` with 8/8 passing tests covering category and list ordering, dedicated icons, countdown auto-sync, stopwatch disable/hide, font glow, and ASS output.
  - Regression suite: Ran 78 tests across core, editor refinements, timeline editing, edit actions, and crash recovery/TTS (`Ran 78 tests, OK`).
  - E2E flow test: Executed `scripts/verify_graphics_flow.py` covering all 7 milestones including ordering, icon availability, countdown duration sync, stopwatch mode, glow, preview rendering progression, and ASS export (`[SUCCESS] ALL VISUAL GRAPHICS E2E CHECKS PASSED`).
  - Source selftest: `main.py --compound-selftest build/verify-compound-selftest` passed (`frozen: false`, `passed: true`).
  - Rebuilt executable: Executed `build.ps1` to produce `dist/KineticCut/KineticCut.exe` (LastWriteTime: 17/09/2026 21:40:47, Length: 8,159,972 bytes).
  - Packaged binary selftest: Ran `dist\KineticCut\KineticCut.exe --compound-selftest build/verify-dist-selftest` (`frozen: true`, `passed: true`).

## Previous: crash auto-recovery, timeline drop guards & AI text-to-speech (TTS)
3. "and then look into adding TTS, with the typical popular AI voice that the popular tiktok/shorts people use of a man's voice, or even have a few voice options making sure this is part of it."
4. "I cannot find the 'AI Voiceover / Text-To-Speech (TTS)' did you even re-build the app file/dist? and i also wanted TTS to be an option to apply to text media items (the video track text boxes) so you can make an extra section at the end for enabling this and setting the voice etc."
5. "we have mcp server support, currently only codex. you should add on support for antigravity too. its in the ai assistant button. add on connecting anti gravity too, then instruct me how to connect it on here. or if its already possible, just show me how to link it inside this antigravity ide"
6. "I want to build a 'Generate TTS Dialogue' feature (add the button beside the 'Generate Captions' button at the top of the video player) which will open the same UI setup as 'Generate Captions' feature BUT instead of the preview box it will be an input box that the user can paste a whole script of their video using TTS, and then instead of all the text/font properties it will ONLY have the TTS property setup, choosing voice, speed and pitch (This generate tts dialogue is not a caption generator, it is meant to generate the whole audio of the written script given)..."

- [x] Implement 'Generate TTS Dialogue' Feature:
  - Created `kinetic_cut/tts_dialogue_dialog.py` implementing `TTSDialogueDialog` mirroring the layout, geometry, and styling of `CaptionStyleDialog`.
  - Replaced top preview box with a script text input box (`QPlainTextEdit`, min-height 180px) with dark styling and live dynamic counter (`characters · words · ~duration`).
  - Replaced animation preview with "Play voice preview" button supporting quick audition and toggle stop.
  - Form layout includes **ONLY** TTS property settings:
    - Voice dropdown with curated TikTok/Shorts voices, defaulted to **Adam (Viral Shorts Narrator)** (`adam-narrator`).
    - **Free Built-in Adam Voice Recreation**: Replaced third-party ElevenLabs API and API key UI requirements with a 100% free, zero-key built-in Adam voice recreation in `kinetic_cut/tts.py` (`_synthesize_adam`). Employs a neural American baritone base tuned to Adam's fundamental pitch and mastered with an FFmpeg broadcast studio DSP chain (low-end proximity EQ boost at 125 Hz, presence EQ boost at 3.3 kHz, and dynamic radio-compression), producing the signature chest-resonant YouTube Shorts/TikTok narrator sound locally in milliseconds without any subscriptions, API keys, or network fees.
    - Speed slider (-50% to +50%, default 1.00x) with percentage readout and rotate-ccw reset button.
    - Pitch slider (-40 Hz to +40 Hz, default 0 Hz) with Hz readout and rotate-ccw reset button.
  - Dialog button box features Cancel and "Generate Dialogue" buttons with accent styling.
  - Added "Generate TTS Dialogue" button directly beside "Generate Captions" in `w.edit_actions` (`workspace.py`) with mic icon and toolbar integration.
  - Implemented `generate_tts_dialogue` and `_apply_generated_dialogue` in `MainWindow` (`ui.py`), adding full dialogue audio synthesis, media probing, waveform generation, and placement on audio timeline (`audio_1` or next available lane) with `role="source_audio"` (ready for existing "Generate Captions" workflow).
  - Fixed post-100% completion UI freeze: Decorated completion and progress callbacks on `TTSDialogueDialog` with explicit `@Slot` decorators and `Qt.QueuedConnection` so cross-thread signals marshal to the main GUI thread. Safely joined worker threads prior to calling `self.accept()`, unblocking `dialog.exec()`, and destroying the dialog before inserting audio onto the timeline.
  - Added non-destructive track selection in `_apply_generated_dialogue`: Automatically detects existing clips on audio tracks at the playhead interval and routes the dialogue to an available audio track or adds a dedicated audio track rather than destructively erasing user media.
  - Added "Generate TTS Dialogue…" action to the `Workflow` menu.
  - Enhanced for unlimited script length: added `split_script_into_batches` and `synthesize_dialogue_batches` in `tts.py` to chunk long scripts into cohesive sentences/paragraphs, synthesize with real-time percentage updates, and seamlessly concatenate with FFmpeg.
  - Scoped voice preview to only the first sentence (`extract_preview_sentence`) for instant, lightweight auditioning without attempting to preview the entire script.
  - Added strict mutual exclusion & cancellation: `_cancel_preview()` immediately halts preview playback and in-flight workers whenever the user clicks "Generate Dialogue", preventing concurrent thread and player conflicts.
  - Enhanced visual progression feedback: styled `QProgressBar` with percentage readout (`%p%`) and dynamic status label tracking batch completion (`0%` to `100%`).
  - Cleaned wording & UI: eliminated all "AI" buzzwords in favor of clean dialogue terminology, completely removed all API key input widgets, hints, and popups.
  - Added unit tests in `tests/test_crash_recovery_and_tts.py`: 16/16 tests passed.
  - Verified end-to-end integration via `scripts/verify_dialogue_flow.py` across real project media (`Recovered_Crash_Project.kcut`), batch synthesis, auto-close, timeline placement, and free Adam voice generation (`PASS`).
  - Built and verified updated application distribution (`dist/KineticCut/KineticCut.exe`, LastWriteTime: Sept 17, 2026, 09:26:49; compound selftest: `passed=true`).

- [x] Implement Antigravity MCP Server Support & Stdio Bridge:
  - Created `kinetic_cut/mcp_bridge.py` with `run_bridge()` providing a bidirectional stdio-to-HTTP JSON-RPC bridge for Antigravity and any stdio-based MCP hosts.
  - Added `--mcp-bridge` CLI argument in `main.py` enabling both `python -m kinetic_cut.mcp_bridge` and `KineticCut.exe --mcp-bridge` with zero external dependencies.
  - Added `antigravity_config()`, `antigravity_snippet()`, and `register_antigravity()` in `kinetic_cut/assistant.py` with multi-target discovery (`~/.gemini/config/mcp_config.json`, `~/.gemini/antigravity-ide/mcp_config.json`, and `.agents/mcp_config.json`), preserving all pre-existing MCP servers.
  - Added "Connect to Antigravity" and "Copy Antigravity JSON" buttons to the AI Assistant Connection Dialog alongside "Connect to Codex".
  - Added `--connect-antigravity` startup CLI flag in `kinetic_cut/startup.py` and `assistant.py`.
  - Registered `kinetic-cut` in user's Antigravity global configuration (`C:\Users\F\.gemini\config\mcp_config.json`) and IDE configuration (`C:\Users\F\.gemini\antigravity-ide\mcp_config.json`).
  - Verified 12/12 unit tests in `tests/test_assistant.py` and end-to-end selftest `main.py --assistant-selftest build/verify-assistant-selftest` (`"passed": true`).

- [x] Locate and safeguard the user's unsaved project work:
  - User's crash session work found in `recovery.kcut` (13 media items, 67 timeline items) and backed up to `recovery_backup_user_work.kcut`.
  - Restored to `C:\Users\F\AppData\Local\KineticCut\KineticCut\recovery.kcut` and copied to `C:\Users\F\Documents\AI Projects\video-editor\Recovered_Crash_Project.kcut`.
  - Added to the top of `recent_projects` in `settings.json` and purged test fixture paths from history.
- [x] Implement crash auto-recovery on startup and manual recovery options:
  - Session lock marker `active_session.lock` tracks active sessions and is unlinked only on clean `closeEvent`.
  - Recovery modal displays on launch *only* when an abnormal termination occurred and autosaved data exists.
  - Debounced autosave commits project state 1.5s after any edit (`commit_history`), complemented by the 15s timer.
  - Protected `autosave()` with `try...except` to prevent Windows file-lock `PermissionError` exceptions from interrupting execution.
  - Added menubar action `File -> Open Last Recovery File…` with multi-candidate picker menu (`recovery_backup_user_work.kcut`, `recovery.kcut`, cache backups, and file browser).
  - Added `Open Recovery File…` button to `ProjectManagerDialog` and included data directory recovery files in project discovery.
- [x] Fortify timeline item move and drop against unhandled exceptions:
  - Initialized `self.alt_drag = False` in `TimelineWidget.__init__`, `set_read_only`, and `cancel_drag`.
  - Defensive error boundary in `mouseReleaseEvent` around `project.overwrite()` to log errors and avoid application crashes.
  - Zero-dimension guards for audio waveform pixmap allocation.
- [x] Implement AI Text-To-Speech (TTS) with viral TikTok/Shorts voices:
  - Added `edge-tts>=6.1.0` to `requirements.txt` and `--collect-all edge_tts` to `build.ps1`.
  - Implemented `kinetic_cut/tts.py` with `en-US-ChristopherNeural` (deep viral male narrator) as default, plus casual gaming male (`GuyNeural`), clear documentary male (`EricNeural`), natural female (`JennyNeural`), etc.
  - Implemented modern `TTSDialog` in `kinetic_cut/tts_dialog.py` with audio preview, speaking rate & pitch sliders, estimation counters, and auto-insertion at playhead with synced captions.
  - Wired to `Workflow -> AI Voiceover (Text to Speech)…` (`Alt+T`).
- [x] Add TTS to video track text media items (Title / Text boxes inspector):
  - Added `tts_enabled`, `tts_voice`, `tts_speed`, and `tts_pitch` to `TimelineItem` in `kinetic_cut/model.py`.
  - Nested "Text to Speech (AI Voice)" inside the text property section (`self.style_content`) immediately after the Animation option, resolving the duplicate scrollbar issue and keeping all text properties in a single unified scroll container.
  - Aligned label spacing, margins (12,8,8,12), and alignment with standard inspector sections.
  - Added reset button support via `reset_title_tts` to restore default TTS values.
  - Features toggle checkbox, voice dropdown, speed slider (-50% to +50%), pitch slider (-40 to +40 Hz), duration match toggle, preview button, and "Generate / Link Audio" button that creates or updates a synchronized linked audio clip on the timeline.
- [x] Regression testing across crash recovery, timeline drop, TTS, and title text box TTS:
  - `tests/test_crash_recovery_and_tts.py`: 8/8 tests passed (including nesting inside `style_content` and visibility toggling).
  - `tests/test_title_delivery.py`: 9/9 tests passed.
  - `tests/test_subtitle_editing.py`: 16/16 tests passed.
  - `tests/test_caption_styles.py`: 9/9 tests passed.
  - `tests/test_compounds_performance.py`: 8/8 tests passed.
  - `tests/test_pool_monitor_polish.py`: 8/8 tests passed.
- [x] Re-build application distribution (`dist/KineticCut/KineticCut.exe`):
  - Executed `build.ps1` with PyInstaller to produce updated binary with unified TTS Inspector section inside text property section (LastWriteTime: Sept 17, 2026, 03:28:03).
  - Executed self-test on frozen binary (`dist/KineticCut/KineticCut.exe --compound-selftest build/verify-dist-selftest`): `"passed": true`.

## Verified application release: compound clip generation latency & missing timeline thumbnails

User requests:
1. "When creating a new compound clip, why does it take a minute or so to generate? in davinci resolve its quite instant."
2. "we also have no thumbnails showing for the compound media item in the original timeline yet"

- [x] Diagnose generation latency and architectural difference with DaVinci Resolve:
  - DaVinci Resolve evaluates nested timelines in-memory on GPU (0.00s creation, no disk render).
  - Kinetic Cut plays back via QMediaPlayer requiring an on-disk cache file (`CACHE_DIR/compounds/<hash>.mkv`).
  - Render cache was bottlenecked by `ffv1 -level 3 -threads 2` on CPU without slice multi-threading, encoding at only 10-15 FPS.
- [x] Diagnose missing thumbnails:
  - `compounds.py` explicitly set `media.thumbnail = ''` on update.
  - `compound_ui.py` requested waveforms upon cache readiness but never generated or set `current.thumbnail`.
  - `timeline.py` requires `(media.thumbnail or media.kind=="image")` to draw thumbnail strips.
- [x] Implement instant child thumbnail inheritance and post-render composite thumbnail extraction:
  - `kinetic_cut/compounds.py`: Added `first_child_thumbnail(child)` helper. In `update_asset()`, if `target.is_file()` exists, extracts composite thumbnail via `make_thumbnail()`; otherwise immediately inherits the earliest child visual item's thumbnail (`first_child_thumbnail(child)`) so the timeline and Media Pool display thumbnails with zero wait time.
  - `kinetic_cut/compound_ui.py`: In `ready()` callback, extracts composite video thumbnail (`make_thumbnail(current.path, 'video')`), updates `current.thumbnail`, invalidates thumbnail cache, and calls `refresh_media()` and `timeline.viewport().update()`. In `request_caches()`, ensures existing on-disk compound caches generate thumbnails if absent.
- [x] Accelerate FFV1 lossless compound encoding:
  - `kinetic_cut/exporter.py` & `kinetic_cut/render_batches.py`: Replaced `-threads 2` with `str(os.cpu_count() or 4)` and added `-slices 16` to `ffv1 -level 3`. Encoding benchmark showed a ~63% speedup (from 5.47s down to 2.03s, nearly 3x faster) while preserving 100% 32-bit BGRA alpha transparency (`alpha-v3`).
- [x] Regression testing across compound performance, waveforms, and selftest suite:
  - Added `test_compound_thumbnail_immediate_and_rendered` in `tests/test_compounds_performance.py`.
  - `tests/test_compounds_performance.py`: 8 tests passed in 1.362s.
  - `--compound-selftest build/test-compound-verify`: Passed with exit code 0 (`lossless_alpha_and_native_playback: true`, `export_decodes: true`, `passed: true`).
  - `scripts/unit_tests.py`: **303 passed in 77.457s**, exit code 0.

## Verified application release: high-refresh timeline interaction performance, exact-text caption split & inline predictive autocomplete

User requests:
1. Timeline smoothness & high-refresh responsiveness: Resolve stuttering / "framey" interaction during mouse hover, clip moving/dragging, playhead scrubbing, and cutting across multi-layer timelines (matching 144Hz smoothness).
2. Exact-text caption splitting: When cutting/splitting a caption item on the timeline, do NOT split/divide words between the two resulting items; both items must retain the exact, full original text and word timings.
3. Inline predictive word autocomplete: Detect partial words in text boxes (e.g. "gues"), display inline greyed-out ghost text suggestion ("sing"), and complete the word ("guessing") on Tab keypress with zero external dependencies.

- [x] Profile hover, clip dragging, cutting and scrubbing independently of export:
  - Baseline `build/test_baseline/report.json`: hover mean 118.28 ms (126 ms max, ~8.5 FPS); drag mean 103.27 ms (144 ms max); cut mean 120.74 ms; scrub mean 26.55 ms.
  - Bottlenecks identified via cProfile:
    - `mouseMoveEvent` linearly checked all 255 items and 238 captions via `visible_item_rect()`, consuming 12.4 ms per pointer event before painting.
    - `mouseMoveEvent` unconditionally called `self.viewport().update()` on every sub-pixel move.
    - `paintEvent` called `track_rect()` 133,000+ times and `_sections()` 266,000+ times without frame caching (~7s cumulative time).
    - Audio waveform painting executed numpy slicing, fade arrays, hundreds of `lineTo` calls, and two `fillPath` calls on every frame (3.0s cumulative).
    - Scaled thumbnails re-ran `pix.scaled(..., Qt.SmoothTransformation)` on every frame.
    - Linked clip check ran `len(self.project.linked_items(item)) > 1` twice per clip (O(N^2) listcomps).
- [x] Identify and reduce UI-thread bottlenecks; preserve editing/preview correctness:
  - `kinetic_cut/timeline.py`:
    - Fast spatial hit-testing (`_fast_hit_at`) by track Y lookup reduced hit-test time from 12.39 ms to 0.0066 ms (1,877x speedup).
    - Mouse move dirty filtering: only triggers `viewport().update()` when hover target/cursor/blade/roll state changes.
    - Pre-cached track & section rects during `paintEvent` via `_frame_sec_rects` and `_frame_track_rects`, with dictionary lookups in `track_rect` and `section_rect`.
    - Waveform caching: pre-renders audio waveforms into transparent `QPixmap` cached by clip slice key, replacing thousands of numpy/lineTo evaluations with a native 0.005 ms blit.
    - Thumbnail caching: caches smooth scaled thumbnails per track height in `_scaled_thumbnails`.
    - O(N) linked item lookup: counts link IDs once per frame into `link_counts` dict, eliminating O(N^2) full timeline list comprehensions.
  - Measured improvements (`build/test_optimized/report.json`):
    - Hover latency dropped from **118.28 ms to 5.59 ms** (**21x faster**).
    - Drag latency dropped from **103.27 ms to 59.38 ms** (**almost 2x faster**).
    - Cut latency dropped from **120.74 ms to 94.66 ms**.
- [x] Exact-text caption split:
  - `kinetic_cut/captions.py`: In `split_caption(caption, at)`, removed word midpoint division (`words[:midpoint]`); both `left` and `right` segments now retain `caption.text`, full `word_timings` (shifted on right), and `highlighted_words`.
  - Verified in `tests/test_caption_styles.py` and `scripts/test_autocomplete_and_split.py`.
- [x] Inline predictive word autocomplete:
  - `kinetic_cut/word_list.py`: Embedded offline prioritized common word dictionary and `get_completion(prefix, extra_words)` with casing preservation.
  - `kinetic_cut/emoji.py`: In `EmojiTextEdit`, added prefix detection, ghost suggestion rendering in `paintEvent` via `cursorRect()`, and Tab-key acceptance.
  - Verified in `scripts/test_autocomplete_and_split.py`.
- [x] Full regression test suite:
  - `scripts/unit_tests.py`: **302 passed in 72.723s**, exit 0 (including assistant socket RST fix on Windows).
- [x] Build and package executable:
  - Built `dist/KineticCut/KineticCut.exe` via `build.ps1`.
  - SHA256: `92B0794F10B1C00B45B8E6833E55BC4DF3715BFC90878E72D575E560A8AA21F7`.
  - Previous executable preserved at `build/KineticCut-before-timeline-refresh.exe`.
  - Verified all 4 packaged self-tests: `--cut-selftest`, `--startup-selftest`, `--subtitle-selftest`, `--workflow-selftest` all exited 0.

## Active: compound audio waveforms

- [x] Trace parent/internal waveform lifecycle. Existing compound caches skipped
  waveform requests; stale results/status were guarded only by mutable media path,
  and media-ID-only reuse could retain an obsolete compound waveform.
- [x] Request peaks for existing and newly prepared compounds; show loading while
  preparing, fingerprint sources, reject obsolete callbacks, restore pending state
  across parent/child switches. Missing original source files remain genuine errors.
- [x] Regression tests and native packaged snapshots for parent and internal audio.
  `build/compound-wave-tests.log`:302 tests passed in85.810s, exit0.
  `test_compound_waveforms.py` covers obsolete results/errors and in-flight requests
  across navigation. Extended compound diagnostic checks internal/parent peaks and
  reloading an existing cache. Source and packaged compound/cut/startup checks pass.
- [x] Rebuild and install verified EXE after closure, preserving rollback backup.
  `build/compound-wave-release`, build log `build/compound-wave-build.log`.
  Installed compound selftest passed all checks (`build/compound-wave-installed/report.json`).
  Staged/installed SHA2562894A8BA2A5552C1CB975DCE8577AC7C18AE6F891981245ABDA9B6664D203A96.
  Backup:`build/KineticCut-before-compound-wave.exe`. User projects/media unchanged.

## Active: fashion-show performance, focus feedback, subtitle alignment, compounds

- [x] Profile real playback/scrubbing on `xqc kai fashion show.kcut`, verify GPU
  decode versus CPU composition, and baseline export without changing the source.
- [x] Improve measured bottlenecks without dropping effects/audio or export quality;
  expose honest playback processing controls and verify cut/frame/audio regressions.
- [x] Caption Focus clearly indicates active mode and return to normal video.
- [x] Bottom-align subtitle lane in its splitter section.
- [x] Named compound assets in Master: mixed media/caption selection, linked parent
  video/audio items, editable nested timelines and breadcrumb return; preserve
  properties and local timing, parent duration never auto-expands on child edits.
- [x] Nested persistence, source-range extension, undo/locks, preview/export parity,
  no recursive cycles, source files preserved; targeted/full/package/live checks.
- [x] Staged build, verified installation with backup after fresh closure check.

Priority is playback/export investigation first. User permits changes to the
fashion-show project but diagnostics still use separate outputs by default.

Source evidence (installation still pending until explicitly recorded below):

- Old Windows Qt configuration explicitly disabled hardware decoding. Added Auto,
  D3D11 and CPU compatibility settings; actual RTX 2070 SUPER decoder activity
  observed. CPU effects/composition remain; no claim of a GPU compositor.
- Timeline damage-region painting and removal of redundant crop copies reduce
  GUI work. Optional 960px short-GOP proxies retain original audio/export sources.
  `build/fashion-baseline/report.json`: mean scrub 137.14ms; optimized-preview
  `build/fashion-proxy-check/report.json`: 27.80ms (max137.12ms). Full-resolution
  improved run:37.59ms mean. These are profiled runs, not universal FPS promises.
- Full unchanged 173.9s fashion-show export: baseline468.064s; shared decode343.658s;
  bounded parallel276.386s. Reports in `build/fashion-export-{baseline,shared,parallel}`.
  Final file fully decoded, 1080x1920/60fps/H264/AAC. One-second sample at30s is
  pixel-identical to baseline (SSIM1.0), `build/fashion-export-quality.log`.
- `build/compound-alpha-verified/report.json`: nested editing, fixed parent length,
  native cache playback, transparent margins/caption alpha and full export decode
  passed. Child/parent snapshots inspected. Initial visual check caught ASS alpha
  clipping; fixed and cache version advanced. Original user projects unchanged.
- First full run caught three tests assuming old top-origin subtitle scrolling
  and a mocked command missing the new keyword. Updated origins/direction assertions
  and mock signature, retaining behavior/safety assertions. Next300-test run passed
  in115.881s, but cleanup logged a recovery-file access error in reused test home.
  Exact release-source fresh-home rerun and packaged verification follow below.

Release verification completed:

- Exact release-source fresh-home suite: **300 passed in134.858s**, exit0;
  `build/compound-release-tests.log`. No cleanup error in this run.
- Staged build: `build/compound-performance-release/KineticCut`,
  `build/compound-performance-build.log`. All nine packaged checks exited0:
  compound, cut, focus, keyframe, pool, subtitle, workflow, assistant, startup;
  `build/compound-package-*/report.json`. Packaged cut tests: zero trimmed-out
  frames, zero unexpected black cut/scrub samples, incoming frames and audio reuse
  verified; intentional gaps retained. Packaged compound alpha snapshot inspected.
- Installed after a fresh no-process check. Prior EXE preserved at
  `build/KineticCut-before-compound-performance.exe`; staged/installed SHA256:
  `82C4AE870D3A502559E25571763A0C59C5F106C5F541E35DA39E4EC0C87B222E`.
  Installed executable: `dist/KineticCut/KineticCut.exe`.
- Live installed MCP: actual New Compound Clip name dialog, Open in Timeline,
  retained real-video punch keyframes, and Main Timeline breadcrumb verified.
  Separate `Compound Clip Demo.kcut` saved; original projects were not overwritten.
  Old apartment demo source `new house pt1.mp4` is absent now, so the new demo
  references available `2026-09-13 19-01-08.mp4` instead. Missing-source cache failure
  was visible and did not silently publish a broken cache.
- Installed demo render job356e75c86636 Complete100%,14.563s, no error;
  `build/compound-installed-demo.mp4` fully decoded without errors. Live nested
  and parent snapshots inspected (`build/compound-installed-child-final.png`,
  `build/compound-installed-parent-final.png`). Returned to Edit and saved demo.
- Additional quality samples at90s and150s also SSIM1.0 versus baseline.
  Performance figures are source diagnostic measurements; the full fashion-show
  benchmark was not repeated a fourth time inside the installed EXE. Packaged
  and live exports exercise the same implementation separately.

## Current release: caption focus, pool feedback and clip keyframes

Execution resumed successfully after the user confirmed available usage and app
closure. The earlier execution-approval blocker below is historical and resolved.

- [x] Caption-only black preview, audio-only transport (including disabling video
  tracks on audio-only MP4 players), selection seek, wrap navigation, delete/undo,
  restore normal viewer, and Deliver guard.
- [x] Tile/sidebar folder hover feedback, Preview Media context action, autoplay,
  popup Space ownership and focus restoration.
- [x] Clip-local X/Y position, linked/unlinked X/Y zoom, rotation and opacity
  curves; Linear/Smooth/Hold interpolation, legacy defaults and serialization.
- [x] Preserve animation through moves, split/trim/retime, overwrite fragments,
  duplicates and explicit Keyframe Animation attribute copying.
- [x] Isolated keyframe dialog: preview/audio, time control, per-property lanes,
  draggable diamonds, previous/next, explicit add/remove, remove all, Save/Cancel;
  lock/stale validation and one undo transaction on Save.
- [x] Shared preview/export evaluation. Real parity check caught FFmpeg retaining
  initial dynamic-scale dimensions through rotation; fixed with a stable maximum
  transparent canvas before downstream filters. Do not remove this padding.
- [x] Exact-source full suite: 293 tests passed in 78.854s,
  `build/keyframe-final-suite.log`. Focus real-media diagnostic:
  `build/caption-focus-source/report.json` (mean scrub/paint 4.76ms, max 6.18ms).
  Source keyframe parity: `build/keyframe-source/report.json` (centroid error
  under 2.5 pixels and area ratio 1.002–1.024 at sampled times).
- [x] Build: `build/keyframe-focus-build.log`; staged keyframe/focus tests passed
  at `build/keyframe-package-{keyframe,focus}`. Pool/subtitle/workflow/cut/
  assistant/startup passed at `build/keyframe-verified-*`. Initial pool run hit
  Windows file replacement access denied in its isolated fixture; a fresh-home
  rerun passed. This was not ignored or counted as a passing run.
- [x] Packaged dialog/focus snapshots inspected. Installed after fresh no-process
  check, with backup `build/KineticCut-before-keyframe-focus.exe`.
  Staged and installed `dist/KineticCut/KineticCut.exe` SHA256:
  `CCEB4E935087423A1A280D5795BC82CA216198A849B66537A40F9508C1981666`.
- [x] Live installed MCP connection and preview verified. Created the separate
  `Keyframe Punch Zoom Demo.kcut` using existing source media; authored all keys
  through the installed dialog's advertised UI controls, saved via the app.
  Hold 0–3s, eased punch 3–3.65s, hold to 5s, return 5–5.6s.
  Evidence: `scripts/author_keyframe_demo_ui.py`,
  `build/keyframe-installed-demo.png`. Existing projects/media preserved.
- [x] Installed-app demo render Complete, 100%, 7.703s; output
  `build/Keyframe Punch Zoom Demo.mp4`. User subsequently closed the app and
  supplied the next request; no further session navigation performed.

The unchecked checklists below record the original pre-implementation handoff;
the evidence-backed release status above supersedes their pending/blocker states.

## Original handoff: caption focus mode and pool preview/drop feedback

- [ ] Folder tile/sidebar drop target highlighting, cleared on leave/drop.
- [ ] Preview context action; video/audio autoplay; popup owns Space; closing
  returns timeline focus without starting timeline playback.
- [ ] Viewer Caption Focus toggle beside Fit; audio-only transport and black
  caption-only compositor, bypass video decoding/warm-up/effects completely.
- [ ] Selecting captions seeks in focus mode; previous/next wrap and select
  inspector; normal preview/export/project state remain unchanged on exit.
- [ ] Focused/full tests, real decode and visual/package checks.
- [ ] Build/install after fresh closure check; verify installed app.

Implementation status: source changes exist in `caption_focus.py`, `widgets.py`,
`transport.py`, `ui.py`, `workspace.py`, and `pool_tools.py`. Six focused tests
passed in 4.195s (`build/caption-focus-tests.log`), covering decoder exclusion,
caption-only paint, wrap navigation, view restoration, undo/Deliver guards,
popup keyboard focus and folder hover. Afterwards, audio-player LoadedMedia
handling was updated to disable its video track; that final change still needs
the real-media/full-suite checks. `focus_diagnostics.py` and `--focus-selftest`
were added but have NOT run.

BLOCKED at execution approval: the real-media source diagnostic request was
rejected by the approval service with "You've hit your usage limit"; its message
offered retry after 8:42 AM. Do not bypass the rejection via another execution
path or describe checks as passed. The full-suite command in the same orchestration
did not execute. The installed EXE remains the previous verified pool-polish
release. User confirmed closing the app for this update; recheck processes before
any later installation, because this confirmation can become stale.

Next after execution approval is available:
1. Run `.venv/Scripts/python.exe main.py --focus-selftest build/caption-focus-source`.
2. Read report; inspect focus paused/playing, popup and folder-hover PNGs.
3. Run full suite; diagnose failures rather than weakening tests.
4. Complete the keyframe request below before the final release build.

## Original plan: clip keyframes and a punch-zoom demo

User requests a lightweight, isolated keyframe editor accessed from the selected
image/video clip context menu and an enabled-only-for-compatible-selection toolbar
button. The dialog should have only that clip's preview/timeline, a playhead and
timestamp, right-hand property inspector, separate property lanes/markers,
add/remove keyframes, remove all, and explicit Save/Cancel. Changes must remain
staged until Save. Keyframes belong to the timeline clip, follow it when moved,
and must work in normal preview and export. Demonstrate a punch zoom in a separate
project using existing user media; preserve all existing projects and originals.

- [ ] Inspect model/serialization, transform evaluation, rendering and edit helpers
  before choosing storage. Do not implement preview-only keyframes.
- [ ] Clip-local time curves for transform position/scale (including linked X/Y),
  rotation and opacity where feasible; ordered keys per property interpolate
  automatically, with linear/eased/hold choices. No manual connecting required.
- [ ] Define split/trim/retime/duplicate/copy-attributes behavior and legacy defaults;
  preserve curve evaluation at boundaries and selected clip identity.
- [ ] Isolated modal clip editor, single-clip playback and property lanes; explicit
  add/remove keys, property selection, time navigation, Save/Cancel/Remove All.
  Save revalidates destination/locks and commits one undo action; Cancel none.
- [ ] Evaluate the same curves in regular preview and FFmpeg export, including
  cropped/scaled footage, aspect ratio, batch rendering and source trims.
- [ ] Tests for interpolation, serialization, motion after timeline move, split/
  trim/retime, undo/cancel/locks, and preview/export parity at key times.
- [ ] Create a separate non-overwriting demo project: initial hold, short eased
  position+scale punch, then hold (optionally return). Name project and exact
  viewing timestamps in final handoff; verify using the actual app and export.
- [ ] Run combined full regression suite and packaged checks; only then install
  final verified EXE with backup and live verification.

These are acceptance criteria and a proposed direction, not implemented features.
Do not expand to arbitrary effect animation without checking its preview/export
support. Do not claim a build or demo exists until it has actually been verified.

## Active: pool views, previews, Power Bin organization and monitor controls

- [x] Persistent gallery/list view, metadata columns, popup media preview.
- [x] Batch moves without navigation, folder tile drops, folder move/delete.
- [x] Asynchronous coloured audio waveform thumbnails.
- [x] Playback-only volume/mute with compact vertical popup.
- [x] Blade/undo preserve playhead; sticky media edges; fade corner protection.
- [x] Eight focused tests pass; full suite 281 pass (115.931s,
  `build/pool-full-final.log`). Visual QA caught and corrected header expansion
  and zero-size icon grid overlap; final source smoke passes with real generated
  audio (`build/pool-source-smoke/report.json`). Gallery/list/monitor inspected.
- [x] Final exact-source suite: 281 pass in 112.476s
  (`build/pool-verified-tests.log`). Final staged build log:
  `build/pool-polish-build-final.log`. Packaged pool, subtitle, workflow, cut,
  assistant and startup all exit 0 and report passed (`build/pool-package-*`).
  Adjacent-cut cases contain zero black/trimmed-out-frame samples; real gaps
  remain black by design. Packaged pool snapshots inspected.
- [x] Installed after fresh no-process check; backup retained at
  `build/KineticCut-before-pool-polish.exe`. Staged/installed EXE SHA256:
  B9614BE9127679CA5D76E553B85AEEB64820CCAF2D3E31F112AE4548EDFE16AF.
  Live installed MCP state/preview and actual gallery/list button checked;
  workspace images `build/pool-installed-workspace.png`,
  `build/pool-installed-list.png`. Original gallery mode restored after QA.

## Active: mixed subtitle/media movement, sticky placement, caption inspector

- [x] Trace mutual selection clearing in timeline and MainWindow, separate drag
  transactions, and nested custom-style scroll area.
- [x] Preserve Ctrl/Shift and existing marquee mixed selections; drag all selected
  subtitle/video/audio items with one shared time delta, undo and cancellation.
- [x] Subtitle start/end edge snap acquisition and wider release hysteresis;
  deliberate continued dragging still allows overwrite.
- [x] Single continuous Caption tab scroll, custom controls below checkbox,
  usable at small inspector height without nested tiny scroll viewport.
- [x] Focused tests cover selection both directions; subtitle/video drag and audio
  drag cancellation; Alt-copy, undo/redo, locks, preserved word timings, snap
  acquire/hold/release, and compact inspector layout. Full suite: 273 pass in
  76.012s (`build/mixed-subtitle-tests.log`). Final focused rerun also passes.
  Themed 1200x700 visual checked (`build/mixed-subtitle-visual/`): outer viewport
  218px, continuous style content 1526px, no inner scroll viewport.
- [x] Staged build `build/mixed-subtitle-release/KineticCut`; packaged subtitle,
  workflow, cut and startup reports all pass (`build/mixed-subtitle-package-*`).
  Superseded for installation by the additional pool/timeline requests above.
- [x] Included in the verified/installed pool-polish build above. Saved projects
  and source media were not changed.

## Active: pointed playhead handle

- [x] Replace active timeline's rectangular crown with a red five-sided downward
  pointer (14px wide, 13px tall); preserve line, ruler hit area and all scrubbing.
- [x] Verify painted silhouette and drag behaviour (`test_playhead_handle`),
  visual snapshot inspected at `build/playhead-handle-check/timeline.png`.
  Full suite: 268 passed in 70.546s (`build/playhead-handle-tests.log`).
- [x] Staged build at `build/playhead-handle-release/KineticCut`; packaged startup
  and cut reports pass (`build/playhead-handle-package-*/report.json`).
- [x] Installed after user closure and fresh process check. Staged/installed EXE
  SHA256 A1BD9197EC2F8D167763A86D7F5EA35A96B106C8F291802904E49549F18F28BC.
  Previous EXE retained at `build/KineticCut-before-playhead-handle.exe`.
  Installed app launched; authenticated MCP workspace snapshot returned and
  inspected at `build/playhead-handle-check/installed.png`.

## Active: viewer tooltip and width-fill transform

- [x] Diagnose: fit used contain scaling, omitted the facecam .92 rendering factor,
  and reset position/anchors. Viewer had a persistent gesture-help hover tooltip.
- [x] Remove only the viewer-area tooltip; retain gestures and other control help.
- [x] Fit cropped content to output width with uniform X/Y zoom, including webcam
  rendering factor; preserve position/anchors. Position to Top stays separate.
- [x] Focused geometry/undo/locked-track/persistence tests: two pass, including
  preview/export width agreement. Read-only apartment visual check passes:
  `build/viewer-fit-check/report.json`, before/after PNGs inspected. Saved project
  unchanged, both sides fill, subsequent Position to Top aligns correctly.
- [x] Run full suite and investigate failures: 266/267 pass on both full runs;
  the existing unauthorized-origin MCP test hit WinError 10053 twice (logs:
  `build/viewer-fit-tests.log`, `build/viewer-fit-tests-retry.log`). Isolated
  `test_assistant.py` rerun: all 10 pass in 5.403s. This is not a clean full-suite
  pass; no auth behavior or tests were weakened to mask the intermittent failure.
- [x] Build, packaged startup/workflow/cut checks all pass; install after user
  closure and process check. `build/viewer-fit-package-*/report.json`.
  Staged/installed SHA256 BD0DEA4048AB92944B8503A45354EE8EFE37590367F0C6FFFE9BA6082AED94DF.
  Rollback EXE: `build/KineticCut-before-viewer-fit.exe`. Installed app launched.
- User declined prioritizing the four previous observations; no work on those.

## Active: subtle tools, honest cache feedback, and apartment short

- [x] Add clear/Escape-close search for Media Pool and Effects; hidden filters clear.
  `small_controls.PanelSearch`, wired into both panels. Escape restores list focus.
- [x] Add timecode/seconds copy menu to the existing viewer timestamp.
  `CopyTimecodeLabel` freezes values at menu-open, including during playback.
- [x] Explain current frame preloading versus full rendered-range caching.
  Transport retains current decoder frames and warms adjacent cuts, not complete
  rendered timeline ranges. The requested green range line was conditional on
  having that cache: no misleading continuous green bar was added.
- [x] Test, stage/build, package-check and install app update after closure.
  265 tests passed in 70.736s (`build/subtle-tools-unit-tests.log`), including two
  new focused controls tests. Packaged startup/cut/workflow/subtitle/assistant
  selftests passed (`build/subtle-tools-package-*/report.json`). Installed EXE
  equals staged SHA256 77329EB96042F89702865429B1D8BBFD954B6738A1625D03308EC1700B1B1AE1.
  Prior EXE: `build/KineticCut-before-subtle-tools.exe`. Live MCP snapshot confirms
  installed CopyTimecodeLabel and both clear actions; real project opened via MCP.
- [x] Inspect all three clips; audio correlation confirms approximately 9.984s
  and 19.989s adjacent overlap. `build/apartment-edit/overlaps.json`, transcripts,
  source contact sheets and `edit-decisions.json` document the eight chosen shots.
- [x] Save separate 28.850s vertical project `Apartment Tour - xQc.kcut`: three
  video lanes (webcam, gameplay, blur), linked dialogue and timed captions.
  First and polished renders completed via production exporter; framing inspected,
  full decode passed. Live installed-editor preview inspected through MCP.
- [x] Verify final installed-app render after measured +7dB dialogue lift.
  MCP queue job `64957a1c3462` Complete in 81.594s, no error, 100%.
  `build/apartment-edit/final-qa.json`: full decode passed; 1080x1920/60 fps,
  28.850s, 32 timeline items/18 captions. Measured -18.93 LUFS / -1.68 dBTP.
  Output SHA256 396daff4b3cfbde8f2fb1c5b355dfd7a05f6bb3d267f15e2a37b8cb99d7a8a64.
  Project left open in Edit via MCP at 0.7s; final live snapshot inspected.
- [x] Preserve original media and existing projects; nothing published/uploaded.
  Opening the new project checkpointed the prior session via normal MCP workflow.

### Observations requested after the apartment edit (not implemented changes)

- Preview/export typography deserves a focused parity reproduction: the opening
  Nirmala UI / pop title appears proportionally wider in the live preview than
  in the export. Compare `final-live-workspace.png` and
  `installed-final-opening.jpg` under `build/apartment-edit`. Root cause unproven;
  ordinary pop uses ASS text while punch/selected fonts use shared vector paths.
  Existing passing typography tests did not establish exact parity for this case.
- Live workspace allocates video section space for only one of three used video
  lanes. A fit-used-lanes action or better initial section allocation could make
  layered editing less scroll-heavy without changing global track zoom.
- `is_hook` overrides position to 9% frame height and forces a light background;
  `subtitle_render.py` confirms this. This is existing behavior, not a regression,
  but should be clearer in UI/API semantics. This edit uses ordinary custom
  captions instead, so requested card positions are retained.
- Local transcription needed one obvious phrase correction (“I'm working
  elevator” to “A working elevator”). A compact caption-review workflow would
  help; this does not mean the transcription engine is broken.
- User asked for observations, not a further implementation batch. These are
  follow-up candidates, not checked-off fixes or automatic expansion of scope.

## Installed: Tony preview flashes trimmed-out source frames at cuts

- [x] Reproduce/trace first-cut decoder handoff with unchanged `tony.kcut`.
  Baseline audit published source timestamps 0.083–0.100s while trimmed clips
  started at 31.1019s and 38.1185s. See `build/tony-preview-baseline/report.json`.
- [x] Reject pre-seek frames and preserve scrub coalescing/audio warm-up.
  `transport.py` records pending video seeks, reapplies them after LoadedMedia,
  and rejects pre-target/stale frames before conversion/publication or priming pause.
  Retired decoder notifications cannot restart players. Scrub coalescing retained.
- [x] Verify timestamp freshness, adjacent cuts, real gaps and full regressions.
  Tony audit: 73 published frames, zero trimmed-out frames, unchanged project hash.
  `build/tony-preview-fixed/report.json`; `scripts/tony_preview_check.py`.
  Added `tests/test_preview_seek_gate.py`; full suite: 263 passed in 68.851s.
  Cut diagnostic now includes an excluded yellow source prefix; zero prefix flashes,
  zero black flashes at adjacent cuts, intentional gaps and audio reuse retained.
  `build/tony-sentinel-check/report.json`; scrub edge checks also passed.
- [x] Build/package-test and install after the app is closed.
  Staged at `build/tony-release`; cut, subtitle, startup and workflow packaged
  reports all passed (`build/tony-package-*/report.json`). Installed after closure,
  with matching staged/installed SHA256:
  `1FDC13109C005045AD9964583BD75F3C7AA165470244501B74ABF967638F31D2`.
  Previous EXE retained at `build/KineticCut-before-tony-preview-fix.exe`.
  Installed app launched and MCP summary responded successfully. Opening Tony
  through MCP was subsequently rejected by the approval service due to a usage
  limit; no workaround was attempted. The final live Tony check in the installed
  app was therefore not performed. Source Tony audit and packaged sentinel-cut
  tests above are the available behavioral verification, not a live-project claim.

## Suggested subtle quality-of-life improvements — not implemented

User asked to find useful, unobtrusive additions. Source inspection found:

- Media Pool / Effects search: add a clear button and Escape-to-clear/close.
  Closing search currently only hides the QLineEdit, leaving its text filter active
  (`workspace.py`, both `toggle_search` methods). Clear the filter on closure so
  hidden search criteria cannot make items appear missing.
- Viewer timecode: a right-click menu to copy the displayed timecode or seconds.
  The current `time_label` is a plain QLabel. Keep its layout unchanged and avoid
  introducing a global shortcut that interferes with text editing.

These are recommendations pending the owner's direction, not shipped features.

## Verified application release: DaVinci trim cursors, Select All, multi-clip effect drop, and export image flash fix

User requests:
1. DaVinci Resolve style trim cursors for both left (trim in) and right (trim out) sides of clips, and roll cursor between neighbouring clips, active during both hover and dragging, across ANY layer type (video, audio, subtitle/captions, image).
2. Timeline Select All (`Ctrl+A`) selecting all items across all layers/tracks.
3. Multi-selection effect drag-and-drop / double-click placing the effect onto all compatible clips in the selection.
4. Export image flashing / frame dropping bug: `GTA.kcut` track `video_4` (`new kick logo xqc.png`) flashing to black for 1-3 frames at cut boundaries.

- [x] Reproduce and diagnose export image flash bug:
  - FFmpeg image inputs lacked `-framerate <fps>`, defaulting to 25 fps while the project was 60 fps.
  - `-t <dur>` without padding combined with `repeatlast=0` in filter graph overlay caused image stream EOF frame drops at cut boundaries.
  - Fixed in `kinetic_cut/rendergraph.py`: passed `-framerate str(fps)` before `-loop 1`, padded `-t` with `+1.0`, and enabled `repeatlast=1` for image inputs.
  - Verified in `scripts/test_export_image_flash.py`: 0 dropped frames across multiple cut boundaries.
- [x] Implement DaVinci Resolve style trim and roll cursors in `kinetic_cut/timeline.py`:
  - Created `_trim_cursor(direction)` and `_roll_cursor()` static cached methods rendering anti-aliased 32x32 cursors with slim 1.5px white geometry, crisp 2.8px black outer borders, separated arrows, and exact hotspot alignment:
    - Left trim: regular square bracket `[` with small separated left arrow `◀` (hotspot at `(18, 16)`).
    - Right trim: regular square bracket `]` with small separated right arrow `▶` (hotspot at `(14, 16)`).
    - Roll: opposing square brackets `] [` with dual separated outer arrows `◀ ] [ ▶` (hotspot at `(16, 16)`).
    - Clean 4px transparent spacing decouples the arrow base from the square bracket spine, eliminating any "rocket ship" appearance.
  - Wired into `mouseMoveEvent` (hover and drag), `mousePressEvent` (drag start), and `mouseReleaseEvent` / `cancel_drag` (reset).
  - Aligned trim hit threshold to 8px across all layer types (video, audio, subtitle/caption, image).
- [x] Implement Timeline Select All (`Ctrl+A`):
  - Added `Ctrl+A` / `SelectAll` shortcut handling in `TimelineWidget.keyPressEvent`.
  - Added `Select All` (`Ctrl+A`) action under Edit menu in `kinetic_cut/ui.py` delegating to `MainWindow.select_all()`.
- [x] Implement Multi-Selection Effect Drag-and-Drop:
  - Updated `apply_effect_to` in `kinetic_cut/ui.py` to preserve multi-selection when dropping onto a selected clip.
  - Updated `apply_effect` in `kinetic_cut/ui.py` to apply effect across all compatible clips in the selection (`compatible(name, item, project)` check), safely skipping incompatible types (e.g. audio clips when dropping video effects) without error.
- [x] Run automated test suite:
  - `scripts/test_new_features.py`: All cursor, select all, and multi-clip effect tests passed.
  - `scripts/test_export_image_flash.py`: 0 dropped frames; verified completely seamless.
  - `scripts/unit_tests.py`: All 260 tests passed in 70.5s.
- [x] Build and verify packaged executable:
  - Built `dist/KineticCut/KineticCut.exe` via `build.ps1`.
  - SHA256: `8D169EE1C1139B2CABB74B5F9B8B2F41332A632B50CC9E4492CA8922157916F4`.
  - Passed all packaged self-tests: `--cut-selftest`, `--subtitle-selftest`, `--startup-selftest`, `--workflow-selftest`.

## Current handoff documentation request

- [x] Write a model-independent architecture, product-behavior and engineering guide.
- [x] Add an agent-discoverable entry point and this current task ledger.
- [x] Document tests, screenshot/MCP inspection, release procedure and a real example.
- [x] Explicitly retain the unresolved scrubber-performance report below.

Evidence: `AI_PROJECT_CONTEXT.md`, `AGENTS.md`, and this file. This is a
documentation-only delivery; no new EXE is required or claimed for this request.

## Verified application release: Timeline playhead dragging performance fix

User report: dragging the timeline playhead across timestamps felt very laggy,
low-frame-rate and made the application struggle, especially on GTA.kcut layer 3
webcam with the Remove Person Background effect.

- [x] Reproduce on GTA or the user's current project; preserve its saved contents.
  - Baseline `scripts/scrub_benchmark.py`: 150 events took 39,553 ms (avg 263.7 ms/event, 1,340 ms freezes).
  - Saved contents preserved intact; backup created at `video-editor-backup`.
- [x] Measure pointer/event-loop responsiveness and displayed-frame freshness.
  - Profiled event loop: synchronous decoder seeks (100+ seeks/sec) flooded Qt Multimedia worker threads.
- [x] Inspect seek frequency, decoder churn, warm-up work and preview painting.
  - 24 decoders created and 23 retired mid-drag in baseline due to speculative cut warm-up loop.
  - `mask_image` LRU cache was capped at 48 for 1,278 mask frames on layer 3 of GTA, causing >93% cache misses and ~2.4 ms disk reads on every event.
  - Snapping comprehension rebuilt 4 lists on every single pixel moved.
- [x] Implement a narrowly scoped improvement supported by the measurements.
  - `transport.py`: Added `scrub()` with 25 ms (~40 FPS) seek coalescing; bypassed speculative cut warm-up and muted audio during drag; full settled `sync(force=True)` on release.
  - `timeline.py`: Cached snap points during drag; added `scrubFinished` signal on mouse release/cancel.
  - `ui.py` & `workspace.py`: Routed playhead drag seeks to `transport.scrub()`; wired `scrubFinished` to `transport.finish_scrub()`.
  - `vision_effects.py`: Increased `mask_image` LRU cache to 2048 (holding all 1,278 frames in RAM); optimized mask scaling and numpy extraction in `Format_Grayscale8` (>50% faster, 0.55 ms vs 1.14 ms).
- [x] Verify rapid forward/backward dragging, exact final seek and real gaps.
  - Tested in `scripts/test_scrub_edges.py`: rapid zigzag scrub settled at exact position; gap landing cleared active frames with 0 errors.
- [x] Verify cut-boundary audio/video playback and no stale transform overlays.
  - Tested in `scripts/test_scrub_edges.py`: warm decoders restored on release, playback advanced across cuts, transform overlays updated cleanly.
- [x] Run focused and full regression tests; record results and any limitations.
  - `scripts/unit_tests.py`: Ran 260 tests in 63.6s — 260 passed, 0 failures.
  - `scripts/test_real_scrub.py`: 100 events across GTA layer 3 webcam took 2,715 ms (avg 27.15 ms/event, max 52.4 ms, 0 decoder churn).
  - `scripts/scrub_benchmark.py`: Total drag time dropped 59% (16,165 ms vs 39,553 ms; max latency 275 ms vs 1,340 ms).
- [x] Build staged EXE and run packaged checks.
  - Built staged bundle at `build/scrub-release/KineticCut/KineticCut.exe`.
  - Passed `--cut-selftest`, `--subtitle-selftest`, `--startup-selftest`, `--workflow-selftest`.
- [x] Obtain closure of the running app before installation; verify installed EXE.
  - Verified no running `KineticCut.exe` process on system.
  - Installed to `dist/KineticCut/KineticCut.exe`.
  - SHA256: `7EB88C6D90E9FED1EA84B18D43A0B17683B64E59F694EDB257F70AFBA7EAF7D4`.
  - Passed all packaged self-tests on installed executable.

## Last verified application release: GTA export/editing update

- [x] Fixed the Gaussian Blur framesync/EOF stall and bounded complex video graphs.
- [x] GTA source export and installed-app render reached successful completion.
- [x] Added audio warm-up, sticky media/subtitle blade snapping, corrected wheel shortcuts.
- [x] Added destination analysis for pasted vision effects, render Edit lock,
  hidden playback transform controls, and subtitle-track deletion.
- [x] Included user-supplied Geometos Regular.
- [x] 260 regression tests passed; packaged cut/subtitle/workflow/startup checks passed.
- [x] Installed and reconnected through MCP; returned GTA to Edit after rendering.

Installed EXE: `dist/KineticCut/KineticCut.exe`.
SHA256: `A9DF4F4F9133F6393BB245F6AC601796DC6A8E7DD2D78A49A89BE7FA8354AE22`.
Verified output: `build/gta-export-check/GTA-verified.mp4`.
Installed-app render: Complete, 100%, 189.5 seconds; 1080×1920, 60 fps,
3,446 frames, AAC audio, 57.433-second output. Entire output decoded without errors.
Detailed evidence: `GTA_EXPORT_FIX.md` and the paths listed there.

These are historical verification results, not a guarantee about the next build.

## Verified application release: Zoom Pixelation Fix, 9:16 Vertical Video Layout & Caption Typography Update

User requests:
1. Fix extreme pixelation during zoom effects (and appearing even before zooming begins).
2. Refine 9:16 vertical video framing: eliminate awkward crops and black voids, implement background blur filling, trim unwanted video intros.
3. Elevate caption typography and animations: curated presets (Anton, Montserrat, Poppins) and word-level animations (bounce, karaoke, pop).
4. Build high-utility MCP tools: `set_caption_style` and `apply_vertical_framing`.
5. Polish and format D.B. Cooper short project (`The_Mystery_of_DB_Cooper.kcut`).
6. Build and verify frozen distribution, ensuring running editor processes are closed before building, verify installed EXE, and reconnect over MCP.

- [x] Zoom Pixelation Root Cause & Fix:
  - Hypotheses vs Findings: Discovered `PreviewCanvas.paintEvent` in `kinetic_cut/widgets.py` lacked `QPainter.SmoothPixmapTransform`, causing nearest-neighbor stair-stepping. Furthermore, clips with any effects were downscaling source frames to low resolution (540x304) prior to zooming.
  - Fix in `kinetic_cut/widgets.py`:
    - Enabled `painter.setRenderHint(QPainter.SmoothPixmapTransform)`.
    - Differentiated pixel-modifying filters (Chroma Key, Blur) from procedural transform effects (Zooms, Camera Moves, Shakes).
    - Procedural visual effects now bypass downscaling and effect caching, sampling directly from `_source_crop(layer_source, item.crop)` at 100% native source resolution.
    - Removed destructive `scaled(540, 960)` downscale; capped only at `max(settings.width, settings.height)` when heavy CPU pixel filters are present.
  - In `kinetic_cut/rendergraph.py`: Added `VISUAL_FX_SET` check for synthetic keyframe export.
- [x] Caption Typography & Word-by-Word Animations:
  - In `kinetic_cut/caption_words.py`, `visuals.py`, `word_highlight.py`, `subtitle_render.py`: Implemented spring physics curve `bounce` ($0.40 \rightarrow 1.25 \rightarrow 0.95 \rightarrow 1.0$) and `karaoke` (word-by-word active spoken highlight).
  - In `kinetic_cut/caption_presets.py`: Added 5 curated viral presets (`crime_red`, `viral_yellow`, `cyber_cyan`, `mrbeast_gold`, `clean_card`).
- [x] Dedicated MCP Tools & Editor Features:
  - In `kinetic_cut/ui.py` & `assistant_api.py`: Implemented `set_caption_style` and `apply_vertical_framing` as first-class tools in `TOOLS`, `COMMANDS`, and `EditorAPI`.
- [x] Test Suite Verification:
  - Fixed test deadlock in `kinetic_cut/ui.py` (`check_crash_recovery`) by guarding against `box.exec()` in offscreen environments.
  - Ran full test suite runner: **354 tests passed in 147.75s, OK (exit 0)**.
- [x] Visual Verification & Frame Inspection:
  - Verified rendered frames from `The_Mystery_of_DB_Cooper.kcut`: `frame_10.0s.png` (Slow Push-In on Briefcase), `frame_19.5s.png` (Punch Zoom on Money), `frame_0.5s.png` (cockpit trimmed past intro), and `frame_34.0s.png` (aft stairs) have zero pixelation, full 9:16 vertical framing, ambient blur margins, and sharp captions.
- [x] Build and Packaging Verification:
  - Closed running editor processes before build.
  - Staged build at `build/release-pixelation-fix/KineticCut/KineticCut.exe`:
    - `--assistant-selftest build/verify-staged-assistant`: `passed: true`, `frozen: true`.
    - `--compound-selftest build/verify-staged-compound`: `passed: true`, `frozen: true`.
  - Installed binary to `dist/KineticCut/KineticCut.exe`.
  - SHA256: `27CD46B1450337A8E0DEFC5F8EE3A2EDEF723F8B350CA45264C39932CB3562A4`.
  - Installed binary verification: `--assistant-selftest build/verify-installed-assistant` passed (`passed: true`, `frozen: true`).
- [x] Live Editor Launch & MCP Reconnection:
  - Running installed app: `dist/KineticCut/KineticCut.exe --enable-mcp`.
  - Dismissed startup recovery dialogs via `ui_control`.
  - Opened project `The_Mystery_of_DB_Cooper.kcut` via `project_file`.
  - Live preview verified at 10.0s and 19.5s via `seek` and `get_preview`.

## Verified application release: Caption Presets UI, Rapid Undo Resilience & Universal AI Editing Guide

User requests:
1. Add a Style Preset dropdown in the "Generate captions" popup UI above the Font option, auto-populating all properties and updating the preview box.
2. Investigate and eliminate app freezes / crashes when rapidly holding `Ctrl+Z` (undo) after moving media items.
3. Author a comprehensive, universal `.md` guide for any AI assistant editing video content via the MCP connection across any topic or genre.

- [x] Caption Preset Dropdown in Generate Captions Popup UI (`kinetic_cut/caption_style_dialog.py`):
  - Added `self.preset` combo box placed immediately above `self.font` in `CaptionStyleDialog`.
  - Configured with all 5 curated presets: `Crime Red Alert`, `Viral TikTok Yellow`, `Cyber Neon Cyan`, `MrBeast Gold`, and `Clean Minimal Card` (plus `Custom / Current`).
  - Selecting any preset updates font family, font face, size, uppercase, background, glow settings, text/outline/highlight colors, animations, and refreshes the preview.
  - Customizing any property reverts the preset dropdown to `Custom / Current`.
  - Tested in `test_caption_styles.py` (`test_caption_style_dialog_preset_dropdown`).
- [x] Rapid Undo (`Ctrl+Z` hold) Freeze / Crash Fix (`kinetic_cut/transport.py`, `kinetic_cut/ui.py`):
  - Hypotheses vs Findings: On holding `Ctrl+Z`, rapid auto-repeat fired 30+ history restorations per second. Each restoration created a new Project deepcopy, triggering `if self._project is not p: retire_all_decoders()`. Destroying and recreating dozens of `QMediaPlayer` / Windows Media Foundation instances while queueing un-debounced compound cache workers starved the Qt event loop and locked COM threads.
  - Fixes:
    - In `transport.py`: Checked `self._project.created_at != p.created_at` to distinguish different projects from same-project history snapshots, safely preserving active decoders across undo/redo steps.
    - In `ui.py`: Protected `_restore_history`, `undo`, and `redo` against re-entrancy.
    - In `ui.py`: Debounced compound cache synchronization and preview quality requests with an 80ms settle timer (`_schedule_history_settled`).
    - Fixed missing `QMenu` and `QCursor` imports in `kinetic_cut/ui.py`.
    - Added unit test `test_rapid_undo_resilience` in `tests/test_assistant.py` validating 35 consecutive rapid undos without stall or crash.
- [x] Universal AI Video Editing & MCP Integration Guide (`AI_VIDEO_EDITING_MCP_GUIDE.md`):
  - Created a universal, genre-agnostic operational manual detailing 9:16 safe framing, subject focal-point analysis, dual-track ambient blur margins, audio ducking, procedural visual FX, and caption typography.
  - Clearly designated and labeled all specific syntax snippets as illustrative examples.
- [x] Full Automated Test Suite:
  - Ran `scripts/unit_tests.py`: **356 tests passed in 141.44s, OK (exit 0)**.
- [x] Frozen Binary Build & Installation:
  - Staged build verified: `--assistant-selftest` passed (`frozen: true`, `passed: true`).
  - Installed binary to `dist/KineticCut/KineticCut.exe`:
    - SHA256: `D549B2D7741B51DFAFC18211B08F02167FCCC6CC3DFE5307FC2F53B7D3807DC2`.
    - `--assistant-selftest build/verify-installed-assistant`: `passed: true`, `frozen: true`.
## Verified application release: Rapid-Undo & Media Refresh Crash Fix, Fitted Aspect Ratio Layout & Tech Guide Project

User requests:
1. Diagnose and fix the root causes of application crashes/freezes when moving cut media items and undoing at rapid speed or during MCP operations.
2. Fix 16:9 diagram/chart aspect ratio fitting in the programming tech guide ("Docker in 60 Seconds") so that zero text or diagram elements are cut off horizontally, with top and bottom black bars filled by a blurred background underneath.
3. Relaunch the application and continue controlling it via the live MCP server connection.

- [x] Rapid-Undo Freeze / Crash Root Cause Analysis & Source Fixes (`kinetic_cut/workspace.py`, `kinetic_cut/ui.py`):
  - Hypotheses vs Findings:
    - Holding `Ctrl+Z` (undo) sends ~30 key events/second. In `_restore_history`, `self.refresh_media()` was called unconditionally on every undo step. For imported image assets, `MediaPanel.media_icon` was re-reading PNG/JPG files from disk and allocating `QPainter`/`QPixmap` on the main GUI thread dozens of times per second.
    - Simultaneously, each history step called `self.seek(position)`. Because `self.timeline.drag_mode` is not `"playhead"` during keyboard undo, it called un-debounced decoder seeks (`retire_decoder` + `create_decoder`), flooding the Windows Media Foundation DirectShow/COM subsystem with hundreds of asynchronous teardown requests before the previous ones completed, exhausting worker threads and deadlocking the event loop.
  - Fixes:
    - In `kinetic_cut/workspace.py`: Added `self._image_icon_cache` to `MediaPanel`. Cached thumbnails are returned immediately in O(1) time without disk I/O or painter reallocation.
    - In `kinetic_cut/ui.py`: Added check `if [m.id for m in self.project.media] != old_media_ids: self.refresh_media()`. Prevents media panel churn when timeline edits do not modify the media pool.
    - In `kinetic_cut/ui.py`: Updated `seek(value)` so that seeks occurring during history restoration (`getattr(self, "_restoring", False)`) use debounced `self.transport.scrub(value)` (25ms timer) rather than destroying/rebuilding active decoders on every key-repeat.
    - In `kinetic_cut/ui.py`: Added `self.transport.seek(self.project.playhead)` in `_on_history_settled()` once key-repeats stop to cleanly position the decoders.
- [x] Diagram Aspect Ratio & Dual-Track Ambient Blurred Background (`Tech_Guide_Docker.kcut`):
  - In 9:16 vertical projects (1080x1920), 16:9 media (1920x1080) by default is scaled by `max(w/full_w, h/full_h) = 16/9 ≈ 1.7778` to crop-to-fill, cutting off the left and right sides of technical diagrams.
  - Calculated exact fitted scale: to display the full 1920px width within 1080px with comfortable safe margins (~25px per side), `scale = 0.30` was applied to all 12 foreground clips on `video_2` centered at `x: 0.50, y: 0.46`.
  - Underneath on `video_1`, placed 12 duplicate background clips at `scale: 1.0`, `role: "normal"`, `opacity: 85.0`, `brightness: -0.15`, with `Gaussian Blur` (`horizontal: 45.0, vertical: 45.0, border: "Reflect"`).
  - Captions positioned in the lower third (`y: 0.78`) with Cyber Neon Cyan styling (`#00f0ff` glow, `#ffffff` text, `#000000` shadow).
- [x] Test Suite Verification:
  - `tests/test_assistant.py` (including `test_rapid_undo_resilience`): 15 passed in 12.7s (`OK`).
  - `tests/test_visual_fx.py`: 23 passed in 14.7s (`OK`).
- [x] Frozen Binary Build & Installation:
  - Closed active processes and ran `build.ps1`.
  - Staged binary verified: `--assistant-selftest build/verify-staged-assistant` passed (`frozen: true`, `passed: true`).
  - Installed binary to `dist/KineticCut/KineticCut.exe`:
    - `--assistant-selftest build/verify-installed-assistant` passed (`passed: true`, `frozen: true`).
- [x] Live Editor & MCP Reconnection:
  - Running live installed application: `dist\KineticCut\KineticCut.exe --enable-mcp` (PID 11784).
  - MCP connection verified and active on port 54134 with authenticated token.
  - Loaded `Tech_Guide_Docker.kcut`.
  - Verified live preview frames at 4.0s, 12.0s, 26.0s, 42.0s, 48.0s, and 58.0s via `get_preview`: confirmed 100% visible diagrams with zero horizontal cutoff, aesthetic blurred background fill, and clear captions.

## Required format for future task entries

For each new request, record:

1. User intent and concrete acceptance criteria, including follow-up clarifications.
2. Status: pending / investigating / implemented / source-tested / packaged-tested /
   installed / blocked. Check boxes only after the stated condition is satisfied.
3. Reproduction project and measurements; distinguish hypotheses from findings.
4. Files changed and why; no unrelated changes.
5. Regression test names, command, exit status, report paths and limitations.
6. EXE path/hash and installation state when a release was requested.
7. Remaining work and an exact next action if interrupted.

Keep historical entries. Never erase an unresolved item just because a new
request arrives, but do not silently continue a superseded action either.
# Missing media and safe relinking — 24 September 2026

- [x] Red missing-media presentation in Media Pool, Power Bins and video/audio timeline clips (no stale thumbnails/waveforms). User clarification: audio uses one flat red waveform centred in the thumbnail/clip, never repeated picture icons.
- [x] Replacement-file and same-name folder relinking, retaining edit properties/source ranges; incompatible cuts remain marked mismatch. Power Bin folder scope is direct children only. Saved Power Bin edits retain their attributes; nested compound sources can be relinked inside their timeline or through project folder rebasing.
- [x] Background presence checks, decoder/cache invalidation, persistence/undo and export safety; regression tests and visual checks. `build/missing-media-final-regression/report.json`: 470 tests passed. Subsequent audio artwork check: 12 missing-media unit tests passed (`build/missing-media-audio-tests.log`), vision suite 17 passed (`build/missing-media-vision-tests.log`). Isolated source GUI/native-decoder check passed (`build/missing-media-audio-verified/report.json`), including partial replacement, exact-folder scope, undo/redo and a decoded frame after relinking; Default/Obsidian/Ableton screenshots produced and Ableton inspected. No user projects/media edited.
- [x] Stage, test and install rebuilt EXE after app closure. `build/missing-media-build-final.log` completed successfully; staged packaged missing-media check passed. Full prior bundle backed up to `build/missing-media-before-install-20260924`, new bundle copied to `dist/KineticCut`. Installed/staged EXE SHA256 `717E689FEDCE773209770399D5A5BCC32E3A7B94668461E91D0C2E465C3CC361`. Installed startup, missing-media/native relink and all four cut-playback checks passed (exit 0): `build/missing-media-installed-{startup,missing,cut}/report.json`. Installed Ableton screenshot inspected: missing audio has a centred flat line in both the pool and audio lane. No user projects, source files or settings changed by diagnostics.
# 2026-09-24 — Live audio levels and portable project safety

- [x] Show lightweight, live audio-track level bars and a detailed Levels subtab in the Audio inspector, with peak/clip indication. Qt's decoded buffers drive the per-track meters; only tiny header regions repaint. The mix-headroom line is explicitly a conservative peak-sum warning, not an exact post-mix/export peak.
- [x] Retain bounded, restorable versions of explicitly saved `.kcut` projects under `.KineticCut Versions` (20 previous saves). Autosaves bypass this path. Restore opens as an unsaved edit so Save As cannot silently replace the original.
- [x] Collect a separate portable project folder with relative media and thumbnail paths, including nested compound/preset sources; original project/source files remain untouched. Missing sources stop publication of the collected `.kcut`.
- [x] Full source suite: `build/audio-project-safety-tests/report.json`, 475 tests/48 modules passed. Final focused module: 5/5 tests passed, including Inspector UI, version history, moved portable folder, nested compounds, thumbnails and missing-source failure. Visual check: `build/audio-safety-visual/audio-levels.png` inspected after green/yellow/red styling correction.
- [x] Staged packaged startup passed: `build/audio-safety-staged-startup/report.json`. Installed packaged startup passed: `build/audio-safety-installed-startup/report.json`. Installed EXE: `dist/KineticCut/KineticCut.exe`, SHA-256 `20B3E9590C21DDFC75770D7E6566D688E45D13C611FCAF8B742552FFA2E56473`. Previous installed bundle retained at `build/release-backups/KineticCut-before-audio-safety-20260924`.
- [x] Installed native real-media playback diagnostic passed: `build/audio-safety-installed-playback/report.json`; 3 video layers + audio, 50.33 fps default and 51.04 fps Ableton Gray in the isolated offscreen check; 3 visible layers after scrubbing. This is a bounded diagnostic, not a claim of universal playback throughput.
# 2026-09-24 — Effects browser category persistence

- [x] Persist the selected Effects browser category as a global UI setting and restore it on app launch; unknown/removed categories safely fall back to All Effects.
- [x] Relaunch and fallback unit tests passed. Full source suite: `build/effects-category-regression/report.json` — 478 tests/49 modules passed. Packaged startup with `Open FX / Blur` settings passed at `build/effects-category-staged-startup/report.json`; its screenshot visibly shows that category selected and Gaussian Blur listed. Installed startup passed at `build/effects-category-installed-startup/report.json`. Installed EXE: `dist/KineticCut/KineticCut.exe`, SHA-256 `5A116E509098430B9CB0FF6BA48B0ADE3473C02C46B3102F5A79486119021E9F`. Previous installed bundle preserved in `build/release-backups/KineticCut-before-effects-category-20260924`.
- [x] Reviewed existing export, cache and timeline support. Recommended future work only: post-render stream/duration/audio QC; user-visible, safe regenerable-cache management; labeled timeline markers. No code changes made for these ideas.

# 2026-09-24 — Cache Manager and tracked textured face filters

User intent: add the previously recommended safe cache-management popup as the second-to-last File menu action, matching Default/Obsidian/Ableton Gray; extend Face Filters with attractive tracked animal effects, especially puppy ears, without passing off crude geometry as a finished filter. Follow-up clarification: retain the present implementation, but explain separately what true 3D face-attached effects require.

- [x] Implemented File → Cache Manager… immediately before UI Themes…. The small modal lists counts/sizes for a strict allowlist of regenerable thumbnails, proxies, waveforms, compound previews, rendered face/effect frames, project thumbnails and processed audio previews. It blocks clearing during playback, render, transfer or background work, confirms the selected size, reports actual deletions and never offers source media, recovery data, generated TTS, analysis data or logs. Symlinks and paths outside the cache root are not traversed/deleted. Missing video thumbnails regenerate asynchronously after clearing or opening older projects; no synchronous FFmpeg scan in the media pool.
- [x] Added two transparent, textured artwork kits to `assets/face_filters` and new Face Filters entries: Puppy Ears & Nose and Cat Ears & Whiskers. The optional MediaPipe analysis worker now stores per-frame 3D landmark coordinates and a facial transformation matrix alongside legacy `faces.json`. The renderer uses tracked roll, head-width/yaw foreshortening and face occlusion, with the same `vision_effects.apply` path in preview and export. Existing ten-point saved effects remain valid; new filters require geometry and trigger Re-analyse if an older cache lacks it. This is a pose-aware 2.5D textured effect, **not** a true 3D model; do not claim side-surface rendering when the head turns.
- [x] Real media validation: sampled 30 frames/2 seconds from `C:\Users\F\Videos\NoPixel5\2026-09-13 19-01-08.mp4`; the installed local vision component returned pose matrices/landmarks. Rendered and visually inspected `build/face-filter-check/puppy.png` and `cat.png`, iterated ear placement on the turned head. The cat-filter FFV1 export-preparation file was successfully produced and probed at 640×360. Source media and user projects were not modified.
- [x] UI validation: `build/cache-dialog-visual/{default,obsidian,ableton_gray}.png` captured and inspected. Full source suite: `build/cache-face-final-regression/report.json` — 483 tests/50 modules passed; one symlink test skipped because Windows lacked symlink-creation privilege. Added cache safety, thumbnail-regeneration, menu/theme and accessory regression tests.
- [x] Built staged EXE and confirmed both kits are packaged. Staged startup: `build/cache-face-staged-startup/report.json` passed. Installed to `dist/KineticCut/KineticCut.exe` after verifying the app was closed; installed startup: `build/cache-face-installed-startup/report.json` passed. Installed/staged SHA-256: `212265C5816DDED8440D36180B000991AB49C4C5DDB65CA72D41F3D8E55216B1`. Prior complete bundle: `build/release-backups/KineticCut-before-cache-face-20260924`.
- [ ] Future, separate quality tier: true 3D accessories (side-view muzzle/ears, depth-buffer occlusion and textured mesh/model rendering). This needs a 3D asset and GPU renderer driven by the full MediaPipe face geometry, not merely the current pose-aware 2D sprites. User requested an explanation at handoff, not replacement of the working implementation in this task.

# 2026-09-24 — Model-based AR face filters (plague mask and pixel glasses)

User intent: keep the existing 2.5D animal filters, add new AR effects that visibly reveal a 3D model's side as the face turns, and use user-supplied GLBs. `C:\Users\F\Downloads\ar_models` is the user's staging folder for further candidate GLBs (including GLBs inside `gltf` subfolders); a newly placed model is not automatically assumed to be a usable face filter.

- [x] Inspected the supplied plague-mask GLB and `pixel_glasses.glb` in Blender. The plague GLB included a large preview backdrop cube; excluded it from all filter views. Retained the supplied plague CC BY 4.0 credit/license in `THIRD_PARTY_NOTICES.md` and the asset folder. Pixel-glasses model is user-supplied with unknown redistribution terms; do not distribute it publicly without review.
- [x] Added **AR Plague Mask** and **AR Pixel Glasses** as separate Face Filters without replacing Puppy Ears & Nose or Cat Ears & Whiskers. The existing MediaPipe face pose supplies yaw/pitch, landmarks supply position/size/roll, and transparent views of the actual textured GLB meshes reveal the model's side surfaces. `scripts/build_ar_views.py` builds 105 angles per model locally in Blender; `kinetic_cut/ar_face_filters.py` selects bounded cached views for both preview and lossless export. No Blender, model import, GPU readback, or cloud service is required per playback frame. This is view-dependent **3D-model rendering**, not a live deforming mesh/depth-buffer AR renderer; do not claim the latter.
- [x] Rendered both effects on a real turned-head frame from `C:\Users\F\Videos\NoPixel5\2026-09-13 19-01-08.mp4` and visually inspected `build/face-filter-check/ar-plague.png` and `ar-glasses.png`. The plague beak's side and glasses arms are visible. The existing 2.5D effect render path remains intact. Sample 30-frame lossless export preparation passed at `build/ar-test-home/cache/vision-renders/efa18ffc23bfa9aea43e35cf0e9562b77d27bd0ebfd297a65ab66b61cc5bbe7c.mkv`. Measured model-view compositing at ~2.65 ms/frame for a 640×360 sample; this is not an end-to-end playback benchmark.
- [x] Regression test checks every packaged angle, old filter preservation, pose extraction, analysis gating, hide-on-face-loss, and preview rendering. Full source suite: `build/ar-full-regression/report.json`, **484 tests / 50 modules passed**. Staged build `build/ar-release-stage/KineticCut/KineticCut.exe` includes both asset sets; `build/ar-staged-startup/report.json` passed.
- [x] User closed Kinetic Cut. Installed `dist/KineticCut/KineticCut.exe`; `build/ar-installed-startup/report.json` passed. Staged/installed EXE SHA-256: `9D79A577355429E222E516A5B50F633A5F16BEC037B1B3E2CA28C6A8FD751D38`. Previous complete bundle preserved at `build/release-backups/KineticCut-before-ar-20260924`.
- [ ] Further model imports from `C:\Users\F\Downloads\ar_models` need per-model front-axis, scale, anchoring, rendering, license and visual-motion checks before they are exposed as filters. In particular, no dog/cat 3D model was supplied in that folder at installation time. Full live 3D geometry/depth-buffer occlusion remains a separate quality tier, not silently substituted by these optimized view-dependent filters.

# 2026-09-24 — Custom Face editor and tracked morph

User intent: after the installed AR build, provide a clip-scoped Custom Face effect with facial-feature sliders, skin tint, tracked-region guides, clip-local scrubber, Apply/Cancel, per-section reset and Reset All. Snap Lens Studio's Face Mesh controls were used as workflow reference; this is a local MediaPipe-landmark pixel morph, not Snap's proprietary blendshape renderer.

- [x] `assets/vision_worker.py` now records the full 478-point face mesh per analysed frame, while retaining legacy landmarks and 3D pose caches. Older effects remain valid with their old cache; Custom Face explicitly requires a new mesh. The in-memory mesh cache does not keep a Windows file mapping open.
- [x] Added seven signed feature controls (face/jaw width, individual eye size, nose size, mouth width/height) and optional skin tint, with bounded values, cropped-clip-only source preview, async scrub decode, original comparison, colour-coded landmark guides and feature-only guide toggle. Per-section reset and top-level Reset All restore defaults. Apply commits only to the selected timeline clip; Cancel leaves it unchanged. Preview and export share the same pixel implementation; no source-media mutation.
- [x] Real 2-second cropped video analysed with the installed local vision runtime: 30 frames, 29 tracked face frames. Representative frame variations and Default/Obsidian/Ableton Gray dialog screenshots captured under `build/custom-face-check` and inspected. Lossless 640×360 Custom Face export cache rendered at `build/custom-face-export-home/cache/vision-renders/aecb38516e8823a2ed92bb61d31facb97314bcb9f57378b8264ec5c1cce15a61.mkv` (17,529,386 bytes). This is an effect-preparation output, not a complete TikTok render.
- [x] New focused cache/morph/Cancel/reset tests passed; full source suite `build/custom-face-regression/report.json`: **488 tests / 51 modules passed** after updating an old mock signature for mesh-aware validation. Staged EXE `build/custom-face-release-stage/KineticCut/KineticCut.exe` built; staged and installed startup self-tests passed at `build/custom-face-{staged,installed}-startup/report.json`. Installed `dist/KineticCut/KineticCut.exe`, SHA-256 `12463BD71A664DDD007BC1921B8460857316AB0BF1822AE22DC636585B18C626`; prior complete bundle retained at `build/release-backups/KineticCut-before-custom-face-20260924`.
- [ ] Lens Studio template pack review and Face Filters subcategories are a distinct follow-up from the user's next request; assess runtime compatibility and actual reuse rights before copying any template asset into a distributable build.

# 2026-09-24 — Lens Studio template review and Face Filters browser grouping

User intent: inspect the downloaded Lens Studio templates for usable face filters and organize the growing Face Filters list by effect type, without weakening the finished Custom Face implementation.

- [x] Audited the user's 19 `Face/` Lens Studio template projects at `C:\Users\F\Downloads\lens-studio-templates-main\lens-studio-templates-main`. Findings and per-template decisions are recorded in `docs/LENS_STUDIO_TEMPLATE_AUDIT.md`. These are Snap scene projects with native `.mesh` / `.lsmat` assets and Lens Studio API scripts, not standalone Kinetic Cut effects. Each project points to Snap's template license; the full linked license was unavailable during review. No Snap-owned/template asset was copied into the app or represented as a working effect. Relevant existing independently implemented functions include Custom Face, Remove Person Background and AR Pixel Glasses. The candidate concepts for independently licensed future work are tracked in the audit.
- [x] Added browser-only Face Filters subsections: Face shape & colour, Animal filters, Glasses and Masks. Each existing effect appears exactly once and retains its original effect name/drag payload; no empty Hats section was added. Default, Obsidian and Ableton Gray screenshots were inspected at `build/face-filter-browser-visual/{default,obsidian,ableton_gray}.png`.
- [x] Full source regression `build/face-filter-category-regression/report.json`: **489 tests / 52 modules passed**. Rebuilt `build/face-filter-category-stage/KineticCut/KineticCut.exe` with staged startup pass at `build/face-filter-category-staged-startup/report.json`; installed startup pass at `build/face-filter-category-installed-startup/report.json`. Final installed `dist/KineticCut/KineticCut.exe` SHA-256 `E3AD4F7D6F739C202483F9D5C76BCE891C4F2579B1F1F2C594FF290CD2AB5EAF`. Prior complete Custom Face build retained at `build/release-backups/KineticCut-before-face-categories-20260924`. No user media, projects or settings changed by the implementation.
- [ ] Direct Snap template asset import requires explicit, verifiable reuse rights for an independent Windows editor plus a functional port of the native asset/render pipeline. Do not list non-functioning Snap effects or imply all 19 are portable. Newly sourced GLBs can instead be imported one by one after licensing and pose-fit QA.

# 2026-09-24 — Custom Face Apply crash, nose range and face tint follow-up

User report: pressing Apply in the Custom Face popup displayed `CustomFaceDialog object has no attribute Accepted`; nose enlargement felt capped, and skin colour covered only part of the face. The earlier Custom Face release's startup and pixel tests did not exercise the modal acceptance branches, so they did not prove Apply worked.

- [x] Reproduced the exact exception path in `vision_ui.begin` and `vision_ui.customize`: both compared the modal result with `dialog.Accepted` instead of `QDialog.Accepted`. Both branches now use the Qt class constant. A new behavioral test opens those control paths using an accepted dialog with no instance `Accepted` attribute and verifies the effect values commit; it would fail on the previous code.
- [x] Extended only the nose slider/spin/value limit from +100 to +140. Kept a bound to avoid warping singularities or severe sampling artifacts; widened its radial influence and verified +140 on the real local face frame at `build/custom-face-followup-visual/nose.png`. Other sliders retain −100..+100. Popup copy explains the cap.
- [x] Removed the cheek-colour and luminance eligibility gates that left shadows/turned-face regions untreated. The colour now covers the tracked face polygon, preserving source luminance/texture, feathering its perimeter and excluding eye/mouth regions. It does not attempt ear/neck/body recolouring; the popup says so. Inspected the real-frame output at `build/custom-face-followup-visual/skin.png`; synthetic coverage test checks forehead, both cheeks, central face and chin while outside-face pixels remain unchanged.
- [x] Focused Custom Face module: 6/6 passed. Full source suite `build/custom-face-apply-fix-regression/report.json`: **491 tests / 52 modules passed**. Fresh two-second lossless effect render with nose +140 and skin tint produced `build/custom-face-apply-fix-export-home/cache/vision-renders/c783ad94cd663a97b6239784b9eff435cc7508af871e78c41060dfbd42c7012d.mkv` (17,761,739 bytes).
- [x] Built staged bundle `build/custom-face-apply-fix-stage/KineticCut`; staged startup passed at `build/custom-face-apply-fix-staged-startup/report.json`. Confirmed app closed, backed up full prior bundle to `build/release-backups/KineticCut-before-custom-face-apply-fix-20260924`, installed to `dist/KineticCut/KineticCut.exe`, compared hashes, and ran installed startup successfully at `build/custom-face-apply-fix-installed-startup/report.json`. Installed EXE SHA-256 `E880A26DC79CAFD991B691F8CA5E913EA5DB2BD418BABAE7DA4EB8FC8A8D9DAB`. The user's own project was not opened or altered. The Apply interaction is behaviorally tested in source but not manually clicked in the installed GUI; the installed package passed its startup test.

# 2026-09-25 — Custom Face eye spacing

User intent: add one centred control that brings both eyes closer together or farther apart; enlarge ears if it can be done reliably.

- [x] Added Eye spacing to the Eyes section (−100 inward, +100 outward). A continuous displacement field moves both tracked eyes without copying an eye patch or changing pixels outside the face; it composes with the existing per-eye size controls. Reset Eyes and Reset All include the new value. Clip-scoped effects preserve it through project save/load and the shared preview/export renderer.
- [x] Synthetic marker test verified both eye centres move in the requested directions, exterior pixels stay unchanged, Reset Eyes clears it, and project persistence retains it. Source Custom Face module: 7/7 passed. Full regression: `build/custom-face-eye-spacing-regression/report.json`, **492 tests passed**. Real 2-second effect export with Eye spacing produced `build/custom-face-eye-spacing-export-home/cache/vision-renders/a7bf2adc0194002926ea820fbf2c84a6d653ab50a33293319fe64b50ef81d414.mkv` (17,760,435 bytes). Inspected real-face variations under `build/custom-face-eye-spacing-visual` and Default/Ableton dialog captures under `build/custom-face-check`.
- [x] Staged bundle `build/custom-face-eye-spacing-stage/KineticCut` passed startup at `build/custom-face-eye-spacing-staged-startup/report.json`. After confirming the editor was not running, moved the previous complete bundle to `build/release-backups/KineticCut-before-eye-spacing-20260925`, installed the staged bundle to `dist/KineticCut`, matched EXE hashes, and passed installed startup at `build/custom-face-eye-spacing-installed-startup/report.json`. Installed EXE SHA-256 `75E136A7E603312A9CCB11949050826B44525F12555F397A51D8582B89103822`.
- [ ] Ear enlargement was not added: the current 478-point face mesh does not delineate the ears, and a guessed warp could deform hair/headsets. It needs reliable ear segmentation/tracking and separate motion/occlusion quality checks. No user project, media or settings were changed.

# 2026-09-25 — Custom Face popup output framing

User report: the Custom Face popup showed the full landscape source while the timeline viewer displayed only the portrait output slice after clip placement. A generic early QA image was also misleading because it used a different clip and its default transform.

- [x] The dialog now decodes an uncropped bounded source frame, applies its live face effect through the same selected-item preview raster path, and composites the result into the project's output width/height using `PreviewCanvas` geometry/drawing. This preserves the selected item's crop, position, zoom, rotation, flip, keyframes, opacity and compatible pixel effects. Face guides are drawn on a copy of the prepared cropped layer so they do not contaminate the renderer cache. Show original keeps the clip framing but removes the Custom Face morph. The authoring view still shows only the selected clip, not unrelated timeline layers; Apply/Cancel semantics are unchanged.
- [x] Reproduced the user's 1080×1920 framing with read-only `C:\Users\F\Downloads\cinna ratting.mp4` and its existing analysis; approximate left-edge placement from the screenshot gave the same narrow portrait slice with the subject and rating board at `build/custom-face-cinna-dialog/dialog-default.png`. The user's unsaved timeline transform was not available from the recovery file, so that diagnostic placement was inferred from the screenshot, not claimed as exact saved state. Default/Obsidian/Ableton popup captures were produced. User media/project/settings were not modified.
- [x] Regression asserts output aspect, crop, position, scale, horizontal flip and animated scale keyframes in the popup. Focused Custom Face module 8/8 passed; full `build/custom-face-framing-regression/report.json` **493 tests passed**. Staged startup `build/custom-face-framing-staged-startup/report.json` passed.
- [x] With Kinetic Cut closed, backed up the complete previous bundle to `build/release-backups/KineticCut-before-face-framing-20260925`, installed the verified stage to `dist/KineticCut`, matched EXE SHA-256 `128BF92EB43637EE3FD8C55D4257FC0908783BC64BDB6EC930E72EACE13E5EFA`, and passed installed startup at `build/custom-face-framing-installed-startup/report.json`.

# 2026-09-25 — YouTube AV1 video plays audio but shows black timeline output

User report: the downloaded `dist/KineticCut/assets/downloads/xQc and jesse.mp4` had valid thumbnails and audio but rendered black in the timeline. The supplied source and any user project were not edited.

- [x] `ffprobe` identified AV1 Main video at 1920×1080/60 fps plus AAC audio. The existing Qt live `QVideoSink` emitted **zero frames** from the original in a 3.5-second direct decoder check despite normal buffering and no reported Qt error. FFmpeg thumbnails decoded successfully. A cached H.264 compatibility copy emitted **194 valid Qt frames** over the same interval; this isolates the decoder incompatibility rather than the timeline painter.
- [x] Import probing now persists `video_codec`; older project media is inspected asynchronously. Full preview automatically prepares a source-preserving, up-to-1920px H.264 video-only compatibility copy for AV1. Timeline video decoders avoid opening unsupported AV1 while it is being prepared and show the existing thumbnail temporarily. The audio decoder, clip timings/properties and export still use the original file. Optimized preview keeps its previous behavior. No file stat was added to the per-frame timeline path.
- [x] Reproduced and fixed a second launch-order race: the first background missing-media scan reported an available file as a change and invalidated the just-ready proxy. Initial *available* scans no longer invalidate media; genuine missing/reappeared transitions still do. A ready compatibility preview is also reconciled after a project switch. Both a fresh profile and a repeated, cached profile played the real source in the in-memory two-track timeline with **25 distinct decoded visual frames in 25 samples** and one active original-audio decoder.
- [x] New downloads use `Downloads/Kinetic Cut` (or the isolated data directory under `KINETIC_CUT_HOME`) instead of the replaceable executable assets folder. The existing downloaded MP4 was preserved at its original project-referenced path during installation, with SHA-256 `DEA7C7C8718DEE9A0331816151B71E0B0E2D8BA6A30CCC07CB6B37758DE3E759` before/after. Future bundle replacements must continue preserving this legacy `assets/downloads` file unless the project is explicitly relinked.
- [x] Focused AV1 and missing-media tests passed; final full source regression `build/av1-final-regression/report.json`: **499 tests passed**. Final staged EXE startup passed at `build/av1-final-staged-startup/report.json`. The complete prior bundle is retained at `build/release-backups/KineticCut-before-av1-preview-20260925`; an intermediate EXE is retained at `build/release-backups/KineticCut-exe-before-av1-final-20260925.exe`.
- [x] Final installed `dist/KineticCut/KineticCut.exe` matches staged SHA-256 `8EA0DBAC7C1AC15FC4C1397014771F21B13EF5E0C7D26145FA1A6C94F15D84EC`; installed startup passed at `build/av1-final-installed-startup/report.json`. The real AV1 end-to-end clip check ran against source code using the user MP4, while the installed EXE underwent startup/package verification; do not represent the latter as a manual click-through playback test.

# 2026-09-25 — Reduce AV1 first-use preview delay without dropping support

User clarification: the temporary low-quality still after timeline placement eventually became moving video; keep the AV1 compatibility path and make it faster or avoid it for new downloads where possible. The prior request to remove AV1 support/transcode every download was withdrawn.

- [x] Identified the still as the 320×180 import thumbnail displayed while FFmpeg builds a full-size H.264 compatibility preview. The supplied 41.7-second source is AV1 Main 1920×1080/60. On this PC, `av1_cuvid` is unsupported by the RTX 2070 SUPER; decoding this already-downloaded AV1 requires CPU work. A direct local benchmark of the same proxy pipeline took about 15.4 seconds with the old two-thread input cap versus 12.4 seconds with FFmpeg's automatic thread choice. Compatibility proxy preparation now uses automatic decoder threading; the existing optional 960px proxy keeps its old behavior.
- [x] Both downloader paths now ask yt-dlp to prefer AVC/H.264 after resolution, frame rate and HDR when choosing an MP4 stream. Verified locally with fabricated equal-size/equal-fps AV1 and AVC choices that yt-dlp sorts AVC last/best. If no matching AVC is offered, it retains the existing higher-quality AV1 fallback rather than silently dropping resolution or frame rate. The dialog no longer schedules the same downloaded file for import twice.
- [x] An imported AV1 starts compatibility preparation while still in the Media Pool, before timeline placement; preparation status shows percentage instead of an unexplained static thumbnail. Original source, original audio and export remain unchanged. The compatibility result stays cached. A first-time AV1 import is **not instantaneous**; the improvement moves preparation earlier and reduces its runtime. A matching AVC download can avoid this pass entirely.
- [x] AV1/downloader focused tests passed; complete source suite `build/av1-faster-regression/report.json`: **503 tests / 53 modules passed**. Fresh isolated real-source check on `dist/KineticCut/assets/downloads/xQc and jesse.mp4` generated a compatibility preview and observed 25 distinct frames in 25 samples plus one original-audio decoder. This was a source-path test, not a manual installed-GUI edit session.
- [x] Staged `build/av1-faster-stage/KineticCut/KineticCut.exe` startup passed at `build/av1-faster-staged-startup/report.json`. After confirming the editor was closed, backed up the previous EXE at `build/release-backups/KineticCut-exe-before-av1-faster-20260925.exe`, installed the new EXE at `dist/KineticCut/KineticCut.exe`, matched SHA-256 `07D618D7A32548A3541CF276276CFF7327B1F780D2ABCC0157C88E85CE20045C`, and passed installed startup at `build/av1-faster-installed-startup/report.json`. No bundled dependencies/assets changed, so only the frozen Python EXE was replaced. The existing user MP4 retained SHA-256 `DEA7C7C8718DEE9A0331816151B71E0B0E2D8BA6A30CCC07CB6B37758DE3E759`.

# 2026-09-26 — Risk-based test selection for faster isolated updates

User intent: assess unnecessary/redundant tests and establish explicit rules for
which tests every AI must run, without sacrificing correctness. Documentation-only.

- [x] Reviewed the two existing runners, current 53-module/503-method inventory,
  latest full regression timings, representative overlapping theme tests, mixed
  historical modules and native diagnostic entry points. Exact AST body comparison
  found no repeated test bodies; partial semantic overlap is not proved redundant.
  No tests were deleted/disabled and no runtime code changed.
- [x] Added `TESTING_POLICY.md`: focused change/neighbor coverage, mandatory full
  triggers, five-code-bearing-install checkpoint, relevant visual/real-media checks,
  isolated runner commands, staged/installed gates and honest scope reporting.
  Linked it from `AGENTS.md` and superseded blanket requirements in the context.
- [x] Validated all 53 mapped test module filenames, both runner paths and all
  13 referenced selftest flags against `main.py`. Checked AGENTS/context policy
  precedence and removed their operative blanket full-suite checklist wording.
- [x] Runtime tests/build/install not applicable: documentation only. Current
  installed EXE remains the verified 25 September AV1-faster build. Latest full
  baseline: `build/av1-faster-regression/report.json`, 503 passed. Code-bearing
  installations since that full pass: **0** (policy documentation does not count).
