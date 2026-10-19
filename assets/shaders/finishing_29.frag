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
    if (mode < 29.5) {
        float e0=(uv.x-0.5);
        float e1=(e0*e0);
        float e2=(uv.y-0.5);
        float e3=(e2*e2);
        float e4=(e1+e3);
        float e5=(p1.z*e4);
        float e6=(e5*4.0);
        float e7=(1.0+e6);
        float e8=(e0*e7);
        float e9=(0.5+e8);
        float e10=(p2.x/100.0);
        float e11=(e9+e10);
        float e12=(e2*e7);
        float e13=(0.5+e12);
        float e14=creativeRgb(vec2(e11,e13)).r;
        float e15=(p1.y/100.0);
        float e16=(e13*p1.x);
        float e17=(e16*2.0);
        float e18=(e17*3.14159265359);
        float e19=cos(e18);
        float e20=(1.0+e19);
        float e21=(e15*e20);
        float e22=(e21/2.0);
        float e23=(1.0-e22);
        float e24=(e14*e23);
        float e25=creativeRgb(vec2(e9,e13)).g;
        float e26=(e25*e23);
        float e27=(e9-e10);
        float e28=creativeRgb(vec2(e27,e13)).b;
        float e29=(e28*e23);
        return vec3(e24,e26,e29);
    }
    return rgb;
}
void main(){vec4 c=texture(source,qt_TexCoord0);vec3 rgb=c.a>.00001?c.rgb/c.a:vec3(0);vec3 outRgb=finishingRgb(rgb,qt_TexCoord0);fragColor=vec4(mix(rgb,clamp(outRgb,0.,1.),p1.w)*c.a,c.a)*qt_Opacity;}
