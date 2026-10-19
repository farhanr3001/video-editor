#version 440
layout(location=0) in vec2 uv;
layout(location=0) out vec4 outputColor;
layout(std140,binding=0) uniform buf { mat4 matrix; float opacity; vec4 base; vec4 border; vec4 mapping; vec4 timing; vec4 sizes; vec4 more; vec4 details; };
layout(binding=1) uniform sampler2D thumbnail;
layout(binding=2) uniform sampler2D waveform;
bool flag(float n){return mod(floor(details.z/n),2.)>.5;}
float ramp(float x){float t=clamp(x,0.,1.);for(int n=0;n<3;n++){float a=1.-t;float f=3.*a*a*t*.3+3.*a*t*t*.7+t*t*t-x;float d=3.*a*a*.3+6.*a*t*.4+3.*t*t*.3;t=clamp(t-f/max(.001,d),0.,1.);}float a=1.-t;return a*a*a+3.*a*a*t*.65+3.*a*t*t*.25;}
void main(){
 vec2 pixel=uv*sizes.xy;vec4 color=base;
 if(more.z>.5 && sizes.x>=28. && sizes.y>=52. && pixel.x>=2. && pixel.x<sizes.x-2. && pixel.y>=2. && pixel.y<sizes.y-23.){
  vec4 image=texture(thumbnail,vec2(fract((pixel.x-2.)/max(1.,sizes.z)),(pixel.y-2.)/max(1.,sizes.y-25.)));
  color=vec4(image.rgb+vec3(.0314)*(1.-image.a),1.);
 }
 if(flag(1.) && mapping.w>0. && pixel.y>6. && pixel.y<sizes.y-18.){
  float elapsed=pixel.x/max(.001,details.x);float at=mapping.x+elapsed*mapping.y;
  float first=floor(at/mapping.z);float end=ceil((at+mapping.y/max(.001,details.x))/mapping.z);vec2 peak=vec2(0.);
  for(int n=0;n<20;n++){float idx=first+float(n);if(idx>=end||idx>=mapping.w)break;if(idx<0.)continue;peak=max(peak,texture(waveform,(vec2(mod(idx,sizes.w),floor(idx/sizes.w))+.5)/vec2(sizes.w,more.x)).rg);}
  float f=timing.w;if(timing.y>0.)f*=clamp(elapsed/timing.y,0.,1.);if(timing.z>0.)f*=clamp((timing.x-elapsed)/timing.z,0.,1.);
  peak=clamp(peak*f,vec2(0.),vec2(1.));float y=(.5-(pixel.y-6.)/max(4.,sizes.y-24.))*2.;float aa=max(fwidth(y),.001);
  float a=smoothstep(-peak.x-aa,-peak.x+aa,y)*(1.-smoothstep(peak.y-aa,peak.y+aa,y));color=mix(color,vec4(.863,.933,.89,1.),a);
 }
 if(flag(1.)||flag(2.)||flag(4.)){
  float fi=min(sizes.x,timing.y*details.x),fo=min(sizes.x,timing.z*details.x);float curve=-1.;
  if(fi>0.&&pixel.x<=fi)curve=3.+ramp(pixel.x/fi)*(sizes.y-3.);
  if(fo>0.&&pixel.x>=sizes.x-fo)curve=3.+ramp((sizes.x-pixel.x)/fo)*(sizes.y-3.);
  if(curve>=0.){if(pixel.y<curve)color.rgb*=.51;if(abs(pixel.y-curve)<.7)color=vec4(.98,.941,.761,1.);}
  if(sizes.x>=34.)for(int n=0;n<2;n++){
   float x=n==0?max(5.,fi):sizes.x-max(5.,fo);
   vec2 q=vec2(abs(pixel.x-x),pixel.y-2.);
   float d=q.y<=6.?max(q.x-4.,max(-q.y,q.y-6.)):length(vec2(q.x,q.y-6.))-4.;
   float outline=1.-smoothstep(.2,.9,d),fill=1.-smoothstep(-.7,0.,d);
   color=mix(color,mix(vec4(.082,.082,.082,1.),vec4(1.),fill),outline);
  }
 }
 if(flag(8.))color=mix(color,vec4(.68,.71,.75,1.),.4);
 vec2 q=abs(pixel-sizes.xy*.5)-(sizes.xy*.5-vec2(3.));float d=length(max(q,vec2(0.)))+min(max(q.x,q.y),0.)-3.;
 float bw=flag(2.)?2.:1.;float edge=1.-smoothstep(-bw-.5,-bw+.5,d);color=mix(border,color,edge);
 color*=1.-smoothstep(-.5,.5,d);outputColor=color*opacity;
}
