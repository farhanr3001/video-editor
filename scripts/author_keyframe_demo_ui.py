"""Author the demo using only advertised controls in the running app's dialog."""
import json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from kinetic_cut.assistant_client import Client
from kinetic_cut.assistant import connection_settings
config=connection_settings(); client=Client(f"http://127.0.0.1:{config['port']}/mcp",config['token']); client.initialize('Keyframe demo UI verification')
def call(tool,**args):
    response=client.call(tool,**args)
    if response.get('isError'):raise RuntimeError(response)
    return json.loads(next(b['text'] for b in response['content'] if b['type']=='text'))
def control(name,operation='click',value=None):
    live=call('inspect_ui')['controls']
    target=next(c for c in live if c.get('name')==name)
    result=call('ui_control',target=target['target'],operation=operation,**({'value':value} if operation=='set' else {}))
    if result.get('id'):
        for _ in range(100):
            jobs=call('get_jobs'); job=next((j for j in jobs['tasks'] if j['id']==result['id']),None)
            if job and job['state']!='Running':
                assert job['state']=='Complete',job
                break
            time.sleep(.03)
    return result
assert call('get_state',section='summary')['name']=='Keyframe Punch Zoom Demo'
assert any(c['type']=='KeyframeEditor' for c in call('inspect_ui')['controls'])
for at,scale,x,y in [(0,1,.5,.5),(3,1,.5,.5),(3.65,1.55,.54,.4),(5,1.55,.54,.4),(5.6,1,.5,.5)]:
    control('keyframe_time','set',at)
    for name,value in [('scale',scale),('x',x),('y',y)]:
        control('keyframe_add_'+name)
        control('keyframe_value_'+name,'set',value)
        control('keyframe_interpolation','set','Smooth')
dialog=next(c for c in call('inspect_ui')['controls'] if c['type']=='KeyframeEditor')
call('ui_control',target=dialog['target'],operation='accept')
state=call('get_state')
item=next(i for i in state['project']['timeline'] if i['id']=='demo_video')
assert set(item['keyframes'])=={'x','y','scale','scale_y'},item
assert all(len(keys)==5 for keys in item['keyframes'].values())
path=str(Path(__file__).resolve().parents[1]/'Keyframe Punch Zoom Demo.kcut')
print(call('project_file',operation='save',path=path,overwrite=True))
print(json.dumps(item['keyframes']))
