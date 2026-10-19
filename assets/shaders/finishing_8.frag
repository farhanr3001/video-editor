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
    if (mode < 8.5) {
        float e0=(p1.x*0.004);
        float e1=(p1.y*0.001);
        float e2=(e0+e1);
        float e3=pow(2.0,e2);
        float e4=(rgb.x*e3);
        float e5=(p1.y*-1.0);
        float e6=(e5*0.002);
        float e7=pow(2.0,e6);
        float e8=(rgb.y*e7);
        float e9=(p1.x*-1.0);
        float e10=(e9*0.004);
        float e11=(e10+e1);
        float e12=pow(2.0,e11);
        float e13=(rgb.z*e12);
        return vec3(e4,e8,e13);
    }
    return rgb;
}
void main(){vec4 c=texture(source,qt_TexCoord0);vec3 rgb=c.a>.00001?c.rgb/c.a:vec3(0);vec3 outRgb=finishingRgb(rgb,qt_TexCoord0);fragColor=vec4(mix(rgb,clamp(outRgb,0.,1.),p1.w)*c.a,c.a)*qt_Opacity;}
