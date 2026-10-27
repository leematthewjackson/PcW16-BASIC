# 14. Timers and animation

A program can run a handler regularly with `TIMER`, read the clock with `SECONDS` and
`CLOCKTICKS`, and combine both with held keys (`KEYDOWN`) and sprites to animate. This chapter
states exactly what a timer promises, and what it does not, and shows the patterns that work.

**The rule to remember: timer events are not a count of time.** Under load, events collapse
(fewer handler runs than intervals), so a program that moves something a fixed amount per event
slows down. Read the clock and do as many fixed steps as the time passed covers. `lib/pace.pbas`
does this for you.

Evidence levels: *Tested in XAnne* (the owner ran it in the XAnne emulator, Rosanne 1.12,
Graphics acceleration off), *Simulator only*, *Untested*. Nothing has yet been tested on a real
PcW16; the timer's rate and the clock's fineness on real hardware are unknown.

Contents: [TIMER … EVERY n (seconds)](#timer--every-n-seconds) ·
[TIMER … EVERY n TICKS](#timer--every-n-ticks) · [TIMER ON and TIMER OFF](#timer-on-and-timer-off) ·
[SECONDS](#seconds) · [CLOCKTICKS](#clockticks) · [The timer contract](#the-timer-contract) ·
[Pacing by the clock](#pacing-by-the-clock) · [lib/pace.pbas](#libpacepbas) ·
[A complete animation](#a-complete-animation-pattern) · [What is not available](#what-is-not-available)

## TIMER … EVERY n (seconds)

**Syntax**

```text
TIMER Handler, EVERY n
```

**Meaning.** Runs `Handler` about every `n` seconds while a window is open. `n` is an integer
literal from 1 to 3599. The timer starts when the first window opens. A timer handler runs
between other events, never during one, with the same value movement as a button handler
(controls read before, redrawn after), except that a NUMBERBOX holding invalid text is left
alone. The timer is stopped before the program ends.

**Requires.** A `WINDOW`. A top-level statement; one `TIMER` per program.

**Example**

```pbas
DIM Count AS INTEGER
DIM Shown$ AS STRING * 24

WINDOW "Seconds"
LABEL Shown$
BUTTON "Quit", Quit
TIMER Tick, EVERY 1

SUB Tick
    Count = Count + 1
    Shown$ = "Ticks seen: " + STR$(Count)
END SUB

SUB Quit
    EXIT
END SUB

Shown$ = "Waiting"
END
```

(This counts events, which is fine for a display; to measure time, read `SECONDS`, below.)

**Common errors**

```pbas-error
' expect-error: TIMER requires a WINDOW declaration
TIMER Tick, EVERY 1
SUB Tick
    BEEP
END SUB
END
```

```pbas-error
' expect-error: TIMER interval must be 1..3599 seconds
WINDOW "Timer"
BUTTON "Quit", Quit
TIMER Quit, EVERY 3600
SUB Quit
    EXIT
END SUB
END
```

```pbas-error
' expect-error: only one TIMER is allowed
WINDOW "Timer"
BUTTON "Quit", Quit
TIMER Quit, EVERY 1
TIMER Quit, EVERY 2
SUB Quit
    EXIT
END SUB
END
```

*Evidence:* tested in XAnne (`stopwatch.pbas`, `tea_timer.pbas`).

**See also.** `../../examples/stopwatch.pbas`, `../../examples/tea_timer.pbas`; spec
[§5.1](../../LANGUAGE-SPEC.md#51-m6-phase-1--native-application-interfaces) (Timer).

## TIMER … EVERY n TICKS

**Syntax**

```text
TIMER Handler, EVERY n TICKS
```

**Meaning.** The interval is `n` sixteenths of a second (a *tick* is 1/16 s), `n` an integer
literal from 1 to 32767. Everything else is as for seconds: one timer, `TIMER ON` and `OFF`,
handlers between events.

How it runs:
- For `n` up to 240 (15 seconds) the program's own event loop runs the timer: before each look
  for an event it compares `CLOCKTICKS` with the time the handler is due, and runs it when due.
  The next run is due `n` ticks later.
- A handler that falls more than an interval behind (a long handler, an alert, the system's own
  work) is **not** run again to catch up: the next run is due an interval from then. Late
  intervals are dropped, never queued.
- For `n` over 240, the timer is a Rosanne timer, as `EVERY n` seconds is.

**Example**

```pbas
DIM X AS INTEGER

WINDOW "Ticks"
CANVAS 300, 40, PAINT Paint
BUTTON "Quit", Quit
TIMER Move, EVERY 4 TICKS

SUB Paint
    DRAW CLEAR
    DRAW FILL X, 10, 20, 20
END SUB

SUB Move
    DRAW FILL X, 10, 20, 20, 8
    X = (X + 5) MOD 280
    DRAW FILL X, 10, 20, 20
END SUB

SUB Quit
    TIMER OFF
    EXIT
END SUB
END
```

This moves the square 5 pixels per event. That is the *simplest* form, but its speed depends on
how many events arrive; the [pacing pattern](#pacing-by-the-clock) below keeps the speed steady.

**Common errors**

```pbas-error
' expect-error: TIMER interval must be 1..32767 TICKS (sixteenths of a second)
WINDOW "Ticks"
BUTTON "Quit", Quit
TIMER Quit, EVERY 0 TICKS
SUB Quit
    EXIT
END SUB
END
```

**Limits.** The handler must be short: while it runs, nothing else happens (no clicks, no
redraws).

*Evidence:* tested in XAnne (`../../developer-tests/timeprb.pbas` and `timepr4.pbas`, `jumper.pbas`,
`../../examples/tutorial/t3_hop.pbas`). The build option `--legacy-timing` rebuilds the older
behaviour (always a Rosanne timer), which paused in XAnne; it exists only to reproduce old
executables byte for byte.

**See also.** spec
[§5.15](../../LANGUAGE-SPEC.md#515-m13--ticks-the-clock-in-sixteenths-and-held-keys) (Ticks).

## TIMER ON and TIMER OFF

```text
TIMER OFF
TIMER ON
```

`TIMER OFF` stops the timer; `TIMER ON` starts it again. Both are ordinary statements (main line
or handlers). Stop the timer while an alert or another window is shown, and before `EXIT` if the
handler draws. After a pause, restart your pacing too (`PaceStart`), so that the paused time is
not caught up. *Tested in XAnne* (`stopwatch.pbas`).

## SECONDS

```text
SECONDS              INTEGER 0..3599: minutes × 60 + seconds of the PcW16's clock
```

For timing in seconds. An interval is `(SECONDS - Start + 3600) MOD 3600` while it is under an
hour. A variable of your own called `Seconds` keeps its meaning (it hides the function, as in
`../../examples/stopwatch.pbas`).

```pbas
DIM Start AS INTEGER
DIM Shown$ AS STRING * 24

WINDOW "Elapsed"
LABEL Shown$
BUTTON "Start", StartIt
BUTTON "How long?", HowLong, DEFAULT
BUTTON "Quit", Quit

SUB StartIt
    Start = SECONDS
    Shown$ = "Started"
END SUB

SUB HowLong
    Shown$ = STR$((SECONDS - Start + 3600) MOD 3600) + " seconds"
END SUB

SUB Quit
    EXIT
END SUB

Start = SECONDS
Shown$ = "Started"
END
```

*Evidence:* tested in XAnne.

## CLOCKTICKS

```text
CLOCKTICKS           INTEGER 0..959: the PcW16 clock in sixteenths of a second within the minute
```

**Meaning.** `CLOCKTICKS` is seconds × 16 plus the sixteenths of the current second. An
interval is `(CLOCKTICKS - Start + 960) MOD 960` sixteenths while it is under a minute. Within a
second it never goes back, so it goes back only at the minute (the `MOD 960` handles that). A
variable of your own called `ClockTicks` keeps its meaning.

**First-second limitation.** In XAnne the clock's fraction byte is not in step with its
seconds. The runtime works out where the second changes from what it sees, which takes up to a
second after the program starts (sooner in a program with a `TICKS` timer, which reads the clock
often). Until then the fraction can be wrong, so a game started in that second can lose up to a
second of steps once (known issue KI-93, [limitations](../limitations.md)).

*Evidence:* tested in XAnne (`../../developer-tests/timeprb.pbas`: the clock never went back, largest step
2/16 s). How fine the clock is on a real PcW16 is untested.

## The timer contract

What a timer **does** promise:
- the handler runs only while a window is open and the timer is on;
- it runs between events, never during another handler;
- it never runs early.

What it does **not** promise:
- **that it runs once per interval.** A handler can take longer than the interval; a late run
  is not repeated; a Rosanne timer (`EVERY n` seconds, or over 240 ticks) posts one event however
  many intervals have passed; and alerts, other windows and the system's own work delay it.

The owner's measurement in XAnne: `TIMER … EVERY 1 TICKS` asks for 160 events in 10 seconds,
and brought **142 to 154** under load, while a program stepping by the clock completed **all 80**
of its 2/16-second steps in the same time (known issue KI-81,
[limitations](../limitations.md)). So **never count events as time**. Pace by the clock.

Held keys are read at the moment you call `KEYDOWN`, so a key pressed and released between two
events may be missed (known issue KI-92). Take taps that must not be lost (a jump) from the
canvas's `KEYS` handler as well ([chapter 11](11-menus-keys-mouse.md#held-keys-keydown)).

## Pacing by the clock

The reliable pattern for animation and games:

1. Choose a fixed step length in ticks (for example 2, an eighth of a second) and what one step
   does (move 4 pixels, add gravity once).
2. In each timer event, read `CLOCKTICKS`, work out how many whole steps have passed since the
   last event, and do that many steps on your variables (not on the screen).
3. Draw once, if at least one step was done.
4. Limit how many steps one event may catch up, so that after a long stall the game slows for a
   moment instead of leaping.

Written out by hand:

```pbas
CONST STEPTICKS = 2

DIM X AS INTEGER
DIM Last AS INTEGER
DIM Acc AS INTEGER

WINDOW "Paced"
CANVAS 300, 40, PAINT Paint
BUTTON "Quit", Quit
TIMER Update, EVERY 1 TICKS

SUB Paint
    DRAW CLEAR
    DRAW FILL X, 10, 20, 20
END SUB

SUB Update
    LOCAL Now AS INTEGER
    LOCAL N AS INTEGER
    LOCAL Old AS INTEGER
    Now = CLOCKTICKS
    Acc = Acc + (Now - Last + 960) MOD 960
    Last = Now
    N = MIN(Acc / STEPTICKS, 4)
    Acc = Acc - (Acc / STEPTICKS) * STEPTICKS
    IF N = 0 THEN
        EXIT SUB
    END IF
    Old = X
    X = (X + 3 * N) MOD 280
    DRAW FILL Old, 10, 20, 20, 8
    DRAW FILL X, 10, 20, 20
END SUB

SUB Quit
    TIMER OFF
    EXIT
END SUB

Last = CLOCKTICKS
END
```

The square now crosses the canvas at the same speed however many events arrive.

## lib/pace.pbas

`INCLUDE "lib/pace.pbas"` gives the same pattern, with counters:

| Name | What it does |
|---|---|
| `SUB PaceStart(StepTicks AS INTEGER, MaxSteps AS INTEGER)` | steps of `StepTicks` sixteenths; at most `MaxSteps` in one call (time beyond that is dropped and counted in `PaceLost`). Call it at the start, and again after every pause |
| `FUNCTION PaceSteps() AS INTEGER` | the steps due since the last call (0..`MaxSteps`). Call it once in each timer handler, do that many steps, and draw if it is not 0 |
| `PaceTotal`, `PaceCalls`, `PaceLost` | steps done, calls that did steps (frames drawn), steps dropped; each stops at 30000 |

A call more than half a minute after the last one, or a clock that went back, counts no time.
Everything in the library starts with `Pace`. It needs a TIMER (it reads `CLOCKTICKS`), and no
canvas.

```pbas
INCLUDE "lib/pace.pbas"

DIM X AS INTEGER

WINDOW "Pace"
CANVAS 300, 40, PAINT Paint
BUTTON "Pause", Pause
BUTTON "Go on", GoOn
BUTTON "Quit", Quit
TIMER Update, EVERY 2 TICKS

SUB Paint
    DRAW CLEAR
    DRAW FILL X, 10, 20, 20
END SUB

SUB Update
    LOCAL N AS INTEGER
    N = PaceSteps()
    IF N = 0 THEN
        EXIT SUB
    END IF
    DRAW FILL X, 10, 20, 20, 8
    X = (X + 3 * N) MOD 280
    DRAW FILL X, 10, 20, 20
END SUB

SUB Pause
    TIMER OFF
END SUB

SUB GoOn
    CALL PaceStart(2, 4)
    TIMER ON
END SUB

SUB Quit
    TIMER OFF
    EXIT
END SUB

CALL PaceStart(2, 4)
END
```

*Evidence:* tested in XAnne inside `jumper.pbas` and `../../examples/tutorial/t3_hop.pbas`.

## A complete animation pattern

A game combines a ticks timer, `lib/pace.pbas`, held keys (`lib/keys.pbas`, which needs a
CANVAS) and sprites with a saved background (`lib/sprite.pbas`). This is the starting point that
`pcw16basic new NAME --kind game` writes, shortened:

```pbas
INCLUDE "lib/geom.pbas"
INCLUDE "lib/sprite.pbas"
INCLUDE "lib/keys.pbas"
INCLUDE "lib/pace.pbas"

CONST CW = 320
CONST CH = 160
DIM Look AS BITMAP * 16, 16
DIM LookM AS BITMAP * 16, 16
DIM Back AS BITMAP * 320, 160
DIM VY AS INTEGER
DIM Ready AS BOOLEAN

WINDOW Main, "HOP", LARGE
CANVAS 320, 160, PAINT Paint, KEYS Keys
BUTTON "Quit", Quit
TIMER Update, EVERY 2 TICKS

SUB Paint
    IF NOT Ready THEN
        DRAW CLEAR
        DRAW FILL 0, 0, 16, 16
        DRAW FILL 4, 4, 3, 3, 8
        DRAW FILL 9, 4, 3, 3, 8
        BITMAP GET Look, 0, 0, 16, 16
        DRAW FILL 0, 0, 16, 16, 8
        BITMAP GET LookM, 0, 0, 16, 16
        DRAW CLEAR
        DRAW FILL 0, CH - 16, CW, 16, 4
        BITMAP GET Back, 0, 0, CW, CH
        Ready = TRUE
    END IF
    BITMAP PUT Back, 0, 0
    CALL SpriteShow(Look, LookM, 1)
END SUB

' Each event: the 1/8 s steps due since the last one, then one draw.
SUB Update
    LOCAL N AS INTEGER
    LOCAL X AS INTEGER
    LOCAL Y AS INTEGER
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
        X = GeomClamp(X + 4 * KeyAxis(SC_LEFT, SC_RIGHT), 0, CW - 16)
        IF KEYDOWN(SC_SPACE) AND Y = CH - 32 THEN
            VY = -10
        END IF
        Y = MIN(Y + VY, CH - 32)
        VY = MIN(VY + 2, 8)
        N = N - 1
    WEND
    CALL SpriteMove(Look, LookM, Back, 1, X, Y, 0)
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

SprCW = CW
SprCH = CH
SprW(1) = 16
SprH(1) = 16
SprX(1) = 20
SprY(1) = CH - 32
CALL PaceStart(2, 4)
END
```

Points to copy:
- the `Ready` flag: the timer can fire before `PAINT` has made the sprite and background, so
  the handler does nothing until then;
- all steps change variables; drawing happens once per event (`SpriteMove` restores the
  background behind the sprite and draws it in its new place);
- movement reads held keys inside the step loop, so it is the same speed at any event rate;
- `Quit` stops the timer before `EXIT`.

*Evidence:* the full version (`pcw16basic new --kind game`) builds; the pattern is the one
`jumper.pbas` and `t3_hop.pbas` use, both tested in XAnne.

**See also.** `../../examples/jumper.pbas` (a complete platform game),
`../../examples/sprited.pbas` (animation preview), [Tutorial 3](../TUTORIAL-3-GAME.md),
[libraries](../libraries/README.md); spec
[§5.15](../../LANGUAGE-SPEC.md#515-m13--ticks-the-clock-in-sixteenths-and-held-keys).

## What is not available

No `SLEEP`, `WAIT` or `TIMER` function (use a `TIMER` handler, `SECONDS` or `CLOCKTICKS`); no
date or time-of-day strings (`DATE$`, `TIME$`); no second timer; no sound other than `BEEP`.
A busy loop in a handler blocks the whole program: there is no way to wait inside a handler
while other events are served. See [chapter 17](17-unsupported.md).

Next: [15. Printing](15-printing.md).
