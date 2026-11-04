"""Rebuild local KineticCut.exe with up-to-date Python source changes."""
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import sys

from PyInstaller.archive.readers import CArchiveReader
from PyInstaller.archive.writers import CArchiveWriter, ZlibArchiveWriter
from PyInstaller.loader.pyimod01_archive import PYZ_ITEM_NSPKG, PYZ_ITEM_PKG
from PyInstaller.utils.win32.winutils import update_exe_pe_checksum as _windows_checksum

root = Path.cwd().resolve()
# Optional: restrict to specific modules (e.g. `--only widgets,timeline`). Needed when running on a
# different Python build than the one that made the exe, which makes unchanged modules compare as different.
ONLY = None
if '--only' in sys.argv:
    ONLY = {name.strip() for name in sys.argv[sys.argv.index('--only') + 1].split(',') if name.strip()}


def update_exe_pe_checksum(path):
    """PyInstaller's helper needs ctypes.windll; fall back to pefile when running off Windows."""
    try:
        return _windows_checksum(path)
    except RuntimeError:
        import pefile
        pe = pefile.PE(path, fast_load=True)
        value = pe.generate_checksum(); offset = pe.OPTIONAL_HEADER.get_field_absolute_offset('CheckSum'); pe.close()
        with open(path, 'r+b') as handle:
            handle.seek(offset); handle.write(struct.pack('<I', value))

sys.path.insert(0, str(root))
from kinetic_cut import update_files as f


def rebuild_exe(exe_path: Path):
    print(f"Rebuilding {exe_path}...")
    raw = exe_path.read_bytes()
    old = CArchiveReader(str(exe_path))
    assert old._end_offset == len(raw)

    pyz_name = next(n for n, v in old.toc.items() if v[-1] == 'z')
    z = old.open_embedded_archive(pyz_name)

    codes = {}
    entries = []
    for name, (kind, offset, length) in z.toc.items():
        entries.append(
            (
                name,
                None
                if kind == PYZ_ITEM_NSPKG
                else '__init__.py'
                if kind == PYZ_ITEM_PKG
                else 'module.py',
                'PYMODULE',
            )
        )
        if kind != PYZ_ITEM_NSPKG:
            codes[name] = z.extract(name)

    targets = []
    added = []
    for source in (root / 'kinetic_cut').glob('*.py'):
        name = 'kinetic_cut.' + source.stem if source.stem != '__init__' else 'kinetic_cut'
        if ONLY is not None and source.stem not in ONLY:
            continue
        compiled = compile(source.read_bytes(), 'kinetic_cut/' + source.name, 'exec')
        if name in codes:
            if codes[name] != compiled:
                targets.append(name)
                codes[name] = compiled
        elif name != 'kinetic_cut':
            # A brand-new plain module of the app package: add it to the archive.
            entries.append((name, 'module.py', 'PYMODULE'))
            codes[name] = compiled; targets.append(name); added.append(name)

    if not targets:
        print(f"{exe_path} is already completely up to date with source.")
        return exe_path, []

    print(f"Updating {len(targets)} modules in {exe_path.name}: {targets}")

    pyz_temp = exe_path.with_name(f"{exe_path.stem}-patched.pyz")
    ZlibArchiveWriter(str(pyz_temp), entries, codes)
    payload = pyz_temp.read_bytes()
    pyz_temp.unlink()

    stream = io.BytesIO()
    toc = []
    for name, (offset, size, uncompressed, compressed, kind) in old.toc.items():
        data = payload if name == pyz_name else raw[old._start_offset + offset : old._start_offset + offset + size]
        assert name != pyz_name or compressed == 0
        toc.append(
            (
                stream.tell(),
                len(data),
                len(data) if name == pyz_name else uncompressed,
                compressed,
                kind,
                name,
            )
        )
        stream.write(data)

    for option in old.options:
        toc.append((0, 0, 0, 0, 'o', option))

    toc_offset = stream.tell()
    toc_data = CArchiveWriter._serialize_toc(toc)
    stream.write(toc_data)

    magic, _, _, _, version, library = struct.unpack(
        old._COOKIE_FORMAT, raw[old._end_offset - old._COOKIE_LENGTH : old._end_offset]
    )
    stream.write(
        struct.pack(
            old._COOKIE_FORMAT,
            magic,
            stream.tell() + old._COOKIE_LENGTH,
            toc_offset,
            len(toc_data),
            version,
            library,
        )
    )

    pending = exe_path.with_name(f"{exe_path.stem}.pending.exe")
    pending.write_bytes(raw[: old._start_offset] + stream.getvalue())
    update_exe_pe_checksum(str(pending))

    new = CArchiveReader(str(pending))
    assert new.options == old.options and set(new.toc) == set(old.toc)
    nz = new.open_embedded_archive(pyz_name)
    assert set(nz.toc) == set(z.toc) | set(added)

    changed = [name for name in z.toc if z.extract(name) != nz.extract(name)] + added

    assert set(changed) == set(targets), (changed, targets)
    for target in targets:
        source_file = (root / target.replace('.', '/')).with_suffix('.py')
        assert nz.extract(target) == compile(
            source_file.read_bytes(), 'kinetic_cut/' + source_file.name, 'exec'
        )

    for name in old.toc:
        if name != pyz_name:
            assert old.extract(name) == new.extract(name), name

    # Atomic swap. A running Windows app keeps its exe locked against replacement but allows renaming.
    try:
        os.replace(pending, exe_path)
    except PermissionError:
        aside = exe_path.with_name(f"{exe_path.stem}.old-{int(__import__('time').time())}{exe_path.suffix}")
        os.rename(exe_path, aside); os.replace(pending, exe_path)
        print(f"Original exe was in use; moved to {aside.name} (delete it after restarting the app)")
    print(f"Successfully updated {exe_path} (new SHA: {f.digest(exe_path)})")
    return exe_path, targets


def update_manifest(folder: Path):
    manifest_file = folder / f.MANIFEST
    if not manifest_file.exists():
        return
    m = json.loads(manifest_file.read_text(encoding='utf-8'))
    exe_path = folder / 'KineticCut.exe'
    if 'KineticCut.exe' in m.get('files', {}):
        m['files']['KineticCut.exe']['sha256'] = f.digest(exe_path)
        m['files']['KineticCut.exe']['size'] = exe_path.stat().st_size
        f.validate_manifest(m)
        f.write_json(manifest_file, m)
        inv_file = folder / f.INVENTORY
        if inv_file.exists():
            inv_file.write_text(
                '\n'.join([*sorted(m['files']), f.MANIFEST, f.INVENTORY]) + '\n',
                encoding='utf-8',
            )
        print(f"Updated manifest and inventory for {folder}")


if __name__ == '__main__':
    dist_exe = root / 'dist/KineticCut/KineticCut.exe'
    stage_exe = root / 'build/distribution-stage/KineticCut/KineticCut.exe'

    rebuild_exe(dist_exe)
    update_manifest(dist_exe.parent)

    if stage_exe.exists():
        rebuild_exe(stage_exe)
        update_manifest(stage_exe.parent)

    print("Rebuild completed successfully!")
