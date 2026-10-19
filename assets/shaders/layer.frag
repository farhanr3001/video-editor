#version 440
layout(location=0) in vec2 qt_TexCoord0;
layout(location=0) out vec4 fragColor;
layout(std140,binding=0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec4 cropRect;
    vec4 grade;
    float alpha;
    float ellipse;
    float sharpen;
    vec2 pixelStep;
};
layout(binding=1) uniform sampler2D source;
vec4 graded(vec2 point) {
    vec2 uv=cropRect.xy+point*cropRect.zw;
    vec4 c=texture(source,uv);
    vec3 rgb=c.a>0.00001?c.rgb/c.a:vec3(0);
    rgb=clamp(rgb*max(0.0,1.0+grade.x),0.0,1.0);
    float gray=dot(rgb,vec3(0.299,0.587,0.114));
    rgb=mix(vec3(gray),rgb,grade.z);
    return vec4(clamp(rgb,0.0,1.0),c.a);
}
void main() {
    vec4 c=graded(qt_TexCoord0);
    vec3 rgb=c.rgb;
    // Pillow's conservative 3x3 SMOOTH kernel used by the CPU preview, followed
    // by the same unsharp blend. Preserve crop edges and source alpha.
    if(sharpen>0.002 && all(greaterThanEqual(qt_TexCoord0,pixelStep)) &&
       all(lessThanEqual(qt_TexCoord0,vec2(1)-pixelStep))) {
        vec3 softened=c.rgb*5.0;
        for(int y=-1;y<=1;y++) for(int x=-1;x<=1;x++) {
            if(x!=0 || y!=0) softened+=graded(qt_TexCoord0+vec2(x,y)*pixelStep).rgb;
        }
        rgb=clamp(c.rgb+(c.rgb-softened/13.0)*sharpen,0.0,1.0);
    }
    rgb*=grade.w;
    float mask=1.0;
    if(ellipse>0.5) {
        float radius=length((qt_TexCoord0-0.5)*2.0);
        mask=1.0-smoothstep(1.0-fwidth(radius),1.0,radius);
    }
    fragColor=vec4(rgb*c.a,c.a)*qt_Opacity*alpha*mask;
}
