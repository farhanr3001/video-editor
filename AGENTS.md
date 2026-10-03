# Instructions for every coding agent

Before working on Kinetic Cut, read **AI_PROJECT_CONTEXT.md** and
**ACTIVE_TASKS.md** completely. Then read the implementation and relevant tests.
These are project-specific working instructions for Codex, Gemini, Claude and
other coding agents; they do not depend on one vendor's tools.

Before choosing verification for a change, read **TESTING_POLICY.md**. Its
risk-based selection rules supersede older blanket full-suite requirements:
isolated changes require affected/neighbor tests, while shared/high-risk changes
and periodic release checkpoints require the complete isolated module suite.
Every requested EXE still requires staged and installed package checks. Do not
delete/disable regression tests just to shorten a run; record the actual scope.

Follow the user's latest request and your host's higher-priority instructions.
Do not treat historical checked tasks as evidence that a reported regression is
fixed. Preserve the user's projects, media, settings and unrelated source edits.
Update the task ledger with evidence, not assumptions. Source changes, passing
tests, a staged build and an installed/verified EXE are different milestones.

The latest reported playhead-dragging performance regression has been **resolved and verified**.
The timeline playhead scrubbing fix has been verified across source tests, staged build, and installed EXE (see ACTIVE_TASKS.md).

## Build storage retention — owner instruction, 3 October 2026

Keep only the current staged application, current installed application, and one
verified rollback bundle. After a successful installed verification, remove the
superseded generated bundles and older rollbacks using verified absolute paths.
Keep small test reports/logs; do not accumulate complete bundles for each fix.
Check free space before staging and copying. Never delete build wholesale: some
test output is media referenced by projects. Personal .kcut files, Power Bin data,
assets_project, assets_docker_guide, Soundtracks and Sound_Effects are not release
payloads and must be preserved locally and excluded from Git/distribution.
