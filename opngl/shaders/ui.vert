#version 450

layout(location = 0) in vec3 inPos;
layout(location = 1) in vec4 inColor;
layout(location = 2) in vec2 inUv;

layout(push_constant) uniform PushConstants {
    vec2 viewport;    // offset 0
    vec2 rectSize;    // offset 8
    float radius;     // offset 16
    float borderWidth;// offset 20
    vec4 borderColor; // offset 24
    vec4 fillColor2;  // offset 40
    float padding;    // offset 56
} pc;

layout(location = 0) out vec4 vColor;
layout(location = 1) out vec2 vUv;
layout(location = 2) out vec2 vLocal;

void main() {
    vColor = inColor;
    vUv = inUv;
    vLocal = inUv;
    // Convertir píxeles (origen arriba-izquierda) a NDC (Vulkan, Y=-1 arriba)
    float ndcX = (inPos.x / pc.viewport.x) * 2.0 - 1.0;
    float ndcY = (inPos.y / pc.viewport.y) * 2.0 - 1.0;
    gl_Position = vec4(ndcX, ndcY, inPos.z, 1.0);
}
