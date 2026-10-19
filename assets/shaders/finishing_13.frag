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
    if (mode < 13.5) {
        float e0=(0.299*rgb.x);
        float e1=(0.587*rgb.y);
        float e2=(e0+e1);
        float e3=(0.114*rgb.z);
        float e4=(e2+e3);
        float e5=(rgb.x-e4);
        float e6=(e5*p1.y);
        float e7=(e6/100.0);
        float e8=(e4+e7);
        bool e9=(e4>0.5);
        float e10=(1.0-rgb.x);
        float e11=(2.0*e10);
        float e12=(1.0-e4);
        float e13=(e11*e12);
        float e14=(1.0-e13);
        float e15=(2.0*rgb.x);
        float e16=(e15*e4);
        float e17=(e9?e14:e16);
        float e18=(e17-e8);
        float e19=(p1.x/100.0);
        float e20=(e18*e19);
        float e21=(e8+e20);
        float e22=(rgb.y-e4);
        float e23=(e22*p1.y);
        float e24=(e23/100.0);
        float e25=(e4+e24);
        float e26=(1.0-rgb.y);
        float e27=(2.0*e26);
        float e28=(e27*e12);
        float e29=(1.0-e28);
        float e30=(2.0*rgb.y);
        float e31=(e30*e4);
        float e32=(e9?e29:e31);
        float e33=(e32-e25);
        float e34=(e33*e19);
        float e35=(e25+e34);
        float e36=(rgb.z-e4);
        float e37=(e36*p1.y);
        float e38=(e37/100.0);
        float e39=(e4+e38);
        float e40=(1.0-rgb.z);
        float e41=(2.0*e40);
        float e42=(e41*e12);
        float e43=(1.0-e42);
        float e44=(2.0*rgb.z);
        float e45=(e44*e4);
        float e46=(e9?e43:e45);
        float e47=(e46-e39);
        float e48=(e47*e19);
        float e49=(e39+e48);
        return vec3(e21,e35,e49);
    }
    return rgb;
}
void main(){vec4 c=texture(source,qt_TexCoord0);vec3 rgb=c.a>.00001?c.rgb/c.a:vec3(0);vec3 outRgb=finishingRgb(rgb,qt_TexCoord0);fragColor=vec4(mix(rgb,clamp(outRgb,0.,1.),p1.w)*c.a,c.a)*qt_Opacity;}
