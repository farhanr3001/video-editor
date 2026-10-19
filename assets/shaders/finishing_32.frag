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
    if (mode < 32.5) {
        float e0=(uv.x-0.5);
        float e1=(e0*e0);
        float e2=(uv.y-0.5);
        float e3=(e2/p2.w);
        float e4=(e3*e3);
        float e5=(e1+e4);
        float e6=sqrt(e5);
        float e7=(e6/p1.z);
        float e8=atan(e3,e0);
        float e9=(p1.y*3.14159265359);
        float e10=(e9/180.0);
        float e11=(e8+e10);
        float e12=(6.28318530718/p1.x);
        float e13=(e11/e12);
        float e14=floor(e13);
        float e15=(e13-e14);
        float e16=(e15*e12);
        float e17=(e12/2.0);
        float e18=(e16-e17);
        float e19=abs(e18);
        float e20=cos(e19);
        float e21=(e7*e20);
        float e22=(0.5+e21);
        float e23=sin(e19);
        float e24=(e7*e23);
        float e25=(e24*p2.w);
        float e26=(0.5+e25);
        float e27=creativeRgb(vec2(e22,e26)).r;
        float e28=creativeRgb(vec2(e22,e26)).g;
        float e29=creativeRgb(vec2(e22,e26)).b;
        return vec3(e27,e28,e29);
    }
    return rgb;
}
void main(){vec4 c=texture(source,qt_TexCoord0);vec3 rgb=c.a>.00001?c.rgb/c.a:vec3(0);vec3 outRgb=finishingRgb(rgb,qt_TexCoord0);fragColor=vec4(mix(rgb,clamp(outRgb,0.,1.),p1.w)*c.a,c.a)*qt_Opacity;}
