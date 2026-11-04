#version 440
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(binding = 1) uniform sampler2D b1;
layout(binding = 2) uniform sampler2D b2;
layout(binding = 3) uniform sampler2D b3;
layout(std140, binding = 0) uniform buf { mat4 qt_Matrix; float qt_Opacity; };
void main() {
    vec3 g = texture(b1, qt_TexCoord0).rgb * 0.5 + texture(b2, qt_TexCoord0).rgb * 0.3 + texture(b3, qt_TexCoord0).rgb * 0.2;
    fragColor = vec4(g, 1.0) * qt_Opacity;
}
