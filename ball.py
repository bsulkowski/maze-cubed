"""Ball for the Maze³ mazes: a truncated octahedron (6 squares, 8 hexagons)
cut from a cube, placed for printing on a hexagon (or, with --on square,
on a square).

The shape is a cube intersected with an octahedron (|x| + |y| + |z| ≤ ¾ of
the cube side, from the centre): the edges and corners of the cube are cut
away, and the square faces stay in the middles of the cube's faces, turned
45°. It rolls well and prints without supports either way: standing on a
hexagon, the steepest overhanging faces are about 55° from horizontal, and
it has 2.6 times more contact with the bed than standing on a square.

Size: the cube side is the width across opposite squares (16 mm by default);
across opposite hexagons it is √3/2 ≈ 0.87 of that, corner to corner
√5/2 ≈ 1.12. A ball of 15–16 mm works best in the default mazes.

Optional "Ariadne's thread" hole (--hole): straight through the centre,
between the face the ball stands on and the opposite one, so a thread or
tape can be pulled through the ball and trace its way through the maze.
It has the shape of that face, scaled down to the given width across flats
and concentric with it: hexagonal through hexagons; through squares
octagonal (corners cut by 1/6 of the width, as on the lattice bars). It
runs vertically when printed, so it needs no supports.

Usage:
    python ball.py              # cut from a 16 mm cube
    python ball.py --cube 15
    python ball.py --cube 20 --hole 5
    python ball.py --on square
"""
import argparse
import itertools
import os

import manifold3d as m3d
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


def stand(ball, on):
    """Rotate the ball so that a hexagon (or a square) faces down."""
    if on == "hexagon":
        down = np.array([-1.0, -1.0, -1.0]) / 3 ** 0.5
        R = trimesh.geometry.align_vectors(down, [0, 0, -1])
        ball = ball.copy()
        ball.apply_transform(R)
    return ball   # built standing on a square already


def drill(ball, width, on):
    """Through hole along Z, centred, `width` across flats: the bottom face
    scaled down (flats parallel to its edges); a square one gets its
    corners cut by width/6, like the lattice bars."""
    zmin, zmax = ball.bounds[:, 2]
    bottom = ball.vertices[np.abs(ball.vertices[:, 2] - zmin) < 1e-6][:, :2]
    centre = bottom.mean(0)
    ang = np.arctan2(*(bottom - centre).T[::-1])
    poly = (bottom - centre)[np.argsort(ang)]
    n = len(poly)
    face_width = 2 * np.linalg.norm((poly[0] + poly[1]) / 2)     # across flats
    poly = poly * (width / face_width)
    if on == "square":
        # cut the corners: each corner replaced by two points width/6 along its edges
        cut = []
        for k in range(n):
            p, a, b = poly[k], poly[k - 1], poly[(k + 1) % n]
            side = np.linalg.norm(b - p)
            cut += [p + (a - p) * (width / 6) / side, p + (b - p) * (width / 6) / side]
        poly = np.array(cut)
    hole = (m3d.Manifold.extrude(m3d.CrossSection([poly.tolist()]), zmax - zmin + 2)
            .translate([centre[0], centre[1], zmin - 1]))
    solid = m3d.Manifold(m3d.Mesh(vert_properties=np.asarray(ball.vertices, np.float32),
                                  tri_verts=np.asarray(ball.faces, np.uint32)))
    out = (solid - hole).to_mesh()
    return trimesh.Trimesh(vertices=out.vert_properties[:, :3], faces=out.tri_verts)


def main():
    ap = argparse.ArgumentParser(description="Ball for the Maze³ mazes")
    ap.add_argument("--cube", type=float, default=16.0,
                    help="side of the cube it is cut from = width across squares, mm (default 16)")
    ap.add_argument("--hole", type=float, default=0.0,
                    help="octagonal through hole for a thread, width across flats, mm (default: none)")
    ap.add_argument("--on", choices=("hexagon", "square"), default="hexagon",
                    help="face the ball stands on when printed (default hexagon)")
    ap.add_argument("--out", default="models")
    args = ap.parse_args()

    ball = truncated_octahedron(args.cube)
    sizes = [len(np.unique(ball.faces[f])) for f in ball.facets]
    assert sizes.count(4) == 6 and sizes.count(6) == 8, sizes
    counts = f"squares: {sizes.count(4)} | hexagons: {sizes.count(6)}"

    ball = stand(ball, args.on)
    edge = args.cube / 4 * 2 ** 0.5
    face_width = edge * 3 ** 0.5 if args.on == "hexagon" else edge     # across flats
    assert args.hole < face_width, f"hole wider than the {args.on} ({face_width:.2f} mm)"
    if args.hole:
        ball = drill(ball, args.hole, args.on)
        print(f"hole: {args.hole:g} mm across flats, through {args.on}s"
              f" | wall at the {args.on}: {(face_width - args.hole) / 2:.2f} mm")

    # put it on the bed
    ball.apply_translation(-ball.bounds[0] * [0, 0, 1] - ball.centroid * [1, 1, 0])

    z0 = ball.bounds[0, 2]
    bed = sum(a for a, f in zip(ball.area_faces, ball.faces) if np.all(np.abs(ball.vertices[f, 2] - z0) < 1e-6))
    print("watertight:", ball.is_watertight, "|", counts)
    print("edge mm:", round(edge, 3), "| on the bed mm²:", round(bed, 1), "| size mm:", np.round(ball.extents, 2),
          "| corner to corner mm:", round(2 * np.linalg.norm(ball.vertices - ball.centroid, axis=1).max(), 2),
          "| PLA mass ~g:", round(ball.volume / 1000 * 1.24, 2))
    name = (f"ball_{args.cube:g}mm" + ("_square" if args.on == "square" else "")
            + (f"_hole{args.hole:g}" if args.hole else ""))
    os.makedirs(args.out, exist_ok=True)
    for ext in ("stl", "3mf"):
        ball.export(os.path.join(args.out, f"{name}.{ext}"))
    print("saved:", os.path.join(args.out, f"{name}.stl / .3mf"))


if __name__ == "__main__":
    main()
