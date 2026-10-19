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
    if (mode < 11.5) {
        float e0=(rgb.x-p1.x);
        float e1=(p1.y-p1.x);
        float e2=max(0.001,e1);
        float e3=(e0/e2);
        float e4=max(e3,0.0);
        float e5=min(e4,1.0);
        float e6=(1.0/p1.z);
        float e7=pow(e5,e6);
        float e8=(rgb.y-p1.x);
        float e9=(e8/e2);
        float e10=max(e9,0.0);
        float e11=min(e10,1.0);
        float e12=pow(e11,e6);
        float e13=(rgb.z-p1.x);
        float e14=(e13/e2);
        float e15=max(e14,0.0);
        float e16=min(e15,1.0);
        float e17=pow(e16,e6);
        return vec3(e7,e12,e17);
    }
    return rgb;
}
void main(){vec4 c=texture(source,qt_TexCoord0);vec3 rgb=c.a>.00001?c.rgb/c.a:vec3(0);vec3 outRgb=finishingRgb(rgb,qt_TexCoord0);fragColor=vec4(mix(rgb,clamp(outRgb,0.,1.),p1.w)*c.a,c.a)*qt_Opacity;}
