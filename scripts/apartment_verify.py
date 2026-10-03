"""Final read-only media QA plus a sensible live-editor handoff."""
import sys,json,subprocess,hashlib,time,base64
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
OUT=ROOT/'build/apartment-edit'; video=ROOT/'exports/Apartment Tour - xQc.mp4'
from kinetic_cut.assistant_client import Client
from kinetic_cut.assistant import connection_settings
config=connection_settings(); client=Client(f'http://127.0.0.1:{config["port"]}/mcp',config['token']); client.initialize('Codex final QA')
jobs=client.value('get_jobs'); job=next(j for j in jobs['renders'] if j['id']=='64957a1c3462')
assert job['state']=='Complete' and not job['error']
def run(args):return subprocess.run(args,capture_output=True,check=True,creationflags=0x08000000)
probe=json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(video)]).stdout)
run(['ffmpeg','-v','error','-i',str(video),'-f','null','-'])
meter=run(['ffmpeg','-hide_banner','-i',str(video),'-vn','-af','loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json','-f','null','-']).stderr.decode(errors='replace')
levels=json.loads(meter[meter.rfind('{'):meter.rfind('}')+1])
project=json.loads((ROOT/'Apartment Tour - xQc.kcut').read_text())
assert len(project['media'])==3 and len(project['video_tracks'])==3
assert all(i['in_point']>=0 and i['duration']>0 for i in project['timeline'])
stream=next(s for s in probe['streams'] if s['codec_type']=='video')
assert (stream['width'],stream['height'],stream['r_frame_rate'])==(1080,1920,'60/1')
assert abs(float(probe['format']['duration'])-28.85)<.05
assert float(levels['input_tp']) < -1
controls=client.value('inspect_ui')['controls']
edit=next(c for c in controls if c['type']=='QToolButton' and c.get('text')=='Edit')
client.value('ui_control',target=edit['target'],operation='click')
client.value('seek',seconds=.7)
time.sleep(.8)
snapshot=client.call('get_preview',area='workspace',max_width=1600)
for block in snapshot['content']:
    if block['type']=='image':(OUT/'final-live-workspace.png').write_bytes(base64.b64decode(block['data']))
report=dict(passed=True,render_job=job,full_decode=True,duration=probe['format']['duration'],
    resolution=[stream['width'],stream['height']],fps=stream['r_frame_rate'],audio_levels=levels,
    project_video_tracks=project['video_tracks'],timeline_items=len(project['timeline']),captions=len(project['captions']),
    output_sha256=hashlib.sha256(video.read_bytes()).hexdigest(),live_editor=client.value('get_state',section='summary'))
(OUT/'final-qa.json').write_text(json.dumps(report,indent=2)); print(json.dumps(report,indent=2))
