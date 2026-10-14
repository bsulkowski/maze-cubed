# Maze³

**English** · [Polski](README.pl.md)

The classic maze, generalised to three dimensions: cubic cells, passages in
all six directions, no privileged axis. A ball travels inside, and you turn
the cube every way to lead it from the entrance to the exit.

A space like this opens possibilities a flat maze doesn't have — for
example, the route through the maze can tie itself into a knot. In
`lab4_1` the route from entrance to exit, closed up outside the cube, forms
a trefoil.

![Maze lab4_1: model, model with routes, routes alone](images/lab4_1.png)

## Mazes

| File | Size | Route | Branches | Knot | Notes |
|---|---|---|---|---|---|
| `lab2_1` | 2×2×2, 42 mm, ~13 g | 8 of 8 cells | 0 | — | print test only |
| `lab3_1` | 3×3×3, 62 mm, ~35 g | 14 of 27 cells | 5 | — | warm-up |
| `lab4_1` | 4×4×4, 82 mm, ~77 g | 39 of 64 cells | 9 | trefoil | the main challenge |
| `lab345_1` | 3×4×5, 62×82×102 mm, ~73 g | 39 of 60 cells | 9 | trefoil | unequal sides help orientation |

Weights are for PLA. Every maze is *perfect*: every cell is reachable, there
are no loops, and there is exactly one route from the entrance to the exit.
Ready-to-print STL and 3MF files are in `models/`.

![Maze lab3_1](images/lab3_1.png)

![Maze lab345_1](images/lab345_1.png)

## How to play

Drop the ball into the entrance — in `lab2_1`, `lab3_1` and `lab4_1` it
is the opening in the bottom face and the exit is on top; in `lab345_1`
the two openings are on the opposite large 4×5 sides. Tilt, turn and flip
the cube until the ball comes out of the exit.

## Printing

- No supports. Print in the orientation from the file.
- Default dimensions are made for a 0.4 mm nozzle: frame bars 2.4 mm
  (6 lines), window grid 1.6 mm (4 lines), 0.4 mm chamfer.
- Every horizontal wall rests on diagonal braces and small pads placed
  exactly under its bridges. The longest bridges are about 6.4 mm
  centre to centre (4.8 mm clear).
- Braces are about 35° from horizontal; good part cooling helps. Their
  undersides may come out slightly rough, which doesn't affect play.
- Designed for a Bambu Lab A1 mini; all models fit its 180 mm build
  volume.

![Bridge support: brace tops sit exactly under the corners of the pad, where the bridge starts](images/bridge_support.png)

## The ball

![Ball](images/ball.png)

`ball.py` makes a truncated icosahedron (a football) of 10 mm diameter,
printed on a hexagonal face. A good range is 8–10 mm: a smaller ball gets
stuck in the 4.8 mm windows of the wall grids, while the passages let
through up to about 16.5 mm. A steel ball bearing or a bead works too.

## The knot

The route through the maze starts and ends outside the cube, so closing
it with an arc outside the cube is unambiguous and the loop has a
well-defined knot type. `tools/knot.py` finds the route, closes it, and
computes the Alexander polynomial in several random projections:

```sh
python tools/knot.py mazes/lab4_1.txt     # → trójlistnik (3₁), i.e. trefoil
```

A flat maze can't do this: a curve needs three dimensions to be knotted.

## Generator

```sh
pip install -r requirements.txt

python maze_cubed.py mazes/lab4_1.txt     # maze → models/lab4_1.stl, .3mf
python maze_cubed.py --size 4 4 4         # full lattice, no passages
python ball.py                            # ball → models/ball_10mm.stl, .3mf
python tools/knot.py mazes/lab4_1.txt     # knot type of the route
python tools/preview.py models/lab4_1.stl --paths mazes/lab4_1.txt -o images/lab4_1.png
```

The generator also checks the maze itself: whether it covers every cell,
whether it is connected and loop-free, and how many exits it has.

Code comments and console messages are in Polish.

### Path file format

A list of paths, each a list of consecutive cells `[x, y, z]`. Inner cells
have coordinates from 1 to N; 0 or N+1 means an exit to the outside. The
wall between two consecutive cells of a path is open. Branches are written
as separate paths starting from an already visited cell.

```js
pass4x = [
	[ [2, 3, 0], [2, 3, 1], [2, 4, 1], /* … */ [3, 3, 5] ],
	[ [2, 4, 2], [3, 4, 2], [3, 4, 1], [3, 3, 1] ],
	/* … */
];
```

The lattice size is inferred from the paths; it can also be given
explicitly with `--size NX NY NZ`.

### Random mazes

`tools/random_maze.py` generates perfect mazes (uniform random spanning
trees, Wilson's algorithm) and picks the layout that best fits the
criteria: the route goes in all six directions, its length is in a given
range, dead ends are longer rather than single cells, the entrance and
exit are on opposite faces, and optionally the route is (or isn't)
knotted. A given `--seed` always produces the same maze.

```sh
python tools/random_maze.py --size 2 2 2 --seed 3 --min-len 0.5 --max-len 1 -o mazes/lab2_1.txt
python tools/random_maze.py --size 3 3 3 --seed 1 --knot unknot -o mazes/lab3_1.txt
python tools/random_maze.py --size 3 4 5 --seed 1 --tries 300 --knot knotted -o mazes/lab345_1.txt
```

A random tree practically never knots its route, so `--knot knotted`
works the other way round: it samples a
strongly tangled Hamiltonian path through the whole lattice (a snake
shuffled with backbite moves), cuts out a segment between opposite faces
whose knot determinant isn't 1, and only then grows the rest of the maze
around it. `--det 5` asks for a figure-eight knot, but at this size it
practically never comes up.

`lab4_1` is the original layout; `lab2_1`, `lab3_1` and `lab345_1` were
generated with the commands above.

### Construction

![A single cell with an open side wall](images/cell.png)

- **Lattice:** square bars with chamfered edges, 20 mm between axes.
- **Walls:** a grid of square muntins dividing each window into 3 × 3
  panes, centred in the plane of the bars. Open walls have no grid.
- **Ceiling braces:** 4 per cell, diagonal in plan, from the muntin
  crossings of the ceiling to the nearest corner post. They disappear only
  together with the ceiling. Every horizontal section of a brace is a
  square aligned with the lattice (rotated 45° relative to the brace's own
  axis), and its top lies at the underside of the pad, where the bridge
  starts — exactly under the muntin crossing.
- **Knee braces:** two 45° braces under the top bar of every open side
  wall, ending under the bar above the outer muntin lines. Ceiling braces
  and knee braces meet the posts at the same height.
- **Pads:** under every closed horizontal wall, the frame of the middle
  pane extends down to the level of the bar undersides (one chamfer below
  the muntins). On the bottom face it rests on the print bed.

Bar, chamfer, muntin and cell size can be changed on the command line
(`--rod`, `--chamfer`, `--muntin`, `--edge`); the output file then gets a
suffix, e.g. `lab3_1_rod2_chamfer0.5_muntin1`. A muntin can't be wider
than the flat part of a bar (bar − 2 × chamfer).

Touching elements differ in size by a few to a few dozen micrometres
(`EPS`), so that no two faces are coplanar and no face lies on another
element's edge. This keeps the mesh watertight, with no duplicate
vertices, for any dimensions. `EPS` is deliberately not a round number, so
its small multiples never cancel out with round dimensions.

## Repository layout

| Path | Contents |
|---|---|
| `maze_cubed.py` | maze generator (STL + 3MF) |
| `ball.py` | the ball |
| `mazes/` | maze layouts (path files) |
| `models/` | ready-to-print models |
| `tools/knot.py` | knot type of the route |
| `tools/random_maze.py` | random maze in the path file format |
| `tools/preview.py`, `tools/render.py` | PNG previews |
| `images/` | previews |
