#version 440
layout(location=0) in vec2 qt_TexCoord0;
layout(location=0) out vec4 fragColor;
layout(std140,binding=0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec4 p1;
    vec4 p2;
    vec4 colorA;
    vec4 colorB;
    float mode;
    float effectTime;
};
layout(binding=1) uniform sampler2D source;
void main() {
    vec4 c=texture(source,qt_TexCoord0);
    vec3 rgb=c.a>0.00001 ? c.rgb/c.a : vec3(0);
    vec3 outRgb=rgb;
    if(mode<1.5) {
        float phase=fract(effectTime*p1.y+p2.y);
        float x=min(phase,1.-phase)/max(.005,p1.z/2.);
        float pulse=x<1. ? (1.-p2.x)+p2.x*(1.+cos(3.14159265359*x))/2. : 0.;
        outRgb=mix(rgb,colorA.rgb,p1.x*pulse);
    } else if(mode<2.5) {
        outRgb=rgb*exp2(p1.z+p1.x*(1.+cos(6.28318530718*(effectTime*p1.y+p2.y)))/2.);
    } else if(mode<3.5) outRgb=mix(rgb,colorA.rgb,p1.x);
    else if(mode<4.5) {
        float y=clamp((dot(rgb,vec3(.299,.587,.114))-.5)*p1.x+.5+p1.y,0.,1.);
        outRgb=mix(colorA.rgb,colorB.rgb,y);
    } else if(mode<5.5) outRgb=floor(rgb*(p1.x-1.)+.5)/(p1.x-1.);
    else if(mode<6.5) outRgb=1.-rgb;
    else outRgb=rgb;
    fragColor=vec4(mix(rgb,clamp(outRgb,0.,1.),p1.w)*c.a,c.a)*qt_Opacity;
}
