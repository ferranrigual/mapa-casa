#!/usr/bin/env python3
"""Convierte output/<escena>/splat.ply (gsplat) en un .splat compacto para visores web,
en metros y con el suelo en z=0 (usa data/work/<escena>/align.json).

Formato .splat (32 bytes por gaussiana): pos float32x3, escala float32x3,
color RGBA uint8x4, rotación (w,x,y,z) uint8x4.

Uso (en el contenedor): python scripts/splat_export.py <escena> [max_gaussianas]
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/opt/gsplat/examples")
from datasets.colmap import Parser  # noqa: E402

SH_C0 = 0.28209479177387814


def read_ply(path):
    with open(path, "rb") as f:
        props, n = [], 0
        while True:
            line = f.readline().decode().strip()
            if line.startswith("element vertex"):
                n = int(line.split()[-1])
            elif line.startswith("property"):
                props.append(line.split()[-1])
            elif line == "end_header":
                break
        data = np.fromfile(f, dtype=np.float32, count=n * len(props)).reshape(n, len(props))
    return {p: data[:, i] for i, p in enumerate(props)}


def quat_mul(a, b):
    w1, x1, y1, z1 = a.T
    w2, x2, y2, z2 = b.T
    return np.stack([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
                     w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                     w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2], 1)


def rot_to_quat(R):
    w = np.sqrt(max(0, 1 + R[0, 0] + R[1, 1] + R[2, 2])) / 2
    x = np.copysign(np.sqrt(max(0, 1 + R[0, 0] - R[1, 1] - R[2, 2])) / 2, R[2, 1] - R[1, 2])
    y = np.copysign(np.sqrt(max(0, 1 - R[0, 0] + R[1, 1] - R[2, 2])) / 2, R[0, 2] - R[2, 0])
    z = np.copysign(np.sqrt(max(0, 1 - R[0, 0] - R[1, 1] + R[2, 2])) / 2, R[1, 0] - R[0, 1])
    q = np.array([w, x, y, z])
    return q / np.linalg.norm(q)


def write_gpu_layout(dst, pos, scale, rot, rgba):
    """Formato listo para textura RGBA32UI (2 texels = 32 bytes por gaussiana):
    texel0 = x, y, z (float32), 0 ; texel1 = cov 3D (6 x float16, multiplicada por 4), color RGBA."""
    w, x, y, z = rot.T
    R = np.stack([
        np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)], -1),
        np.stack([2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)], -1),
        np.stack([2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)], -1)], 1)
    M = R * scale[:, None, :]
    S = 4 * M @ M.transpose(0, 2, 1)
    cov = np.stack([S[:, 0, 0], S[:, 0, 1], S[:, 0, 2], S[:, 1, 1], S[:, 1, 2], S[:, 2, 2]], 1)
    out = np.zeros((len(pos), 8), dtype=np.uint32)
    out[:, :3] = pos.astype(np.float32).view(np.uint32)
    out[:, 4:7] = cov.astype(np.float16).view(np.uint32)
    out[:, 7] = np.ascontiguousarray(rgba).view(np.uint32)[:, 0]
    out.tofile(dst)


def main():
    scene = sys.argv[1]
    maxn = int(sys.argv[2]) if len(sys.argv) > 2 else 450000
    W = Path("data/work") / scene
    out = Path("output") / scene

    v = read_ply(out / "splat.ply")
    pos = np.stack([v["x"], v["y"], v["z"]], 1).astype(np.float64)
    logscale = np.stack([v["scale_0"], v["scale_1"], v["scale_2"]], 1)
    rot = np.stack([v["rot_0"], v["rot_1"], v["rot_2"], v["rot_3"]], 1)
    rot /= np.linalg.norm(rot, axis=1, keepdims=True)
    alpha = 1 / (1 + np.exp(-v["opacity"]))
    rgb = np.clip(0.5 + SH_C0 * np.stack([v["f_dc_0"], v["f_dc_1"], v["f_dc_2"]], 1), 0, 1)

    # normalizado de gsplat -> coordenadas COLMAP -> metros alineados
    T = Parser(str(W / "dense"), factor=1, normalize=True).transform
    sT = np.cbrt(np.linalg.det(T[:3, :3]))
    RT = T[:3, :3] / sT
    A = json.loads((W / "align.json").read_text())
    sA, RA, tA = A["s"], np.array(A["R"]), np.array(A["t"])
    Rtot = RA @ RT.T
    stot = sA / sT
    pos = (stot * (Rtot @ (pos - T[:3, 3]).T).T) + tA
    logscale = logscale + np.log(stot)
    rot = quat_mul(np.tile(rot_to_quat(Rtot), (len(rot), 1)), rot)

    scale = np.exp(logscale)
    keep = (alpha > 0.05) & (scale.max(1) < 0.5)
    imp = alpha * np.exp(logscale.sum(1))
    idx = np.where(keep)[0]
    idx = idx[np.argsort(-imp[idx])][:maxn]
    print(f"{len(pos)} gaussianas -> {len(idx)}")

    buf = np.zeros(len(idx), dtype=[("p", "<f4", 3), ("s", "<f4", 3), ("c", "u1", 4), ("r", "u1", 4)])
    buf["p"] = pos[idx]
    buf["s"] = scale[idx]
    buf["c"][:, :3] = np.round(rgb[idx] * 255)
    buf["c"][:, 3] = np.round(alpha[idx] * 255)
    buf["r"] = np.clip(np.round(rot[idx] * 128 + 128), 0, 255)
    dst = out / "splat_web.splat"
    buf.tofile(dst)
    write_gpu_layout(out / "splat_gpu.bin", pos[idx], scale[idx], rot[idx], buf["c"])
    P = pos[idx]
    print(f"{dst}: {dst.stat().st_size / 1e6:.1f} MB; z p1-p99: "
          f"{np.percentile(P[:, 2], 1):.2f}..{np.percentile(P[:, 2], 99):.2f} m")


if __name__ == "__main__":
    main()
