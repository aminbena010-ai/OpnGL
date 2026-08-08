#version 450

layout(binding = 0) uniform sampler2D uFontAtlas;

layout(push_constant) uniform PushConstants {
    vec2 viewport;
    vec2 rectSize;
    float radius;
    float borderWidth;
    vec4 borderColor;
    vec4 fillColor2;
    float padding;
} pc;

layout(location = 0) in vec4 vColor;
layout(location = 1) in vec2 vUv;
layout(location = 0) out vec4 outColor;

void main() {
    float a = texture(uFontAtlas, vUv).r;
    outColor = vec4(vColor.rgb, vColor.a * a);
}
