#version 440
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(binding = 1) uniform sampler2D source;
layout(binding = 2) uniform sampler2D maskTex;
layout(std140, binding = 0) uniform buf { mat4 qt_Matrix; float qt_Opacity; float invert; };
void main() {
    float m = texture(maskTex, qt_TexCoord0).a;
    if (invert > 0.5) m = 1.0 - m;
    fragColor = texture(source, qt_TexCoord0) * m * qt_Opacity;
}
