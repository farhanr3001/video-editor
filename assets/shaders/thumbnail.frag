#version 440
layout(location=0) in vec2 qt_TexCoord0;
layout(location=0) out vec4 fragColor;
layout(std140,binding=0) uniform buf { mat4 qt_Matrix; float qt_Opacity; float repeatCount; };
layout(binding=1) uniform sampler2D source;
void main(){fragColor=texture(source,vec2(fract(qt_TexCoord0.x*repeatCount),qt_TexCoord0.y))*qt_Opacity;}
