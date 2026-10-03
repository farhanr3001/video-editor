"""Convenience launcher for the app-owned native timeline diagnostic."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kinetic_cut.timeline_diagnostics import run

if __name__=='__main__':
    sys.exit(run(sys.argv[1] if len(sys.argv)>1 else ROOT/'build/lagtest-marquee-diagnosis',
                 ROOT/'LagTest.kcut', '--waveforms' in sys.argv))
