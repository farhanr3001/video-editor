"""Real free Edge speech request cancellation, in an isolated output directory."""
from pathlib import Path
import json
import os
import sys
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
output = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "build/tts-stability/backend"
output.mkdir(parents=True, exist_ok=True)
os.environ["KINETIC_CUT_HOME"] = str(output / "home")
from kinetic_cut import tts

report = {"service": "Free Microsoft Edge speech service", "paid_service_used": False}
cancel = threading.Event()
entered = threading.Event()
real_save = tts.edge_tts.Communicate.save

async def observed_save(communicator, *args, **kwargs):
    entered.set()
    return await real_save(communicator, *args, **kwargs)

timer = threading.Timer(.25, cancel.set)
began = time.monotonic()
timer.start()
try:
    with patch.object(tts.edge_tts.Communicate, "save", observed_save):
        tts.synthesize_speech("This is a real speech cancellation test. " * 100,
                              voice="en-US-BrianNeural", output_path=output / "cancelled.mp3",
                              cancel_check=cancel.is_set)
    report["cancelled"] = False
    report["error"] = "Unexpected successful delivery after cancellation"
except InterruptedError:
    report["cancelled"] = True
except Exception as err:
    report["cancelled"] = False
    report["error"] = repr(err)
finally:
    timer.cancel()
    report["entered_real_network_coroutine"] = entered.is_set()
    report["elapsed_seconds"] = time.monotonic() - began
    report["final_audio_published"] = (output / "cancelled.mp3").exists()
    report["remaining_request_temp_dirs"] = [path.name for path in output.glob(".tts-*")]
    report["passed"] = bool(report["cancelled"] and entered.is_set() and report["elapsed_seconds"] < 2
                             and not report["final_audio_published"] and not report["remaining_request_temp_dirs"])
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
sys.exit(0 if report["passed"] else 1)
