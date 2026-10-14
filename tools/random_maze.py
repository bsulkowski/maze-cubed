"""Random Maze³ maze in the path file format.

A perfect maze (a spanning tree: every cell reachable, no loops) with two
exits to the outside. Out of many random draws, the layout that best fits
the criteria is chosen:
- the route from entrance to exit goes in all six directions
  (you have to turn the cube every way),
- the route length is within a given range,
- dead ends are longer rather than single cells,
- entrance and exit are on opposite faces,
- optionally: the route is (or isn't) knotted. A random tree practically
  never knots its route, so in --knot knotted mode the order is reversed:
  a random Hamiltonian path (a snake shuffled with "backbite" moves) is
  strongly tangled; a segment of it between opposite faces whose knot
  determinant isn't 1 becomes the route, and the tree grows from it.

The result is always reproducible for a given --seed.

Usage:
    python tools/random_maze.py --size 3 3 3 --seed 1 --knot unknot -o mazes/lab3_1.txt
"""
import argparse
import itertools
import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import maze_cubed as mc  # noqa: E402

DIRS = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]


def add(a, d):
    return tuple(x + y for x, y in zip(a, d))


def wilson_tree(cells, rng, route=None):
    """Uniform random spanning tree (Wilson's algorithm); if a route (a list
    of adjacent cells) is given, the tree grows from it."""
    cells = list(cells)
    adj = {x: set() for x in cells}
    if route:
        in_tree = set(route)
        for a, b in zip(route, route[1:]):
            adj[a].add(b)
            adj[b].add(a)
    else:
        in_tree = {cells[0]}
    cellset = set(cells)
    for start in cells:
        if start in in_tree:
            continue
        walk = {}                       # loop-erased random walk
        x = start
        while x not in in_tree:
            nbrs = [add(x, d) for d in DIRS if add(x, d) in cellset]
            walk[x] = rng.choice(nbrs)
            x = walk[x]
        x = start
        while x not in in_tree:
            adj[x].add(walk[x])
            adj[walk[x]].add(x)
            in_tree.add(x)
            x = walk[x]
    return adj


def tree_path(adj, a, b):
    prev, stack = {a: None}, [a]
    while stack:
        x = stack.pop()
        for y in adj[x]:
            if y not in prev:
                prev[y] = x
                stack.append(y)
    route, x = [], b
    while x is not None:
        route.append(x)
        x = prev[x]
    return route[::-1]


def snake(N):
    """Hamiltonian path through all cells (a snake) — the starting point."""
    nx, ny, nz = N
    path = []
    for z in range(1, nz + 1):
        layer = []
        for y in range(1, ny + 1):
            row = [(x, y, z) for x in range(1, nx + 1)]
            layer += row if y % 2 else row[::-1]
        path += layer if z % 2 else layer[::-1]
    return path


def backbite(path, N, rng, steps):
    """"Backbite" moves: random transformations of a Hamiltonian path that
    keep it Hamiltonian and, over time, shuffle it thoroughly."""
    inside = lambda x: all(1 <= v <= n for v, n in zip(x, N))
    pos = {x: i for i, x in enumerate(path)}
    for _ in range(steps):
        if rng.random() < 0.5:
            path.reverse()
            pos = {x: i for i, x in enumerate(path)}
        end = path[-1]
        y = add(end, rng.choice(DIRS))
        if not inside(y) or y == path[-2]:
            continue
        i = pos[y]
        path[i + 1:] = path[i + 1:][::-1]
        for k in range(i + 1, len(path)):
            pos[path[k]] = k
    return path


def knotted_routes(path, N, rng, args, samples):
    """Random segments of the Hamiltonian path as entrance-to-exit routes."""
    inside = lambda x: all(1 <= v <= n for v, n in zip(x, N))
    total = len(path)
    lo, hi = int(args.min_len * total), int(args.max_len * total)
    for _ in range(samples):
        L = rng.randint(lo, hi)
        i = rng.randrange(0, total - L + 1)
        seg = path[i:i + L]
        a_out = [d for d in DIRS if not inside(add(seg[0], d))]
        b_out = [d for d in DIRS if not inside(add(seg[-1], d))]
        pairs = [(da, db) for da in a_out for db in b_out
                 if not args.opposite or db == tuple(-v for v in da)]
        if not pairs:
            continue
        da, db = rng.choice(pairs)
        yield [add(seg[0], da)] + seg + [add(seg[-1], db)]


def boundary_exits(N):
    """(boundary cell, outside cell) for every wall facing the outside."""
    out = []
    for cell in itertools.product(*[range(1, n + 1) for n in N]):
        for d in DIRS:
            o = add(cell, d)
            if not all(1 <= x <= n for x, n in zip(o, N)):
                out.append((cell, o, d))
    return out


def to_paths(adj, route):
    """Path file layout: the route first, then the branches, each starting
    from an already visited cell; longest branches first."""
    visited = set(route)
    paths = [list(route)]
    queue = [x for x in route if x in adj]
    while queue:
        x = queue.pop(0)
        for y in sorted(adj[x] - visited, key=lambda y: -depth(adj, y, x)):
            if y in visited:
                continue
            branch, prev, cur = [x], x, y
            while True:                 # follow the longest branch to a leaf
                branch.append(cur)
                visited.add(cur)
                nxt = [z for z in adj[cur] if z != prev and z not in visited]
                if not nxt:
                    break
                nxt.sort(key=lambda z: -depth(adj, z, cur))
                prev, cur = cur, nxt[0]
            paths.append(branch)
            queue.extend(branch[1:])
    return paths


def depth(adj, x, parent):
    return 1 + max((depth(adj, y, x) for y in adj[x] if y != parent), default=0)


def dead_ends(adj, route):
    """Lengths of the dead ends (branches leaving the route)."""
    on = set(route)
    return [depth(adj, y, x) for x in route if x in adj for y in adj[x] if y not in on]


def score(adj, route, N, args):
    inner = route[1:-1]
    moves = {tuple(b - a for a, b in zip(p, q)) for p, q in zip(route, route[1:])}
    if len(moves) < 6:
        return None
    total = len(adj)
    if not (args.min_len * total <= len(inner) <= args.max_len * total):
        return None
    axis_in = next(i for i in range(3) if not 1 <= route[0][i] <= N[i])
    axis_out = next(i for i in range(3) if not 1 <= route[-1][i] <= N[i])
    if args.opposite and not (axis_in == axis_out and route[0][axis_in] != route[-1][axis_out]):
        return None
    de = dead_ends(adj, inner)
    s = sum(min(L, 4) for L in de) - 2 * sum(1 for L in de if L == 1)
    s += len(inner) * 0.5
    return s


def main():
    ap = argparse.ArgumentParser(description="Random Maze³ maze")
    ap.add_argument("--size", nargs=3, type=int, default=[3, 3, 3], metavar=("NX", "NY", "NZ"))
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--tries", type=int, default=3000)
    ap.add_argument("--min-len", type=float, default=0.4, help="min. route length (fraction of cells)")
    ap.add_argument("--max-len", type=float, default=0.65, help="max. route length (fraction of cells)")
    ap.add_argument("--opposite", action=argparse.BooleanOptionalAction, default=True,
                    help="entrance and exit on opposite faces")
    ap.add_argument("--knot", choices=["any", "unknot", "knotted"], default="any",
                    help="knotted: a knotted route is drawn first, then the rest of the tree")
    ap.add_argument("--det", type=int, default=None,
                    help="(knotted) required knot determinant, e.g. 3 = trefoil, 5 = figure-eight")
    ap.add_argument("--mix", type=int, default=400,
                    help="(knotted) shuffling moves of the Hamiltonian path between tries")
    ap.add_argument("--name", default=None, help="variable name in the file")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()

    N = tuple(args.size)
    mc.configure(None, N)
    cells = list(itertools.product(*[range(1, n + 1) for n in N]))
    exits = boundary_exits(N)
    rng = random.Random(args.seed)
    best = None
    import numpy as np
    import knot
    ham = backbite(snake(N), N, rng, 20 * len(cells))
    for _ in range(args.tries):
        if args.knot == "knotted":
            ham = backbite(ham, N, rng, args.mix)
            found = None
            for route in knotted_routes(ham, N, rng, args, 30):
                moves = {tuple(b - a for a, b in zip(p, q)) for p, q in zip(route, route[1:])}
                if len(moves) < 6:
                    continue
                det = knot.determinant(knot.close_outside([np.array(x, float) for x in route]))
                if det != 1 and (args.det is None or det == args.det):
                    found = route            # determinant ≠ 1: certainly knotted
                    break
            if not found:
                continue
            route = found
            adj = wilson_tree(cells, rng, route[1:-1])
        else:
            adj = wilson_tree(cells, rng)
            (ca, oa, _), (cb, ob, _) = rng.sample(exits, 2)
            if ca == cb:
                continue
            route = [oa] + tree_path(adj, ca, cb) + [ob]
        s = score(adj, route, N, args)
        if s is None or (best and s <= best[0]):
            continue
        if args.knot == "unknot":
            poly, _ = knot.alexander(knot.close_outside([np.array(x, float) for x in route]), 0)
            if str(poly) != "1":
                continue
        best = (s, adj, route)
    if not best:
        sys.exit("no layout meeting the criteria was found")
    _, adj, route = best
    adj = {k: set(v) for k, v in adj.items()}
    adj.setdefault(route[0], set()).add(route[1]); adj[route[1]].add(route[0])
    adj.setdefault(route[-1], set()).add(route[-2]); adj[route[-2]].add(route[-1])
    paths = to_paths(adj, route)

    name = args.name or "pass{}x".format("x".join(map(str, N)) if len(set(N)) > 1 else N[0])
    lines = [f"{name} = ["]
    for k, p in enumerate(paths):
        lines.append("\t[" if k == 0 else "\t], [")
        lines += [f"\t\t[{x}, {y}, {z}]," for x, y, z in p]
    lines += ["\t]", "];", ""]
    with open(args.out, "w") as f:
        f.write("\n".join(lines))
    de = dead_ends(adj, route)
    print(f"saved: {args.out}")
    print(f"route: {len(route) - 2} of {len(cells)} cells, from {route[0]} to {route[-1]}")
    print(f"dead ends (lengths): {sorted(de, reverse=True)}")


if __name__ == "__main__":
    main()
