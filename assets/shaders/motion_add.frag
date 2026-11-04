#version 440
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(binding = 1) uniform sampler2D source;
layout(std140, binding = 0) uniform buf { mat4 qt_Matrix; float qt_Opacity; float gain; };
// Additive blending on the GPU: premultiplied colour with zero alpha makes the standard source-over blend add (dst + src).
void main() {
    vec4 c = texture(source, qt_TexCoord0);
    fragColor = vec4(min(c.rgb * gain, vec3(1.0)), 0.0) * qt_Opacity;
}
