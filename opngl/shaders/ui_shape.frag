#version 450

layout(location = 0) in vec4 vColor;
layout(location = 2) in vec2 vLocal;

layout(push_constant) uniform PushConstants {
    vec2 viewport;    // offset 0
    vec2 rectSize;    // offset 8
    float radius;     // offset 16
    float borderWidth;// offset 20
    vec4 borderColor; // offset 24
    vec4 fillColor2;  // offset 40 (gradiente inferior; a==0 => sin gradiente)
    float padding;    // offset 56
} pc;

layout(location = 0) out vec4 outColor;

// SDF de rectángulo redondeado centrado en el origen.
float roundedRectSDF(vec2 p, vec2 b, float r) {
    vec2 q = abs(p) - b + r;
    return min(max(q.x, q.y), 0.0) + length(max(q, 0.0)) - r;
}

void main() {
    vec2 hsz = pc.rectSize * 0.5;
    float d = roundedRectSDF(vLocal, hsz, pc.radius);
    float outer = clamp(0.5 - d, 0.0, 1.0);

    // Relleno base; con gradiente se mezcla de arriba (vColor) a abajo (fillColor2).
    vec3 fill = vColor.rgb;
    if (pc.fillColor2.a > 0.0) {
        float t = clamp((vLocal.y / max(hsz.y, 0.0001) + 1.0) * 0.5, 0.0, 1.0);
        fill = mix(vColor.rgb, pc.fillColor2.rgb, t);
    }

    // Borde: banda entre el rect exterior y el interior (contraído borderWidth).
    if (pc.borderWidth > 0.0 && pc.borderColor.a > 0.0) {
        vec2 innerSize = max(hsz - pc.borderWidth, vec2(0.0));
        float innerR = max(pc.radius - pc.borderWidth, 0.0);
        float di = roundedRectSDF(vLocal, innerSize, innerR);
        float inner = clamp(0.5 - di, 0.0, 1.0);
        fill = mix(fill, pc.borderColor.rgb, outer - inner);
    }

    outColor = vec4(fill, vColor.a * outer);
}
