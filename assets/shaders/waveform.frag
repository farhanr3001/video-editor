#version 440
layout(location=0) in vec2 qt_TexCoord0;
layout(location=0) out vec4 fragColor;
layout(std140,binding=0) uniform buf {
 mat4 qt_Matrix;float qt_Opacity;
 vec4 mapping;vec4 timing;vec2 textureSize;
 float pixelsPerSecond;float clipWidth;
};
layout(binding=1) uniform sampler2D source;
void main(){
 float elapsed=(qt_TexCoord0.x*max(1.,clipWidth-6.)+3.)/max(.001,pixelsPerSecond);
 float at=mapping.x+elapsed*mapping.y;
 float first=floor(at/mapping.z);float end=ceil((at+mapping.y/max(.001,pixelsPerSecond))/mapping.z);
 vec2 peak=vec2(0);
 for(int n=0;n<20;n++){
  float idx=first+float(n);if(idx>=end || idx>=mapping.w)break;
  if(idx<0.)continue;
  vec2 uv=(vec2(mod(idx,textureSize.x),floor(idx/textureSize.x))+.5)/textureSize;
  peak=max(peak,texture(source,uv).rg);
 }
 float fade=timing.w;
 if(timing.y>0.)fade*=clamp(elapsed/timing.y,0.,1.);
 if(timing.z>0.)fade*=clamp((timing.x-elapsed)/timing.z,0.,1.);
 peak=clamp(peak*fade,vec2(0),vec2(1));
 float y=(.5-qt_TexCoord0.y)*2.;
 float aa=max(fwidth(y),.001);
 float inside=smoothstep(-peak.x-aa,-peak.x+aa,y)*(1.-smoothstep(peak.y-aa,peak.y+aa,y));
 fragColor=vec4(vec3(.863,.933,.89)*inside,inside)*qt_Opacity;
}
