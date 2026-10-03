# Phone Connect

The third workspace tab pauses timeline playback and disables timeline shortcuts.
Deliver's **Send Completed Video to Phone** stages its output here; it never sends
to a device without the user's destination choice and Send action.

## Capabilities

| Capability | iPhone / iPad | Android |
|---|---|---|
| Detection | USB usbmux / trusted pairing | Local ADB / authorized device |
| Browse and send | File-sharing apps' Documents | Shared storage under `/sdcard` |
| Copy to PC | App documents and local DCIM files | Regular shared-storage files |
| Gallery | App's Share → Save Video/Image action on phone; no direct Camera Roll injection | Send and request media scan; visibility depends on format/OS |
| Mirror / control | Not implemented; Apple's iPhone Mirroring requires Mac | Official scrcpy native window embedded in page |
| Cloud / root | Neither | Neither |

On Windows the iPhone backend requires **Apple Mobile Device Service**. Upstream
recommends iTunes from Microsoft Store to provide it. Apple Devices is useful for
Apple's own file-sharing workflow but did not expose the needed localhost usbmux
service on the test PC. Unlock and trust, then Connect. Receiving requires an
already installed compatible file-sharing app; no apps are installed automatically.
No jailbreak, Developer Mode or filesystem spoofing. DCIM can omit cloud-only
originals; download those on the phone before copying.

Android needs Developer options → USB debugging and authorization. Some phones
need an OEM USB driver. Official scrcpy 4.1 includes ADB and is bundled; USB Setup
allows executable overrides. Private app storage, protected Android/data folders,
symlinks, root access, recursive folder copying and in-app MTP are not implemented.
Open Windows Device Browser provides Windows' MTP alternative.

## Architecture and safety

- `phone_common.py`: scoped paths and safe device/Windows filenames.
- `phone_worker.py`: one JSON request per hidden process; pymobiledevice3 11.15.5
  async AFC/HouseArrest or adbutils 2.12.0 SYNC. iOS USB selection is explicit and
  usbmux is pinned to localhost:27015. Device libraries never enter the GUI process.
- `phone_process.py`: QProcess JSONL bridge, byte progress, deadlines, cancellation
  and bounded forced-stop fallback.
- `phone_connect.py`: device/location selection, native local-file drop, browse
  picker, multi-file copy and serial queue. Immutable device/destination snapshots
  prevent retargeting when switching phones. Generation tokens reject stale lists.
- `phone_mirror.py`: embeds only its own scrcpy PID's window. Stops on leaving
  the page or changing devices; separate-window fallback if embedding fails.
  Never kills another mirror or an existing ADB server.

Random `.kinetic-<uuid>.partial` files are checked for complete byte size before
publication. Local downloads flush and publish without replacing existing files.
Existing-name conflicts fail explicitly. Ordinary cancellation cleans only its
owned partial; cable removal or forced shutdown may leave one. Source files are
never deleted. Size verification is not a cryptographic integrity proof. Queue
history is session-only; failed/cancelled jobs offer explicit Retry.

## Primary research sources (September 20, 2026)

- Apple file sharing: https://support.apple.com/guide/devices-windows/transfer-files-between-your-devices-mchl4bd77d3a/windows
- Apple Mirroring: https://support.apple.com/en-us/120421
- Windows USB/trust requirements: https://doronz88.github.io/pymobiledevice3/guides/troubleshooting/
- AFC: https://github.com/doronz88/pymobiledevice3/blob/master/pymobiledevice3/services/afc.py
- App Documents: https://github.com/doronz88/pymobiledevice3/blob/master/pymobiledevice3/services/house_arrest.py
- ADB authorization: https://developer.android.com/tools/adb
- SYNC library: https://github.com/openatx/adbutils
- scrcpy: https://github.com/Genymobile/scrcpy

The mockup is a layout reference, not evidence of a Photos write API, unrestricted
iPhone filesystem or Windows equivalent of Apple's Mirroring.

## Verification

Run `scripts/unit_tests.py test_phone_connect.py`, then the full suite.
`main.py --phone-selftest <fresh-directory>` (also supported by the EXE) checks
actual helper startup, honest unavailable states, tools, navigation/shortcuts and
large/compact widget snapshots. It does not claim successful hardware transfers.
Real device checks separately need list, small upload/download hash comparison,
Unicode names, conflicts, cancellation, disconnect and Android mirroring. Retain
untested hardware cases explicitly in ACTIVE_TASKS.md.

The official scrcpy ZIP SHA256 is
`5b12172b3264b2889f4583ee64752ce832e29bc8b1089dca81093459697165db`,
checked against upstream SHA256SUMS.txt before extraction. Keep matching ADB,
scrcpy/server libraries and notices together when updating.
