#version 440
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(binding = 1) uniform sampler2D source;
layout(std140, binding = 0) uniform buf { mat4 qt_Matrix; float qt_Opacity; float threshold; };
void main() {
    vec4 c = texture(source, qt_TexCoord0);
    float l = dot(c.rgb, vec3(0.299, 0.587, 0.114));
    float m = clamp((l - threshold) / max(0.01, 1.0 - threshold), 0.0, 1.0);
    fragColor = vec4(c.rgb * m, 1.0) * qt_Opacity;
}
