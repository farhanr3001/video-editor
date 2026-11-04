#version 440
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(binding = 1) uniform sampler2D source;
layout(std140, binding = 0) uniform buf { mat4 qt_Matrix; float qt_Opacity; vec2 sigma; };
// Gaussian blur along an arbitrary (x, y) axis; sigma is in texture units. 64 taps over +-3 sigma with a per-pixel jitter so wide
// blurs of thin strokes smear instead of showing a comb pattern.
void main() {
    float jitter = fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715))));
    vec4 acc = vec4(0.0); float sum = 0.0;
    for (int i = 0; i < 64; i++) {
        float u = ((float(i) + jitter) / 64.0) * 2.0 - 1.0;
        float w = exp(-4.5 * u * u);
        acc += texture(source, qt_TexCoord0 + sigma * 3.0 * u) * w;
        sum += w;
    }
    fragColor = acc / sum * qt_Opacity;
}
