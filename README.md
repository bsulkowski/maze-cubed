# Maze³

Klasyczny labirynt, uogólniony na trzy wymiary: sześcienne komórki,
przejścia we wszystkich sześciu kierunkach, żadnej wyróżnionej osi.
Kostkę obraca się na wszystkie strony, prowadząc w środku kulkę.

Taka przestrzeń otwiera możliwości, których płaski labirynt nie ma — na
przykład droga przez labirynt może zawiązać się w węzeł. W labiryncie
`lab4_1` droga od wejścia do wyjścia, domknięta na zewnątrz kostki, tworzy
trójlistnik.

![Labirynt lab4_1: model, model z drogami, same drogi](images/lab4_1.png)

## Zawartość

| Ścieżka | Co to jest |
|---|---|
| `maze_cubed.py` | generator labiryntu (STL + 3MF) |
| `ball.py` | piłka do labiryntu: dwudziestościan ścięty |
| `mazes/` | układy labiryntów (pliki ze ścieżkami) |
| `models/` | gotowe modele do druku |
| `tools/knot.py` | typ węzła drogi przez labirynt |
| `tools/preview.py`, `tools/render.py` | podglądy PNG |
| `images/` | podglądy |

## Użycie

```sh
pip install -r requirements.txt

python maze_cubed.py mazes/lab4_1.txt     # labirynt → models/lab4_1.stl, .3mf
python maze_cubed.py --size 4 4 4         # pełna kratownica bez przejść
python ball.py                            # piłka 10 mm → models/ball_10mm.stl, .3mf
python tools/knot.py mazes/lab4_1.txt     # typ węzła drogi
```

Generator sprawdza też sam labirynt: czy obejmuje wszystkie komórki, czy
jest spójny i bez pętli i ile ma wyjść na zewnątrz.

## Format pliku ze ścieżkami

Lista ścieżek, każda jako lista kolejnych komórek `[x, y, z]`. Komórki
wewnątrz mają współrzędne od 1 do N; 0 albo N+1 oznacza wyjście na
zewnątrz. Między dwiema kolejnymi komórkami ścieżki ścianka jest otwarta.
Odgałęzienia zapisuje się jako osobne ścieżki, zaczynające się w komórce
już odwiedzonej.

```js
pass4x = [
	[ [2, 3, 0], [2, 3, 1], [2, 4, 1], /* … */ [3, 3, 5] ],
	[ [2, 4, 2], [3, 4, 2], [3, 4, 1], [3, 3, 1] ],
	/* … */
];
```

Rozmiar kratownicy jest odgadywany ze ścieżek; można go też podać jawnie:
`--size NX NY NZ`.

## Konstrukcja

![Pojedyncza komórka z otwartą ścianką](images/cell.png)

- **Kratownica:** pręty 2 × 2 mm z fazką 0,5 mm, rozstaw osi 20 mm.
  Labirynt 4×4×4 ma 82 mm boku.
- **Ścianki:** kratka szprosów 1 × 1 mm dzieląca każde okno na 3 × 3
  okienka (5,33 mm), wyśrodkowana w płaszczyźnie prętów. Na przejściach
  szprosów nie ma.
- **Wsporniki sufitu:** 4 w każdej komórce, w rzucie po przekątnej, od
  skrzyżowań szprosów sufitu do narożnych prętów pionowych, zaczepione na
  wysokości górnej linii szprosów. Znikają tylko razem z sufitem.
- **Zastrzały:** nad każdą otwartą ścianką boczną dwa zastrzały 45°
  podpierają górny pręt, na tej samej wysokości co wsporniki.
- **Oparcie:** w dolnej warstwie ramka środkowego okienka podłogi sięga
  stołu.

Wymiary są parametrami na początku `maze_cubed.py`. Elementy, które się
stykają, różnią się grubością o kilka mikrometrów (`EPS`), żeby żadne ich
ścianki nie były współpłaszczyznowe — dzięki temu siatka jest zawsze
szczelna i bez zdublowanych wierzchołków.

## Druk

Model drukuje się bez podpór, w orientacji z pliku. Najdłuższe mosty mają
ok. 5,3 mm. Wsporniki sufitu są nachylone ok. 35° od poziomu — przy dobrym
chłodzeniu wychodzą, ale ich spód może być mniej równy.

## Piłka

![Piłka](images/ball.png)

Dwudziestościan ścięty o średnicy 10 mm (krawędź 2 mm), do druku na
sześciokątnej ściance. Rozsądny zakres to 8–10 mm: mniejsza kulka klinuje
się w okienkach podłogi, a otwory ze zastrzałami przepuszczają ok. 17 mm.
Średnicę zmienia `--diameter`.
