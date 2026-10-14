"""PNG previews of Maze³ models (software renderer, no GPU needed).

Usage:
    python tools/preview.py models/lab4_1.stl --paths mazes/lab4_1.txt -o images/lab4_1.png
    python tools/preview.py models/lab4_1.stl --cell 2 3 4 -o images/cell.png
    python tools/preview.py models/ball_10mm.stl --ball -o images/ball.png
"""
import argparse
import os
import sys

import manifold3d as m3d
import numpy as np
import trimesh
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import maze_cubed as mc  # noqa: E402
from render import render  # noqa: E402

BLUE = np.array([0.22, 0.5, 0.82])
RED = np.array([0.9, 0.25, 0.2])


def path_tubes(paths):
    def centre(cell):
        return np.array([(x - 0.5) * mc.EDGE + mc.h for x in cell])
    parts = []
    for p in paths:
        for a, b in zip(p, p[1:]):
            parts.append(trimesh.creation.cylinder(radius=1.4, segment=[centre(a), centre(b)], sections=10))
        for cell in p:
            parts.append(trimesh.creation.icosphere(1, radius=1.9).apply_translation(centre(cell)))
    return trimesh.util.concatenate(parts)


def crop_cell(mesh, cell):
    """Cut a single cell (coordinates 1..N) out of the model."""
    M = m3d.Manifold(m3d.Mesh(vert_properties=np.asarray(mesh.vertices, np.float32),
                              tri_verts=np.asarray(mesh.faces, np.uint32)))
    lo = (np.array(cell) - 1) * mc.EDGE + mc.h - 1.2
    box = m3d.Manifold.cube([mc.EDGE + 2.4] * 3).translate(lo.tolist())
    o = (M ^ box).to_mesh()
    return trimesh.Trimesh(o.vert_properties[:, :3], o.tri_verts)


def main():
    ap = argparse.ArgumentParser(description="PNG preview of a Maze³ model")
    ap.add_argument("model")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--paths", help="overlay the maze paths from a file")
    ap.add_argument("--cell", nargs=3, type=int, help="show a single cell (coordinates 1..N)")
    ap.add_argument("--ball", action="store_true", help="colour the pentagons black")
    ap.add_argument("--size", type=int, default=700, help="side of one panel in pixels")
    args = ap.parse_args()

    m = trimesh.load(args.model)
    S = args.size
    if args.ball:
        cols = np.tile([0.92, 0.92, 0.92], (len(m.faces), 1))
        for f in m.facets:
            if len(np.unique(m.faces[f])) == 5:
                cols[f] = [0.12, 0.12, 0.12]
        panels = [render(m, 25, -55, size=S, colors=cols), render(m, -60, 30, size=S, colors=cols)]
    elif args.cell:
        t = crop_cell(m, args.cell)
        panels = [render(t, -30, 215, size=S), render(t, 10, 200, size=S)]
    elif args.paths:
        paths = mc.load_paths(args.paths)
        tubes = path_tubes(paths)
        both = trimesh.util.concatenate([m, tubes])
        cols = np.vstack([np.tile(BLUE, (len(m.faces), 1)), np.tile(RED, (len(tubes.faces), 1))])
        ctr, span = m.bounds.mean(0), m.extents.max() * 1.9
        panels = [render(m, 25, -55, size=S),
                  render(both, 25, -55, size=S, center=ctr, span=span, colors=cols),
                  render(tubes, 25, -55, size=S, center=ctr, span=span,
                         colors=np.tile(RED, (len(tubes.faces), 1)))]
    else:
        panels = [render(m, 25, -55, size=S), render(m, -35, -55, size=S)]
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    Image.fromarray(np.hstack(panels)).save(args.out)
    print("saved:", args.out)


if __name__ == "__main__":
    main()
