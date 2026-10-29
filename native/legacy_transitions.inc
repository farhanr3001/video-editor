// Concatenate this raw string to the common shader source.  Input textures hold
// straight-alpha, effect-prepared endpoint crops, not independently placed clips.
R"HLSL(
#if defined(KINETIC_TRANSITION_MODE) && KINETIC_TRANSITION_MODE >= 25
float4 legacyOver(float4 under,float4 over){return over+under*(1-over.a);}
float4 legacyA(float2 uv){
 if(direction.z<.5||any(uv<0)||any(uv>1))return 0;
 float4 c=image.SampleLevel(sampleImage,legacyCropA.xy+uv*legacyCropA.zw,0);c.rgb*=c.a;return c;
}
float4 legacyB(float2 uv){
 if(direction.w<.5||any(uv<0)||any(uv>1))return 0;
 float4 c=original.SampleLevel(sampleImage,legacyCropB.xy+uv*legacyCropB.zw,0);c.rgb*=c.a;return c;
}
float4 legacyFill(float3 color,float alpha){return float4(color*alpha,alpha);}
float4 legacyTransitionPixel(V v):SV_Target {
 float3 position=float3(v.uv*direction.xy,1);
 float divisor=dot(row2.xyz,position);if(abs(divisor)<.000001)discard;
 float2 uv=float2(dot(row0.xyz,position),dot(row1.xyz,position))/divisor;
 if(any(uv<0)||any(uv>1)||direction.z+direction.w<.5)discard;
 float p=extra.y,opacity=extra.x,peak=1-abs(p-.5)*2;
 float4 result=0;
 // The explicit setOpacity calls in the original compositor replace the
 // inherited outer opacity.  Draws without that call retain outer opacity.
#if KINETIC_TRANSITION_MODE == 25 || KINETIC_TRANSITION_MODE == 28 || KINETIC_TRANSITION_MODE == 30 || KINETIC_TRANSITION_MODE == 45 || KINETIC_TRANSITION_MODE == 46 || KINETIC_TRANSITION_MODE == 49
 result=legacyOver(legacyA(uv)*(1-p),legacyB(uv)*p);
 #if KINETIC_TRANSITION_MODE == 28
 if(peak>.05)result=legacyOver(result,legacyFill(float3(1,1,1),floor(120*peak)/255*opacity));
 #elif KINETIC_TRANSITION_MODE == 45 || KINETIC_TRANSITION_MODE == 46
 if(peak>.1){
  float slice=min(7,floor(uv.y*8));
  float shift=sin(slice*13.5+p*40)*(30*peak)/max(.0001,box.z);
  if(uv.x>=shift&&uv.x<=1+shift){
   float3 color=fmod(slice,2)<.5?float3(0,240./255,1):float3(1,0,120./255);
   result=legacyOver(result,legacyFill(color,floor(80*peak)/255*opacity));
  }
 }
 #elif KINETIC_TRANSITION_MODE == 49
 if(peak>.15)result=legacyOver(result,legacyFill(float3(0,0,0),floor(90*peak)/255*opacity));
 #endif
#elif KINETIC_TRANSITION_MODE == 29
 result=saturate(legacyA(uv)*(1-p*.5)+legacyB(uv)*p);
#elif KINETIC_TRANSITION_MODE == 26 || KINETIC_TRANSITION_MODE == 27
 result=(p<.5?legacyA(uv):legacyB(uv))*opacity;
 result=legacyOver(result,legacyFill(crop.rgb,(p<.5?p*2:(1-p)*2)*opacity));
#elif KINETIC_TRANSITION_MODE >= 31 && KINETIC_TRANSITION_MODE <= 36
 result=legacyA(uv)*opacity;bool revealed=false;
 #if KINETIC_TRANSITION_MODE == 31
 revealed=uv.x>=1-p;
 #elif KINETIC_TRANSITION_MODE == 32
 revealed=uv.x<=p;
 #elif KINETIC_TRANSITION_MODE == 33
 revealed=uv.y>=1-p;
 #elif KINETIC_TRANSITION_MODE == 34
 revealed=uv.y<=p;
 #elif KINETIC_TRANSITION_MODE == 35
 revealed=abs(uv.x-.5)<=p*.5;
 #else
 float2 radius=(uv-.5)*box.zw;
 float angle=atan2(radius.x,-radius.y);if(angle<0)angle+=6.28318530718;
 revealed=angle<=p*6.28318530718;
 #endif
 if(revealed)result=legacyOver(result,legacyB(uv)*opacity);
#elif KINETIC_TRANSITION_MODE >= 37 && KINETIC_TRANSITION_MODE <= 40
 float2 movement=0;
 #if KINETIC_TRANSITION_MODE == 37
 movement=float2(-1,0);
 #elif KINETIC_TRANSITION_MODE == 38
 movement=float2(1,0);
 #elif KINETIC_TRANSITION_MODE == 39
 movement=float2(0,-1);
 #else
 movement=float2(0,1);
 #endif
 result=legacyOver(legacyA(uv-movement*p)*opacity,legacyB(uv+movement*(1-p))*opacity);
#elif KINETIC_TRANSITION_MODE == 41
 result=legacyA(uv)*opacity;
 if(direction.w>.5){
  float shadowLeft=1-p-10/max(.0001,box.z),shadowRight=shadowLeft+12/max(.0001,box.z);
  if(uv.x>=shadowLeft&&uv.x<=shadowRight)result=legacyOver(result,legacyFill(float3(0,0,0),90./255*opacity));
  result=legacyOver(result,legacyB(uv-float2(1-p,0))*opacity);
 }
#elif KINETIC_TRANSITION_MODE == 42
 result=legacyOver(legacyB(uv)*opacity,legacyA(uv+float2(p,0))*opacity);
#elif KINETIC_TRANSITION_MODE == 43 || KINETIC_TRANSITION_MODE == 44
 // Existing Whip Pan and Whoosh use this crop-local zoom/fade in preview.
 // Do not replace their saved visual result with a new canvas-space pan.
 if(p<.5)result=legacyA((uv-.5)/(1+p*3)+.5)*(1-p*2);
 else {float incoming=(p-.5)*2;result=legacyB((uv-.5)/(1+(1-incoming)*1.5)+.5)*incoming;}
#elif KINETIC_TRANSITION_MODE == 47
 float roll=grade.y;float2 at=float2(uv.x,frac(uv.y-roll));
 result=(direction.z>.5&&grade.x>.5?legacyA(at):legacyB(at))*opacity;
 if(abs((uv.y-roll)*box.w)<=8)result=legacyOver(result,legacyFill(float3(10./255,10./255,12./255),opacity));
#elif KINETIC_TRANSITION_MODE == 48
 result=legacyOver(legacyA(uv)*opacity,legacyB(uv)*p);
 if(peak>.05&&abs((uv.y-.5)*box.w)<=12*peak)
  result=legacyOver(result,legacyFill(float3(1,250./255,230./255),floor(220*peak)/255*opacity));
#endif
 if(extra.z>.5){float radius=length((uv-.5)*2);result*=1-smoothstep(1-fwidth(radius),1,radius);}
 return result;
}
#endif
)HLSL"

