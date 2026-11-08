#!/usr/bin/env python3
"""Paso 5: genera el plano 2D a partir de la nube escalada (output/<escena>/nube.ply).

Salida en output/<escena>/:
  plano.dxf  capas MUROS (líneas), COTAS (medidas), PUNTOS (corte de la nube), ESCALA
             -> abrir en LibreCAD / QCAD / FreeCAD (unidades: metros)
  plano.svg  -> Inkscape o cualquier navegador
  plano.png  vista rápida

Supone el modelo nivelado (suelo z=0) y paredes alineadas con X/Y (paso 4).
Uso (en el contenedor): python scripts/05_plan.py <escena>
"""
import sys
from pathlib import Path

import ezdxf
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import open3d as o3d  # noqa: E402
from ezdxf import units  # noqa: E402

BIN = 0.01          # resolución de los histogramas (m)
BAND = 0.04         # grosor de la banda alrededor de cada pared (m)
GAP = 0.25          # hueco que parte un muro en dos tramos (m) – p.ej. una puerta
MIN_LEN = 0.30      # longitud mínima de un tramo de muro (m)


def ceiling_height(P):
    z = P[:, 2]
    hist, edges = np.histogram(z, bins=np.arange(1.5, 4.0, 0.02))
    return edges[np.argmax(hist)] + 0.01 if hist.max() > 0.01 * len(z) else np.percentile(z, 99.5)


def runs(vals, gap, min_len):
    v = np.sort(vals)
    if len(v) == 0:
        return []
    out, start = [], v[0]
    for a, b in zip(v[:-1], v[1:]):
        if b - a > gap:
            if a - start >= min_len:
                out.append((start, a))
            start = b
    if v[-1] - start >= min_len:
        out.append((start, v[-1]))
    return out


def find_walls(P, N, ceil_h):
    """Planos verticales alineados a X o Y que suben hasta cerca del techo."""
    walls = []
    for axis in (0, 1):                      # axis 0: muro con x=cte (normal X)
        other = 1 - axis
        sel = np.abs(N[:, axis]) > 0.85
        Q = P[sel]
        if len(Q) == 0:
            continue
        lo, hi = Q[:, axis].min(), Q[:, axis].max()
        hist, edges = np.histogram(Q[:, axis], bins=np.arange(lo, hi + BIN, BIN))
        k = np.ones(5) / 5
        hs = np.convolve(hist, k, "same")
        thr = max(30, 0.01 * len(Q))
        peaks = [i for i in range(1, len(hs) - 1)
                 if hs[i] >= hs[i - 1] and hs[i] > hs[i + 1] and hs[i] > thr]
        # suprime picos a menos de 15 cm de otro mayor
        peaks.sort(key=lambda i: -hs[i])
        kept = []
        for i in peaks:
            if all(abs(edges[i] - edges[j]) > 0.15 for j in kept):
                kept.append(i)
        for i in kept:
            c = edges[i] + BIN / 2
            band = Q[np.abs(Q[:, axis] - c) < BAND]
            c = float(np.median(band[:, axis]))
            high = band[band[:, 2] > ceil_h - 0.45]          # tiene que llegar cerca del techo
            for a, b in runs(band[:, other], GAP, MIN_LEN):
                inrun = high[(high[:, other] >= a) & (high[:, other] <= b)]
                if len(inrun) < 20:
                    continue
                cover = runs(inrun[:, other], GAP, 0.1)
                if sum(y - x for x, y in cover) < 0.5 * (b - a):
                    continue
                walls.append({"axis": axis, "c": c, "a": float(a), "b": float(b), "n": len(band)})
    return walls


def seg(w):
    if w["axis"] == 0:
        return (w["c"], w["a"]), (w["c"], w["b"])
    return (w["a"], w["c"]), (w["b"], w["c"])


def snap_corners(walls, tol=0.20):
    """Alarga/recorta los extremos de los muros hasta la pared perpendicular más cercana."""
    for w in walls:
        perp = [v for v in walls if v["axis"] != w["axis"]]
        for end in ("a", "b"):
            val = w[end]
            best = None
            for v in perp:
                if v["a"] - tol <= w["c"] <= v["b"] + tol and abs(v["c"] - val) < tol:
                    if best is None or abs(v["c"] - val) < abs(best - val):
                        best = v["c"]
            if best is not None:
                w[end] = best
    return walls


def main():
    scene = sys.argv[1]
    out = Path("output") / scene
    pcd = o3d.io.read_point_cloud(str(out / "nube.ply"))
    pcd = pcd.voxel_down_sample(0.01)
    pcd, _ = pcd.remove_statistical_outlier(20, 2.0)
    pcd.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=0.05, max_nn=30))
    P, N = np.asarray(pcd.points), np.asarray(pcd.normals)
    ceil_h = ceiling_height(P)
    print(f"{len(P)} puntos; techo a {ceil_h:.2f} m")

    walls = snap_corners(find_walls(P, N, ceil_h))
    print(f"{len(walls)} tramos de muro:")
    for w in walls:
        (x1, y1), (x2, y2) = seg(w)
        print(f"  {'X' if w['axis'] == 0 else 'Y'}={w['c']:+.3f}  "
              f"({x1:+.2f},{y1:+.2f})-({x2:+.2f},{y2:+.2f})  L={abs(w['b'] - w['a']):.2f} m")

    # Corte horizontal para dibujar (entre 0.1 m y techo-0.15 m)
    sl = P[(P[:, 2] > 0.10) & (P[:, 2] < ceil_h - 0.15)]
    sl2 = sl[np.random.default_rng(0).choice(len(sl), min(len(sl), 40000), replace=False)]

    # ---------- DXF ----------
    doc = ezdxf.new("R2010", setup=True)
    doc.units = units.M
    doc.header["$INSUNITS"] = units.M
    doc.header["$MEASUREMENT"] = 1
    for name, color in (("MUROS", 7), ("COTAS", 1), ("PUNTOS", 8), ("ESCALA", 3)):
        doc.layers.add(name, color=color)
    msp = doc.modelspace()
    for x, y, _ in sl2:
        msp.add_point((x, y), dxfattribs={"layer": "PUNTOS"})
    dimstyle = doc.dimstyles.duplicate_entry("EZDXF", "METROS")
    dimstyle.dxf.dimtxt = 0.08
    dimstyle.dxf.dimasz = 0.06
    dimstyle.dxf.dimdec = 2
    dimstyle.dxf.dimexe = 0.03
    dimstyle.dxf.dimexo = 0.03
    for w in walls:
        p1, p2 = seg(w)
        msp.add_line(p1, p2, dxfattribs={"layer": "MUROS", "lineweight": 50})
        off = 0.25
        msp.add_aligned_dim(p1=p1, p2=p2, distance=off, dimstyle="METROS",
                            dxfattribs={"layer": "COTAS"}).render()
    # barra de escala de 1 m
    xmin, ymin = sl2[:, 0].min(), sl2[:, 1].min()
    sb = (xmin, ymin - 0.5)
    msp.add_line(sb, (sb[0] + 1, sb[1]), dxfattribs={"layer": "ESCALA", "lineweight": 50})
    msp.add_text("1 m", height=0.1, dxfattribs={"layer": "ESCALA"}).set_placement((sb[0] + 0.4, sb[1] + 0.05))
    doc.saveas(out / "plano.dxf")

    # ---------- SVG / PNG ----------
    fig, ax = plt.subplots(figsize=(10, 10))
    ax.scatter(sl2[:, 0], sl2[:, 1], s=0.3, c="#9a9a9a", lw=0)
    for w in walls:
        (x1, y1), (x2, y2) = seg(w)
        ax.plot([x1, x2], [y1, y2], "k-", lw=3, solid_capstyle="projecting")
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        L = abs(w["b"] - w["a"])
        rot = 90 if w["axis"] == 0 else 0
        ax.text(mx, my, f"{L:.2f} m", rotation=rot, ha="center", va="center", fontsize=9,
                color="#c0392b", bbox=dict(fc="white", ec="none", alpha=0.8, pad=1))
    ax.plot([sb[0], sb[0] + 1], [sb[1], sb[1]], "g-", lw=3)
    ax.text(sb[0] + 0.5, sb[1] + 0.08, "1 m", ha="center", color="g")
    ax.set_aspect("equal")
    ax.grid(True, lw=0.3, alpha=0.5)
    ax.set_xlabel("m")
    ax.set_ylabel("m")
    ax.set_title(f"Plano: {scene}  (techo {ceil_h:.2f} m)")
    fig.tight_layout()
    fig.savefig(out / "plano.svg")
    fig.savefig(out / "plano.png", dpi=150)
    print(f"Guardado {out}/plano.dxf, plano.svg, plano.png")


if __name__ == "__main__":
    main()
