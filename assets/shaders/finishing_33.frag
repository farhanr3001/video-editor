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
    if (mode < 33.5) {
        float e0=(p2.x/100.0);
        float e1=(uv.y*p1.z);
        float e2=floor(e1);
        float e3=float((uint(int(e2))*uint(int(1973.0)))&65535u);
        float e4=float((uint(int(0.0))*uint(int(9277.0)))&65535u);
        float e5=float((uint(int(e3))^uint(int(e4)))&65535u);
        float e6=(effectTime*p1.y);
        float e7=floor(e6);
        float e8=float((uint(int(e7))*uint(int(26699.0)))&65535u);
        float e9=float((uint(int(e5))^uint(int(e8)))&65535u);
        float e10=(e9/128.0);
        float e11=floor(e10);
        float e12=float((uint(int(e9))^uint(int(e11)))&65535u);
        float e13=float((uint(int(e12))*uint(int(40503.0)))&65535u);
        float e14=(e13/512.0);
        float e15=floor(e14);
        float e16=float((uint(int(e13))^uint(int(e15)))&65535u);
        float e17=float((uint(int(e16))*uint(int(57005.0)))&65535u);
        float e18=(e17/65535.0);
        float e19=(e18-0.5);
        float e20=(e19+0.5);
        bool e21=(e0>e20);
        float e22=(e2*7.0);
        float e23=(e7*3.0);
        float e24=(e22+e23);
        float e25=sin(e24);
        float e26=(e25*p1.x);
        float e27=(e26/100.0);
        float e28=(e21?e27:0.0);
        float e29=(uv.x+e28);
        float e30=creativeRgb(vec2(e29,uv.y)).r;
        float e31=(e28*0.2);
        float e32=(uv.x-e31);
        float e33=creativeRgb(vec2(e32,uv.y)).g;
        float e34=(uv.x-e28);
        float e35=creativeRgb(vec2(e34,uv.y)).b;
        return vec3(e30,e33,e35);
    }
    return rgb;
}
void main(){vec4 c=texture(source,qt_TexCoord0);vec3 rgb=c.a>.00001?c.rgb/c.a:vec3(0);vec3 outRgb=finishingRgb(rgb,qt_TexCoord0);fragColor=vec4(mix(rgb,clamp(outRgb,0.,1.),p1.w)*c.a,c.a)*qt_Opacity;}
