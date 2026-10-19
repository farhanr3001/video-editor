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
    if (mode < 15.5) {
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
        float e10=(p1.x*3.14159265359);
        float e11=(e10/180.0);
        float e12=cos(e11);
        float e13=(e9*e12);
        float e14=(0.211*rgb.x);
        float e15=(0.523*rgb.y);
        float e16=(e14-e15);
        float e17=(0.312*rgb.z);
        float e18=(e16+e17);
        float e19=sin(e11);
        float e20=(e18*e19);
        float e21=(e13-e20);
        float e22=(0.956*e21);
        float e23=(e4+e22);
        float e24=(e9*e19);
        float e25=(e18*e12);
        float e26=(e24+e25);
        float e27=(0.621*e26);
        float e28=(e23+e27);
        float e29=(0.272*e21);
        float e30=(e4-e29);
        float e31=(0.647*e26);
        float e32=(e30-e31);
        float e33=(1.106*e21);
        float e34=(e4-e33);
        float e35=(1.703*e26);
        float e36=(e34+e35);
        return vec3(e28,e32,e36);
    }
    return rgb;
}
void main(){vec4 c=texture(source,qt_TexCoord0);vec3 rgb=c.a>.00001?c.rgb/c.a:vec3(0);vec3 outRgb=finishingRgb(rgb,qt_TexCoord0);fragColor=vec4(mix(rgb,clamp(outRgb,0.,1.),p1.w)*c.a,c.a)*qt_Opacity;}
