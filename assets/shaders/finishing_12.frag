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
    if (mode < 12.5) {
        float e0=(colorB.x-colorA.x);
        float e1=(0.299*rgb.x);
        float e2=(0.587*rgb.y);
        float e3=(e1+e2);
        float e4=(0.114*rgb.z);
        float e5=(e3+e4);
        float e6=(0.5+p1.y);
        float e7=(e6-p1.z);
        float e8=(e5-e7);
        float e9=(e6+p1.z);
        float e10=(e9-e7);
        float e11=max(0.0001,e10);
        float e12=(e8/e11);
        float e13=max(e12,0.0);
        float e14=min(e13,1.0);
        float e15=(e14*e14);
        float e16=(2.0*e14);
        float e17=(3.0-e16);
        float e18=(e15*e17);
        float e19=(e0*e18);
        float e20=(colorA.x+e19);
        float e21=(e20-0.5);
        float e22=(e21*p1.x);
        float e23=(e22/100.0);
        float e24=(e23*4.0);
        float e25=(e24*rgb.x);
        float e26=(1.0-rgb.x);
        float e27=(e25*e26);
        float e28=(rgb.x+e27);
        float e29=(colorB.y-colorA.y);
        float e30=(e29*e18);
        float e31=(colorA.y+e30);
        float e32=(e31-0.5);
        float e33=(e32*p1.x);
        float e34=(e33/100.0);
        float e35=(e34*4.0);
        float e36=(e35*rgb.y);
        float e37=(1.0-rgb.y);
        float e38=(e36*e37);
        float e39=(rgb.y+e38);
        float e40=(colorB.z-colorA.z);
        float e41=(e40*e18);
        float e42=(colorA.z+e41);
        float e43=(e42-0.5);
        float e44=(e43*p1.x);
        float e45=(e44/100.0);
        float e46=(e45*4.0);
        float e47=(e46*rgb.z);
        float e48=(1.0-rgb.z);
        float e49=(e47*e48);
        float e50=(rgb.z+e49);
        return vec3(e28,e39,e50);
    }
    return rgb;
}
void main(){vec4 c=texture(source,qt_TexCoord0);vec3 rgb=c.a>.00001?c.rgb/c.a:vec3(0);vec3 outRgb=finishingRgb(rgb,qt_TexCoord0);fragColor=vec4(mix(rgb,clamp(outRgb,0.,1.),p1.w)*c.a,c.a)*qt_Opacity;}
