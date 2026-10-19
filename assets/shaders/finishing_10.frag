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
    if (mode < 10.5) {
        float e0=(0.299*rgb.x);
        float e1=(0.587*rgb.y);
        float e2=(e0+e1);
        float e3=(0.114*rgb.z);
        float e4=(e2+e3);
        float e5=(rgb.x-e4);
        float e6=(p1.y/100.0);
        float e7=(p1.x/100.0);
        float e8=max(rgb.y,rgb.z);
        float e9=max(rgb.x,e8);
        float e10=min(rgb.y,rgb.z);
        float e11=min(rgb.x,e10);
        float e12=(e9-e11);
        float e13=(1.0-e12);
        float e14=(e7*e13);
        float e15=(1.0+e14);
        float e16=(e6*e15);
        float e17=(e5*e16);
        float e18=(e4+e17);
        float e19=(rgb.y-e4);
        float e20=(e19*e16);
        float e21=(e4+e20);
        float e22=(rgb.z-e4);
        float e23=(e22*e16);
        float e24=(e4+e23);
        return vec3(e18,e21,e24);
    }
    return rgb;
}
void main(){vec4 c=texture(source,qt_TexCoord0);vec3 rgb=c.a>.00001?c.rgb/c.a:vec3(0);vec3 outRgb=finishingRgb(rgb,qt_TexCoord0);fragColor=vec4(mix(rgb,clamp(outRgb,0.,1.),p1.w)*c.a,c.a)*qt_Opacity;}
