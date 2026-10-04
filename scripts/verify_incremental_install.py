"""Disposable installed update/migration checks. Never use the real uninstall AppId."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from kinetic_cut import update_files as f
from kinetic_cut.update_helper import probe


def execute(command, env):
    result = subprocess.run([str(x) for x in command], env=env, cwd=ROOT, timeout=240,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:raise RuntimeError('Verification command failed: ' + str(command[0]))


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--test-installer', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT/'build/incremental-update/integration')
    args = parser.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True,exist_ok=True)
    root = out/'installed'; profile = out/'profile'
    env = dict(os.environ, KINETIC_CUT_HOME=str(profile), KINETIC_CUT_UPDATE_PROBE='1')
    stage = ROOT/'build/distribution-stage/KineticCut'
    old = ROOT/'dist/KineticCut'
    baseline = json.loads((ROOT/'build/incremental-update/baseline-1.1.0.json').read_text())
    if f.digest(old/'KineticCut.exe') != baseline['files']['KineticCut.exe']['sha256']:raise RuntimeError('Legacy fixture is no longer 1.1.0')
    if root.exists():raise RuntimeError('Disposable installed directory already exists; inspect it before retrying')
    root.mkdir()
    # Never copy another installation's uninstaller log: it contains absolute paths.
    for name in baseline['files']:
        destination = root/name; destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(old/name,destination)
    profile.mkdir(exist_ok=True); data = profile/'data'; data.mkdir(exist_ok=True)
    settings = profile/'config/settings.json'; settings.parent.mkdir(); settings.write_text('{"ui_theme":"resolve"}')
    power = data/'powerbins.json'; power.write_text('{"media":[]}')
    component = data/'components/fixture/pack-ready.json'; component.parent.mkdir(parents=True); component.write_text('{}')
    external = out/'preserve.kcut'; external.write_text('user project')
    personal = root/'preserve.kcut'; personal.write_text('user project inside install')
    # Migration through the actual small EXE and its copied, independent helper.
    execute([args.test_installer,'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/NOICONS',f'/DIR={root}','/COMPONENTS=main',f'/LOG={out / "migration.log"}'],env)
    manifest = f.validate_manifest(json.loads((stage/f.MANIFEST).read_text()))
    f.verify_install(root,manifest)
    assert settings.read_text() == '{"ui_theme":"resolve"}' and power.read_text() == '{"media":[]}' and component.is_file()
    probe(root,out/'migration-startup')
    # Exercise skipped-version planning and real frozen helper execution; use unchanged EXE,
    # but target new app-owned asset and removed old asset. This is a transport fixture,
    # not a claim that an unreleased 1.1.3 editor was compiled.
    transport = json.loads(json.dumps(manifest)); transport['version']='1.1.3'
    payloads = out/'payloads'; payloads.mkdir()
    import hashlib,zipfile
    copied=out/'KineticCutUpdater.exe';shutil.copy2(stage/'KineticCutUpdater.exe',copied)
    failed = json.loads(json.dumps(manifest)); failed['version']='1.1.2'
    broken_exe = b'intentionally invalid test executable'
    bad_archive = payloads/'bad.zip'
    with zipfile.ZipFile(bad_archive,'w',compression=zipfile.ZIP_DEFLATED) as z:z.writestr('KineticCut.exe',broken_exe)
    bad_sha=f.digest(bad_archive); bad_archive.rename(payloads/('KineticCut-Part-'+bad_sha+'.zip'))
    failed['bundles'][bad_sha]=dict(sha256=bad_sha,size=(payloads/('KineticCut-Part-'+bad_sha+'.zip')).stat().st_size,
        url=f'https://github.com/farhanr3001/video-editor/releases/download/v1.1.2/KineticCut-Part-{bad_sha}.zip')
    failed['files']['KineticCut.exe']=dict(sha256=hashlib.sha256(broken_exe).hexdigest(),size=len(broken_exe),bundle=bad_sha)
    failed_job=f.stage_update(root,failed,f.plan(root,failed),out/'failed-update',threading.Event(),local_payloads=payloads)
    failure=subprocess.run([str(copied),'apply',str(failed_job),'--no-restart','--quiet'],env=env,timeout=120,creationflags=subprocess.CREATE_NO_WINDOW)
    assert failure.returncode == 1
    f.verify_install(root,manifest)
    assert not (root/f.JOURNAL).exists()
    # Simulate interruption after replacement and exercise recovery in the frozen helper.
    f.prepare_transaction(root, {'KineticCut.exe':dict(sha256=hashlib.sha256(broken_exe).hexdigest())},
                          {'KineticCut.exe':f.digest(root/'KineticCut.exe')})
    (root/'KineticCut.exe').write_bytes(broken_exe)
    execute([copied,'recover',root,'--no-restart','--quiet'],env)
    f.verify_install(root,manifest)
    archive = payloads/'test.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:z.writestr('_internal/update-verification.txt',b'verified incremental asset')
    checksum=f.digest(archive); archive.rename(payloads/('KineticCut-Part-'+checksum+'.zip'))
    transport['bundles'][checksum]=dict(sha256=checksum,size=(payloads/('KineticCut-Part-'+checksum+'.zip')).stat().st_size,
        url=f'https://github.com/farhanr3001/video-editor/releases/download/v1.1.3/KineticCut-Part-{checksum}.zip')
    transport['files']['_internal/update-verification.txt']=dict(sha256=hashlib.sha256(b'verified incremental asset').hexdigest(),size=26,bundle=checksum)
    # Correct size from the actual fixture, never infer character count.
    transport['files']['_internal/update-verification.txt']['size']=len(b'verified incremental asset')
    job=f.stage_update(root,transport,f.plan(root,transport),out/'update',threading.Event(),local_payloads=payloads)
    execute([copied,'apply',job,'--no-restart'],env); f.verify_install(root,transport)
    assert personal.is_file() and external.is_file() and settings.is_file() and component.is_file()
    # New asset must be cleaned even though it is absent from the native installer file log.
    execute([root/'unins000.exe','/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',f'/LOG={out / "uninstall.log"}'],env)
    # Inno starts a second-phase uninstaller. The launcher can exit before that
    # child finishes inventory cleanup; wait for its final log closure.
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        text = (out/'uninstall.log').read_text(encoding='utf-8-sig',errors='replace')
        if 'Log closed.' in text:break
        time.sleep(.2)
    else:raise RuntimeError('The second-phase Windows uninstaller did not finish')
    assert not (root/'_internal/update-verification.txt').exists()
    assert not (root/'KineticCut.exe').exists() and not component.exists()
    assert external.is_file() and personal.is_file() and power.is_file()
    report=dict(passed=True,real_legacy_migration=True,frozen_incremental_helper=True,skipped_version_transport_fixture=True,
                frozen_failed_startup_rollback=True,frozen_interrupted_update_recovery=True,
                settings_powerbin_components_preserved_during_update=True,incremental_added_file_removed_on_uninstall=True,
                personal_projects_preserved=True)
    f.write_json(out/'report.json',report); print(json.dumps(report))


if __name__=='__main__':main()
