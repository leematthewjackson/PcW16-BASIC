# Tutorial 3: a sprite that runs and jumps

Games need three things that forms do not:
- something that happens **on time**, whether or not a key is pressed;
- keys that are **held** down;
- pictures that **move** without leaving a trail.

This tutorial makes a small figure that runs while Left or Right is held, and jumps when Space is pressed.

*Evidence:* **Tested in XAnne.** The project owner ran T3HOP in XAnne (Rosanne 1.12) and recorded that it runs, moves, jumps and lands by itself. The test suite also runs it on the project's simulator (`tests/test_m13_tutorials.py`): five steps with Right held move the figure from x 20 to x 40, and three steps of a jump raise it from y 128 to y 98, whether the timer runs once per step or once for all three. It has not been tested on a real PcW16.

## The sprite

`examples/assets/tutorial-hero.png` holds three 16 × 16 frames: standing, a step, and jumping. Its transparent pixels are where the background shows through. Convert it with a mask:

```sh
python3 pcw16basic image sheet examples/assets/tutorial-hero.png T3HERO.PBI --frame 16,16 --mask T3HEROM.PBI
```

```text
T3HERO.PBI: 3 frames of 16 x 16, a 16 x 48 strip; frame k is the part 0, k * 16, 16, 16
T3HEROM.PBI: the mask strip
```

- `T3HERO.PBI` holds the frames one under the other.
- `T3HEROM.PBI` is the mask, white where the figure is drawn.

`BITMAP MASK` draws a picture through its mask, and `lib/sprite.pbas` does that for you ([manual/13-bitmaps-and-sprites.md](manual/13-bitmaps-and-sprites.md)). The same two files are prebuilt in `programs/`.

## The program

The program is `examples/tutorial/t3_hop.pbas`:

<!-- file: examples/tutorial/t3_hop.pbas -->
```basic
' Tutorial 3: a sprite that runs while a key is held and jumps.
INCLUDE "../lib/geom.pbas"
INCLUDE "../lib/sprite.pbas"
INCLUDE "../lib/keys.pbas"
INCLUDE "../lib/pace.pbas"

CONST FLOOR = 128
DIM Hero AS BITMAP * 16, 48
DIM HeroM AS BITMAP * 16, 48
DIM Back AS BITMAP * 320, 160
DIM Status$ AS STRING * 24
DIM VY AS INTEGER
DIM Ready AS BOOLEAN

WINDOW Main, "HOP", LARGE
LABEL Status$
CANVAS 320, 160, PAINT Paint, KEYS Keys
BUTTON "Quit", Quit
TIMER Update, EVERY 2 TICKS

SUB Paint
    IF NOT Ready THEN
        DRAW CLEAR
        DRAW FILL 0, FLOOR + 16, 320, 160 - FLOOR - 16, 4
        BITMAP GET Back, 0, 0, 320, 160
        Ready = TRUE
    END IF
    BITMAP PUT Back, 0, 0
    CALL SpriteShow(Hero, HeroM, 1)
END SUB

SUB Update
    LOCAL N AS INTEGER
    LOCAL X AS INTEGER
    LOCAL Y AS INTEGER
    LOCAL D AS INTEGER
    IF NOT Ready THEN
        EXIT SUB
    END IF
    N = PaceSteps()
    IF N = 0 THEN
        EXIT SUB
    END IF
    X = SprX(1)
    Y = SprY(1)
    WHILE N > 0
        D = KeyAxis(SC_LEFT, SC_RIGHT)
        X = GeomClamp(X + 4 * D, 0, 320 - 16)
        IF KEYDOWN(SC_SPACE) AND Y = FLOOR THEN
            VY = -12
        END IF
        Y = MIN(Y + VY, FLOOR)
        VY = MIN(VY + 2, 8)
        N = N - 1
    WEND
    IF Y < FLOOR THEN
        CALL SpriteMove(Hero, HeroM, Back, 1, X, Y, 2)
    ELSE
        CALL SpriteMove(Hero, HeroM, Back, 1, X, Y, ABS(D) * ((X / 4) MOD 2))
    END IF
    Status$ = "X " + STR$(X) + "  Y " + STR$(Y)
END SUB

SUB Keys
    IF KEYCODE = KC_STOP THEN
        CALL Quit
    END IF
END SUB

SUB Quit
    TIMER OFF
    EXIT
END SUB

SprCW = 320
SprCH = 160
SprW(1) = 16
SprH(1) = 16
SprX(1) = 20
SprY(1) = FLOOR
BITMAP LOAD Hero, "T3HERO.PBI"
BITMAP LOAD HeroM, "T3HEROM.PBI"
CALL PaceStart(2, 4)
Status$ = "Left / Right, Space"
END
```

Build it:

```sh
python3 pcw16basic build examples/tutorial/t3_hop.pbas
```

Copy `build/t3_hop.prg` as `T3HOP.PRG`, with `T3HERO.PBI` and `T3HEROM.PBI`, into the same folder ([running-in-xanne.md](running-in-xanne.md)). Like Tutorial 2, it has one code bank, so copy the `.PRG` whole. `programs/T3HOP.PRG` is the same program, prebuilt: it is the build that was tested in XAnne. The program writes no files.

This program does not check `IOERR` after its `BITMAP LOAD`s. If the pictures are missing, it runs without them and the figure is not drawn properly. Tutorial 2 shows the check to add.

## What you should see

A large window titled `HOP`, with the status line `Left / Right, Space`. Below it is a 320 × 160 drawing area, white, with a grey floor along its bottom and the figure standing on the floor near the left edge. Hold Left or Right and the figure runs. Press Space and it jumps, then lands on the floor by itself. The status line shows the figure's position, for example `X 40  Y 128`. **Quit** ends the program.

## How it works

- **TIMER Update, EVERY 2 TICKS** runs `Update` every 2/16 of a second while the window is open. A tick is a sixteenth of a second. For intervals up to 240 ticks, the program's own event loop runs the timer: it compares the clock (`CLOCKTICKS`) with the time the handler is due. `TIMER OFF` stops it ([manual/14-timers-and-animation.md](manual/14-timers-and-animation.md)).
- **Steps of time, not of events.** The handler is not guaranteed to run once for every interval. If a run is late by more than an interval, because of a long handler, an alert or the system's own work, the missed runs are dropped, not queued. In XAnne a `TIMER ... EVERY 1 TICKS` ran its handler 142 to 154 times in 10 seconds instead of 160 while the program was busy (known issue KI-81, docs/limitations.md). So the game does not count handler runs. It moves in **steps** of 1/8 s of the clock:
  - `PaceStart(2, 4)` (`lib/pace.pbas`) sets steps of 2 ticks, and lets one run catch up at most 4 steps;
  - in each run, `PaceSteps()` says how many steps the time since the last run covers;
  - `Update` does that many steps, then draws once.

  The figure therefore moves at the same speed however often the handler runs. Programs built this way did 80 steps in 80 for 10 seconds in XAnne, with the program idle and with it loaded.
- **KEYDOWN(code)** is TRUE while that key is held down, at the moment it is called, and several keys can be down at once. `lib/keys.pbas` names the codes (`SC_LEFT`, `SC_SPACE`, ...): use the names, not the numbers. `KeyAxis(SC_LEFT, SC_RIGHT)` gives −1, 0 or 1. One caution: a key pressed and released between two runs of `Update` is never seen held, so a very short tap on Space can be missed. `examples/jumper.pbas` also takes Space from the canvas's `KEYS` handler, so that no tap is lost.
- **The background.** The first `Paint` draws the scenery and captures it into the BITMAP `Back`. `SpriteMove` first puts back the part of `Back` where the sprite was, and then draws the frame at its new place. That is why nothing is left behind.
- **The jump.** `VY` is the speed downwards. −12 starts a jump, and gravity adds 2 every step until the figure is back on the floor. Everything is in whole pixels.
- **The frame.** In the air the figure shows frame 2 (jumping). On the floor it shows frame 0 or 1, alternating with its x position while it runs.
- **Keys** is the canvas's key handler. It quits on the Stop key (`KC_STOP`). No recorded XAnne session confirms the Stop key, so **Quit** is the sure way out.

## Try

1. Change the jump to −16, or gravity to 1.
2. Add a platform. Draw it in the first `Paint`, and stop the fall on it the way the floor stops it.
3. `examples/jumper.pbas` is a whole game built from these pieces: platforms, coins, beetles, lives, and frames that face left and right (Tested in XAnne). [libraries/sprite.md](libraries/sprite.md) and [libraries/pace.md](libraries/pace.md) describe the two libraries it relies on, and [memory.md](memory.md) explains what large bitmaps such as `Back` cost.
