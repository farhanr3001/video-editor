"""Apply the measured dialogue lift and render using the running editor."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from kinetic_cut.assistant_client import Client
from kinetic_cut.assistant import connection_settings
config=connection_settings(); client=Client(f'http://127.0.0.1:{config["port"]}/mcp',config['token'])
client.initialize('Codex apartment edit')
state=client.value('get_state')
assert state['name']=='Apartment Tour | xQc'
audio=[i for i in state['project']['timeline'] if i['track']=='audio_1']
assert len(audio)==8 and all(i['gain_db'] in {-1,-10} for i in audio), 'Do not apply gain twice'
client.value('apply_edits',revision=state['revision'],operations=[dict(op='update',collection='timeline',id=i['id'],values=dict(gain_db=i['gain_db']+7)) for i in audio])
client.value('seek',seconds=0)
client.value('project_file',operation='save',path=str(ROOT/'Apartment Tour - xQc.kcut'),overwrite=True)
job=client.value('queue_export',path=str(ROOT/'exports/Apartment Tour - xQc.mp4'),encoder='Auto',codec='h264',bitrate_mbps=14,burn_subtitles=True,export_audio=True,start=True,overwrite=True)
print(json.dumps(job))
