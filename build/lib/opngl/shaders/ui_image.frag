#version 450

layout(binding = 0) uniform sampler2D uImage;

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
    vec4 t = texture(uImage, vUv);
    vec4 c = t * vColor;
    // Salida premultiplicada: el pipeline 'image' mezcla con
    // srcColor=ONE / dstColor=ONE_MINUS_SRC_ALPHA para bordes limpios
    // en imágenes con transparencia (sin halos).
    outColor = vec4(c.rgb * c.a, c.a);
}
