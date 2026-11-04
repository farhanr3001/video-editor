#version 440
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(binding = 1) uniform sampler2D source;
layout(binding = 2) uniform sampler2D bloomTex;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float aberration;   // uv offset
    float bloomGain;
    float brightness;
    float contrast;
    float saturation;
    float tintAmount;
    float vignette;
    float vignetteSoft;
    float grain;
    float seed;
    float aspect;
    vec4 tintColor;
};
float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
void main() {
    vec2 uv = qt_TexCoord0;
    vec4 c = texture(source, uv);
    if (aberration != 0.0) {
        c.r = texture(source, uv - vec2(aberration, 0.0)).r;
        c.b = texture(source, uv + vec2(aberration, 0.0)).b;
    }
    vec3 rgb = c.rgb; float a = c.a;
    if (bloomGain > 0.0) {
        vec3 g = min(texture(bloomTex, uv).rgb * bloomGain, vec3(1.0));
        rgb += g; a = max(a, dot(g, vec3(0.299, 0.587, 0.114)));
    }
    rgb = clamp(rgb, 0.0, 1.0);
    if (brightness != 0.0 || contrast != 1.0) rgb = clamp((rgb - 0.5) * contrast + 0.5 + brightness, 0.0, 1.0);
    if (saturation != 1.0) { float l = dot(rgb, vec3(0.299, 0.587, 0.114)); rgb = clamp(vec3(l) + (rgb - vec3(l)) * saturation, 0.0, 1.0); }
    if (tintAmount > 0.0) rgb *= (1.0 - tintAmount) + tintAmount * tintColor.rgb;
    if (vignette > 0.0) {
        vec2 d = (uv - 0.5) * 2.0;
        float e = clamp((length(d) / 1.414 - (1.0 - vignetteSoft)) / max(0.01, vignetteSoft), 0.0, 1.0);
        rgb *= 1.0 - vignette * e * e;
    }
    if (grain > 0.0) {
        float n = hash(uv * vec2(1731.0, 1731.0 * aspect) + seed) + hash(uv * 977.0 - seed) - 1.0;
        rgb += n * 1.6 * grain * 0.08;
    }
    rgb = min(clamp(rgb, 0.0, 1.0), vec3(a));
    fragColor = vec4(rgb, a) * qt_Opacity;
}
