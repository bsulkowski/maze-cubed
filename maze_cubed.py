"""Maze³ — a printable 3D maze generator.

The classic maze generalised to three dimensions: cubic cells in an
NX × NY × NZ lattice, passages in all six directions, no privileged axis.

Construction:
- edges: square bars of size ROD with chamfered edges (CHAMFER),
  corner nodes as cubes chamfered the same way;
- every wall (including inner walls shared by two cells): a grid of
  MUNTIN × MUNTIN muntins dividing the window into DIVS × DIVS equal panes,
  centred in the plane of the bar axes;
- in every cell, 4 braces under the muntin crossings of the ceiling,
  diagonal in plan, running to the nearest corner post and attached at the
  height of the upper muntin line lowered by half a bar; square horizontal
  section, sitting under the muntin crossing at bridge level and widening
  slightly towards the top (FLARE), so that the last printed layers cover
  the whole crossing;
- in every closed inner wall (not on the outside of the cube): a plate of
  thickness PLATE filling the middle pane; it marks the walls inside the
  maze and shows their depth as the cube is turned;
- under every horizontal wall: a pad — the frame of the middle pane
  extended down to the level of the bar undersides (one chamfer below the
  muntins); on the bottom face it rests on the print bed;
- maze: along the paths from the file, the wall between consecutive cells
  is open (no muntins). A cell's braces disappear only when its ceiling is
  open. Above an open side wall the top bar gets two 45° knee braces from
  the posts (in the plane of the wall).

EDGE is the distance between bar axes (cell size). The outer size of the
model is N * EDGE + ROD.

Usage:
    python maze_cubed.py mazes/lab4_1.txt          # maze
    python maze_cubed.py --size 4 4 4              # full lattice, no passages
"""
import argparse
import itertools
import json
import os
import re
from collections import defaultdict

import manifold3d as m3d
import numpy as np
import trimesh

EDGE = 25.0      # mm, cell size (axis to axis)
ROD = 2.4        # mm, square bar section (6 lines of a 0.4 mm nozzle)
CHAMFER = 0.4    # mm, edge chamfer (45°)
MUNTIN = 1.6     # mm, square muntin section (4 lines of a 0.4 mm nozzle)
FLARE = 0.4      # mm, braces widen by this much towards the top (0.2 mm per side), so
                 # that the last printed layers under a bridge cover the whole crossing
PLATE = 0.8      # mm, plate in the middle pane of closed inner walls (0 = none)
DIVS = 3         # number of panes the muntins divide a window into, per direction
EPS = 0.0047     # mm, micro-offsets that keep faces of different elements from
                 # ever being coplanar (so the mesh comes out clean);
                 # 5–70 µm, invisible in print. Deliberately not a round number:
                 # small multiples of EPS never hit round dimensions in mm, so
                 # the offsets can't accidentally cancel out differences in size


def set_dims(edge=None, rod=None, chamfer=None, muntin=None):
    """Set the construction dimensions and recompute derived quantities."""
    global EDGE, ROD, CHAMFER, MUNTIN, h, c, H_AXIS, H_NODE, CENTERS, BRACES
    EDGE = EDGE if edge is None else edge
    ROD = ROD if rod is None else rod
    CHAMFER = CHAMFER if chamfer is None else chamfer
    MUNTIN = MUNTIN if muntin is None else muntin
    assert MUNTIN <= ROD - 2 * CHAMFER + 1e-9, "muntin wider than the flat part of a bar"
    h = ROD / 2
    c = CHAMFER
    # Bars along different axes differ in thickness by EPS, and corner nodes
    # are another EPS smaller, so the flat faces of crossing bars never lie
    # in one plane.
    H_AXIS = [h, h - EPS, h - 2 * EPS]
    H_NODE = h - 3 * EPS
    # muntin axes within one cell, spaced for equal panes
    pane = (EDGE - ROD - (DIVS - 1) * MUNTIN) / DIVS
    CENTERS = [h + k * pane + (k - 0.5) * MUNTIN for k in range(1, DIVS)]
    BRACES = braces_spec()


# Actual widths of the elements thinner than a bar. A muntin may be equal to
# the flat part of a bar (bar − 2 × chamfer); if it lay exactly on its edges,
# rounding errors would leave gaps in the mesh for some dimensions. So each
# kind of element is narrower than the nominal muntin by a different multiple
# of EPS, and different from the flat faces of the bars (0–3·EPS per side):
# no two faces are coplanar or lie on another element's edge, whatever the
# dimensions. The differences are 20–70 µm.
def w_muntin():
    return MUNTIN - 9 * EPS


def w_brace():
    return MUNTIN - 11 * EPS


def w_knee():
    return MUNTIN - 13 * EPS


def w_pad():
    return MUNTIN - 15 * EPS


def pane_size():
    """Side of a pane in the muntin grid."""
    return (EDGE - ROD - (DIVS - 1) * MUNTIN) / DIVS


# set by configure()
N = (4, 4, 4)
SIZE = [n * EDGE for n in N]
OPEN = set()


# --- path file ------------------------------------------------------------------

def load_paths(fname):
    """JS-style file: `name = [ [ [x, y, z], ... ], ... ];`.
    Cell coordinates 1..N; 0 or N+1 means an exit to the outside."""
    txt = open(fname).read().split("=", 1)[1].strip().rstrip(";")
    return json.loads(re.sub(r",(\s*\])", r"\1", txt))


def size_from_paths(paths):
    """Lattice size inferred from the paths: the largest coordinate along
    each axis, minus one if only exits reach it (path ends entering that
    layer along that axis). When in doubt, give the size explicitly:
    --size NX NY NZ."""
    size = []
    for i in range(3):
        top = max(p[i] for path in paths for p in path)
        only_exits = True
        for path in paths:
            for k, p in enumerate(path):
                if p[i] != top:
                    continue
                is_end = k in (0, len(path) - 1)
                nb = path[1] if k == 0 else path[-2] if is_end else None
                if not (is_end and nb[i] == top - 1):
                    only_exits = False
        size.append(top - 1 if only_exits else top)
    return tuple(size)


def maze_graph(paths):
    """Passage graph: cell -> set of neighbours (coordinates as in the file)."""
    g = defaultdict(set)
    for p in paths:
        for a, b in zip(p, p[1:]):
            a, b = tuple(a), tuple(b)
            g[a].add(b)
            g[b].add(a)
    return g


def is_inside(cell):
    return all(1 <= x <= n for x, n in zip(cell, N))


def describe(paths):
    """Short report on the maze: coverage, loops, exits."""
    g = maze_graph(paths)
    nodes = set(g)
    edges = sum(len(v) for v in g.values()) // 2
    inside = {x for x in nodes if is_inside(x)}
    exits = sorted(nodes - inside)
    all_cells = set(itertools.product(*[range(1, n + 1) for n in N]))
    # connectivity
    seen, stack = set(), [next(iter(nodes))]
    while stack:
        x = stack.pop()
        if x not in seen:
            seen.add(x)
            stack.extend(g[x] - seen)
    print(f"cells visited: {len(inside)} of {len(all_cells)}"
          + ("" if inside == all_cells else f" (missing: {sorted(all_cells - inside)})"))
    print(f"passages: {edges} | exits: {len(exits)} {exits}")
    print("connected:", len(seen) == len(nodes),
          "| tree (no loops):", len(seen) == len(nodes) and edges == len(nodes) - 1)


def open_faces(paths):
    """Wall = (axis, cell on the lower side, 0-based indices; -1 outside)."""
    faces = set()
    for p in paths:
        for a, b in zip(p, p[1:]):
            d = [abs(x - y) for x, y in zip(a, b)]
            assert sorted(d) == [0, 0, 1], f"cells {a} and {b} are not adjacent"
            axis = d.index(1)
            lo = tuple(min(x, y) - 1 for x, y in zip(a, b))
            assert all(-1 <= lo[i] < N[i] for i in range(3)), f"outside the lattice: {a}, {b}"
            faces.add((axis, lo))
    return faces


def configure(paths=None, size=None):
    """Set the lattice size and the set of open walls."""
    global N, SIZE, OPEN
    if size is None:
        size = size_from_paths(paths) if paths else (4, 4, 4)
    N = tuple(size)
    SIZE = [n * EDGE for n in N]
    OPEN = open_faces(paths) if paths else set()


def face(axis, cell, upper=False):
    """Key of the wall of `cell` (0-based) perpendicular to `axis`."""
    t = list(cell)
    if not upper:
        t[axis] -= 1
    return (axis, tuple(t))


# --- geometry -------------------------------------------------------------------

def octagon(hh):
    return [(-hh + c, -hh), (hh - c, -hh), (hh, -hh + c), (hh, hh - c),
            (hh - c, hh), (-hh + c, hh), (-hh, hh - c), (-hh, -hh + c)]


def axis_frame(axis):
    """3×4 matrix laying the local Z axis along `axis` (cyclic rotation)."""
    M = np.zeros((3, 4))
    a, b = (axis + 1) % 3, (axis + 2) % 3
    M[a, 0] = M[b, 1] = M[axis, 2] = 1.0
    return M


def octo_prism(axis, a0, a1, hh=None):
    hh = H_AXIS[axis] if hh is None else hh
    p = m3d.Manifold.extrude(m3d.CrossSection([octagon(hh)]), a1 - a0).translate([0, 0, a0])
    return p.transform(axis_frame(axis).tolist())


def slanted_bar(p, q, w, overrun=0.0, underrun=0.0, flare=0.0):
    """Oblique bar whose every horizontal section is a square with sides
    parallel to X and Y, the section centres lying on segment p→q (p below
    q). Cut horizontally at both ends. The section perpendicular to the axis
    is not square — instead, where the bar meets the lattice, its footprint
    matches the square of a crossing. `overrun` and `underrun` extend the
    top and bottom ends along the axis by the given height (so the ends
    don't share a plane with other elements).

    `flare` widens the bar towards the top: the section grows linearly from
    w at p to w + flare at q. A slicer takes each layer's outline from the
    middle of the layer, where a leaning bar has already moved outwards;
    the flare keeps the last layers under a bridge covering the whole
    crossing square."""
    p, q = np.asarray(p, float), np.asarray(q, float)
    d = q - p
    assert d[2] > 0
    q = q + d / d[2] * overrun
    p = p - d / d[2] * underrun
    d = q - p
    if not flare:
        M = [[1, 0, d[0] / d[2], p[0]],
             [0, 1, d[1] / d[2], p[1]],
             [0, 0, 1, p[2]]]
        return m3d.Manifold.cube([w, w, d[2]]).translate([-w / 2, -w / 2, 0]).transform(M)
    lo, hi = w / 2, (w + flare) / 2
    pts = [(p[0] + sx * lo, p[1] + sy * lo, p[2]) for sx in (-1, 1) for sy in (-1, 1)]
    pts += [(q[0] + sx * hi, q[1] + sy * hi, q[2]) for sx in (-1, 1) for sy in (-1, 1)]
    return m3d.Manifold.hull_points(pts)


def rods_and_nodes():
    parts = []
    # bars: continuous lines through the whole lattice
    for axis in range(3):
        a, b = (axis + 1) % 3, (axis + 2) % 3
        for i in range(N[a] + 1):
            for j in range(N[b] + 1):
                pos = [0.0] * 3
                pos[a], pos[b] = i * EDGE, j * EDGE
                parts.append(octo_prism(axis, 0, SIZE[axis]).translate(pos))
    # node = intersection of three short bars (a chamfered cube);
    # needed only at the 8 corners, where all bars end
    node = (octo_prism(0, -h, h, H_NODE) ^ octo_prism(1, -h, h, H_NODE)
            ^ octo_prism(2, -h, h, H_NODE))
    for corner in itertools.product(*[(0, n) for n in N]):
        parts.append(node.translate([k * EDGE for k in corner]))
    return parts


def muntins():
    """One 2D grid per plane, made of the grids of the individual walls
    (except open ones); muntin lines run continuously through the bars.
    The union is computed in 2D exactly, so no coplanar faces arise."""
    w = w_muntin()
    parts = []
    cell_grid = m3d.CrossSection()
    for cc in CENTERS:
        cell_grid += m3d.CrossSection.square([EDGE, w]).translate([0, cc - w / 2])
        cell_grid += m3d.CrossSection.square([w, EDGE]).translate([cc - w / 2, 0])
    for axis in range(3):
        a, b = (axis + 1) % 3, (axis + 2) % 3
        for i in range(N[axis] + 1):
            grid = m3d.CrossSection()
            for j in range(N[a]):
                for k in range(N[b]):
                    t = [0, 0, 0]
                    t[axis], t[a], t[b] = i - 1, j, k
                    if (axis, tuple(t)) not in OPEN:
                        grid += cell_grid.translate([j * EDGE, k * EDGE])
            if grid.is_empty():
                continue
            slab = m3d.Manifold.extrude(grid, w).translate([0, 0, -w / 2])
            slab = slab.transform(axis_frame(axis).tolist())
            pos = [0.0] * 3
            pos[axis] = i * EDGE
            parts.append(slab.translate(pos))
    return parts


def plates(t):
    """Plates filling the middle pane of every closed inner wall (outer
    walls of the cube stay without them): they mark the walls inside
    the maze and show depth when the cube is turned. A plate of thickness t
    lies centred in the plane of the wall, its edges on the axes of the
    surrounding muntins. Horizontal plates rest on the pads below them."""
    if not t:
        return []
    t = t - 17 * EPS
    c0, c1 = CENTERS[0], CENTERS[-1]
    square = m3d.CrossSection.square([c1 - c0, c1 - c0]).translate([c0, c0])
    parts = []
    for axis in range(3):
        a, b = (axis + 1) % 3, (axis + 2) % 3
        for i in range(1, N[axis]):                 # inner planes only
            sheet = m3d.CrossSection()
            for j in range(N[a]):
                for k in range(N[b]):
                    w = [0, 0, 0]
                    w[axis], w[a], w[b] = i - 1, j, k
                    if (axis, tuple(w)) not in OPEN:
                        sheet += square.translate([j * EDGE, k * EDGE])
            if sheet.is_empty():
                continue
            slab = m3d.Manifold.extrude(sheet, t).translate([0, 0, -t / 2])
            slab = slab.transform(axis_frame(axis).tolist())
            pos = [0.0] * 3
            pos[axis] = i * EDGE
            parts.append(slab.translate(pos))
    return parts


def braces_spec():
    """The 4 braces of a cell: from a ceiling muntin crossing, diagonally
    (in plan), to the nearest corner post, attached at the height of the
    upper muntin line lowered by half a bar — the same as the knee braces
    at open walls. About 35.3° from horizontal."""
    out = []
    for a in CENTERS:
        for b in CENTERS:
            cx = 0.0 if a < EDGE / 2 else EDGE
            cy = 0.0 if b < EDGE / 2 else EDGE
            # top end: centre of the crossing at the underside of the pad
            # (z = −h below the ceiling axis), where the bridge starts; the
            # bottom end is lowered by the same amount, keeping the angle
            out.append(((cx, cy, CENTERS[-1] - h), (a, b, EDGE - h)))
    return out


def cell_braces():
    """Braces as oblique prisms with a square horizontal section: at the
    underside of the ceiling pad, where the bridge starts, their section is
    exactly the square of the muntin crossing (rotated 45° relative to the
    brace axis)."""
    w = w_brace()
    return m3d.Manifold.batch_boolean([slanted_bar(p, q, w, 4 * EPS, 4 * EPS, FLARE) for p, q in BRACES],
                                      m3d.OpType.Add)


def knee_braces():
    """Knee braces under the top bar of every open side wall: from both
    posts (at the height of the upper muntin line lowered by half a bar) to
    the underside of the top bar (above the outer muntin lines), at 45°, in
    the plane of the wall. Square horizontal section, as for the ceiling
    braces."""
    w = w_knee()
    c0, c1 = CENTERS[0], CENTERS[-1]
    out = []
    for axis, lo in OPEN:
        if axis == 2:
            continue                              # ceiling/floor: no bar above the opening
        along = 1 - axis                          # horizontal axis in the plane of the wall
        base = [k * EDGE for k in lo]
        base[axis] += EDGE                        # plane of the wall
        z_top = base[2] + EDGE
        for pv, ph in ((0.0, c0), (EDGE, c1)):    # (post, point on the top bar)
            # top end under the top bar (where the bridge starts),
            # bottom end lowered by the same amount — still 45°
            p = list(base); p[along] += pv; p[2] += c1 - h
            q = list(base); q[along] += ph; q[2] = z_top - h
            out.append(slanted_bar(p, q, w, 6 * EPS, 6 * EPS, FLARE))
    return out


def cell_pad():
    """Pad: the frame of the middle pane of a horizontal wall extended down
    to the level of the bar undersides, i.e. one chamfer below the muntins
    (when the muntin equals the flat part of a bar). On the bottom face it
    rests on the print bed."""
    c0, c1, w = CENTERS[0], CENTERS[-1], w_pad()
    z0, z1 = -h, 0.0
    outer = m3d.Manifold.cube([c1 - c0 + w, c1 - c0 + w, z1 - z0]).translate([c0 - w / 2, c0 - w / 2, z0])
    inner = m3d.Manifold.cube([c1 - c0 - w, c1 - c0 - w, z1 - z0 + 2]).translate([c0 + w / 2, c0 + w / 2, z0 - 1])
    return outer - inner


set_dims()


def build(plate=None):
    """Assemble the whole model; return a trimesh standing on the bed (z_min = 0)."""
    plate = PLATE if plate is None else plate
    plate_parts = plates(plate)
    n_plates = sum(1 for axis, lo in itertools.product(range(3), itertools.product(*[range(-1, n) for n in N]))
                   if 0 <= lo[axis] < N[axis] - 1 and all(0 <= lo[i] < N[i] for i in range(3) if i != axis)
                   and (axis, lo) not in OPEN)
    parts = rods_and_nodes() + muntins() + plate_parts
    braces, n_braces = cell_braces(), 0
    for cell in itertools.product(*[range(n) for n in N]):
        if face(2, cell, upper=True) not in OPEN:   # braces disappear only with the ceiling
            n_braces += len(BRACES)
            parts.append(braces.translate([k * EDGE for k in cell]))
    knees = knee_braces()
    parts += knees
    pad, n_pads = cell_pad(), 0
    for i, j, k in itertools.product(range(N[0]), range(N[1]), range(N[2] + 1)):
        if face(2, (i, j, k)) not in OPEN:          # horizontal wall under cell (i, j, k)
            n_pads += 1
            parts.append(pad.translate([i * EDGE, j * EDGE, k * EDGE]))
    print(f"open walls: {len(OPEN)} | braces: {n_braces} of {len(BRACES) * np.prod(N)}"
          f" | knee braces: {len(knees)} | pads: {n_pads}"
          + (f" | plates: {n_plates} ({plate:g} mm)" if plate else ""))

    frame = m3d.Manifold.batch_boolean(parts, m3d.OpType.Add).translate([h, h, h])
    mesh = frame.to_mesh()
    v = mesh.vert_properties[:, :3]
    _, cnt = np.unique(np.round(v, 5), axis=0, return_counts=True)
    tm = trimesh.Trimesh(vertices=v, faces=mesh.tri_verts)
    print("watertight:", tm.is_watertight, "| duplicate vertices:", int((cnt > 1).sum()))
    print("size mm:", np.round(tm.extents, 2), "| triangles:", len(tm.faces))
    print("volume cm³:", round(tm.volume / 1000, 2), "| PLA mass ~g:", round(tm.volume / 1000 * 1.24, 1))
    return tm


def main():
    ap = argparse.ArgumentParser(description="Maze³ — printable 3D maze generator")
    ap.add_argument("paths", nargs="?", help="path file; without it a full lattice is built")
    ap.add_argument("--size", nargs=3, type=int, metavar=("NX", "NY", "NZ"),
                    help="lattice size (default: from the path file, or 4 4 4)")
    ap.add_argument("--out", default="models", help="directory for STL and 3MF files (default: models)")
    ap.add_argument("--rod", type=float, help=f"lattice bar section, mm (default {ROD:g})")
    ap.add_argument("--chamfer", type=float, help=f"bar chamfer, mm (default {CHAMFER:g})")
    ap.add_argument("--muntin", type=float, help=f"muntin section, mm (default {MUNTIN:g})")
    ap.add_argument("--edge", type=float, help=f"cell size (distance between bar axes), mm (default {EDGE:g})")
    ap.add_argument("--plate", type=float, default=PLATE,
                    help=f"plate in the middle pane of closed inner walls, mm (default {PLATE:g}; 0 = none)")
    args = ap.parse_args()

    defaults = dict(edge=EDGE, rod=ROD, chamfer=CHAMFER, muntin=MUNTIN, plate=PLATE)
    set_dims(args.edge, args.rod, args.chamfer, args.muntin)
    suffix = "".join(f"_{k}{v:g}" for k, v in
                     dict(edge=EDGE, rod=ROD, chamfer=CHAMFER, muntin=MUNTIN, plate=args.plate).items()
                     if v != defaults[k])

    paths = load_paths(args.paths) if args.paths else None
    configure(paths, args.size)
    name = (os.path.splitext(os.path.basename(args.paths))[0] if args.paths
            else "lattice_{}x{}x{}".format(*N)) + suffix
    print(f"lattice {N[0]}×{N[1]}×{N[2]} | bar {ROD:g} mm, chamfer {CHAMFER:g} mm,"
          f" muntin {MUNTIN:g} mm, pane {pane_size():.2f} mm")
    if paths:
        describe(paths)
    tm = build(args.plate)
    os.makedirs(args.out, exist_ok=True)
    for ext in ("stl", "3mf"):
        tm.export(os.path.join(args.out, f"{name}.{ext}"))
    print("saved:", os.path.join(args.out, f"{name}.stl / .3mf"))


if __name__ == "__main__":
    main()
