"""Ball for the Maze³ mazes: a truncated icosahedron (12 pentagons,
20 hexagons), placed for printing on a hexagonal face.

Size: a ball smaller than about 8 mm gets stuck in the 4.8 mm panes of the
wall grids, while the passages let through up to about 16.5 mm.

Usage:
    python ball.py              # 10 mm diameter
    python ball.py --diameter 9
"""
import argparse
import itertools
import os

import numpy as np
import trimesh


def truncated_icosahedron(diameter):
    phi = (1 + 5 ** 0.5) / 2
    base = [(0, 1, 3 * phi), (1, 2 + phi, 2 * phi), (phi, 2, phi ** 3)]   # edge = 2
    pts = set()
    for x, y, z in base:
        for p in [(x, y, z), (y, z, x), (z, x, y)]:                      # even permutations
            for s in itertools.product((1, -1), repeat=3):
                pts.add(tuple(round(a * b, 12) for a, b in zip(p, s)))
    V = np.array(sorted(pts))
    assert len(V) == 60
    ball = trimesh.convex.convex_hull(V)
    ball.apply_scale(diameter / 2 / np.linalg.norm(V[0]))
    return ball


def main():
    ap = argparse.ArgumentParser(description="Ball for the Maze³ mazes")
    ap.add_argument("--diameter", type=float, default=10.0,
                    help="circumscribed sphere diameter in mm (default 10)")
    ap.add_argument("--out", default="models")
    args = ap.parse_args()

    ball = truncated_icosahedron(args.diameter)
    sizes = [len(np.unique(ball.faces[f])) for f in ball.facets]
    assert sizes.count(5) == 12 and sizes.count(6) == 20, sizes

    # lay it on a hexagon: its normal should point down
    hexagon = ball.facets[sizes.index(6)]
    n = ball.face_normals[hexagon[0]]
    ball.apply_transform(trimesh.geometry.align_vectors(n, [0, 0, -1]))
    ball.apply_translation(-ball.bounds[0] * [0, 0, 1] - ball.centroid * [1, 1, 0])

    e = ball.edges_unique_length
    print("watertight:", ball.is_watertight, "| pentagons:", sizes.count(5), "| hexagons:", sizes.count(6))
    print("edge mm:", round(min(e[e > 1e-6]), 3), "| size mm:", np.round(ball.extents, 2),
          "| PLA mass ~g:", round(ball.volume / 1000 * 1.24, 2))
    name = f"ball_{args.diameter:g}mm"
    os.makedirs(args.out, exist_ok=True)
    for ext in ("stl", "3mf"):
        ball.export(os.path.join(args.out, f"{name}.{ext}"))
    print("saved:", os.path.join(args.out, f"{name}.stl / .3mf"))


if __name__ == "__main__":
    main()
