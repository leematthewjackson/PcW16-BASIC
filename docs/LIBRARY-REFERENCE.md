# PcW16 BASIC library reference

The libraries in `examples/lib/` are ordinary PcW16 BASIC: `INCLUDE "lib/NAME.pbas"` near the top of a program (each library once; one that needs another says so). Every name a library declares starts with its prefix, and a program's own CONSTs never clash with a library's parameters (LANGUAGE-SPEC §5.1). This page is made from each library's own opening comment by `tools/libref.py`; the code is the authority. docs/libraries/README.md shows how the graphical ones fit together; tests/test_m11_*, test_m12_* and test_m13_libraries.py test them.

## Applications

### lib/app.pbas

```text
app.pbas: what every document application repeats.
INCLUDE "lib/app.pbas" near the top of a program, before its own SUBs.

Status line
  The library declares AppStatus$ (a LABEL shows at most 24 characters,
  M5d). Put "LABEL AppStatus$" in a window, then CALL AppSay(Text$): the
  text is cut to 24 characters, so a status can never stop the program.

Unsaved changes
  CALL AppChanged after any change, CALL AppSaved after a good save;
  AppDirty tells which. FUNCTION AppMayClose() AS BOOLEAN asks
  "Unsaved changes" with Save / Discard / Cancel when AppDirty is TRUE:
  Save calls the program's own FUNCTION AppSave() AS BOOLEAN (which must
  save and return TRUE if it did); the result is TRUE when the program
  may go on (close, open another file), FALSE for Cancel or a failed save.
  A program that includes this library defines AppSave.

File errors
  FUNCTION AppError$(Code AS INTEGER) AS STRING: an IOERR code in a few
  words (LANGUAGE-SPEC §7.1 files, §5.7 TEXT, §5.9 databases).
  SUB AppFail(What$ AS STRING, Code AS INTEGER) shows "What: meaning"
  as an alert.

Names: everything here starts with App; a program must not reuse them.
```

Defines (with its internal helpers; the comment above says which are for programs):

- `SUB AppSay(Text$ AS STRING)`
- `SUB AppChanged`
- `SUB AppSaved`
- `FUNCTION AppMayClose() AS BOOLEAN`
- `FUNCTION AppError$(Code AS INTEGER) AS STRING`
- `SUB AppFail(What$ AS STRING, Code AS INTEGER)`

### lib/forms.pbas

```text
forms.pbas: reusable checks for data-entry forms.
INCLUDE "lib/forms.pbas" near the top of a program, before its own SUBs.

A form check collects the first problem only:
    CALL FormStart
    CALL FormRequire(Name$, "Name")
    CALL FormPhone(Phone$, "Phone")
    CALL FormEmail(Mail$, "E-mail")
    IF NOT FormOK() THEN
        MESSAGE FormError$
    END IF
Rules (documented in docs/libraries/forms.md):
  required  - not empty and not only spaces;
  phone     - empty, or digits with optional spaces, + ( ) -, at least
              3 digits (": a bad character", ": too short");
  e-mail    - empty, or exactly one @ with text before it and a dot with
              text on both sides after it; no spaces;
  number    - empty is refused; digits with an optional leading -,
              between Low and High.
The library declares FormError$ and the helper functions below; their
names start with Form or are listed here, so a program must not reuse
them: IsBlank, IsDigits, PadRight$, Confirm.
```

Defines (with its internal helpers; the comment above says which are for programs):

- `FUNCTION IsBlank(S$ AS STRING) AS BOOLEAN`
- `FUNCTION IsDigits(S$ AS STRING) AS BOOLEAN`
- `FUNCTION PadRight$(S$ AS STRING, N AS INTEGER) AS STRING`
- `FUNCTION Confirm(Q$ AS STRING) AS BOOLEAN`
- `SUB FormStart`
- `FUNCTION FormOK() AS BOOLEAN`
- `SUB FormFail(Why$ AS STRING)`
- `SUB FormRequire(V$ AS STRING, Label$ AS STRING)`
- `SUB FormPhone(V$ AS STRING, Label$ AS STRING)`
- `SUB FormEmail(V$ AS STRING, Label$ AS STRING)`
- `SUB FormNumber(V$ AS STRING, Label$ AS STRING, Low AS INTEGER, High AS INTEGER)`

### lib/listview.pbas

```text
listview.pbas: a list of
rows on a CANVAS, chosen with the keyboard or the mouse. INCLUDE
"lib/listview.pbas" before the program's own SUBs. Each row is drawn in
Rosanne's dialog font, normally spaced (one DRAW TEXT a column); a column
too long for its room is cut at a whole character so that it never reaches
the next column (TEXTWIDTH measures it). The chosen row is shown inverted.

The program
  - sets ListCount (rows in the list, 0 or more), ListRows (rows shown,
    each 16 pixels) and ListWidth (the canvas width) before the canvas is
    painted, and ListSel / ListTop when it wants another row chosen;
  - sets ListCols (1..8, default 1) and ListX(1..ListCols), the x where
    each column starts (ListX(1) is 2 unless set); column K runs to 4
    pixels before ListX(K + 1), the last one to 2 pixels before the edge;
  - defines FUNCTION ListCell$(I AS INTEGER, K AS INTEGER) AS STRING, the
    text of row I (1..ListCount) in column K, and SUB ListPicked, which
    runs after the chosen row changed (it may do nothing);
  - calls ListPaint from its canvas's PAINT handler (and after it changed
    the rows), ListKey() from KEYS and ListMouse from MOUSE.

Keys: Up, Down, PgUp, PgDn, Home, End move the choice; ListKey() returns
TRUE when it used the key, FALSE for any other key (the program's own).
Mouse: a press or a drag over a row chooses it. A key or a click redraws
only the two rows that change, unless the list scrolls.

State: ListSel is the chosen row (0 only when the list is empty), ListTop
the first row shown. Names: everything here starts with List.
```

Defines (with its internal helpers; the comment above says which are for programs):

- `FUNCTION ListFit$(S$ AS STRING, W AS INTEGER) AS STRING`
- `SUB ListClamp`
- `SUB ListDrawRow(I AS INTEGER)`
- `SUB ListPaint`
- `SUB ListMoveTo(I AS INTEGER)`
- `FUNCTION ListKey() AS BOOLEAN`
- `SUB ListMouse`

### lib/files.pbas

```text
files.pbas: a file name with the extension a program
needs, and a file replaced only once its new version is complete.
INCLUDE "lib/files.pbas" in a program with files. docs/libraries/files.md.

Why. A program that keeps several files under one name (FORM.DSN, a
picture FORM.PBI, a listing FORM.BAS) must never write one where another
is: a name typed with its own extension (FORM.DSN when exporting a
picture) once replaced a design with a picture (seen in XAnne). And
DB SAVE and BITMAP SAVE keep their previous version and their temporary
file as NAME.BAK and NAME.NEW, the name's extension replaced
(LANGUAGE-SPEC §5.9): FORM.DSN and FORM.PBI share FORM.BAK, so saving
the picture with BITMAP SAVE would replace the design's backup. So:
  FUNCTION SafeName(Ext$ AS STRING) AS INTEGER
      SafeOut$ (set it to the name typed first) in capitals, with any
      extension typed replaced by Ext$ (".PBI"; "" for none). 0 done,
      1 no name, 2 more than 8 characters before the dot.
  FUNCTION SafeReplace() AS INTEGER
      the file SafeOut$ deleted (if it is there) and SafeTemp$ renamed
      to it: the IOERR of that (0 done). Write the new version to
      SafeTemp$ first and call this only when it is complete; if the
      rename fails the new version is still in SafeTemp$. Give SafeTemp$
      a name of its own (its .NEW and .BAK too), e.g. "DSGNTMP.PBI", and
      refuse it for SafeOut$: the same name loses the new version (KI-99).
The names go in and out through SafeOut$ and SafeTemp$, not parameters:
a STRING parameter costs the resident block its whole capacity.
Names: everything here starts with Safe.
```

Defines (with its internal helpers; the comment above says which are for programs):

- `FUNCTION SafeName(Ext$ AS STRING) AS INTEGER`
- `FUNCTION SafeReplace() AS INTEGER`

## Graphics and interaction

### lib/geom.pbas

```text
geom.pbas: points and rectangles for graphical programs.
INCLUDE "lib/geom.pbas" near the top of a program. docs/libraries/geom.md.

A rectangle is X, Y, W, H in pixels: from X to X + W - 1 across and Y to
Y + H - 1 down. A rectangle with W or H 0 (or less) is empty: it holds no
pixel, meets nothing and is ignored by GeomUnite.

  FUNCTION GeomIn(X, Y, RX, RY, RW, RH) AS BOOLEAN
      the pixel X, Y is in the rectangle
  FUNCTION GeomMeets(AX, AY, AW, AH, BX, BY, BW, BH) AS BOOLEAN
      the two rectangles share at least one pixel
  FUNCTION GeomClamp(V, Lo, Hi) AS INTEGER
      V kept within Lo .. Hi
  SUB GeomSpan(X1, Y1, X2, Y2)
      the rectangle whose opposite corners are the pixels X1, Y1 and
      X2, Y2 (both included, in any order): a rubber band's rectangle
  SUB GeomClip(X, Y, W, H, CX, CY, CW, CH)
      the part of X, Y, W, H inside CX, CY, CW, CH; GeomW = 0 when there
      is none. GeomDX, GeomDY say how far its top-left corner moved
      (GeomX - X, GeomY - Y): to draw the visible part of a bitmap drawn
      at X, Y, use the part GeomDX, GeomDY, GeomW, GeomH of it
  SUB GeomUnite(AX, AY, AW, AH, BX, BY, BW, BH)
      the smallest rectangle holding both (an empty one is ignored)
The SUBs leave their rectangle in GeomX, GeomY, GeomW, GeomH.
Names: everything here starts with Geom.
```

Defines (with its internal helpers; the comment above says which are for programs):

- `FUNCTION GeomIn(X AS INTEGER, Y AS INTEGER, RX AS INTEGER, RY AS INTEGER, RW AS INTEGER, RH AS INTEGER) AS BOOLEAN`
- `FUNCTION GeomMeets(AX AS INTEGER, AY AS INTEGER, AW AS INTEGER, AH AS INTEGER, BX AS INTEGER, BY AS INTEGER, BW AS INTEGER, BH AS INTEGER) AS BOOLEAN`
- `FUNCTION GeomClamp(V AS INTEGER, Lo AS INTEGER, Hi AS INTEGER) AS INTEGER`
- `SUB GeomSpan(X1 AS INTEGER, Y1 AS INTEGER, X2 AS INTEGER, Y2 AS INTEGER)`
- `SUB GeomClip(X AS INTEGER, Y AS INTEGER, W AS INTEGER, H AS INTEGER, CX AS INTEGER, CY AS INTEGER, CW AS INTEGER, CH AS INTEGER)`
- `SUB GeomUnite(AX AS INTEGER, AY AS INTEGER, AW AS INTEGER, AH AS INTEGER, BX AS INTEGER, BY AS INTEGER, BW AS INTEGER, BH AS INTEGER)`

### lib/drag.pbas

```text
drag.pbas: pressing, dragging and releasing the mouse on a CANVAS,
with rubber-band feedback. INCLUDE "lib/drag.pbas" near the top of a
program with a CANVAS. docs/libraries/drag.md.

The program sets DragW, DragH to its canvas's size (once), and calls
DragMouse first thing in the canvas's MOUSE handler; it then reads:
  DragEvent  1 a press, 2 a move with the button down, 3 the release
             (0 after DragCancel, until the next press)
  DragOn     TRUE from a press to its release
  DragX0, DragY0   where the button went down
  DragX, DragY     where the pointer is now, kept inside the canvas
  DragDX, DragDY   DragX - DragX0, DragY - DragY0
  DragMoved  TRUE once the pointer has gone DragSlop (default 2) pixels or
             more from the press: a click is a press and release without
  DragEnded  TRUE on the release that ends a drag (not after DragCancel)

Feedback is drawn in XOR ink, so drawing it again erases it; each Show
first erases what was shown before. They leave DRAW INK BLACK.
  SUB DragShowBox         the rectangle from the press to now
  SUB DragShowLine        a line from the press to now
  SUB DragShowFrame(X, Y, W, H)   any outline (e.g. an object being moved
                          at its new place); clipped to the canvas
  SUB DragHide            erase what is shown
  SUB DragCancel          erase it and forget the drag (the Stop key, a
                          tool change): the release that follows is ignored
Names: everything here starts with Drag.
```

Defines (with its internal helpers; the comment above says which are for programs):

- `SUB DragMouse`
- `SUB DragFbDraw`
- `SUB DragHide`
- `SUB DragShowBox`
- `SUB DragShowLine`
- `SUB DragShowFrame(X AS INTEGER, Y AS INTEGER, W AS INTEGER, H AS INTEGER)`
- `SUB DragCancel`

### lib/handles.pbas

```text
handles.pbas: selection handles on a rectangle, and resizing by
dragging one. INCLUDE "lib/handles.pbas" near the top of a program with a
CANVAS. docs/libraries/handles.md.

Handles are small squares (HandleSize pixels, default 5) on the four
corners and the middle of each side of a rectangle, numbered clockwise:
    1 --- 2 --- 3
    8           4
    7 --- 6 --- 5
The program sets HandleCW, HandleCH to its canvas's size (once).
  SUB HandlesShow(X, Y, W, H)  draw the handles of X, Y, W, H (inverted,
                      so drawing them again erases them; clipped to the
                      canvas); first erases the ones shown before
  SUB HandlesHide     erase the handles shown
  FUNCTION HandleAt(MX, MY, X, Y, W, H) AS INTEGER
                      the handle of X, Y, W, H under the pixel MX, MY:
                      1..8, or 0 (a pixel of the rectangle itself is 0)
  SUB HandleResize(K, DX, DY, X, Y, W, H, MinW, MinH)
                      the rectangle after handle K is moved by DX, DY:
                      the sides it does not touch stay where they are,
                      and it is never smaller than MinW x MinH;
                      in HandX, HandY, HandW, HandH
  FUNCTION HandleOn AS BOOLEAN   handles are shown now
Names: everything here starts with Handle or Hand.
```

Defines (with its internal helpers; the comment above says which are for programs):

- `SUB HandlePos(K AS INTEGER, X AS INTEGER, Y AS INTEGER, W AS INTEGER, H AS INTEGER)`
- `SUB HandleFlip(K AS INTEGER)`
- `SUB HandlesFlipAll`
- `SUB HandlesHide`
- `SUB HandlesShow(X AS INTEGER, Y AS INTEGER, W AS INTEGER, H AS INTEGER)`
- `FUNCTION HandleOn AS BOOLEAN`
- `FUNCTION HandleAt(MX AS INTEGER, MY AS INTEGER, X AS INTEGER, Y AS INTEGER, W AS INTEGER, H AS INTEGER) AS INTEGER`
- `SUB HandleResize(K AS INTEGER, DX AS INTEGER, DY AS INTEGER, X AS INTEGER, Y AS INTEGER, W AS INTEGER, H AS INTEGER, MinW AS INTEGER, MinH AS INTEGER)`

### lib/scene.pbas

```text
scene.pbas: objects on a CANVAS in a stacking order, found by
pointing. INCLUDE "lib/geom.pbas" first, then "lib/scene.pbas".
docs/libraries/scene.md.

An object is a number 1..SceneN with a rectangle SceneX(I), SceneY(I),
SceneW(I), SceneH(I) (its bounds: where it can be clicked and what it may
cover). Everything else about an object (its kind, colour, text, ...)
is the program's own, in its own arrays indexed by the same number.
SceneOrder(1..SceneN) is the stacking order, back to front: the object
at SceneOrder(SceneN) is drawn last and is on top.
  SUB SceneAdd(X, Y, W, H)        a new object on top: SceneNew is its number
  SUB SceneRemove(I)              object I removed; objects above it move
                                  down one number (the program moves its
                                  own arrays the same way: SceneRemoved
                                  tells it which number went)
  FUNCTION SceneAt(X, Y) AS INTEGER   the topmost object holding X, Y (0 none)
  SUB SceneToFront(I), SUB SceneToBack(I)   restack object I
  FUNCTION SceneDepth(I) AS INTEGER  where object I is in the order (1 = back)
  SUB SceneDirty(X, Y, W, H)  add a rectangle to the area to redraw;
      SceneDirtyX, Y, W, H is the union so far (SceneDirtyW 0: nothing);
      SceneClean empties it. The program redraws its background there,
      then every object (back to front) that meets it.
At most 100 objects (500 INTEGERs: 1000 bytes of the program's 16K).
Names: everything here starts with Scene.
```

Defines (with its internal helpers; the comment above says which are for programs):

- `SUB SceneAdd(X AS INTEGER, Y AS INTEGER, W AS INTEGER, H AS INTEGER)`
- `FUNCTION SceneDepth(I AS INTEGER) AS INTEGER`
- `SUB SceneRemove(I AS INTEGER)`
- `FUNCTION SceneAt(X AS INTEGER, Y AS INTEGER) AS INTEGER`
- `SUB SceneToFront(I AS INTEGER)`
- `SUB SceneToBack(I AS INTEGER)`
- `SUB SceneClean`
- `SUB SceneDirty(X AS INTEGER, Y AS INTEGER, W AS INTEGER, H AS INTEGER)`

### lib/toolbar.pbas

```text
toolbar.pbas: an icon palette and a pattern palette on a CANVAS.
INCLUDE "lib/toolbar.pbas" near the top of a program with a CANVAS.
docs/libraries/toolbar.md.

Icons. The program keeps its icons in one BITMAP: square icons of
ToolSize pixels one under another (a strip ToolSize wide and ToolN *
ToolSize high, made with tools/pbimage.py sheet), and loads it before the
canvas is painted. It sets:
  ToolN       icons (1..24)          ToolSize   their size in pixels
  ToolX, ToolY  the palette's top-left corner on the canvas
  ToolAcross  icons a row (default ToolN: one row; 1: one column)
  ToolGap     pixels between icons (default 2)
  ToolSel     the selected icon (1..ToolN; 0 none)
  ToolOff(I)  TRUE: icon I is disabled (drawn greyed, not chosen)
  ToolKey(I)  a KEYCODE that chooses icon I (0 none)
and calls:
  SUB ToolPaint(Icons AS BITMAP)    draw every icon: the selected one
                                    inverted, disabled ones greyed
  FUNCTION ToolAt(X, Y) AS INTEGER  the icon under X, Y (0 none, and 0 for
                                    a disabled icon)
  SUB ToolPick(Icons AS BITMAP, I)  select icon I (redraws the two icons)
  FUNCTION ToolForKey(K) AS INTEGER the icon whose ToolKey is K (0 none)

Patterns. SwatchN swatches (1..9) of SwatchSize pixels at SwatchX,
SwatchY, SwatchAcross a row (default SwatchN), each filled with
SwatchShade(I) (default I - 1: the DRAW FILL shades 0 black .. 8 white,
Rosanne's own patterns); SwatchSel is the chosen one.
  SUB SwatchPaint, FUNCTION SwatchAt(X, Y) AS INTEGER, SUB SwatchPick(I)
The chosen swatch has a double frame.
Names: everything here starts with Tool or Swatch.
```

Defines (with its internal helpers; the comment above says which are for programs):

- `SUB ToolCell(I AS INTEGER)`
- `SUB ToolDraw(Icons AS BITMAP, I AS INTEGER)`
- `SUB ToolPaint(Icons AS BITMAP)`
- `FUNCTION ToolAt(X AS INTEGER, Y AS INTEGER) AS INTEGER`
- `SUB ToolPick(Icons AS BITMAP, I AS INTEGER)`
- `FUNCTION ToolForKey(K AS INTEGER) AS INTEGER`
- `SUB SwatchDefaults`
- `SUB SwatchCell(I AS INTEGER)`
- `SUB SwatchDraw(I AS INTEGER)`
- `SUB SwatchPaint`
- `FUNCTION SwatchAt(X AS INTEGER, Y AS INTEGER) AS INTEGER`
- `SUB SwatchPick(I AS INTEGER)`

## Games

### lib/sprite.pbas

```text
sprite.pbas: sprites on a CANVAS: frames from a strip, drawn
through a mask, clipped at the edges, the background put back behind
them. INCLUDE "lib/sprite.pbas" near the top of a program with a CANVAS.
docs/libraries/sprite.md.

Assets. A sprite's frames are one BITMAP, frames of W x H one under
another (tools/pbimage.py sheet), with a mask BITMAP of the same shape:
white where the sprite is drawn, black where it is transparent (the
sheet command's --mask). Frame F (0 = the first) is the part 0, F * H.

The play area is the rectangle 0, 0, SprCW, SprCH of the canvas (the
program sets both, e.g. to the canvas size). A sprite may be partly or
wholly outside it: only the part inside is drawn.

Slots. Up to 16 sprites have a slot I (1..16) the program fills:
  SprX(I), SprY(I)   the top-left corner     SprW(I), SprH(I)  the frame size
  SprF(I)            the frame               SprOn(I)          drawn now
  SUB SpriteShow(Sheet AS BITMAP, Mask AS BITMAP, I)
      draw slot I as it is now (SprOn(I) becomes TRUE)
  SUB SpriteHide(Back AS BITMAP, I)
      put back the background where slot I was drawn (from Back, a
      picture of the whole play area drawn at 0, 0), SprOn(I) FALSE
  SUB SpriteMove(Sheet AS BITMAP, Mask AS BITMAP, Back AS BITMAP, I, X, Y, F)
      hide slot I, move it to X, Y with frame F, show it
  FUNCTION SpriteHits(I, J) AS BOOLEAN     slots I and J overlap
  FUNCTION SpriteHitsRect(I, X, Y, W, H) AS BOOLEAN
Without slots:
  SUB SpriteDraw(Sheet AS BITMAP, Mask AS BITMAP, X, Y, F, W, H)
  SUB SpriteDrawOpaque(Sheet AS BITMAP, X, Y, F, W, H)  (no mask)
  SUB SpriteBack(Back AS BITMAP, X, Y, W, H)   that part of the background
Overlapping sprites: hide every one that moves, then show them all again,
back to front. Names: everything here starts with Sprite or Spr.
```

Defines (with its internal helpers; the comment above says which are for programs):

- `SUB SpriteClip(X AS INTEGER, Y AS INTEGER, W AS INTEGER, H AS INTEGER)`
- `SUB SpriteDraw(Sheet AS BITMAP, Mask AS BITMAP, X AS INTEGER, Y AS INTEGER, F AS INTEGER, W AS INTEGER, H AS INTEGER)`
- `SUB SpriteDrawOpaque(Sheet AS BITMAP, X AS INTEGER, Y AS INTEGER, F AS INTEGER, W AS INTEGER, H AS INTEGER)`
- `SUB SpriteBack(Back AS BITMAP, X AS INTEGER, Y AS INTEGER, W AS INTEGER, H AS INTEGER)`
- `SUB SpriteShow(Sheet AS BITMAP, Mask AS BITMAP, I AS INTEGER)`
- `SUB SpriteHide(Back AS BITMAP, I AS INTEGER)`
- `SUB SpriteMove(Sheet AS BITMAP, Mask AS BITMAP, Back AS BITMAP, I AS INTEGER, X AS INTEGER, Y AS INTEGER, F AS INTEGER)`
- `FUNCTION SpriteHitsRect(I AS INTEGER, X AS INTEGER, Y AS INTEGER, W AS INTEGER, H AS INTEGER) AS BOOLEAN`
- `FUNCTION SpriteHits(I AS INTEGER, J AS INTEGER) AS BOOLEAN`

### lib/keys.pbas

```text
keys.pbas: names for keys. INCLUDE "lib/keys.pbas" near the top of
a program. docs/libraries/keys.md, LANGUAGE-SPEC §5.15.

Two kinds of number name a key:
- KEYDOWN(code) tells whether a key is held down now. Its codes are the
  numbers Rosanne's keyboard interrupt keeps a key's state under (PCW045.SYS
  block 6 #6A6B): a key's PS/2 set-2 scan code, except the keys that send
  an #E0 prefix, which get a number of their own from the table at #6A31.
  They are the SC_ names below (owner, XAnne SPRPROBE: Left 99, Right 100,
  Up 101, Down 98, Space 41, A 28). A held key is how a game moves while
  the key is down; several keys may be down at once.
- KEYCODE, in a canvas's KEYS handler, is the character a key press
  gives (ROSAN283 Appendix A). Those are the KC_ names. A key held down
  repeats at the keyboard's own rate, so KEYS is right for typing and
  commands, not for steady movement.
The cursor keys and the keypad's 8, 2, 4, 6 have different SC_ codes
(SC_UP and SC_KP8 and so on); KC_UP is the character of both.
  FUNCTION KeyAxis(Minus, Plus) AS INTEGER   -1 while only the Minus key
      is down, 1 while only the Plus key is, else 0 (scan codes)
Names: SC_ and KC_ constants, KeyAxis.
```

Defines (with its internal helpers; the comment above says which are for programs):

- `FUNCTION KeyAxis(Minus AS INTEGER, Plus AS INTEGER) AS INTEGER`

### lib/pace.pbas

```text
pace.pbas: steps of real time for animation and games,
however often the TIMER comes. INCLUDE "lib/pace.pbas" near the top of a
program with a TIMER. docs/libraries/pace.md, LANGUAGE-SPEC §5.15.

A TIMER's handler runs are not a count of time. A handler can take
longer than its interval; one that falls behind is not run again to catch
up; and a Rosanne timer (EVERY n seconds, or more than 240 TICKS) posts
one event however many intervals have passed (PCW045.SYS block 6 #6C4C,
#6958; static), and in XAnne stopped once a second (measured).
A program that moves things a fixed amount an event slows down as much.
Instead, count the time that has passed (CLOCKTICKS, in 1/16 s) and do as
many steps of a fixed length as it covers, then draw once:

  SUB PaceStart(StepTicks AS INTEGER, MaxSteps AS INTEGER)
      steps of StepTicks sixteenths of a second; at most MaxSteps at once
      (time beyond that is dropped and counted in PaceLost: after a long
      stall the game slows down for a moment instead of leaping ahead)
  FUNCTION PaceSteps() AS INTEGER
      the steps due since the last call (0..MaxSteps); call it once in
      each TIMER handler, do that many steps, and draw if it is not 0
PaceStart again after a pause, so the time paused is not caught up.
Counters since PaceStart (each stops at 30000): PaceTotal steps done,
PaceCalls calls of PaceSteps that did steps (the frames drawn), PaceLost
steps dropped by MaxSteps. The clock is read within the minute (0..959):
a call more than half a minute after the last one, or a clock that went
back, counts no time. Names: everything here starts with Pace.
```

Defines (with its internal helpers; the comment above says which are for programs):

- `SUB PaceStart(StepTicks AS INTEGER, MaxSteps AS INTEGER)`
- `FUNCTION PaceAdd(C AS INTEGER, N AS INTEGER) AS INTEGER`
- `FUNCTION PaceSteps() AS INTEGER`

## Charts and printing

### lib/chart.pbas

```text
chart.pbas: bar and line charts on the canvas.
INCLUDE "lib/chart.pbas" near the top of a program with a CANVAS.

Data
  ChartN values ChartV(1..ChartN) (0 to 20000) with labels ChartL$(i),
  at most 12. Set them, then CALL ChartBars or ChartLines.

Drawing (inside the rectangle X, Y, W, H of the canvas; W at least 120,
H at least 80; the rectangle is cleared first)
  SUB ChartBars(X, Y, W, H)    a bar a value, the value above its bar
  SUB ChartLines(X, Y, W, H)   the values joined by lines, a dot at each
Both draw a scale on the left from 0 to ChartTop, a "nice" number (1, 2
or 5 times a power of ten, at least the largest value: FUNCTION
ChartNiceTop), divided into ChartDiv steps, and the labels under the
plot. A label too wide for its slot is shown shortened, ending in "."
(the whole label is the program's to show elsewhere, e.g. in a table).

Numbers
  FUNCTION ChartScale(V, Size) AS INTEGER: V of ChartTop as a length of
  Size pixels, rounded to the nearest (exact: done in REAL arithmetic, so
  no product overflows). A bar of value V is ChartScale(V, plot height)
  pixels high. ChartSelected (0 none) is drawn in a darker shade.

Names: everything here starts with Chart; a program must not reuse them.
```

Defines (with its internal helpers; the comment above says which are for programs):

- `FUNCTION ChartNiceTop(Max AS INTEGER) AS INTEGER`
- `FUNCTION ChartScale(V AS INTEGER, Size AS INTEGER) AS INTEGER`
- `SUB ChartFrame(X AS INTEGER, Y AS INTEGER, W AS INTEGER, H AS INTEGER)`
- `SUB ChartLabel(I AS INTEGER)`
- `SUB ChartBars(X AS INTEGER, Y AS INTEGER, W AS INTEGER, H AS INTEGER)`
- `SUB ChartLines(X AS INTEGER, Y AS INTEGER, W AS INTEGER, H AS INTEGER)`

### lib/chartprt.pbas

```text
chartprt.pbas: the bar chart of lib/chart.pbas on a printed
page (LANGUAGE-SPEC §5.13). INCLUDE "lib/chart.pbas" first, then this.

  SUB ChartPrintBars(X, Y, W, H)   in points, on the open page (PAGE NEW):
                                   the scale, the bars, their values and
                                   labels, as ChartBars draws them
The labels and values are printed in the page's current font (8 or 10
points suit a chart). A line chart is not offered: a printed line is
horizontal or vertical only (Rosanne's meta-file has no sloped line).
Names: everything here starts with ChartPrint.
```

Defines (with its internal helpers; the comment above says which are for programs):

- `SUB ChartPrintBars(X AS INTEGER, Y AS INTEGER, W AS INTEGER, H AS INTEGER)`
