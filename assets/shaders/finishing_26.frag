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
    if (mode < 26.5) {
        float e0=(uv.y*p1.x);
        float e1=(effectTime*p1.z);
        float e2=(e0+e1);
        float e3=(e2*2.0);
        float e4=(e3*3.14159265359);
        float e5=cos(e4);
        float e6=(1.0+e5);
        float e7=(e6/2.0);
        float e8=(e7*p1.y);
        float e9=(e8/100.0);
        float e10=(1.0-e9);
        float e11=(rgb.x*e10);
        float e12=(rgb.y*e10);
        float e13=(rgb.z*e10);
        return vec3(e11,e12,e13);
    }
    return rgb;
}
void main(){vec4 c=texture(source,qt_TexCoord0);vec3 rgb=c.a>.00001?c.rgb/c.a:vec3(0);vec3 outRgb=finishingRgb(rgb,qt_TexCoord0);fragColor=vec4(mix(rgb,clamp(outRgb,0.,1.),p1.w)*c.a,c.a)*qt_Opacity;}
