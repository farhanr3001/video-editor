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
    if (mode < 34.5) {
        float e0=(0.299*rgb.x);
        float e1=(0.587*rgb.y);
        float e2=(e0+e1);
        float e3=(0.114*rgb.z);
        float e4=(e2+e3);
        float e5=(0.596*rgb.x);
        float e6=(0.274*rgb.y);
        float e7=(e5-e6);
        float e8=(0.322*rgb.z);
        float e9=(e7-e8);
        float e10=(effectTime*p1.x);
        float e11=(e10*2.0);
        float e12=(e11*3.14159265359);
        float e13=(p1.y*3.14159265359);
        float e14=(e13/180.0);
        float e15=(e12+e14);
        float e16=cos(e15);
        float e17=(e9*e16);
        float e18=(0.211*rgb.x);
        float e19=(0.523*rgb.y);
        float e20=(e18-e19);
        float e21=(0.312*rgb.z);
        float e22=(e20+e21);
        float e23=sin(e15);
        float e24=(e22*e23);
        float e25=(e17-e24);
        float e26=(0.956*e25);
        float e27=(e4+e26);
        float e28=(e9*e23);
        float e29=(e22*e16);
        float e30=(e28+e29);
        float e31=(0.621*e30);
        float e32=(e27+e31);
        float e33=(0.272*e25);
        float e34=(e4-e33);
        float e35=(0.647*e30);
        float e36=(e34-e35);
        float e37=(1.106*e25);
        float e38=(e4-e37);
        float e39=(1.703*e30);
        float e40=(e38+e39);
        return vec3(e32,e36,e40);
    }
    return rgb;
}
void main(){vec4 c=texture(source,qt_TexCoord0);vec3 rgb=c.a>.00001?c.rgb/c.a:vec3(0);vec3 outRgb=finishingRgb(rgb,qt_TexCoord0);fragColor=vec4(mix(rgb,clamp(outRgb,0.,1.),p1.w)*c.a,c.a)*qt_Opacity;}
