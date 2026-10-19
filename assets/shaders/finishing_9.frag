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
    if (mode < 9.5) {
        float e0=(p1.x/100.0);
        float e1=(0.299*rgb.x);
        float e2=(0.587*rgb.y);
        float e3=(e1+e2);
        float e4=(0.114*rgb.z);
        float e5=(e3+e4);
        float e6=(1.0-e5);
        float e7=(1.0/p1.z);
        float e8=pow(e6,e7);
        float e9=(e0*e8);
        float e10=(e9*0.5);
        float e11=(p1.y/100.0);
        float e12=pow(e5,e7);
        float e13=(e11*e12);
        float e14=(e13*0.5);
        float e15=(e10+e14);
        float e16=(rgb.x+e15);
        float e17=(rgb.y+e15);
        float e18=(rgb.z+e15);
        return vec3(e16,e17,e18);
    }
    return rgb;
}
void main(){vec4 c=texture(source,qt_TexCoord0);vec3 rgb=c.a>.00001?c.rgb/c.a:vec3(0);vec3 outRgb=finishingRgb(rgb,qt_TexCoord0);fragColor=vec4(mix(rgb,clamp(outRgb,0.,1.),p1.w)*c.a,c.a)*qt_Opacity;}
