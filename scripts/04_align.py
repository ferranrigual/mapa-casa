#!/usr/bin/env python3
"""Paso 4: nivela, orienta y escala la reconstrucción a metros reales.

- Detecta el suelo (plano grande y bajo) y lo pone en z = 0, con z hacia arriba.
- Gira el modelo para que las paredes queden alineadas con los ejes X/Y.
- Calcula la escala a partir de medidas reales (data/work/<escena>/refs.json).

refs.json:
{
  "points": {                       # puntos marcados en las imágenes sin distorsión (dense/images)
    "puerta_sup_der": {"<video>/00012.jpg": [x, y], "<video>/00015.jpg": [x, y]}
  },
  "heights":   [{"point": "puerta_sup_der", "m": 2.10}],      # altura real sobre el suelo
  "distances": [{"a": "p1", "b": "p2", "m": 0.80}]            # distancia real entre dos puntos
}

Resultado:
  data/work/<escena>/align.json   transformación (escala s, rotación R, traslación t): X' = s·R·X + t
  output/<escena>/nube.ply        nube densa en metros, suelo en z=0

Uso (en el contenedor): python scripts/04_align.py <escena>
"""
import json
import sys
from pathlib import Path

import numpy as np
import open3d as o3d

sys.path.insert(0, "/opt/gsplat/examples")
from pycolmap import SceneManager  # noqa: E402


def load_model(sparse_dir):
    m = SceneManager(str(sparse_dir))
    m.load_cameras()
    m.load_images()
    return m


def projection(m, name):
    img = next(i for i in m.images.values() if i.name == name)
    cam = m.cameras[img.camera_id]
    K = np.array([[cam.fx, 0, cam.cx], [0, cam.fy, cam.cy], [0, 0, 1]])
    R = img.R()
    t = img.tvec.reshape(3, 1)
    return K @ np.hstack([R, t]), R, img.tvec


def triangulate(m, obs):
    """DLT con todas las observaciones {imagen: [x, y]}. Devuelve punto y error de reproyección."""
    A, Ps = [], []
    for name, (x, y) in obs.items():
        P, _, _ = projection(m, name)
        Ps.append((P, x, y))
        A.append(x * P[2] - P[0])
        A.append(y * P[2] - P[1])
    _, _, Vt = np.linalg.svd(np.array(A))
    X = Vt[-1][:3] / Vt[-1][3]
    errs = []
    for P, x, y in Ps:
        p = P @ np.append(X, 1)
        errs.append(np.hypot(p[0] / p[2] - x, p[1] / p[2] - y))
    return X, max(errs)


def camera_up(m):
    """Dirección 'arriba' aproximada: media del eje -Y de las cámaras (el móvil se sostiene derecho)."""
    ups = [img.R().T @ np.array([0, -1, 0]) for img in m.images.values()]
    u = np.mean(ups, axis=0)
    return u / np.linalg.norm(u)


def dominant_dir(N, mask, ang=10):
    """Dirección (con signo libre) con más normales a menos de `ang` grados."""
    cand = N[mask]
    rng = np.random.default_rng(0)
    samp = cand[rng.choice(len(cand), min(len(cand), 1500), replace=False)]
    sub = cand[rng.choice(len(cand), min(len(cand), 30000), replace=False)]
    c = np.cos(np.radians(ang))
    scores = (np.abs(samp @ sub.T) > c).sum(1)
    d = samp[np.argmax(scores)]
    for _ in range(5):  # refina con la media de los vecinos
        near = sub[np.abs(sub @ d) > c]
        near = near * np.sign(near @ d)[:, None]
        d = near.mean(0)
        d /= np.linalg.norm(d)
    return d


def manhattan_frame(pcd, cam_up):
    """Tres direcciones ortogonales dominantes (suelo/paredes). Devuelve R con filas X, Y, Z(arriba)."""
    p = o3d.geometry.PointCloud(pcd)
    diag = np.linalg.norm(p.get_max_bound() - p.get_min_bound())
    p.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=diag / 60, max_nn=40))
    N = np.asarray(p.normals)
    d1 = dominant_dir(N, np.ones(len(N), bool))
    d2 = dominant_dir(N, np.abs(N @ d1) < np.sin(np.radians(10)))
    d2 = d2 - (d2 @ d1) * d1
    d2 /= np.linalg.norm(d2)
    d3 = np.cross(d1, d2)
    dirs = [d1, d2, d3]
    k = int(np.argmax([abs(d @ cam_up) for d in dirs]))
    z = dirs.pop(k)
    z = z if z @ cam_up > 0 else -z
    x = dirs[0]
    y = np.cross(z, x)
    R = np.vstack([x, y, z])
    return R, N, np.asarray(p.points)


def horizontal_levels(P, N, R):
    """Alturas (en unidades del modelo) de las superficies horizontales: suelo y techo."""
    z = P @ R[2]
    horiz = np.abs(N @ R[2]) > np.cos(np.radians(15))
    zh = z[horiz]
    span = np.percentile(z, 99.5) - np.percentile(z, 0.5)
    bins = np.linspace(z.min(), z.max(), 400)
    hist, edges = np.histogram(zh, bins=bins)
    hist = np.convolve(hist, np.ones(3) / 3, "same")
    thr = 0.15 * hist.max()
    low_cut = np.percentile(z, 0.5) + 0.3 * span
    high_cut = np.percentile(z, 99.5) - 0.3 * span
    lows = [i for i in range(len(hist)) if hist[i] > thr and edges[i] < low_cut]
    floor = edges[min(lows, key=lambda i: edges[i])] if lows else np.percentile(z, 1)
    # refina el suelo: mediana de puntos horizontales en +-2% de la altura total
    near = zh[np.abs(zh - floor) < 0.02 * span]
    floor = float(np.median(near)) if len(near) else float(floor)
    highs = [i for i in range(len(hist)) if hist[i] > 0.05 * hist.max() and edges[i] > high_cut]
    ceil = float(edges[max(highs, key=lambda i: edges[i])]) if highs else None
    return floor, ceil


def main():
    scene = sys.argv[1]
    W = Path("data/work") / scene
    out = Path("output") / scene
    out.mkdir(parents=True, exist_ok=True)

    m = load_model(W / "dense" / "sparse")
    pcd = o3d.io.read_point_cloud(str(W / "dense" / "fused.ply"))
    print(f"Nube densa: {len(pcd.points)} puntos")
    pcd_s = pcd.voxel_down_sample(0.01 * np.linalg.norm(pcd.get_max_bound() - pcd.get_min_bound()) / 10)

    up = camera_up(m)
    R, N, Pn = manhattan_frame(pcd_s, up)
    print(f"Vertical: ángulo con el 'arriba' de las cámaras {np.degrees(np.arccos(R[2] @ up)):.1f}º")
    floor_z, ceil_z = horizontal_levels(Pn, N, R)

    def to_level(X):  # coordenadas niveladas, todavía sin escala
        Y = R @ X
        Y[2] -= floor_z
        return Y

    # Escala
    refs = json.loads((W / "refs.json").read_text())
    pts = {}
    for k, obs in refs.get("points", {}).items():
        X, err = triangulate(m, obs)
        pts[k] = to_level(X)
        print(f"Punto {k}: reproyección máx {err:.1f}px")
    scales = []
    for h in refs.get("heights", []):
        z = pts[h["point"]][2]
        scales.append(h["m"] / z)
        print(f"Altura {h['point']}: {z:.4f} u. modelo -> real {h['m']} m  => escala {h['m'] / z:.4f}")
    for dd in refs.get("distances", []):
        L = np.linalg.norm(pts[dd["a"]] - pts[dd["b"]])
        scales.append(dd["m"] / L)
        print(f"Distancia {dd['a']}-{dd['b']}: {L:.4f} u. -> real {dd['m']} m  => escala {dd['m'] / L:.4f}")
    if not scales:
        raise SystemExit("refs.json no tiene medidas")
    s = float(np.median(scales))
    if len(scales) > 1:
        print(f"Dispersión entre medidas: {100 * (max(scales) - min(scales)) / s:.1f}%")
    print(f"ESCALA FINAL: {s:.4f} m por unidad")

    t = np.array([0, 0, -floor_z * s])
    T = {"s": s, "R": R.tolist(), "t": t.tolist(), "note": "X_m = s*R*X + t (z arriba, suelo z=0)"}
    (W / "align.json").write_text(json.dumps(T, indent=2))

    pcd.rotate(R, center=(0, 0, 0))
    pcd.scale(s, center=(0, 0, 0))
    pcd.translate(t)
    o3d.io.write_point_cloud(str(out / "nube.ply"), pcd)

    P = np.asarray(pcd.points)
    lo, hi = np.percentile(P, 1, axis=0), np.percentile(P, 99, axis=0)
    print(f"Dimensiones aprox (p1-p99): X {hi[0] - lo[0]:.2f} m, Y {hi[1] - lo[1]:.2f} m, Z {hi[2] - lo[2]:.2f} m")
    if ceil_z is not None:
        print(f"Altura del techo estimada: {(ceil_z - floor_z) * s:.2f} m")
    print(f"Guardado {out / 'nube.ply'} y {W / 'align.json'}")


if __name__ == "__main__":
    main()
