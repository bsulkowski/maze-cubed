"""Ball for the Maze³ mazes: a truncated octahedron (6 squares, 8 hexagons)
cut from a cube, placed for printing on a hexagon (or, with --on square,
on a square).

The shape is a cube intersected with an octahedron (|x| + |y| + |z| ≤ ¾ of
the cube side, from the centre): the edges and corners of the cube are cut
away, and the square faces stay in the middles of the cube's faces, turned
45°. It rolls well and prints without supports either way: standing on a
hexagon, the steepest overhanging faces are about 55° from horizontal, and
it has 2.6 times more contact with the bed than standing on a square.

All edges get a 0.4 mm chamfer by default (--chamfer), like the lattice
bars; it is also the countersink at both ends of the hole.

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


def chamfered(cube, leg):
    """The same solid with every edge chamfered: each edge is cut by a plane
    halfway between its two faces, leaving `leg` mm of each face cut away
    (on a 90° edge that is the usual 45° chamfer, as on the lattice bars).
    Built as an intersection of half-spaces: the 14 faces plus one per edge."""
    from scipy.spatial import HalfspaceIntersection
    plain = truncated_octahedron(cube)
    normals, offsets = [], []
    faces = [np.array(n, float) for n in itertools.product((1, -1), repeat=3)]
    faces = [n / 3 ** 0.5 for n in faces] + [s * e for e in np.eye(3) for s in (1, -1)]
    support = lambda n: (plain.vertices @ n).max()
    for n in faces:
        normals.append(n); offsets.append(support(n))
    for a, b in itertools.combinations(faces, 2):
        m = a + b
        if np.linalg.norm(m) < 1e-9:
            continue
        m /= np.linalg.norm(m)
        # a shared edge: at least two vertices lie on both faces
        on_both = np.sum((np.abs(plain.vertices @ a - support(a)) < 1e-6)
                         & (np.abs(plain.vertices @ b - support(b)) < 1e-6))
        if on_both < 2:
            continue
        phi = np.arccos(np.clip(a @ b, -1, 1))          # angle between the normals
        normals.append(m); offsets.append(support(m) - leg * np.sin(phi / 2))
    hs = np.hstack([np.array(normals), -np.array(offsets)[:, None]])
    pts = HalfspaceIntersection(hs, np.zeros(3)).intersections
    return trimesh.convex.convex_hull(pts)


def stand(ball, on):
    """Rotate the ball so that a hexagon (or a square) faces down."""
    if on == "hexagon":
        down = np.array([-1.0, -1.0, -1.0]) / 3 ** 0.5
        R = trimesh.geometry.align_vectors(down, [0, 0, -1])
        ball = ball.copy()
        ball.apply_transform(R)
    return ball   # built standing on a square already


def drill(ball, width, on, plain, leg):
    """Through hole along Z, centred, `width` across flats: the bottom face
    of the unchamfered `plain` solid scaled down (flats parallel to its
    edges); a square one gets its corners cut by width/6, like the lattice
    bars. Both ends get a 45° countersink with the given leg."""
    zmin, zmax = ball.bounds[:, 2]
    pz = plain.bounds[0, 2]
    bottom = plain.vertices[np.abs(plain.vertices[:, 2] - pz) < 1e-6][:, :2]
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
    section = m3d.CrossSection([poly.tolist()])
    hole = m3d.Manifold.extrude(section, zmax - zmin + 2).translate([0, 0, zmin - 1])
    if leg:
        # 45° countersinks: the section grows by 1 mm per mm, from `leg`
        # inside the face to 1 mm outside it
        def ring(off, z):
            cs = section.offset(off, m3d.JoinType.Miter) if off else section
            return [(x, y, z) for x, y in np.asarray(cs.to_polygons()[0])]
        top = ring(0, zmax - leg) + ring(leg + 1, zmax + 1)
        bot = ring(0, zmin + leg) + ring(leg + 1, zmin - 1)
        hole = hole + m3d.Manifold.hull_points(top) + m3d.Manifold.hull_points(bot)
    hole = hole.translate([centre[0], centre[1], 0])
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
    ap.add_argument("--chamfer", type=float, default=0.4,
                    help="chamfer on all edges and at the ends of the hole, mm (default 0.4; 0 = none)")
    ap.add_argument("--on", choices=("hexagon", "square"), default="hexagon",
                    help="face the ball stands on when printed (default hexagon)")
    ap.add_argument("--out", default="models")
    args = ap.parse_args()

    ball = truncated_octahedron(args.cube)
    sizes = [len(np.unique(ball.faces[f])) for f in ball.facets]
    assert sizes.count(4) == 6 and sizes.count(6) == 8, sizes
    counts = f"squares: {sizes.count(4)} | hexagons: {sizes.count(6)}"

    plain = stand(ball, args.on)
    ball = stand(chamfered(args.cube, args.chamfer), args.on) if args.chamfer else plain
    edge = args.cube / 4 * 2 ** 0.5
    face_width = edge * 3 ** 0.5 if args.on == "hexagon" else edge     # across flats
    assert args.hole < face_width, f"hole wider than the {args.on} ({face_width:.2f} mm)"
    if args.hole:
        ball = drill(ball, args.hole, args.on, plain, args.chamfer)
        print(f"hole: {args.hole:g} mm across flats, through {args.on}s"
              f" | wall at the {args.on}: {(face_width - args.hole) / 2:.2f} mm")

    # put it on the bed
    ball.apply_translation(-ball.bounds[0] * [0, 0, 1] - ball.centroid * [1, 1, 0])

    z0 = ball.bounds[0, 2]
    bed = sum(a for a, f in zip(ball.area_faces, ball.faces) if np.all(np.abs(ball.vertices[f, 2] - z0) < 1e-6))
    print("watertight:", ball.is_watertight, "|", counts)
    print("edge mm:", round(edge, 3), "| chamfer mm:", round(args.chamfer, 2), "| on the bed mm²:", round(bed, 1), "| size mm:", np.round(ball.extents, 2),
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
