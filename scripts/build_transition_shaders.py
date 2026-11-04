"""Generate paired-image Qt and D3D11 shaders from transition map graphs."""
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
import subprocess,shutil
from kinetic_cut.animated_transitions import ALL_NAMES,NAMES,EXTRA_NAMES,mode_of,shader_map
header='''#version 440
layout(location=0) in vec2 qt_TexCoord0;
layout(location=0) out vec4 fragColor;
layout(std140,binding=0) uniform buf {mat4 qt_Matrix;float qt_Opacity;float effectTime;vec4 p1;vec4 p2;};
layout(binding=1) uniform sampler2D sourceA;
layout(binding=2) uniform sampler2D sourceB;
'''
hlsl=['// BEGIN GENERATED TRANSITION MAPS','#ifdef KINETIC_TRANSITION_MODE',
 'float4 transitionPixel(V v):SV_Target {float2 uv=v.uv,uvA=uv,uvB=uv;float weight=extra.y;']
for name in ALL_NAMES:
 mode=mode_of(name)
 code='void main(){vec2 uv=qt_TexCoord0,uvA=uv,uvB=uv;float weight=effectTime;\n'+shader_map(name,'glsl')+'\nfragColor=mix(texture(sourceA,clamp(uvA,vec2(0),vec2(1))),texture(sourceB,clamp(uvB,vec2(0),vec2(1))),weight)*qt_Opacity;}\n'
 if name in EXTRA_NAMES or not (root/f'assets/shaders/transition_{mode}.frag').exists():
  frag=root/f'assets/shaders/transition_{mode}.frag';frag.write_text(header+code,encoding='utf-8')
  tool=shutil.which('qsb') or shutil.which('pyside6-qsb')
  if tool:subprocess.run([tool,'--glsl','150,300 es','--hlsl','50','--msl','12','-o',str(frag)+'.qsb',str(frag)],check=True)
  else:print('qsb not found: compile',frag.name,'by hand')
 hlsl+=['#if KINETIC_TRANSITION_MODE == '+str(mode),shader_map(name,'hlsl'),'#endif']
hlsl+=['return lerp(image.SampleLevel(sampleImage,saturate(uvA),0),original.SampleLevel(sampleImage,saturate(uvB),0),weight);}','#endif','// END GENERATED TRANSITION MAPS']
p=root/'native/gpu_export.cpp';s=p.read_text(encoding='utf-8');begin='// BEGIN GENERATED TRANSITION MAPS';end='// END GENERATED TRANSITION MAPS'
if begin in s:s=s[:s.index(begin)]+'\n'.join(hlsl)+s[s.index(end)+len(end):]
else:s=s.replace('float4 placePixel(', '\n'.join(hlsl)+'\nfloat4 placePixel(',1)
p.write_text(s,encoding='utf-8');print('Generated',len(ALL_NAMES),'paired transition shaders; highest mode',max(mode_of(n) for n in ALL_NAMES))
