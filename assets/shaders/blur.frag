#version 440
layout(location=0) in vec2 qt_TexCoord0;
layout(location=0) out vec4 fragColor;
layout(std140,binding=0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 stepSize;
    float mixAmount;
    float borderMode;
    float alpha;
    float ellipse;
};
layout(binding=1) uniform sampler2D source;
layout(binding=2) uniform sampler2D original;
vec4 readPixel(vec2 uv) {
    if (borderMode>1.5 && (any(lessThan(uv,vec2(0))) || any(greaterThan(uv,vec2(1))))) return vec4(0);
    if (borderMode>.5 && borderMode<1.5) uv=1.-abs(mod(uv,2.)-1.);
    return texture(source,clamp(uv,vec2(0),vec2(1)));
}
void main() {
    vec2 uv=qt_TexCoord0;
    vec4 c=texture(source,uv);
    if (dot(stepSize,stepSize)>0.) {
        // 33 symmetric samples over six sigma. Both axes run on the render
        // thread; the work is bounded independently of source/project size.
        vec4 sum=c;float weight=1.;
        for (int i=1;i<=16;i++) {
            float x=float(i)*3./16.;float w=exp(-.5*x*x);
            vec2 d=stepSize*x;sum+=(readPixel(uv-d)+readPixel(uv+d))*w;weight+=2.*w;
        }
        c=sum/weight;
    }
    c=mix(texture(original,uv),c,mixAmount);
    float mask=1.;
    if(ellipse>.5) { float d=length((uv-.5)*2.); mask=1.-smoothstep(1.-fwidth(d),1.,d); }
    fragColor=c*qt_Opacity*alpha*mask;
}
