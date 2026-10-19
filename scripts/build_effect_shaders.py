"""Generate both GPU implementations from the tested finishing expression graphs."""
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from kinetic_cut.finishing_effects import shader_cases,CONTROLS
gl=root/'assets/shaders/creative.frag';native=root/'native/gpu_export.cpp'
start='// BEGIN GENERATED FINISHING EFFECTS';end='// END GENERATED FINISHING EFFECTS'
def replace(path,code,before):
    text=path.read_text(encoding='utf-8');block=start+'\n'+code+'\n'+end+'\n'
    if start in text:text=text[:text.index(start)]+block+text[text.index(end)+len(end)+1:]
    else:text=text.replace(before,block+before,1)
    path.write_text(text,encoding='utf-8')
# Keep the original six-effect shader small. Every finishing effect gets its
# own pre-baked shader so first application does not compile unrelated kernels.
text=gl.read_text(encoding='utf-8')
if start in text:text=text[:text.index(start)]+text[text.index(end)+len(end)+1:]
text=text.replace('else outRgb=finishingRgb(rgb,qt_TexCoord0);','else outRgb=rgb;')
gl.write_text(text,encoding='utf-8')
header=text[:text.index('void main()')]
for index,name in enumerate(CONTROLS,7):
    helper='vec3 creativeRgb(vec2 uv){vec4 c=texture(source,clamp(uv,vec2(0),vec2(1)));return c.a>.00001?c.rgb/c.a:vec3(0);}\n'
    body=helper+'vec3 finishingRgb(vec3 rgb,vec2 uv){\n'+shader_cases('glsl',{name})+'\n}\n'
    body+='void main(){vec4 c=texture(source,qt_TexCoord0);vec3 rgb=c.a>.00001?c.rgb/c.a:vec3(0);vec3 outRgb=finishingRgb(rgb,qt_TexCoord0);fragColor=vec4(mix(rgb,clamp(outRgb,0.,1.),p1.w)*c.a,c.a)*qt_Opacity;}\n'
    (gl.parent/f'finishing_{index}.frag').write_text(header+body,encoding='utf-8')
replace(native,'#ifdef KINETIC_CREATIVE_MODE\nfloat3 creativeRgb(float2 uv){uv=saturate(uv);if(extra.z>.5)uv.x=1-uv.x;if(extra.w>.5)uv.y=1-uv.y;return samplePixel(uv).rgb;}\nfloat3 finishingRgb(float3 rgb,float2 uv){if(extra.z>.5)uv.x=1-uv.x;if(extra.w>.5)uv.y=1-uv.y;\n'+shader_cases('hlsl').replace('extra.x','KINETIC_CREATIVE_MODE')+'\n}\n#endif', 'float4 creativePixel(')
s=gl.read_text(encoding='utf-8');s=s.replace('else outRgb=1.-rgb;','else if(mode<6.5) outRgb=1.-rgb;\n    else outRgb=rgb;');gl.write_text(s,encoding='utf-8')
s=native.read_text(encoding='utf-8');s=s.replace('else outRgb=1-rgb;','else if(mode<6.5) outRgb=1-rgb;\n else outRgb=finishingRgb(rgb,v.uv);');native.write_text(s,encoding='utf-8')
print('Generated Qt and D3D11 finishing shaders')
