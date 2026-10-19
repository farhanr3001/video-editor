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
vec3 creativeRgb(vec2 uv){vec4 c=texture(source,clamp(uv,vec2(0),vec2(1)));return c.a>.00001?c.rgb/c.a:vec3(0);}
vec3 finishingRgb(vec3 rgb,vec2 uv){
    if (mode < 24.5) {
        float e0=(uv.x*100.0);
        float e1=(e0/p1.y);
        float e2=floor(e1);
        float e3=float((uint(int(e2))*uint(int(1973.0)))&65535u);
        float e4=(uv.y*100.0);
        float e5=(p1.y*p2.w);
        float e6=(e4/e5);
        float e7=floor(e6);
        float e8=float((uint(int(e7))*uint(int(9277.0)))&65535u);
        float e9=float((uint(int(e3))^uint(int(e8)))&65535u);
        float e10=(effectTime*p1.z);
        float e11=floor(e10);
        float e12=float((uint(int(e11))*uint(int(26699.0)))&65535u);
        float e13=float((uint(int(e9))^uint(int(e12)))&65535u);
        float e14=(e13/128.0);
        float e15=floor(e14);
        float e16=float((uint(int(e13))^uint(int(e15)))&65535u);
        float e17=float((uint(int(e16))*uint(int(40503.0)))&65535u);
        float e18=(e17/512.0);
        float e19=floor(e18);
        float e20=float((uint(int(e17))^uint(int(e19)))&65535u);
        float e21=float((uint(int(e20))*uint(int(57005.0)))&65535u);
        float e22=(e21/65535.0);
        float e23=(e22-0.5);
        float e24=(e23*p1.x);
        float e25=(e24/100.0);
        float e26=(rgb.x+e25);
        float e27=(rgb.y+e25);
        float e28=(rgb.z+e25);
        return vec3(e26,e27,e28);
    }
    return rgb;
}
void main(){vec4 c=texture(source,qt_TexCoord0);vec3 rgb=c.a>.00001?c.rgb/c.a:vec3(0);vec3 outRgb=finishingRgb(rgb,qt_TexCoord0);fragColor=vec4(mix(rgb,clamp(outRgb,0.,1.),p1.w)*c.a,c.a)*qt_Opacity;}
