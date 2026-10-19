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
    if (mode < 28.5) {
        float e0=(uv.x*p1.x);
        float e1=floor(e0);
        float e2=(e1+0.5);
        float e3=(e2/p1.x);
        float e4=(uv.y*p1.y);
        float e5=floor(e4);
        float e6=(e5+0.5);
        float e7=(e6/p1.y);
        float e8=creativeRgb(vec2(e3,e7)).r;
        float e9=creativeRgb(vec2(e3,e7)).g;
        float e10=creativeRgb(vec2(e3,e7)).b;
        return vec3(e8,e9,e10);
    }
    return rgb;
}
void main(){vec4 c=texture(source,qt_TexCoord0);vec3 rgb=c.a>.00001?c.rgb/c.a:vec3(0);vec3 outRgb=finishingRgb(rgb,qt_TexCoord0);fragColor=vec4(mix(rgb,clamp(outRgb,0.,1.),p1.w)*c.a,c.a)*qt_Opacity;}
