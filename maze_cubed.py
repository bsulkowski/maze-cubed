"""Maze³ — generator labiryntu 3D do druku.

Klasyczny labirynt uogólniony na trzy wymiary: sześcienne komórki
w kratownicy NX × NY × NZ, przejścia we wszystkich sześciu kierunkach,
żadnej wyróżnionej osi.

Konstrukcja:
- krawędzie: pręty o przekroju kwadratowym ROD ze ściętymi kantami CHAMFER,
  węzły narożne jako sześciany fazowane tak samo;
- każda ścianka (także wewnętrzna, wspólna dla dwóch komórek): kratka
  szprosów MUNTIN × MUNTIN dzieląca okno na DIVS × DIVS równych okienek,
  wyśrodkowana w płaszczyźnie osi prętów;
- w każdej komórce 4 wsporniki pod skrzyżowaniami szprosów sufitu,
  w rzucie biegnące po przekątnej do najbliższego narożnego pręta
  pionowego, zaczepione na wysokości górnej linii szprosów;
- pod każdą poziomą ścianką: podpórka — ramka środkowego okienka sięgająca
  w dół do poziomu spodu prętów (o grubość fazki pod szprosy); na dolnej
  ściance kostki opiera się o stół;
- labirynt: na ścieżkach z pliku ścianka między kolejnymi komórkami jest
  otwarta (bez szprosów). Wsporniki komórki znikają tylko wtedy, gdy
  otwarty jest jej sufit. Nad otwartą ścianką boczną górny pręt dostaje
  dwa zastrzały 45° od prętów pionowych (w płaszczyźnie ścianki).

Wymiar EDGE to rozstaw osi prętów (bok komórki). Zewnętrzny wymiar
bryły to N * EDGE + ROD.

Użycie:
    python maze_cubed.py mazes/lab4_1.txt          # labirynt
    python maze_cubed.py --size 4 4 4              # pełna kratownica bez przejść
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

EDGE = 20.0      # mm, bok komórki (oś do osi)
ROD = 2.0        # mm, bok kwadratowego przekroju pręta
CHAMFER = 0.5    # mm, ścięcie kantów (fazka 45°)
MUNTIN = 1.0     # mm, bok kwadratowego przekroju szprosu
DIVS = 3         # na ile części szprosy dzielą okno w każdym kierunku
EPS = 0.0047     # mm, mikro-odsunięcia, dzięki którym ścianki różnych elementów
                 # nigdy nie są współpłaszczyznowe (siatka wychodzi czysta);
                 # 5–70 µm, niewidoczne w druku. Wartość celowo „nieokrągła”:
                 # małe wielokrotności EPS nie trafiają w okrągłe wymiary w mm,
                 # więc odsunięcia nie znoszą się przypadkiem z różnicami wymiarów



def set_dims(edge=None, rod=None, chamfer=None, muntin=None):
    """Ustawia wymiary konstrukcji i przelicza wielkości pochodne."""
    global EDGE, ROD, CHAMFER, MUNTIN, h, c, H_AXIS, H_NODE, CENTERS, BRACES
    EDGE = EDGE if edge is None else edge
    ROD = ROD if rod is None else rod
    CHAMFER = CHAMFER if chamfer is None else chamfer
    MUNTIN = MUNTIN if muntin is None else muntin
    assert MUNTIN <= ROD - 2 * CHAMFER + 1e-9, "szpros szerszy niż płaska część pręta"
    h = ROD / 2
    c = CHAMFER
    # Pręty biegnące wzdłuż różnych osi różnią się grubością o EPS, a węzły
    # narożne są o kolejne EPS mniejsze: płaskie ścianki krzyżujących się
    # prętów nigdy nie leżą w jednej płaszczyźnie.
    H_AXIS = [h, h - EPS, h - 2 * EPS]
    H_NODE = h - 3 * EPS
    # osie szprosów w obrębie jednej komórki, rozstawione na równe okienka
    pane = (EDGE - ROD - (DIVS - 1) * MUNTIN) / DIVS
    CENTERS = [h + k * pane + (k - 0.5) * MUNTIN for k in range(1, DIVS)]
    BRACES = braces_spec()


# Rzeczywiste szerokości elementów cieńszych od pręta. Szpros bywa równy
# płaskiej części pręta (pręt − 2 × fazka); gdyby leżał dokładnie na jej
# krawędziach, przy niektórych wymiarach błędy zaokrągleń dają szczeliny
# w siatce. Dlatego każdy rodzaj elementu jest węższy o inną wielokrotność
# EPS niż szpros nominalny i niż płaskie ścianki prętów (0–3·EPS z każdej
# strony): żadne dwie ścianki nie leżą w jednej płaszczyźnie ani na
# krawędzi innej, niezależnie od wymiarów. Różnice to 20–70 µm.
def w_muntin():
    return MUNTIN - 9 * EPS


def w_brace():
    return MUNTIN - 11 * EPS


def w_knee():
    return MUNTIN - 13 * EPS


def w_pad():
    return MUNTIN - 15 * EPS


def pane_size():
    """Bok okienka w kratce szprosów."""
    return (EDGE - ROD - (DIVS - 1) * MUNTIN) / DIVS


# ustawiane przez configure()
N = (4, 4, 4)
SIZE = [n * EDGE for n in N]
OPEN = set()


# --- plik ze ścieżkami --------------------------------------------------------

def load_paths(fname):
    """Plik w stylu JS: `nazwa = [ [ [x, y, z], ... ], ... ];`.
    Współrzędne komórek 1..N; 0 lub N+1 oznacza wyjście na zewnątrz."""
    txt = open(fname).read().split("=", 1)[1].strip().rstrip(";")
    return json.loads(re.sub(r",(\s*\])", r"\1", txt))


def size_from_paths(paths):
    """Rozmiar kratownicy odgadnięty ze ścieżek: w każdej osi największa
    współrzędna, chyba że osiągają ją wyłącznie wyjścia na zewnątrz (końce
    ścieżek wchodzące w tę warstwę wzdłuż tej osi) — wtedy o jeden mniej.
    W razie wątpliwości rozmiar podaje się jawnie: --size NX NY NZ."""
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
    """Graf przejść: komórka -> zbiór sąsiadów (współrzędne jak w pliku)."""
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
    """Krótki raport o labiryncie: pokrycie, pętle, wyjścia."""
    g = maze_graph(paths)
    nodes = set(g)
    edges = sum(len(v) for v in g.values()) // 2
    inside = {x for x in nodes if is_inside(x)}
    exits = sorted(nodes - inside)
    all_cells = set(itertools.product(*[range(1, n + 1) for n in N]))
    # spójność
    seen, stack = set(), [next(iter(nodes))]
    while stack:
        x = stack.pop()
        if x not in seen:
            seen.add(x)
            stack.extend(g[x] - seen)
    print(f"komórek odwiedzonych: {len(inside)} z {len(all_cells)}"
          + ("" if inside == all_cells else f" (brak: {sorted(all_cells - inside)})"))
    print(f"przejść: {edges} | wyjść na zewnątrz: {len(exits)} {exits}")
    print("graf spójny:", len(seen) == len(nodes),
          "| drzewo (bez pętli):", len(seen) == len(nodes) and edges == len(nodes) - 1)


def open_faces(paths):
    """Ścianka = (oś, komórka po niższej stronie, indeksy od 0; -1 na zewnątrz)."""
    faces = set()
    for p in paths:
        for a, b in zip(p, p[1:]):
            d = [abs(x - y) for x, y in zip(a, b)]
            assert sorted(d) == [0, 0, 1], f"komórki {a} i {b} nie sąsiadują"
            axis = d.index(1)
            lo = tuple(min(x, y) - 1 for x, y in zip(a, b))
            assert all(-1 <= lo[i] < N[i] for i in range(3)), f"poza kratownicą: {a}, {b}"
            faces.add((axis, lo))
    return faces


def configure(paths=None, size=None):
    """Ustawia rozmiar kratownicy i zbiór otwartych ścianek."""
    global N, SIZE, OPEN
    if size is None:
        size = size_from_paths(paths) if paths else (4, 4, 4)
    N = tuple(size)
    SIZE = [n * EDGE for n in N]
    OPEN = open_faces(paths) if paths else set()


def face(axis, cell, upper=False):
    """Klucz ścianki komórki `cell` (indeksy od 0) prostopadłej do `axis`."""
    t = list(cell)
    if not upper:
        t[axis] -= 1
    return (axis, tuple(t))


# --- geometria ----------------------------------------------------------------

def octagon(hh):
    return [(-hh + c, -hh), (hh - c, -hh), (hh, -hh + c), (hh, hh - c),
            (hh - c, hh), (-hh + c, hh), (-hh, hh - c), (-hh, -hh + c)]


def axis_frame(axis):
    """Macierz 3×4 kładąca lokalną oś Z wzdłuż osi `axis` (obrót cykliczny)."""
    M = np.zeros((3, 4))
    a, b = (axis + 1) % 3, (axis + 2) % 3
    M[a, 0] = M[b, 1] = M[axis, 2] = 1.0
    return M


def octo_prism(axis, a0, a1, hh=None):
    hh = H_AXIS[axis] if hh is None else hh
    p = m3d.Manifold.extrude(m3d.CrossSection([octagon(hh)]), a1 - a0).translate([0, 0, a0])
    return p.transform(axis_frame(axis).tolist())


def slanted_bar(p, q, w, overrun=0.0, underrun=0.0):
    """Ukośny graniastosłup, którego każdy przekrój poziomy to kwadrat w×w
    o bokach równoległych do osi X i Y, a środki przekrojów leżą na odcinku
    p→q (p niżej niż q). Na obu końcach ścięty poziomo. Przekrój prostopadły
    do osi nie jest kwadratem — za to tam, gdzie pręt dochodzi do kraty,
    jego ślad pokrywa się z kwadratem skrzyżowania. `overrun` i `underrun`
    przedłużają górny i dolny koniec wzdłuż osi o podaną wysokość (żeby
    końce nie leżały w jednej płaszczyźnie z innymi elementami)."""
    p, q = np.asarray(p, float), np.asarray(q, float)
    d = q - p
    assert d[2] > 0
    q = q + d / d[2] * overrun
    p = p - d / d[2] * underrun
    d = q - p
    M = [[1, 0, d[0] / d[2], p[0]],
         [0, 1, d[1] / d[2], p[1]],
         [0, 0, 1, p[2]]]
    return m3d.Manifold.cube([w, w, d[2]]).translate([-w / 2, -w / 2, 0]).transform(M)


def rods_and_nodes():
    parts = []
    # pręty: ciągłe linie przez całą kratownicę
    for axis in range(3):
        a, b = (axis + 1) % 3, (axis + 2) % 3
        for i in range(N[a] + 1):
            for j in range(N[b] + 1):
                pos = [0.0] * 3
                pos[a], pos[b] = i * EDGE, j * EDGE
                parts.append(octo_prism(axis, 0, SIZE[axis]).translate(pos))
    # węzeł = część wspólna trzech krótkich prętów (fazowany sześcian);
    # potrzebny tylko w 8 narożnikach, gdzie wszystkie pręty się kończą
    node = (octo_prism(0, -h, h, H_NODE) ^ octo_prism(1, -h, h, H_NODE)
            ^ octo_prism(2, -h, h, H_NODE))
    for corner in itertools.product(*[(0, n) for n in N]):
        parts.append(node.translate([k * EDGE for k in corner]))
    return parts


def muntins():
    """Jedna kratka 2D na płaszczyznę, złożona z kratek poszczególnych
    ścianek (bez otwartych); linie szprosów przechodzą ciągle przez pręty.
    Suma liczona w 2D jest dokładna, więc nie powstają współpłaszczyznowe ścianki."""
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


def braces_spec():
    """4 wsporniki komórki: od skrzyżowania szprosów sufitu po przekątnej
    (w rzucie) do najbliższego narożnego pręta pionowego, zaczepione na
    wysokości górnej linii szprosów obniżonej o pół pręta — tak samo jak
    zastrzały przy otwartych ściankach. Ok. 35,3° od poziomu."""
    out = []
    for a in CENTERS:
        for b in CENTERS:
            cx = 0.0 if a < EDGE / 2 else EDGE
            cy = 0.0 if b < EDGE / 2 else EDGE
            # górny koniec: środek skrzyżowania na spodzie podpórki (z = −h
            # pod osią sufitu), bo tam zaczyna się most; dolny obniżony
            # o tyle samo, żeby kąt się nie zmienił
            out.append(((cx, cy, CENTERS[-1] - h), (a, b, EDGE - h)))
    return out


def cell_braces():
    """Wsporniki jako ukośne graniastosłupy o poziomym przekroju kwadratowym:
    na spodzie podpórki sufitu, gdzie zaczyna się most, ich przekrój to
    dokładnie kwadrat skrzyżowania szprosów (względem osi wspornika —
    przekrój obrócony o 45°)."""
    w = w_brace()
    return m3d.Manifold.batch_boolean([slanted_bar(p, q, w, 4 * EPS, 4 * EPS) for p, q in BRACES],
                                      m3d.OpType.Add)


def knee_braces():
    """Zastrzały pod górnym prętem każdej otwartej ścianki bocznej: od obu
    prętów pionowych (na wysokości górnej linii szprosów obniżonej o pół
    pręta) do spodu pręta górnego (nad skrajnymi liniami szprosów), pod 45°,
    w płaszczyźnie ścianki.
    Przekrój poziomy kwadratowy, jak przy wspornikach sufitu."""
    w = w_knee()
    c0, c1 = CENTERS[0], CENTERS[-1]
    out = []
    for axis, lo in OPEN:
        if axis == 2:
            continue                              # sufit/podłoga: brak pręta nad otworem
        along = 1 - axis                          # pozioma oś w płaszczyźnie ścianki
        base = [k * EDGE for k in lo]
        base[axis] += EDGE                        # płaszczyzna ścianki
        z_top = base[2] + EDGE
        for pv, ph in ((0.0, c0), (EDGE, c1)):    # (pręt pionowy, punkt na pręcie górnym)
            # górny koniec pod spodem pręta górnego (tam zaczyna się most),
            # dolny obniżony o tyle samo — kąt 45° bez zmian
            p = list(base); p[along] += pv; p[2] += c1 - h
            q = list(base); q[along] += ph; q[2] = z_top - h
            out.append(slanted_bar(p, q, w, 6 * EPS, 6 * EPS))
    return out


def cell_pad():
    """Podpórka: ramka środkowego okienka poziomej ścianki przedłużona w dół
    do poziomu spodu prętów, czyli wystająca pod szprosy o grubość fazki
    (przy szprosie równym płaskiej części pręta). Na dolnej ściance kostki
    opiera się o stół."""
    c0, c1, w = CENTERS[0], CENTERS[-1], w_pad()
    z0, z1 = -h, 0.0
    outer = m3d.Manifold.cube([c1 - c0 + w, c1 - c0 + w, z1 - z0]).translate([c0 - w / 2, c0 - w / 2, z0])
    inner = m3d.Manifold.cube([c1 - c0 - w, c1 - c0 - w, z1 - z0 + 2]).translate([c0 + w / 2, c0 + w / 2, z0 - 1])
    return outer - inner


set_dims()


def build():
    """Składa całą bryłę; zwraca trimesh ustawiony na stole (z_min = 0)."""
    parts = rods_and_nodes() + muntins()
    braces, n_braces = cell_braces(), 0
    for cell in itertools.product(*[range(n) for n in N]):
        if face(2, cell, upper=True) not in OPEN:   # wsporniki znikają tylko z sufitem
            n_braces += len(BRACES)
            parts.append(braces.translate([k * EDGE for k in cell]))
    knees = knee_braces()
    parts += knees
    pad, n_pads = cell_pad(), 0
    for i, j, k in itertools.product(range(N[0]), range(N[1]), range(N[2] + 1)):
        if face(2, (i, j, k)) not in OPEN:          # pozioma ścianka pod komórką (i, j, k)
            n_pads += 1
            parts.append(pad.translate([i * EDGE, j * EDGE, k * EDGE]))
    print(f"otwartych ścianek: {len(OPEN)} | wsporników: {n_braces} z {len(BRACES) * np.prod(N)}"
          f" | zastrzałów: {len(knees)} | podpórek: {n_pads}")

    frame = m3d.Manifold.batch_boolean(parts, m3d.OpType.Add).translate([h, h, h])
    mesh = frame.to_mesh()
    v = mesh.vert_properties[:, :3]
    _, cnt = np.unique(np.round(v, 5), axis=0, return_counts=True)
    tm = trimesh.Trimesh(vertices=v, faces=mesh.tri_verts)
    print("szczelna:", tm.is_watertight, "| zdublowane wierzchołki:", int((cnt > 1).sum()))
    print("wymiary mm:", np.round(tm.extents, 2), "| trójkątów:", len(tm.faces))
    print("objętość cm³:", round(tm.volume / 1000, 2), "| masa PLA ~g:", round(tm.volume / 1000 * 1.24, 1))
    return tm


def main():
    ap = argparse.ArgumentParser(description="Maze³ — generator labiryntu 3D do druku")
    ap.add_argument("paths", nargs="?", help="plik ze ścieżkami; bez niego powstaje pełna kratownica")
    ap.add_argument("--size", nargs=3, type=int, metavar=("NX", "NY", "NZ"),
                    help="rozmiar kratownicy (domyślnie z pliku ścieżek albo 4 4 4)")
    ap.add_argument("--out", default="models", help="katalog na pliki STL i 3MF (domyślnie: models)")
    ap.add_argument("--rod", type=float, help=f"bok przekroju pręta kraty nośnej, mm (domyślnie {ROD:g})")
    ap.add_argument("--chamfer", type=float, help=f"fazka prętów, mm (domyślnie {CHAMFER:g})")
    ap.add_argument("--muntin", type=float, help=f"bok przekroju szprosu, mm (domyślnie {MUNTIN:g})")
    ap.add_argument("--edge", type=float, help=f"bok komórki (rozstaw osi prętów), mm (domyślnie {EDGE:g})")
    args = ap.parse_args()

    defaults = dict(edge=EDGE, rod=ROD, chamfer=CHAMFER, muntin=MUNTIN)
    set_dims(args.edge, args.rod, args.chamfer, args.muntin)
    suffix = "".join(f"_{k}{v:g}" for k, v in
                     dict(edge=EDGE, rod=ROD, chamfer=CHAMFER, muntin=MUNTIN).items()
                     if v != defaults[k])

    paths = load_paths(args.paths) if args.paths else None
    configure(paths, args.size)
    name = (os.path.splitext(os.path.basename(args.paths))[0] if args.paths
            else "lattice_{}x{}x{}".format(*N)) + suffix
    print(f"kratownica {N[0]}×{N[1]}×{N[2]} | pręt {ROD:g} mm, fazka {CHAMFER:g} mm,"
          f" szpros {MUNTIN:g} mm, okienko {pane_size():.2f} mm")
    if paths:
        describe(paths)
    tm = build()
    os.makedirs(args.out, exist_ok=True)
    for ext in ("stl", "3mf"):
        tm.export(os.path.join(args.out, f"{name}.{ext}"))
    print("zapisano:", os.path.join(args.out, f"{name}.stl / .3mf"))


if __name__ == "__main__":
    main()
