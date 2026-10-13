"""Piłka do labiryntu Maze³: dwudziestościan ścięty (12 pięciokątów,
20 sześciokątów), ustawiony do druku na sześciokątnej ściance.

Rozmiar: kulka mniejsza niż ok. 8 mm klinuje się w okienkach podłogi
(5,33 mm), a otwory ze zastrzałami przepuszczają ok. 17 mm.

Użycie:
    python ball.py              # średnica 10 mm
    python ball.py --diameter 9
"""
import argparse
import itertools
import os

import numpy as np
import trimesh


def truncated_icosahedron(diameter):
    phi = (1 + 5 ** 0.5) / 2
    base = [(0, 1, 3 * phi), (1, 2 + phi, 2 * phi), (phi, 2, phi ** 3)]   # krawędź = 2
    pts = set()
    for x, y, z in base:
        for p in [(x, y, z), (y, z, x), (z, x, y)]:                      # permutacje parzyste
            for s in itertools.product((1, -1), repeat=3):
                pts.add(tuple(round(a * b, 12) for a, b in zip(p, s)))
    V = np.array(sorted(pts))
    assert len(V) == 60
    ball = trimesh.convex.convex_hull(V)
    ball.apply_scale(diameter / 2 / np.linalg.norm(V[0]))
    return ball


def main():
    ap = argparse.ArgumentParser(description="Piłka do labiryntu Maze³")
    ap.add_argument("--diameter", type=float, default=10.0,
                    help="średnica sfery opisanej w mm (domyślnie 10)")
    ap.add_argument("--out", default="models")
    args = ap.parse_args()

    ball = truncated_icosahedron(args.diameter)
    sizes = [len(np.unique(ball.faces[f])) for f in ball.facets]
    assert sizes.count(5) == 12 and sizes.count(6) == 20, sizes

    # połóż na sześciokącie: jego normalna ma wskazywać w dół
    hexagon = ball.facets[sizes.index(6)]
    n = ball.face_normals[hexagon[0]]
    ball.apply_transform(trimesh.geometry.align_vectors(n, [0, 0, -1]))
    ball.apply_translation(-ball.bounds[0] * [0, 0, 1] - ball.centroid * [1, 1, 0])

    e = ball.edges_unique_length
    print("szczelna:", ball.is_watertight, "| pięciokąty:", sizes.count(5), "| sześciokąty:", sizes.count(6))
    print("krawędź mm:", round(min(e[e > 1e-6]), 3), "| wymiary mm:", np.round(ball.extents, 2),
          "| masa PLA ~g:", round(ball.volume / 1000 * 1.24, 2))
    name = f"ball_{args.diameter:g}mm"
    os.makedirs(args.out, exist_ok=True)
    for ext in ("stl", "3mf"):
        ball.export(os.path.join(args.out, f"{name}.{ext}"))
    print("zapisano:", os.path.join(args.out, f"{name}.stl / .3mf"))


if __name__ == "__main__":
    main()
