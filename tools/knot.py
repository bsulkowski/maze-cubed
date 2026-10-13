"""Typ węzła drogi przez labirynt Maze³.

Droga od wejścia do wyjścia zaczyna się i kończy na zewnątrz kostki, więc
domknięcie jej łukiem poza kostką jest jednoznaczne, a typ węzła dobrze
określony. Skrypt:
1. znajduje drogę między dwoma wyjściami w grafie przejść,
2. domyka ją: z każdego wyjścia prosto na zewnątrz, potem po dużym okręgu
   daleko od kostki,
3. liczy wielomian Alexandera (macierz Alexandera z diagramu) w kilku
   losowych rzutach.

Δ(t) = 1 — niewęzeł albo węzeł o trywialnym wielomianie (co najmniej
11 skrzyżowań); t² − t + 1 — trójlistnik; t² − 3t + 1 — ósemka.

Użycie:
    python tools/knot.py mazes/lab4_1.txt
"""
import argparse
import os
import sys
from collections import deque

import numpy as np
import sympy as sp

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import maze_cubed as mc  # noqa: E402

KNOWN = {"1": "niewęzeł (albo węzeł o trywialnym wielomianie Alexandera)",
         "t**2 - t + 1": "trójlistnik (3₁)",
         "t**2 - 3*t + 1": "ósemka (4₁)",
         "t**4 - t**3 + t**2 - t + 1": "węzeł 5₁",
         "2*t**2 - 3*t + 2": "węzeł 5₂"}


def solution_path(paths):
    """Droga między dwoma wyjściami na zewnątrz (BFS w grafie przejść)."""
    g = mc.maze_graph(paths)
    exits = [x for x in g if not mc.is_inside(x)]
    if len(exits) != 2:
        sys.exit(f"oczekiwane dokładnie 2 wyjścia na zewnątrz, jest {len(exits)}: {exits}")
    start, goal = exits
    prev, queue = {start: None}, deque([start])
    while queue:
        x = queue.popleft()
        for y in g[x]:
            if y not in prev:
                prev[y] = x
                queue.append(y)
    if goal not in prev:
        sys.exit("wyjścia nie są połączone")
    route, x = [], goal
    while x is not None:
        route.append(np.array(x, float))
        x = prev[x]
    return route[::-1]


def close_outside(route):
    """Domknięcie drogi łukiem daleko poza kostką."""
    center = (np.array(mc.N, float) + 1) / 2
    R = 4 * max(mc.N)

    def outward(end, inner):
        d = end - inner                        # kierunek wyjścia z kostki
        return end + d * R

    a_far, b_far = outward(route[-1], route[-2]), outward(route[0], route[1])
    u, v = a_far - center, b_far - center
    u, v = u / np.linalg.norm(u), v / np.linalg.norm(v)
    # okrąg wielki od u do v (dla kierunków przeciwnych — przez dowolny prostopadły)
    w = v - np.dot(u, v) * u
    if np.linalg.norm(w) < 1e-9:
        w = np.cross(u, [1, 0, 0] if abs(u[0]) < 0.9 else [0, 1, 0])
    w = w / np.linalg.norm(w)
    ang = np.arccos(np.clip(np.dot(u, v), -1, 1))
    if ang < 1e-9:
        ang = 0.0
    arc = [center + 2 * R * (np.cos(s) * u + np.sin(s) * w) for s in np.linspace(0, ang, 24)]
    return np.array(list(route) + [a_far] + arc + [b_far])


def alexander(P, seed):
    """Wielomian Alexandera zamkniętej łamanej P w losowym rzucie."""
    rng = np.random.default_rng(seed)
    q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    Q = P @ q.T                                # losowy obrót -> rzut na (x, y), wysokość z
    n = len(Q)
    segs = [(Q[i], Q[(i + 1) % n]) for i in range(n)]
    cr = []                                    # (odc. nad, t nad, odc. pod, t pod, znak)
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            p, r = segs[i][0][:2], segs[i][1][:2] - segs[i][0][:2]
            s, d = segs[j][0][:2], segs[j][1][:2] - segs[j][0][:2]
            den = r[0] * d[1] - r[1] * d[0]
            if abs(den) < 1e-12:
                continue
            t = ((s - p)[0] * d[1] - (s - p)[1] * d[0]) / den
            u = ((s - p)[0] * r[1] - (s - p)[1] * r[0]) / den
            if 0 < t < 1 and 0 < u < 1:
                zi = segs[i][0][2] + t * (segs[i][1][2] - segs[i][0][2])
                zj = segs[j][0][2] + u * (segs[j][1][2] - segs[j][0][2])
                if zi > zj:
                    o, to, un, tu, vo, vu = i, t, j, u, r, d
                else:
                    o, to, un, tu, vo, vu = j, u, i, t, d, r
                sign = 1 if (vo[0] * vu[1] - vo[1] * vu[0]) < 0 else -1
                cr.append((o, to, un, tu, sign))
    m = len(cr)
    if m == 0:
        return sp.Integer(1), 0
    # łuki diagramu: krzywa cięta w miejscach przejść dołem
    unders = sorted(range(m), key=lambda k: cr[k][2] + cr[k][3])
    pos_u = [cr[k][2] + cr[k][3] for k in unders]
    T = sp.symbols("t")
    M = sp.zeros(m, m)
    for row, k in enumerate(unders):
        o, to, _, _, s = cr[k]
        over_arc = np.searchsorted(pos_u, o + to) % m
        tt = T if s > 0 else 1 / T
        M[row, row] += tt                      # łuk kończący się w tym skrzyżowaniu
        M[row, (row + 1) % m] += -1            # łuk zaczynający się za nim
        M[row, over_arc] += 1 - tt
    D = sp.factor(sp.simplify(M[1:, 1:].det()))
    coeffs = sp.Poly(sp.numer(sp.together(D)), T).all_coeffs()
    while coeffs and coeffs[-1] == 0:
        coeffs.pop()
    poly = sp.Poly(coeffs, T).as_expr()
    if sp.Poly(poly, T).LC() < 0:
        poly = -poly
    return sp.expand(poly), m


def main():
    ap = argparse.ArgumentParser(description="Typ węzła drogi przez labirynt Maze³")
    ap.add_argument("paths", help="plik ze ścieżkami labiryntu")
    ap.add_argument("--size", nargs=3, type=int, metavar=("NX", "NY", "NZ"))
    ap.add_argument("--projections", type=int, default=4)
    args = ap.parse_args()

    paths = mc.load_paths(args.paths)
    mc.configure(paths, args.size)
    route = solution_path(paths)
    print(f"droga: {len(route) - 2} komórek, od {tuple(map(int, route[0]))} do {tuple(map(int, route[-1]))}")
    P = close_outside(route)
    results = set()
    for seed in range(args.projections):
        poly, m = alexander(P, seed)
        results.add(str(poly))
        print(f"rzut {seed}: skrzyżowań {m:3d}  Δ(t) = {poly}   |Δ(−1)| = {abs(poly.subs('t', -1))}")
    if len(results) == 1:
        key = results.pop()
        print("wynik:", KNOWN.get(key, f"Δ(t) = {key} — sprawdź w tabeli węzłów"))
    else:
        print("UWAGA: rzuty dały różne wyniki — błąd w obliczeniach")


if __name__ == "__main__":
    main()
