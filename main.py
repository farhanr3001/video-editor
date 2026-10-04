import json
import sys
from pathlib import Path

from kinetic_cut.process import install_desktop_process_policy


if __name__ == "__main__":
    if len(sys.argv) == 1:
        from kinetic_cut.update_helper import recover_on_startup
        if recover_on_startup():sys.exit(0)
    if len(sys.argv) == 2 and sys.argv[1] == '--uninstall-data':
        from kinetic_cut.uninstall_data import run
        sys.exit(run())
    if len(sys.argv) in (3,4) and sys.argv[1] == '--install-components':
        if getattr(sys,'frozen',False):
            from kinetic_cut.component_ui import installer_downloads as install_selected
        else:
            from kinetic_cut.feature_packs import install_selected
        sys.exit(install_selected(sys.argv[2].split(','),sys.argv[3] if len(sys.argv)==4 else None))
    install_desktop_process_policy()
    import multiprocessing
    multiprocessing.freeze_support()
    if len(sys.argv)==3 and sys.argv[1]=='--update-menu-selftest':
        from kinetic_cut.update_menu_diagnostics import run
        sys.exit(run(sys.argv[2]))
    if len(sys.argv)==4 and sys.argv[1]=='--caption-followup-selftest':
        from kinetic_cut.caption_followup_diagnostics import run
        sys.exit(run(sys.argv[2],sys.argv[3]))
    if len(sys.argv) in (4,5) and sys.argv[1]=='--caption-emoji-selftest':
        from kinetic_cut.caption_emoji_diagnostics import run
        sys.exit(run(sys.argv[2],sys.argv[3],len(sys.argv)==5 and sys.argv[4]=='--regenerate'))
    if len(sys.argv)==3 and sys.argv[1]=='--editing-followup-selftest':
        from kinetic_cut.editing_followup_diagnostics import run
        sys.exit(run(sys.argv[2]))
    if len(sys.argv) in (3,4) and sys.argv[1]=='--editing-selftest':
        from kinetic_cut.editing_diagnostics import run
        sys.exit(run(sys.argv[2],sys.argv[3] if len(sys.argv)==4 else None))
    if len(sys.argv) == 2 and sys.argv[1] == '--phone-worker':
        from kinetic_cut.phone_worker import run
        sys.exit(run())
    elif len(sys.argv) == 3 and sys.argv[1] == '--missing-selftest':
        from kinetic_cut.missing_diagnostics import run
        sys.exit(run(sys.argv[2]))
    elif len(sys.argv) == 4 and sys.argv[1] == '--timeline-selftest':
        from kinetic_cut.timeline_diagnostics import run
        sys.exit(run(sys.argv[2], sys.argv[3]))
    elif len(sys.argv) == 4 and sys.argv[1] == '--playback-selftest':
        from kinetic_cut.playback_diagnostics import run
        sys.exit(run(sys.argv[2], sys.argv[3]))
    elif len(sys.argv) == 3 and sys.argv[1] == '--theme-selftest':
        from kinetic_cut.theme_diagnostics import run
        sys.exit(run(sys.argv[2]))
    elif len(sys.argv) == 3 and sys.argv[1] == '--phone-selftest':
        from kinetic_cut.phone_diagnostics import run
        sys.exit(run(sys.argv[2]))
    elif len(sys.argv) == 4 and sys.argv[1] == "--caption-selftest":
        from kinetic_cut.captions import transcribe
        from kinetic_cut.config import load_settings
        settings = load_settings()
        captions, backend = transcribe(sys.argv[2], settings)
        Path(sys.argv[3]).write_text(json.dumps({"backend": backend,
                                                "captions": [c.__dict__ | {"style": c.style.__dict__} for c in captions]},
                                               indent=2), encoding="utf-8")
    elif len(sys.argv) == 3 and sys.argv[1] == "--workflow-selftest":
        from kinetic_cut.diagnostics import workflow_selftest
        sys.exit(workflow_selftest(sys.argv[2]))
    elif len(sys.argv)==3 and sys.argv[1]=='--cut-selftest':
        from kinetic_cut.cut_diagnostics import run
        sys.exit(run(sys.argv[2]))
    elif len(sys.argv) in (3,4) and sys.argv[1]=='--waveform-selftest':
        from kinetic_cut.waveform_diagnostics import run
        sys.exit(run(sys.argv[2],sys.argv[3] if len(sys.argv)==4 else None))
    elif len(sys.argv)==3 and sys.argv[1]=='--compound-selftest':
        from kinetic_cut.compound_diagnostics import run
        sys.exit(run(sys.argv[2]))
    elif len(sys.argv)==3 and sys.argv[1]=='--keyframe-selftest':
        from kinetic_cut.keyframe_diagnostics import run
        sys.exit(run(sys.argv[2]))
    elif len(sys.argv)==3 and sys.argv[1]=='--focus-selftest':
        from kinetic_cut.focus_diagnostics import run
        sys.exit(run(sys.argv[2]))
    elif len(sys.argv)==3 and sys.argv[1]=='--pool-selftest':
        from kinetic_cut.pool_diagnostics import run
        sys.exit(run(sys.argv[2]))
    elif len(sys.argv)==3 and sys.argv[1]=='--subtitle-selftest':
        from kinetic_cut.subtitle_diagnostics import run
        sys.exit(run(sys.argv[2]))
    elif len(sys.argv)==3 and sys.argv[1]=='--assistant-selftest':
        from kinetic_cut.assistant_diagnostics import run
        sys.exit(run(sys.argv[2]))
    elif len(sys.argv)==3 and sys.argv[1] in ('--startup-selftest','--startup-windows-selftest'):
        import os
        target=Path(sys.argv[2]).resolve(); target.mkdir(parents=True,exist_ok=True)
        native_windows = sys.argv[1] == '--startup-windows-selftest'
        os.environ['KINETIC_CUT_HOME']=str(target/'home'); os.environ['QT_QPA_PLATFORM']='windows' if native_windows else 'offscreen'
        from kinetic_cut.startup import run
        sys.exit(run(target, native_window_test=native_windows))
    elif len(sys.argv) >= 2 and sys.argv[1] == '--mcp-bridge':
        try:
            from kinetic_cut.mcp_bridge import run_bridge
            sys.exit(run_bridge())
        except Exception:
            sys.exit(0)
    elif len(sys.argv) >= 2 and sys.argv[1] == '--phone-worker':
        from kinetic_cut.phone_worker import run
        sys.exit(run())
    elif len(sys.argv) == 3 and sys.argv[1] == '--phone-selftest':
        from kinetic_cut.phone_diagnostics import run
        sys.exit(run(sys.argv[2]))
    else:
        from kinetic_cut.startup import run
        sys.exit(run())
