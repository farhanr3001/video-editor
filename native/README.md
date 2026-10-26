# Native preview and timeline engine

The Windows editor keeps its PySide6 widgets, editor model, input handlers and
history. Two embedded `QQuickView` surfaces use Qt's threaded Direct3D 11 scene
graph. Do not replace these with `QQuickWidget`: that changes the render-loop
threading contract.

Ordinary video follows Qt FFmpeg → native `VideoOutput` textures → GPU crop,
transforms, opacity, colour and supported Gaussian/background blur → scene-graph
composition. Native media commands and decoder destruction run on an owned C++
thread. Hardware decode depends on the source/device; it is reported separately
from GPU composition. Text, motion graphics and unsupported pixel operations
retain exact, bounded background preparation and upload their finished textures.
Supported exports use the native D3D11 compositor and hardware encoder in
`gpu_export.cpp`; unsupported stacks retain exact compatibility preparation.

`RenderAdmission` coalesces update requests while the previous frame is in flight
instead of entering Qt's GUI-blocking scene synchronization. Its retry affects
preview admission only, never input or widget refresh. Window presentation uses
swap interval zero; DWM handles final desktop composition. Initial exposure,
device initialization and operating-system scheduling remain distinct from
steady-state input responsiveness.

Every window container must acquire its own native HWND **before first Show**.
Otherwise the timeline scroll area's native ancestors can cover a correctly
rendering preview. A renderer-only `grabWindow()` cannot detect that regression;
verify the actual parent window as well.

Timeline clip nodes, image loading, texture retention and peak sampling are
native/retained. Original ruler, timecode, pointed playhead and editing controls
retain their existing drawing and hit algorithms. Small original-pixel ruler
strips are cached with matching fractional-DPI phase, within an 8 MiB budget.
Live meters are independent of stationary track headers. The project runtime
index handles active/boundary/visible queries; private observers never enter
serialized projects or history snapshots.

## Build and verification

The Windows preview now has an isolated process boundary. `remote_preview.py`
keeps the input window and current edit hit geometry in the editor;
`gpu_preview_process.py` owns decoding, the existing GPU scene graph, effect
islands and presentation in a persistent child. The child embeds beneath an
input-owning native host and stays disabled for native input hit testing. It
inherits the owner's desktop explicitly, including private diagnostic desktops,
and never shows a helper top-level window. Audio remains in the editor transport.
When the frozen helper already starts on that desktop, leave its thread desktop
unchanged: the bootloader may already own hidden native windows, making even a
redundant `SetThreadDesktop` call fail with WinError 170. Startup errors return
through the owned control pipe; windowed multiprocessing children also receive
writable null standard streams so CPython cannot mask the original exception.

Playback transfers active/warm scene metadata and a shared monotonic clock, not
video images. Unchanged documents are acknowledged once and omitted from later
clock/control packets. The channel admits one batch in flight plus one latest
scene; explicit seek intent survives replacement. Only requested captures return
pixels. Acknowledgment prevents simultaneous large writes on the duplex pipe.
One bridge owns pipe polling, writes and closure. Owned-process supervision and
the close guard retain the host until the renderer has exited; parent death,
EOF, device failures and blocked writes have bounded cleanup/restart paths.
`KINETIC_GPU_PREVIEW_PROCESS=0` retains the in-process GPU compatibility option;
it does not turn hardware decoding into a claim of GPU composition.

`scripts/build_native.ps1` builds the interval/mailbox engine (C ABI **2**).
`scripts/build_qt_native.ps1` builds the Qt adapter against **Qt 6.11.2**, matching
the bundled PySide6 runtime. Its current C ABI is **3**. Update both native and
Python declarations whenever the ABI/buffer layout changes. The loader rejects
mismatches and retains the existing CPU compatibility path.

Run affected GPU/index/painting/input tests while iterating. Shared lifecycle,
model or composition changes require the complete isolated checkpoint under
`TESTING_POLICY.md`. `--gpu-functional-selftest <output> <project>` checks actual
clip/thumbnail/wave pixels, native embedding, editing/history, caption/effect/
transition parity, moving video and a short decoded export. Use a disposable
profile and do not save the owner's project.

Keep native test windows off the user's input desktop. The retained private
desktop launcher under `build/gpu-responsive-20261017/private-launcher.py` uses
an explicitly separate desktop and never calls `SwitchDesktop`. Do not use
topmost, foreground or focus-taking diagnostic windows. Performance runs come
after functional checks and run without concurrent builds/full tests.

The offline exporter (`scripts/build_gpu_export.ps1`, `gpu_export.dll`) now uses
C ABI **3**. Its CPU reader keeps the same callback signature:0 supplies pixels,
1 reports failure, and2 retains an already uploaded, dimension-matching raw
overlay texture. The Python worker accepts ABI2 with reuse disabled. Cached
caption images do not skip scene draws or encoded frames. Exact ASS sampling
uses original timestamps and conservative dynamic/boundary retention; unknown
scripts use the continuous path. Keep full native/owned-producer/pixel checks
when changing this protocol.

Diagnostics expose the backend, hardware texture evidence, native CPU/GPU
timings, coalesced source frames, deferred scene synchronization, bounded effect
work and GUI heartbeat delays. Qt's public decoder does not expose execution
duration or exact per-video presentation drops; unavailable fields stay null.
Do not rename delivery/seek latency or coalescing as those unavailable metrics.

Qt's synchronization behavior is documented by its
[pinned threaded render-loop source](https://github.com/qt/qtdeclarative/blob/v6.11.2/src/quick/scenegraph/qsgthreadedrenderloop.cpp).
