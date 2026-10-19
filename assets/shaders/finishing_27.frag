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
    if (mode < 27.5) {
        float e0=(uv.x*p1.x);
        float e1=floor(e0);
        float e2=(e0-e1);
        float e3=(e2-0.5);
        float e4=(e3*e3);
        float e5=(uv.y*p1.x);
        float e6=(e5/p2.w);
        float e7=floor(e6);
        float e8=(e6-e7);
        float e9=(e8-0.5);
        float e10=(e9*e9);
        float e11=(e4+e10);
        float e12=sqrt(e11);
        float e13=(0.299*rgb.x);
        float e14=(0.587*rgb.y);
        float e15=(e13+e14);
        float e16=(0.114*rgb.z);
        float e17=(e15+e16);
        float e18=(1.0-e17);
        float e19=max(e18,0.0);
        float e20=sqrt(e19);
        float e21=(0.55*e20);
        float e22=(0.5*p1.y);
        float e23=(e21-e22);
        float e24=(e12-e23);
        float e25=(e21+e22);
        float e26=(e25-e23);
        float e27=max(0.0001,e26);
        float e28=(e24/e27);
        float e29=max(e28,0.0);
        float e30=min(e29,1.0);
        float e31=(e30*e30);
        float e32=(2.0*e30);
        float e33=(3.0-e32);
        float e34=(e31*e33);
        float e35=(e34*p1.z);
        return vec3(e35,e35,e35);
    }
    return rgb;
}
void main(){vec4 c=texture(source,qt_TexCoord0);vec3 rgb=c.a>.00001?c.rgb/c.a:vec3(0);vec3 outRgb=finishingRgb(rgb,qt_TexCoord0);fragColor=vec4(mix(rgb,clamp(outRgb,0.,1.),p1.w)*c.a,c.a)*qt_Opacity;}
