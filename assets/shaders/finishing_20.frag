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
    if (mode < 20.5) {
        float e0=(uv.x-0.5);
        float e1=(e0/p1.y);
        float e2=(e1*e1);
        float e3=(uv.y-0.5);
        float e4=(p1.y*p2.w);
        float e5=(e3/e4);
        float e6=(e5*e5);
        float e7=(e2+e6);
        float e8=(p1.x*e7);
        float e9=(e8*4.0);
        float e10=(1.0+e9);
        float e11=(e1*e10);
        float e12=(0.5+e11);
        float e13=(e5*e10);
        float e14=(e13*p2.w);
        float e15=(0.5+e14);
        float e16=creativeRgb(vec2(e12,e15)).r;
        float e17=creativeRgb(vec2(e12,e15)).g;
        float e18=creativeRgb(vec2(e12,e15)).b;
        return vec3(e16,e17,e18);
    }
    return rgb;
}
void main(){vec4 c=texture(source,qt_TexCoord0);vec3 rgb=c.a>.00001?c.rgb/c.a:vec3(0);vec3 outRgb=finishingRgb(rgb,qt_TexCoord0);fragColor=vec4(mix(rgb,clamp(outRgb,0.,1.),p1.w)*c.a,c.a)*qt_Opacity;}
