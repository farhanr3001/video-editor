"""Build deterministic, reusable changed-file payloads and the 1.1.0 bridge."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from kinetic_cut import update_files as files
from kinetic_cut.version import VERSION, REPOSITORY


def build(stage, output, version, previous=None, baseline=None):
    stage = Path(stage); output = Path(output); output.mkdir(parents=True, exist_ok=True)
    payload_dir = output / 'update-payloads'; payload_dir.mkdir(exist_ok=True)
    groups = {}; inventory = {}
    for path in sorted(stage.rglob('*')):
        if not path.is_file():continue
        name = path.relative_to(stage).as_posix()
        if name in (files.MANIFEST, files.INVENTORY):continue
        files.valid_name(name)
        item = dict(sha256=files.digest(path), size=path.stat().st_size); inventory[name] = item
        bucket = 'large:' + name if item['size'] > 256 * 1024 else 'small:' + str(int(hashlib.sha256(name.encode()).hexdigest()[:4], 16) % 64)
        groups.setdefault(bucket, []).append(name)
    bundles = {}
    for names in groups.values():
        pending = payload_dir / 'pending.zip'
        with zipfile.ZipFile(pending, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
            for name in names:
                info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0)); info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                with zipped.open(info, 'w') as target, (stage / name).open('rb') as source:shutil.copyfileobj(source, target)
        checksum = files.digest(pending); filename = 'KineticCut-Part-' + checksum + '.zip'
        item = dict(sha256=checksum, size=pending.stat().st_size,
                    url=f'https://github.com/{REPOSITORY}/releases/download/v{version}/{filename}')
        if previous and checksum in previous['bundles']:
            item = previous['bundles'][checksum]; pending.unlink()
        else:pending.replace(payload_dir / filename)
        bundles[checksum] = item
        for name in names:inventory[name]['bundle'] = checksum
    manifest = files.validate_manifest(dict(schema=1, application='KineticCut', version=version, files=inventory, bundles=bundles))
    current_payloads = {'KineticCut-Part-' + key + '.zip' for key, item in bundles.items()
                        if f'/download/v{version}/' in item['url']}
    for archive in payload_dir.glob('KineticCut-Part-*.zip'):
        if archive.name not in current_payloads:archive.unlink()
    files.write_json(stage / files.MANIFEST, manifest)
    (stage / files.INVENTORY).write_text('\n'.join([*sorted(inventory), files.MANIFEST, files.INVENTORY]) + '\n', encoding='utf-8')
    shutil.copy2(stage / files.MANIFEST, output / f'KineticCut-Update-{version}.json')
    if baseline:
        bridge = ROOT / 'build/incremental-update/migration'
        if bridge.exists():shutil.rmtree(bridge)
        bridge.mkdir(parents=True)
        changed = [name for name, item in inventory.items() if baseline['files'].get(name, {}).get('sha256') != item['sha256']]
        for name in [*changed, files.MANIFEST, files.INVENTORY]:
            dest = bridge / name; dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(stage / name, dest)
        files.write_json(output / 'KineticCut-Baseline-1.1.0.json', baseline)
        files.write_json(ROOT / 'build/incremental-update/bridge-report.json', dict(version=version, files=changed,
                         changed_bytes=sum(inventory[name]['size'] for name in changed),
                         download_bytes=sum(bundles[key]['size'] for key in {inventory[name]['bundle'] for name in changed})))
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--previous', type=Path); parser.add_argument('--baseline', type=Path, required=True)
    args = parser.parse_args()
    build(ROOT / 'build/distribution-stage/KineticCut', ROOT / 'release', VERSION,
          json.loads(args.previous.read_text()) if args.previous else None, json.loads(args.baseline.read_text()))
