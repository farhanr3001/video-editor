# Kinetic Cut MCP connection

The **AI Assistant** button at the top right opens connection setup/status, not a
built-in chatbot. Kinetic Cut remains the editor; instructions are entered in
Codex or another MCP-compatible client.

1. Keep Kinetic Cut open. Open **AI Assistant → Enable connection**.
2. Click **Connect to Codex**. This adds only `mcp_servers.kinetic_cut` to the
   user's Codex configuration, preserving other settings and saving a backup.
3. Reload MCP servers / restart Codex if the new tools are not available yet.
4. Ask the assistant to inspect Kinetic Cut. The panel reports the actual client
   handshake and last request, not merely the existence of a config entry.

For other clients, **Copy MCP configuration** supplies the loopback Streamable
HTTP URL and access token. Keep that token private. Disconnect stops the local
server; the separate checkbox controls enabling it on future launches. No model
download, API key, public server, or embedded chat interface is required.

Automatic enablement is silent, including command-line setup. A green check on
AI Assistant and inside its panel means an authenticated client has connected in
this editor session. Waiting listeners are not marked connected. Last-request
and idle information are shown: stateless HTTP does not continuously monitor
whether the client's process is still running.

## Tools and editing workflow

- `get_state` returns the live project, selection, jobs and revision.
- `get_capabilities` lists all model fields, edit operations, effects, and editor
  command signatures.
- `apply_edits` checks the revision and validates a staged batch before applying
  it as one undo step. Supports clips, caption/title styles, effects arrays,
  transforms/crops, audio values, track controls, splitting, trimming, linking,
  inserting media, project format, track creation/reordering/duplication/deletion.
- `import_media` indexes local files asynchronously and deduplicates pool entries.
- `seek` and `get_preview` inspect the viewer; `get_preview(area="workspace")`
  includes the whole editor. Seeking is asynchronous: a snapshot is of the
  currently displayed frame, not a promise that a pending decoder has completed.
- `select_items`, `history`, `project_file` control selection, undo/redo,
  checkpointing and saving/loading. Project switches checkpoint current work.
- `queue_export`, `render_control`, `get_jobs` provide queued snapshot exports,
  progress, errors and cancellation. Only `Complete` means render success.
- `editor_command` invokes normal workflows, including effects, titles, crop,
  captions, silence removal, webcam placement, clipboard and transport.
- `inspect_ui` and `ui_control` expose live controls, menus and Qt dialogs for
  remaining workflows, including optional component consent and settings.

Time values are seconds. Transform/crop coordinates are normalized. Get a fresh
revision before editing, then inspect a preview and the resulting state. GUI
commands may open a dialog or start background processing: command return does
not mean that analysis/rendering has finished. Native OS dialogs may require
manual completion; the explicit import/save/export tools avoid those dialogs.

## Reliability and privacy

Networking uses a background listener; widget operations are marshalled to Qt's
GUI thread. Expired queued requests cannot apply late edits. The connection binds
only to `127.0.0.1`, checks Origin/Host, and requires a per-installation token.
It does not execute arbitrary Python or expose a general-purpose system shell.
This still gives broad access to editor features without introducing an
uncancellable arbitrary-code operation on the editor's UI thread.

Edits respect locked lanes; an assistant can explicitly unlock a lane through
the track controls. Timeline deletion never deletes original media. Existing
output files require explicit overwrite, and exports cannot overwrite source
media. Returned project details and images are shared with the connected AI
client; local rendering does not mean the assistant's analysis is offline.

For development, `scripts/mcp_client.py` connects to the running instance using
the stored local credentials without printing the token. The packaged
`--assistant-selftest <folder>` command exercises a real HTTP handshake, tool
discovery, editing/undo/redo, preview, import and export in an isolated profile.
