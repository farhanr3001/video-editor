"""Compile a separate-identity/no-shortcuts installer and test its lifecycle privately."""
import argparse,json,os,shutil,subprocess,sys,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.check_project import fingerprint
from scripts.private_desktop import run as private_run
from scripts.release_gate import sha

def worker(output):
    output=Path(output).resolve();os.environ['KINETIC_CUT_HOME']=str(output/'profile')
    from kinetic_cut import update_files as f
    from kinetic_cut.version import VERSION
    stage=ROOT/'build/distribution-stage/KineticCut';manifest=json.loads((stage/f.MANIFEST).read_text());f.verify_install(stage,manifest)
    root=output/'installed';root.mkdir(exist_ok=False);setup=output/'setup.exe';log=(output/'process.log').open('wb');child=None
    env=dict(os.environ,KINETIC_CUT_UPDATE_PROBE='1');result=dict(passed=False,kind='installer',source_fingerprint=fingerprint(),identity=json.loads((output/'build.json').read_text())['identity'])
    def command(args,timeout=300):
        completed=subprocess.run([str(a) for a in args],env=env,cwd=ROOT,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW,timeout=timeout)
        if completed.returncode:raise RuntimeError('Installer check failed: '+str(args[0]))
    try:
        switches=['/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/NOICONS','/COMPONENTS=main',f'/DIR={root}']
        command([setup,*switches,f'/LOG={output/"install.log"}']);f.verify_install(root,manifest)
        marker=output/'profile/data/keep-during-upgrade.txt';marker.parent.mkdir(parents=True,exist_ok=True);marker.write_text('retained')
        external=output/'personal-project.kcut';external.write_text('preserved personal project')
        child=subprocess.Popen([str(root/'KineticCut.exe'),'--mcp-bridge'],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log,env=env,creationflags=subprocess.CREATE_NO_WINDOW)
        time.sleep(.5);assert child.poll() is None
        command([setup,*switches,f'/LOG={output/"upgrade.log"}']);child.wait(timeout=10);f.verify_install(root,manifest)
        assert marker.read_text()=='retained';assert external.read_text()=='preserved personal project'
        command([root/'KineticCut.exe','--startup-selftest',output/'startup'],timeout=120)
        assert json.loads((output/'startup/report.json').read_text())['passed']
        command([root/'unins000.exe','/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',f'/LOG={output/"uninstall.log"}'])
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            text=(output/'uninstall.log').read_text(encoding='utf-8-sig',errors='replace')
            if 'Log closed.' in text and not root.exists():break
            time.sleep(.2)
        else:raise RuntimeError('Uninstaller second phase has not finished')
        assert external.read_text()=='preserved personal project'
        result.update(passed=True,install=True,repeated_upgrade=True,owned_bridge_closed=True,user_data_preserved=True,startup=True,uninstall_second_phase_closed=True,setup_sha256=sha(setup))
    finally:
        if child:
            if child.poll() is None:child.terminate();child.wait(timeout=5)
            child.stdin.close()
        log.close();(output/'report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return 0

def main():
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('--compiler',type=Path,default=ROOT/'build/tools/inno/ISCC.exe');p.add_argument('--worker',action='store_true');a=p.parse_args();output=a.output.resolve()
    if a.worker:return worker(output)
    if not output.is_relative_to(ROOT/'build'):raise ValueError('Installer test must use a dedicated build folder')
    if output.exists() and any(output.iterdir()):raise ValueError('Use a new empty installer-test folder')
    output.mkdir(parents=True,exist_ok=True);identity='{'+str(uuid.uuid4()).upper()+'}'
    (output/'build.json').write_text(json.dumps(dict(identity=identity,no_shortcuts=True)))
    with (output/'compiler.log').open('wb') as stream:
        subprocess.run([str(a.compiler),'/DTestingSetup','/DAppIdentity={'+identity,'/O'+str(output),'/Fsetup',str(ROOT/'installer/KineticCut.iss')],cwd=ROOT,stdout=stream,stderr=stream,check=True,timeout=600,creationflags=subprocess.CREATE_NO_WINDOW)
    code=private_run([sys.executable,Path(__file__),output,'--worker'],output/'console.log',ROOT,timeout=600)
    if not code and json.loads((output/'report.json').read_text())['passed']:(output/'setup.exe').unlink()
    return code
if __name__=='__main__':sys.exit(main())
