"""Run the native TTS dialog stability diagnostic in a disposable app profile."""
import os
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
output = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "build/tts-stability/native"
os.environ["KINETIC_CUT_HOME"] = str(output / "home")
from kinetic_cut.tts_stability_diagnostics import run
raise SystemExit(run(output))
