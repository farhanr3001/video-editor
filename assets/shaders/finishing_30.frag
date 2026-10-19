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
    if (mode < 30.5) {
        float e0=(p1.x/100.0);
        float e1=(uv.y*p1.y);
        float e2=(effectTime*p1.z);
        float e3=(e1+e2);
        float e4=(e3*2.0);
        float e5=(e4*3.14159265359);
        float e6=sin(e5);
        float e7=(e0*e6);
        float e8=(uv.x+e7);
        float e9=creativeRgb(vec2(e8,uv.y)).r;
        float e10=creativeRgb(vec2(e8,uv.y)).g;
        float e11=creativeRgb(vec2(e8,uv.y)).b;
        return vec3(e9,e10,e11);
    }
    return rgb;
}
void main(){vec4 c=texture(source,qt_TexCoord0);vec3 rgb=c.a>.00001?c.rgb/c.a:vec3(0);vec3 outRgb=finishingRgb(rgb,qt_TexCoord0);fragColor=vec4(mix(rgb,clamp(outRgb,0.,1.),p1.w)*c.a,c.a)*qt_Opacity;}
