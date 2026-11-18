"""Known native reproductions and regression suites in one discoverable catalogue."""
import argparse,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.private_desktop import run
CASES={
    'recovery-updates-help':('--reliability-selftest','Recovery, Help, repair controls and all themes'),
    'preview-controls':('--gpu-functional-selftest','Selected media transform handles; full native preview checks'),
    'short-audio-cuts':('--audio-cut-selftest','Removed audio/video interval guards on synthetic media'),
    'tracking':('--tracking-selftest','Object tracking preview, selection and playback'),
    'speech-service':('--tts-provider-selftest','Live free online speech generation; sends synthetic diagnostic text'),
    'startup':('--startup-windows-selftest','Native window placement and ordinary startup'),
}
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('case',choices=sorted(CASES));parser.add_argument('output',type=Path);parser.add_argument('--exe',type=Path)
    a=parser.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    cmd=[a.exe] if a.exe else [Path(sys.executable),ROOT/'main.py']
    sys.exit(run(cmd+[CASES[a.case][0],a.output],a.output/'console.log',ROOT))
