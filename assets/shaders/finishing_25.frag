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
    if (mode < 25.5) {
        float e0=(p1.x/100.0);
        float e1=(0.299*rgb.x);
        float e2=(0.587*rgb.y);
        float e3=(e1+e2);
        float e4=(0.114*rgb.z);
        float e5=(e3+e4);
        float e6=(rgb.x-e5);
        float e7=(e6*p1.z);
        float e8=(e7/100.0);
        float e9=(e5+e8);
        float e10=(p1.x+p1.y);
        float e11=(e10/100.0);
        float e12=(1.0-e11);
        float e13=(e9*e12);
        float e14=(e0+e13);
        float e15=(rgb.y-e5);
        float e16=(e15*p1.z);
        float e17=(e16/100.0);
        float e18=(e5+e17);
        float e19=(e18*e12);
        float e20=(e0+e19);
        float e21=(rgb.z-e5);
        float e22=(e21*p1.z);
        float e23=(e22/100.0);
        float e24=(e5+e23);
        float e25=(e24*e12);
        float e26=(e0+e25);
        return vec3(e14,e20,e26);
    }
    return rgb;
}
void main(){vec4 c=texture(source,qt_TexCoord0);vec3 rgb=c.a>.00001?c.rgb/c.a:vec3(0);vec3 outRgb=finishingRgb(rgb,qt_TexCoord0);fragColor=vec4(mix(rgb,clamp(outRgb,0.,1.),p1.w)*c.a,c.a)*qt_Opacity;}
