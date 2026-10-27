# lib/pace.pbas: fixed time steps for animation and games

`lib/pace.pbas` lets a game or animation move at the same speed however often its TIMER handler actually runs. It reads the clock (`CLOCKTICKS`, in sixteenths of a second) and tells each TIMER handler how many fixed-length steps of time have passed since the last one.

Why it is needed: a TIMER's handler runs are not a count of time. A handler can take longer than its interval, a late run is not repeated to catch up, and under load Rosanne delivers fewer events than asked (in XAnne, 142 to 154 events in 10 s for `EVERY 1 TICKS`, which asks for 160; known issue KI-81, [limitations](../limitations.md)). A program that moves things a fixed amount per event slows down when the machine is busy. A program that moves by elapsed time does not.

**Evidence:** *Tested in XAnne* through JUMPER, the third tutorial game (T3HOP) and the timing probes `developer-tests/timeprb.pbas` and `developer-tests/timepr4.pbas`, which measured 80 steps of 2/16 s in 10 s, as wanted, while the event count varied. Not yet tested on a real PcW16.

## Adding it

```text
INCLUDE "lib/pace.pbas"
```

It needs no other library and builds in any program, but it is only useful with a TIMER, normally `TIMER Handler, EVERY n TICKS` (see [timers and animation](../manual/14-timers-and-animation.md)).

## Procedures and functions

| Name | Kind | Parameters | Result | What it does |
|---|---|---|---|---|
| `PaceStart` | SUB | `StepTicks AS INTEGER, MaxSteps AS INTEGER` | | Starts counting: steps of `StepTicks` sixteenths of a second, at most `MaxSteps` at once. Values below 1 are taken as 1. Also resets the counters. |
| `PaceSteps` | FUNCTION | none | INTEGER | The steps due since the last call, 0..MaxSteps. Call it once in each TIMER handler, do that many steps of your game, and draw once if it was not 0. |

`PaceAdd` is internal.

Time beyond `MaxSteps` is dropped and counted in `PaceLost`: after a long stall, the game slows down for a moment instead of leaping ahead. Call `PaceStart` again after a pause, so that the paused time is not caught up.

## Names it defines

| Name | Type | Meaning |
|---|---|---|
| `PaceTotal` | INTEGER | steps done since `PaceStart` (stops at 30000) |
| `PaceCalls` | INTEGER | calls of `PaceSteps` that returned steps: the frames drawn (stops at 30000) |
| `PaceLost` | INTEGER | steps dropped because of `MaxSteps` (stops at 30000) |
| `PaceLast`, `PaceStep`, `PaceMax`, `PaceAcc` | INTEGER | internal |

Every name starts with `Pace`; do not declare your own.

## Memory cost

| | bytes |
|---|---:|
| whole program, one 16K image | +930 |
| resident 16K block, procedures in code banks | +535 |
| of which variables | +38 |

Most of the resident figure is the runtime's clock routine.

## Errors and edge cases

- The clock is read within the minute (0..959 sixteenths). A call more than half a minute after the previous one, or a clock that went back, counts no time. It never returns a negative number.
- In a program's first second the clock's fraction is not yet in step with the seconds, so a game started then can lose up to a second of steps once (known issue KI-93, [limitations](../limitations.md)).
- `PaceSteps` before any `PaceStart` uses a step of 0 and stops the program with `Runtime error: division by zero` (checked on the simulator). Call `PaceStart` first, in the main line.

## Example

The block crosses the canvas at 4 pixels per 1/8 s (32 pixels a second), however often `Tick` runs.

```pbas
INCLUDE "lib/pace.pbas"
DIM X AS INTEGER
WINDOW "Pace"
CANVAS 200, 60, PAINT Paint
BUTTON "Quit", Quit
TIMER Tick, EVERY 1 TICKS
SUB Paint
    DRAW CLEAR
    DRAW FILL X, 20, 16, 16, 0
END SUB
SUB Tick
    LOCAL N AS INTEGER
    N = PaceSteps()
    IF N = 0 THEN
        EXIT SUB
    END IF
    DRAW FILL X, 20, 16, 16, 8
    WHILE N > 0
        X = X + 4
        IF X > 200 - 16 THEN
            X = 0
        END IF
        N = N - 1
    WEND
    DRAW FILL X, 20, 16, 16, 0
END SUB
SUB Quit
    EXIT
END SUB
CALL PaceStart(2, 4)
END
```

## Used by

- `examples/jumper.pbas`, `examples/tutorial/t3_hop.pbas` ([Tutorial 3](../TUTORIAL-3-GAME.md))
- `developer-tests/timeprb.pbas`, `developer-tests/timepr4.pbas` (through `developer-tests/timecore.pbas`)

## Limitations

- The resolution is the clock's: 1/16 s. Steps shorter than one tick are not possible.
- It paces your program's logic; it cannot make drawing itself faster. If one frame takes longer than `MaxSteps` steps, the game runs slower than real time and `PaceLost` grows.

See also: [library index](README.md), [lib/sprite.pbas](sprite.md), [lib/keys.pbas](keys.md), [generated reference](../LIBRARY-REFERENCE.md).
