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
    if (mode < 7.5) {
        float e0=pow(2.0,p1.x);
        float e1=(rgb.x*e0);
        float e2=(e1+p1.z);
        float e3=max(e2,0.0);
        float e4=(1.0/p1.y);
        float e5=pow(e3,e4);
        float e6=(rgb.y*e0);
        float e7=(e6+p1.z);
        float e8=max(e7,0.0);
        float e9=pow(e8,e4);
        float e10=(rgb.z*e0);
        float e11=(e10+p1.z);
        float e12=max(e11,0.0);
        float e13=pow(e12,e4);
        return vec3(e5,e9,e13);
    }
    return rgb;
}
void main(){vec4 c=texture(source,qt_TexCoord0);vec3 rgb=c.a>.00001?c.rgb/c.a:vec3(0);vec3 outRgb=finishingRgb(rgb,qt_TexCoord0);fragColor=vec4(mix(rgb,clamp(outRgb,0.,1.),p1.w)*c.a,c.a)*qt_Opacity;}
