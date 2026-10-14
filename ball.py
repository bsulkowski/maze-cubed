"""Ball for the Maze³ mazes: a truncated octahedron (6 squares, 8 hexagons)
cut from a cube, placed for printing on a square face.

The shape is a cube intersected with an octahedron (|x| + |y| + |z| ≤ ¾ of
the cube side, from the centre): the edges and corners of the cube are cut
away, and the square faces stay in the middles of the cube's faces, turned
45°. It rolls well and prints without supports — the side squares are
vertical and the hexagons are about 55° from horizontal.

Size: the cube side is the width across opposite squares (16 mm by default);
across opposite hexagons it is √3/2 ≈ 0.87 of that, corner to corner
√5/2 ≈ 1.12. A ball of 15–17 mm works best in the default mazes.

Usage:
    python ball.py              # cut from a 16 mm cube
    python ball.py --cube 15
"""
import argparse
import itertools
import os

import numpy as np
import trimesh


def truncated_octahedron(cube):
    """Vertices: all permutations of (0, ±1, ±2), scaled so that the square
    faces (at ±2) are `cube` apart."""
    pts = set()
    for p in itertools.permutations((0, 1, 2)):
        for s in itertools.product((1, -1), repeat=3):
            pts.add(tuple(float(a * b) for a, b in zip(p, s)))
    V = np.array(sorted(pts)) * (cube / 4)
    assert len(V) == 24
    return trimesh.convex.convex_hull(V)


def main():
    ap = argparse.ArgumentParser(description="Ball for the Maze³ mazes")
    ap.add_argument("--cube", type=float, default=16.0,
                    help="side of the cube it is cut from = width across squares, mm (default 16)")
    ap.add_argument("--out", default="models")
    args = ap.parse_args()

    ball = truncated_octahedron(args.cube)
    sizes = [len(np.unique(ball.faces[f])) for f in ball.facets]
    assert sizes.count(4) == 6 and sizes.count(6) == 8, sizes

    # already standing on a square face (normal −z); just put it on the bed
    ball.apply_translation(-ball.bounds[0] * [0, 0, 1] - ball.centroid * [1, 1, 0])

    e = ball.edges_unique_length
    print("watertight:", ball.is_watertight, "| squares:", sizes.count(4), "| hexagons:", sizes.count(6))
    print("edge mm:", round(min(e[e > 1e-6]), 3), "| size mm:", np.round(ball.extents, 2),
          "| corner to corner mm:", round(2 * np.linalg.norm(ball.vertices - ball.centroid, axis=1).max(), 2),
          "| PLA mass ~g:", round(ball.volume / 1000 * 1.24, 2))
    name = f"ball_{args.cube:g}mm"
    os.makedirs(args.out, exist_ok=True)
    for ext in ("stl", "3mf"):
        ball.export(os.path.join(args.out, f"{name}.{ext}"))
    print("saved:", os.path.join(args.out, f"{name}.stl / .3mf"))


if __name__ == "__main__":
    main()
