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
    if (mode < 14.5) {
        float e0=(0.299*rgb.x);
        float e1=(0.587*rgb.y);
        float e2=(e0+e1);
        float e3=(0.114*rgb.z);
        float e4=(e2+e3);
        float e5=(rgb.x-e4);
        float e6=(p1.z/100.0);
        float e7=(1.0-e6);
        float e8=(rgb.x-colorA.x);
        float e9=(e8*e8);
        float e10=(0.0+e9);
        float e11=(rgb.y-colorA.y);
        float e12=(e11*e11);
        float e13=(e10+e12);
        float e14=(rgb.z-colorA.z);
        float e15=(e14*e14);
        float e16=(e13+e15);
        float e17=(e16/3.0);
        float e18=sqrt(e17);
        float e19=(e18-p1.x);
        float e20=(p1.x+p1.y);
        float e21=(e20-p1.x);
        float e22=max(0.0001,e21);
        float e23=(e19/e22);
        float e24=max(e23,0.0);
        float e25=min(e24,1.0);
        float e26=(e25*e25);
        float e27=(2.0*e25);
        float e28=(3.0-e27);
        float e29=(e26*e28);
        float e30=(1.0-e29);
        float e31=(e7*e30);
        float e32=(e6+e31);
        float e33=(e5*e32);
        float e34=(e4+e33);
        float e35=(rgb.y-e4);
        float e36=(e35*e32);
        float e37=(e4+e36);
        float e38=(rgb.z-e4);
        float e39=(e38*e32);
        float e40=(e4+e39);
        return vec3(e34,e37,e40);
    }
    return rgb;
}
void main(){vec4 c=texture(source,qt_TexCoord0);vec3 rgb=c.a>.00001?c.rgb/c.a:vec3(0);vec3 outRgb=finishingRgb(rgb,qt_TexCoord0);fragColor=vec4(mix(rgb,clamp(outRgb,0.,1.),p1.w)*c.a,c.a)*qt_Opacity;}
