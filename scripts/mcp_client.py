"""Call the running local editor from a development shell without exposing tokens."""
import sys,json,argparse,base64
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from kinetic_cut.assistant_client import Client
from kinetic_cut.assistant import connection_settings
parser=argparse.ArgumentParser(); parser.add_argument('tool',nargs='?',default='get_state'); parser.add_argument('--arguments',default='{}'); parser.add_argument('--image')
args=parser.parse_args(); config=connection_settings(); client=Client(f"http://127.0.0.1:{config['port']}/mcp",config['token']); client.initialize('Codex local connection')
result=client.call(args.tool,**json.loads(args.arguments))
for block in result['content']:
    if block['type']=='text':print(block['text'])
    elif block['type']=='image' and args.image:Path(args.image).write_bytes(base64.b64decode(block['data'])); print('Preview saved to '+args.image)
