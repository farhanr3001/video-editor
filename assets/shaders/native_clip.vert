#version 440
layout(location=0) in vec4 vertex;
layout(location=1) in vec2 texCoord;
layout(location=0) out vec2 uv;
layout(std140,binding=0) uniform buf { mat4 matrix; float opacity; vec4 base; vec4 border; vec4 mapping; vec4 timing; vec4 sizes; vec4 more; vec4 details; };
void main(){uv=texCoord;gl_Position=matrix*vertex;}
