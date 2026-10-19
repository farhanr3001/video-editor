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
    if (mode < 16.5) {
        float e0=(p1.x/100.0);
        float e1=(uv.x-p2.x);
        float e2=(e1*e1);
        float e3=(uv.y-p2.y);
        float e4=(e3*e3);
        float e5=(e2+e4);
        float e6=sqrt(e5);
        float e7=(e6*1.41421356237);
        float e8=(e7-p1.y);
        float e9=(p1.y+p1.z);
        float e10=(e9-p1.y);
        float e11=max(0.0001,e10);
        float e12=(e8/e11);
        float e13=max(e12,0.0);
        float e14=min(e13,1.0);
        float e15=(e14*e14);
        float e16=(2.0*e14);
        float e17=(3.0-e16);
        float e18=(e15*e17);
        float e19=(e0*e18);
        float e20=(1.0-e19);
        float e21=(rgb.x*e20);
        float e22=(rgb.y*e20);
        float e23=(rgb.z*e20);
        return vec3(e21,e22,e23);
    }
    return rgb;
}
void main(){vec4 c=texture(source,qt_TexCoord0);vec3 rgb=c.a>.00001?c.rgb/c.a:vec3(0);vec3 outRgb=finishingRgb(rgb,qt_TexCoord0);fragColor=vec4(mix(rgb,clamp(outRgb,0.,1.),p1.w)*c.a,c.a)*qt_Opacity;}
