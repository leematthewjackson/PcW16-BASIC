> **About this document.** This is the normative specification of the PcW16 BASIC
> language. It was written alongside the compiler and keeps the record of how each rule was
> established: notes such as "M9", "KI-25", "owner XAnne" or "static" say when a rule was
> added and what evidence supports it (an XAnne session, a reading of Rosanne's code, the
> simulator). References to `docs/M*.md`, `RUNTIME-RESULTS.md`, `KNOWN-ISSUES.md` and similar
> files are to the project's engineering records, which are not part of this repository. Where
> a later section extended the language, the earlier text says so in place; §5.16 lists what
> the M14 revision made stricter or corrected. For learning the language, start with
> [the developer manual](docs/manual/README.md); this file is the place to settle exactly
> what a rule says. Current evidence for each feature is summarised in
> [docs/limitations.md](docs/limitations.md).

# PcW16 BASIC — Language Specification

**Status:** the normative specification of the language the compiler accepts (M14 revision). It consolidates the proved semantics of the POC (v0.3–v0.5.1, XAnne-tested where noted) and removes POC-only restrictions that were implementation accidents rather than language decisions. Anything not listed here is **not part of the language**; a conforming program using it must receive a clear compile error with source location.

Types, limits and runtime behaviour cited to `ROSAN283.DOC` are doc-derived; those cited "POC-proven" carried an XAnne acceptance script; those marked "policy" are conservative choices pending XAnne measurement.

**How to read it (M14).** The specification grew section by section: §1–§10 were written for the first compiler ("Stage 1"), and §3.1 and §5.1–§5.16 each record what a later milestone added. Where a later section extended the language, the earlier text now says so in place, so every statement here is current. Notes such as "M9" or "KI-25" say when a rule was added and which record supports it; an *Evidence status* line says what the rule was tested on when it was written, and a later line adds later evidence. §5.16 lists the rules M14 made stricter or corrected.

---

## 1. Source text

- UTF-8 `.pbas`, one statement per line. Keywords and identifiers are case-insensitive.
- Optional traditional line numbers; if present they must strictly increase and have no semantic effect (no `GOTO` exists).
- Comments: `REM …`, `' …` to end of line.
- **Reserved words (M5b, M5c):** `MOD` (M5b) and `AND`, `OR`, `NOT`, `CALL` (M5c) are part of the language and can no longer be used as variable or SUB names.
- Strings: `"…"` with `""` for an embedded quote. String content is ASCII for generated UI text (enforced where it enters Rosanne objects/alerts).

## 2. Types

| Type | Representation | Range / rule |
|---|---|---|
| `INTEGER` | signed 16-bit two's complement | −32768..32767; arithmetic wraps with no overflow trap (POC-proven; documented, not accidental) |
| `BOOLEAN` | 16-bit cell, values 0 (`FALSE`) / 1 (`TRUE`) | no other truthiness |
| `REAL` (M7) | 5-byte binary floating point: 32-bit mantissa (31 stored bits + implicit leading 1, sign in the top bit), exponent byte biased by 128 | about ±2.9E−39 .. ±1.7E+38 and 0; about 9.6 significant decimal digits; overflow is a runtime error, underflow gives 0 (§3.1) |
| `STRING` | zero-terminated byte string, fixed capacity | capacity is a compile-time property (§4); a value that does not fit is an error, never truncated (§4); ASCII in UI contexts |

Integer literals: decimal magnitudes 0..32767 with unary `-` for negatives (so `-32768` is expressible). A literal `32768` is a compile error (the POC silently wrapped it to −32768 — fixed here). Boolean literals `TRUE`, `FALSE`.

**M7 REAL literals:** digits with a decimal point and/or an exponent — `2.5`, `.5`, `3.`, `1E10`, `6.02E+23`, `1.5e-3` — are REAL. A literal is stored as the REAL nearest to its exact decimal value (`pbas/real.py`). A literal beyond about 1.7E+38 is a compile error; one too small for the format is 0. `PI` is the REAL nearest to π.

## 3. Expressions and operators

Precedence (tightest first): unary `+ -` > `* / MOD` > `+ -` > comparisons > `NOT` > `AND` > `OR` (M5c); binary operators of equal precedence group left to right. Parentheses override. So `NOT A = B` means `NOT (A = B)`, and `A OR B AND C` means `A OR (B AND C)`.

- `INTEGER + - *`, unary `+ -`: INTEGER.
- **`INTEGER / INTEGER` and `INTEGER MOD INTEGER` (M5b):** integer division. The quotient truncates toward zero (`-7 / 2` = −3); `MOD` is the remainder with the sign of the dividend (`-7 MOD 2` = −1, `7 MOD -2` = 1), so `A = (A / B) * B + A MOD B` always holds. `-32768 / -1` wraps to −32768 and `-32768 MOD -1` is 0, consistent with the wrapping of `+ - *` (§2). Division by a **constant** zero is a compile error; by a computed zero, `Runtime error: division by zero at line N` (§8).
- `STRING + STRING`: concatenation. **M5a: a STRING expression anywhere a STRING is expected** — assignment, comparison operands, `LEN`, substring sources, `MESSAGE`, `FILESAVE`. (Before M5a it was restricted to `MESSAGE`/`FILESAVE` values.) `STRING + INTEGER` stays an error: use `STR$`.
- Comparisons `= == <>`: operands of the same type, result BOOLEAN. STRING literal and variable operands are compared in place, at any length. A *computed* STRING operand (`STR$`, a substring, a concatenation) is built in a runtime scratch string and may be at most **127 bytes** in the worst case; a longer one is a compile error (M2.1, unchanged by M5a). The same limit applies to a computed argument of `LEN` and to a computed substring source. `< <= > >=`: two INTEGER operands, or **two STRING operands (M5b)** compared in unsigned byte order (ASCII): a string that is the start of a longer one sorts first (`"abc" < "abcd"`), and capitals sort before lower case (`"Zebra" < "apple"`). Mixed types and BOOLEAN operands are compile errors.
- **Temporary strings (M5a).** Computed operands nested inside one another use a pool of six 128-byte scratch strings, by nesting depth; an expression needing more at once is a positioned compile error ("nested too deeply") — split it into statements.
- Built-in functions (arguments must be statically typed):
  - `LEN(s)` → INTEGER, length in bytes.
  - `STR$(i)` → the decimal text of a signed INTEGER (M7: or of a REAL, §3.1).
  - `LEFT$(s, n)`, `RIGHT$(s, n)`, `MID$(s, start, n)` → STRING. **M5a:** `s` is any STRING expression; `n` and `start` are any INTEGER expressions. `MID$` start is 1-based. Rules:
    - a *constant* count below 0 or constant `MID$` start below 1 is a compile error (as before);
    - a *computed* count below 0 or computed start below 1 stops the program with `Runtime error: substring position out of range at line N` (§8);
    - otherwise the result is the available characters: `n` larger than what is left takes what is left; a start past the end gives `""`; empty in → empty out (POC-proven edges, unchanged);
    - all arguments are evaluated before anything is written to the destination.
  - **M5b:** `VAL(s)` → INTEGER: skips leading spaces, takes an optional `+`/`-` and the decimal digits that follow, and stops at the first other character (`VAL("12abc")` = 12, `VAL(" -7")` = −7). No digits gives 0 (`VAL("")`, `VAL("abc")`, `VAL("-")`). A number outside −32768..32767 is `Runtime error: number out of range at line N` — it never wraps.
  - **M5b:** `ASC(s)` → INTEGER: the code (1..255) of the first character; `ASC("")` is −1 (no error).
  - **M5b:** `CHR$(n)` → a one-character STRING. `n` must be 1..255 (0 cannot be part of a STRING): a constant outside that range is a compile error, a computed one `Runtime error: character code out of range at line N`.
  - **M5b:** `INSTR(a, b)` and `INSTR(start, a, b)` → INTEGER: the 1-based position of the first occurrence of `b` in `a` at or after `start` (default 1), or 0. An empty `b` is found at `start` when `start` ≤ `LEN(a)` + 1. `start` below 1 is a compile error when constant, else the substring runtime error. Matching is exact (case-sensitive).
- **M5c:** `UCASE$(s)` / `LCASE$(s)` → STRING: `s` with the ASCII letters `a`–`z` changed to `A`–`Z` (or `A`–`Z` to `a`–`z`); every other byte, including Rosanne's codes 128–255, is unchanged. The result has exactly the length of `s`. Use them for case-insensitive tests: `IF UCASE$(A$) = "YES" THEN`.
- **Logical operators (M5c):** `NOT b`, `a AND b`, `a OR b` take **BOOLEAN operands** and give a BOOLEAN. Since M7, two INTEGER operands make `AND`, `OR`, `NOT` (and `XOR`) bitwise operators instead (§5.3); one of each is a compile error, and there is no numeric truthiness (§2).
  - **Evaluation order: left to right, stopping as soon as the result is known** ("short-circuit"). In `a AND b`, `b` is not evaluated when `a` is FALSE; in `a OR b`, `b` is not evaluated when `a` is TRUE. A guard therefore protects what follows it: `IF B <> 0 AND A / B > 2 THEN` never divides by zero, and `IF LEN(S$) > 0 AND ASC(S$) = 32 THEN` never looks at an empty string. (Classic Microsoft BASICs evaluate both sides; PcW16 BASIC does not.) Expressions have no side effects other than the runtime errors of §8, so this is the only observable consequence.
  - `NOT`, `AND` and `OR` are words, so they need spaces around them like other keywords (`A AND B`, not `AANDB`).
- No implicit conversions between STRING and numbers (use `VAL`, `REALVAL` and `STR$`). M7: INTEGER widens to REAL (§3.1); user FUNCTIONs exist (§5.3).

### 3.1 M7 — REAL numbers

*Evidence status:* written on simulator, memory-checker and independent Z80 core evidence. The M7 REAL programs (SCICALC, JOURNAL, M7_EDGES) were then accepted by the owner in XAnne, with limitations (commit 9c417af); the rounding and accuracy statements below still rest on the simulator tests. Implementation: `pbas/real.py` (format), `tools/realconst.py` (constant tables), runtime `IF PB_REAL` section. The format follows the Amstrad/Locomotive 5-byte layout, so values and precision are those familiar from Locomotive BASIC, but the code is new and independent.

- **Declaration:** `DIM X AS REAL`, `DIM A(n) AS REAL` (5 bytes per element), `LOCAL X AS REAL`, `X AS REAL` parameters, `FUNCTION F(...) AS REAL`, `CONST RATE = 1.25`. A REAL starts as 0.
- **Mixed arithmetic:** when one operand of `+ - * /` or of a comparison is REAL and the other INTEGER, the INTEGER is converted to REAL (exactly) first. `INTEGER / INTEGER` is still integer division (§3; write `N / 2.0` for a REAL quotient). `^` (power) always gives a REAL. `MOD`, `AND`/`OR`/`XOR`/`NOT`, `SHL`/`SHR` and FOR counters stay INTEGER-only.
- **Assignment:** an INTEGER value may be assigned to a REAL (converted). A REAL may **not** be assigned to an INTEGER: that is a compile error asking for `CINT`, `INT` or `FIX` — nothing is truncated silently.
- **Rounding:** `+ - * /` are correctly rounded (the exact result rounded to the nearest REAL, halves away from zero); randomised tests compare them with exact rational arithmetic. *M14:* up to M13, `+` and `-` dropped the bits shifted below the guard byte, so a result just under half a unit in the last place could be rounded the wrong way (by one unit, in about 1.5% of cases built to lie near a half); since M14 those bits are kept as a sticky bit (tests/test_m14_real.py). `tools/build.py --legacy-real-rounding` rebuilds the old code, only to reproduce accepted executables. Results smaller than about 2.9E−39 become 0.
- **Precedence:** `^` binds tighter than unary minus and `* /`, and associates to the left: `-2 ^ 2` = −4, `2 ^ 3 ^ 2` = 64.
- **Comparisons** `= <> < <= > >=` compare exact values (so `0.1 + 0.2 = 0.3` happens to be TRUE in this format, but in general, compare with a tolerance: `ABS(A - B) < 1E-6`).
- **Functions (argument INTEGER or REAL; result REAL unless stated):**
  - `SQR(x)` (x ≥ 0), `EXP(x)`, `LOG(x)` (natural log, x > 0), `SIN(x)`, `COS(x)`, `TAN(x)` (radians, |x| ≤ 51000), `ATN(x)` (result −π/2..π/2), `x ^ y` (x < 0 needs a whole y; `0 ^ 0` = 1; `0 ^` negative is division by zero).
  - `INT(x)` largest whole number ≤ x (`INT(-2.5)` = −3); `FIX(x)` toward zero (`FIX(-2.5)` = −2). Both REAL.
  - `CINT(x)` → INTEGER: nearest, halves away from zero (`CINT(2.5)` = 3, `CINT(-2.5)` = −3); outside −32768..32767 is `number out of range`.
  - `REAL(n)` → the INTEGER n as a REAL (rarely needed, conversion is automatic).
  - `ABS`, `SGN`, `MIN`, `MAX` accept REALs too (`SGN` returns an INTEGER; `MIN`/`MAX` of mixed operands give a REAL).
  - **Accuracy:** the maths functions are within a few units of the last place of the 32-bit mantissa (relative error ≤ 4E−9 in the tests against Python's maths, which compare SQR/EXP/LOG/SIN/COS/TAN/ATN/^ over representative arguments). SIN/COS/TAN reduce the argument with a two-part π/2, so accuracy falls gradually for large |x|; beyond 51000 they are an error rather than a meaningless value.
- **Text conversion:**
  - `STR$(x)` gives the decimal of 9 significant digits nearest to the stored value (halves away from zero; computed exactly, not by repeated scaling), trailing zeros removed, `-` for negatives, no leading space: plain notation from 0.0001 up to 999999999 (`0.1`, `123.456`, `-2`, `0.333333333`), otherwise `d.dddE±XX` (`1E+10`, `1.23456789E+09`, `1E-05`). At most 15 characters.
  - `REALVAL(s)` → REAL: like `VAL` (§3): skips leading spaces, reads an optional sign, digits, an optional `.` and digits, and an optional `E`/`e` exponent with optional sign, and stops at the first other character. No digits gives 0. A value too large is `number out of range`. Only the first 9 significant digits are used (later ones are ignored, not rounded); the result is the REAL nearest to the value of those digits, computed exactly.
  - `ISNUM(s)` → BOOLEAN: TRUE when the whole of `s` (leading and trailing spaces allowed) is one number in `REALVAL` syntax that is in range. Use it to validate typed input before `REALVAL`.
  - `PRINT #n, x` writes `STR$(x)`.
- **Not supported:** REAL FOR counters, REAL `NUMBERBOX` bindings, `TEXTBOX`/`LABEL` binding to a REAL (bind a STRING and convert with `STR$`/`REALVAL`), formatted output (`PRINT USING`), double precision.
- **Size:** since M8 a program includes only the parts of the REAL library it can reach (`pbas/prune.py`); the whole library, which `--whole-real-library` includes, is about 4.5 KB of the resident 16 KB (§8).

## 4. Variables, declarations, capacity

- `DIM name AS INTEGER|STRING|BOOLEAN|REAL` declares a global variable, including inside procedures (POC semantics, retained; since M14 the compiler warns about a `DIM` inside a procedure, because it is easily mistaken for a local). M7: procedures have parameters and `LOCAL` variables (§5.3).
- A name may not be both a variable and a `SUB`.
- `$`-suffixed names must be declared `STRING`. Case-insensitive.
- `TEXTBOX name$ [, "caption"]` implicitly declares/binds a STRING; `CHECKBOX name [, "caption"]` implicitly declares/binds a BOOLEAN. The same binding may be declared by both `DIM` and a widget if types agree.
- **STRING capacity:** default 64 bytes including the NUL; compiler option `--string-capacity=N` (2 ≤ N ≤ 127) sets the program-wide default. **M8:** `DIM S$ AS STRING * n` gives one variable or array its own capacity of n characters (§5.4). A TEXTBOX-bound string must additionally have capacity ≤ 128 (doc-derived textedit maximum; the POC's 33-byte buffer was an implementation accident and is gone) — **≤ 64 in M3b** (conservative policy, §5). A string of capacity N holds at most N − 1 characters.
- **Assignment reading its own destination (M5a).** `S$ = expr` may read `S$` anywhere in `expr`; the result is always as if `expr` were evaluated completely first (`S$ = "<" + S$ + ">"`, `S$ = S$ + S$`, `S$ = RIGHT$(S$, 2) + LEFT$(S$, 2)`). The compiler builds in place when only the first part reads `S$` (safe: copies move bytes forward) and otherwise builds in a scratch string and copies.
- **String overflow policy (M2.1, replaces M2's truncation rule).** No string operation ever writes outside its destination, and nothing is silently truncated:
  - **Overflow certain at compile time is a compile error.** The compiler knows each STRING expression's shortest and longest possible length (a literal or a substring of a literal: exact; a STRING variable: 0..capacity − 1; `STR$`: 1..6). Assigning a value whose *shortest* length exceeds the destination's room is rejected, e.g. `T$ = LEFT$("<100 characters>", 100)` with capacity 64. Dynamic `MESSAGE` text whose *longest* possible length exceeds the alert buffer is rejected (§6), as are over-long computed comparison/`LEN` operands (§3).
  - **Overflow only knowable at run time is a reported runtime error** (§8), e.g. `S$ = STR$(N)` with capacity 4 when `N` is −32768. Characters that fitted before the check may already be inside the destination; nothing is ever written outside it, and the program stops.

## 5. Program structure and execution model

```
declarations and statements, in source order
SUB handler … END SUB            (one or more)
END                              (mandatory, final)
```

- **Main-line statements execute once, in order, at launch.** This is the unification decision of `ARCHITECTURE.md` D1: the same statements mean the same thing everywhere.
- `WINDOW "title"` (exactly one; ASCII; layout cap applies) plus any `LABEL`/`TEXTBOX`/`CHECKBOX`/`BUTTON` declarations describe the program's dialog. If a `WINDOW` exists, the dialog is built and shown after main-line execution completes, and the program then serves events. Without `WINDOW`, the program ends at `END`.
- `BUTTON "caption", Handler` requires `SUB Handler` to exist. Handlers run on button click (mouse path XAnne-proven); M5d: a `DEFAULT` button also runs on the Return key (below).
- `SUB … END SUB` defines a procedure. Reaching `END SUB` returns to whoever started the procedure: the event loop (a button handler) or the statement after the `CALL` (M5c).
- **`CALL Name` (M5c)** runs `SUB Name` from the main line or from any procedure, then continues with the next statement. `Name` must be a `SUB` of the program (defined before or after the `CALL`). Since M7 a SUB may have parameters, and `CALL Name(x, y)` passes their values (§5.3). A procedure may also be a button handler. Rules:
  - **No recursion.** A procedure may not call itself, directly or through other procedures (`A` calls `B` calls `A`): compile error naming the cycle. Basis: parameters and locals have static storage, one copy per procedure (§5.3), and each `FOR` keeps its limit in one fixed cell, so a re-entered procedure would overwrite the state of its own unfinished activation.
  - **Nesting limit: at most 16 procedures active at once**, counting the button handler or the first procedure the main line calls (a positioned compile error at the `CALL` that makes a chain deeper). With recursion impossible, the compiler checks every chain. Stack basis: a `CALL` is made at statement level, where the program keeps nothing on the stack, so each level costs 2 bytes (the return address). 16 levels are 32 bytes of the ~2K stack (ROSAN283 'Memory Layout'), measured in the simulator tests.
  - `CALL` does not move values between bound variables and controls. The M3b synchronisation points (§5 table) are unchanged: controls are read before a button's handler starts and redrawn after it returns, whatever that handler calls.
- **`EXIT` and `EXIT SUB` (M5c policy).** `EXIT` ends the whole program wherever it is executed (main line, handler, or a procedure at any call depth): the window is removed and `os_app_exit` is called. `EXIT SUB` (M5c) returns early from the current procedure, exactly as if `END SUB` had been reached; outside a `SUB` it is a compile error. In a button handler, `EXIT SUB` therefore returns to the event loop, after which the bound controls are updated as usual.

**Dialog programs — contract (M3a: WINDOW, LABEL, BUTTON; M3b: TEXTBOX, CHECKBOX, below).**

1. Main-line statements run first, exactly as in a program without `WINDOW` (`MESSAGE` alerts appear on the desktop before the window). `END` ends the main line; the program does not stop there.
2. The window then opens: title, labels in source order, buttons in source order in one centred row (M5d: two rows when there are more than 3). The first button has the keyboard focus highlight (M5d: the `DEFAULT` button, if there is one).
3. The program waits for events. A **mouse click on a button** runs that button's `SUB` once, to completion (including any `MESSAGE` alerts it shows); then the program waits again. Each click is one run of the handler; variables keep their values between clicks (one global scope). Two buttons may name the same `SUB`.
4. Nothing else runs BASIC code: clicks on labels or the window background, double-clicks, keys and other OS messages are handed to Rosanne (`os_process_event`, per ROSAN283's event table) or ignored, and the program keeps waiting. A click outside the window does not close it (the definition's exit-by-click flag is 0). **Buttons cannot be activated from the keyboard in M3a** (M5d: except Return for a `DEFAULT` button, below).
5. The program ends when a handler (or the main line) executes `EXIT`, or when Rosanne sends its exit message (`om_exit`). Either way an open window is removed (`os_dialog_remove`, restoring the screen) before `os_app_exit`. A runtime error (§8) in a handler is reported the same way and also removes the window.
6. If Rosanne refuses the dialog definition or display, the program shows `Runtime error: the window could not be opened` and exits.

**M3b — controls bound to variables (implemented: TEXTBOX, CHECKBOX).** `TEXTBOX name [, "caption"]` shows an editable single-line text field bound to the STRING `name`; `CHECKBOX name [, "caption"]` shows a tick box bound to the BOOLEAN `name`. Each declares its variable if no `DIM` did (types must agree). Values move between variables and controls **only** at these points:

| When | Direction | Detail |
|---|---|---|
| The window opens (after the main line) | variable → control | every control shows its variable's value: a TEXTBOX its text (empty string: an empty field), a CHECKBOX ticked for TRUE |
| The user types or ticks | — | Rosanne edits the control; **no BASIC code runs and variables do not change yet** |
| A button is clicked | control → variable, then the handler | every bound variable receives its control's current value, then the button's SUB runs |
| The handler returns | variable → control | each control whose variable now differs from it is updated on screen; unchanged controls are left alone |
| `EXIT`, Rosanne's exit message, a runtime error | none | the program ends; edits made since the last button click are discarded |

Consequences: a handler always sees what is on screen at the moment of the click; a handler may set bound variables (e.g. clear a field, tick a box) and the window shows the new values when it returns; repeated clicks repeat the cycle. A TEXTBOX holds at most capacity − 1 characters (Rosanne refuses more while typing); because the program-wide capacity also bounds the variable, a control value always fits its variable — if Rosanne ever returned more, the copy stops with `Runtime error: string too long at line N` (N = the TEXTBOX line), never an overrun. Characters typed are copied byte for byte (Rosanne's typography codes ≥ 128 included).

**M5d — labels that change, more buttons, the Return key.**

*Dynamic labels.* `LABEL Name$` (a STRING variable instead of a literal) shows the variable's current text in a label row; `LABEL "text"` is unchanged. The variable is declared by the `LABEL` if no `DIM` did (like `TEXTBOX`); it must be STRING (`LABEL Count` with an INTEGER is a compile error: use a STRING and `STR$`). A dynamic label follows the §5 synchronisation table in one direction only (variable → screen):

| When | What the label shows |
|---|---|
| The window opens (after the main line) | the variable's value |
| A button's handler is running (including everything it `CALL`s and any `MESSAGE` it shows) | **unchanged**: the label still shows the value from before the click |
| The handler returns | the variable's new value, if it differs from what is shown; the old text is erased completely first (each dynamic label has its own background box, repainted before the text — the M3b TEXTBOX redraw rule) |

A dynamic label shows **at most 24 characters, each a printable ASCII character** (space `" "` to `~`, codes 32–126). Both rules are checked at the moment the window would show the value (opening, or after a handler), before anything is defined or drawn:

1. a value longer than 24 characters stops the program with `Runtime error: string too long at line N`;
2. a value containing any other character (a control code, code 127, or Rosanne's accented and typographic codes 128–255) stops the program with `Runtime error: label text has an unsupported character at line N`.

N is the `LABEL` line. Text is never cut. *Basis (M5d recovery):*
- XAnne showed Rosanne sometimes drawing a label wider than its object outside the window, unclipped (D3).
- Rosanne's own width call (`os_dialog_string_width`) returned an error in every XAnne test (WIDTHDG), so the program could not measure text. (M11 found that the call returns the correct width despite its error flag; `TEXTWIDTH` uses it, §5.6. The label rule below is unchanged.)
- The content therefore bounds the width instead. A capital `W`, the widest letter, is 11 px in the dialog font (measured in XAnne). With every printable character assumed to be at most 12 px — checked one character at a time in XAnne by script G1 — 24 characters take at most 288 px, inside the label's 305 px.

Use `LEFT$` to shorten values that could be longer, and keep typed text that may contain accented characters out of labels.
*Static* labels (`LABEL "text"`) keep their 47-character limit: their text is fixed and seen when the program is written (risk R-LABELW). A variable may be shown by one control only: it cannot be both a dynamic `LABEL` and a `TEXTBOX`.

*Button layout.* A window has **1 to 6** buttons. Up to 3 sit in one centred row at y=180, exactly as before. With 4 to 6, the first three keep that row and the rest form a second centred row at y=208, in source order; the row pitch is 28 px and both rows lie inside the window's background box. Every button runs its own `SUB` on a click, whatever its row. Other widgets still end above y=180. A seventh button is a compile error.

*The Return key: `BUTTON "caption", Handler, DEFAULT`.* At most one button per window may be marked `DEFAULT` (`DEFAULT` is only special in this position; it is not a reserved word). That button:
1. is given the Return key in its definition. ROSAN283 'os_dialog_define' gives every `ob_textbutton` "Keycodes (4 pairs of Ascii, Shift[#80=ignore])". The code is #0D: CONSTBIO.Z80 `kc_return` = `kc_enter` = #0D, so the keypad Enter key matches as well, with the shift state ignored (#80). This is how Amstrad's own OK buttons are defined (NIKMACRO.Z80 `ok_can_help`: `kc_ok,#80,kc_return,#80,kc_enter,#80`);
2. receives the window's initial focus highlight (instead of the first button), so the user can see which button Return will press;
3. runs its handler when Rosanne reports that key as an `obev_key` event on it ("object key pressed (txt/bmpbutton only)", ROSAN283 event table; `obev_key` = 3 in CONSTOS.Z80). The program treats it exactly like a click: controls are read, the handler runs, controls and labels are updated.

What is **not** defined in M5d: Return pressed while a `TEXTBOX` is being edited is handled by Rosanne's text editor first (`os_text_edit` exit code "Return / Enter Key Pressed"); whether the default button then also runs is an XAnne question (K2), and programs must not depend on it. The space bar on a focused button (`obev_focfire`), Tab to move the focus, and other key assignments are not part of the language yet. A program without `DEFAULT` behaves exactly as before. *Evidence status: documented contract; XAnne verification pending (RUNTIME-RESULTS "M5d scripts").*

**Dialog limits (positioned compile errors):** at least one `BUTTON` per `WINDOW` (a dialog with no button has no XAnne-verified way to close — risk R-DLG); at most **6** `BUTTON`s (M5d: one row of up to 3 at the bottom — POC-proven geometry — and a second row of up to 3 below it), at most one `DEFAULT`. The other widgets are stacked top-down in **source order** from y=48 and must end above the buttons at y=180: a `LABEL` row takes 32 px (so 4 labels alone fill it, exactly the M3a layout), a `CHECKBOX` row 28 px, a `TEXTBOX` row 48 px (caption above a framed 300×25 field — a white box with a 1-pixel outline holding a 292×18 text area, the Amstrad `textentry64` pattern); the first widget that does not fit is the error. A program with a `TEXTBOX` needs a string capacity ≤ **64** (63 characters; Rosanne allows 128 — conservative M3b policy). A variable may be bound to only one control.
### 5.1 M6 Phase 1 — native application interfaces

*Evidence status for the whole section:* every OS contract below is documented (ROSAN283, CONSTOS, CONSTBIO, Amstrad's NIKMACRO/MACROS) and exercised by the simulator, but **none is XAnne-verified yet**. The probe UIPROBE.PRG and the Phase 1 acceptance scripts (RUNTIME-RESULTS "M6 Phase 1 scripts") verify them. Where Rosanne's behaviour is uncertain, the runtime does the work itself (noted per feature), so the contract below does not depend on the uncertain part. Programs that use none of these features compile to exactly the bytes they had before.

**Windows.** `WINDOW "title" [, LARGE]` declares the single window of a program, as before. A program may instead declare **2 to 8 named windows**: `WINDOW Name, "title" [, LARGE]`. Every `LABEL`, `TEXTBOX`, `CHECKBOX`, `RADIO`, `NUMBERBOX` and `BUTTON` belongs to the most recent `WINDOW` above it (with named windows, a control before the first `WINDOW` is an error). Each window has its own layout and limits (§5 dialog limits, per window) and needs at least one `BUTTON`. A variable may be bound to one control per window; the same variable may appear in several windows. `LARGE` makes a window 600×400 at screen 20,50 instead of 360×240 at 140,110; rows are stacked the same way, buttons sit in two centred rows at y=340 and y=368, and every label, field and caption keeps the width it has in a normal window (so the character limits of §5 and §6 are unchanged).

`SHOW Name` (a statement, anywhere in code) chooses a window. In the main line it chooses which window opens when the main line ends (default: the first declared). In a handler it takes effect when the handler returns: the current window closes (`os_dialog_remove`) and `Name` opens with every control set from its variables, exactly as the first window opens. `SHOW` of the window already open does nothing. Only one window is on screen at a time. `SHOW` needs named windows.

**Radio buttons.** `RADIO Choice, "First", "Second" [, …]` shows 2 to 6 options, one per 24-px row, and binds the INTEGER `Choice` (declared by the `RADIO` if needed; a `$` name is an error): 0 = no option selected, 1..n = that option. Clicking an option selects it and clears the others in the group; the runtime enforces this itself after every click, whatever Rosanne does with the other members (ROSAN283 gives `ob_radio` a status and a radio number, but does not say who clears the group — XAnne P2). Values move like a `CHECKBOX` (§5 table): read before each handler, shown after it. A handler setting `Choice` outside 0..n stops the program: `Runtime error: option number out of range at line N` (N = the `RADIO` line). Captions: ≤ 34 characters, ASCII (like `CHECKBOX`). At most 16 `RADIO` groups per window (ROSAN283 radio numbers 0..15).

**Number fields.** `NUMBERBOX N [, "caption"] [, MIN lo] [, MAX hi] [, SPIN]` shows a framed field of up to 6 characters that accepts only `-` and the digits `0`–`9` (an explicit legal-character list in the field's definition, ROSAN283 `os_text_edit` +21/+24), and binds the INTEGER `N`. `lo`/`hi` are integer literals, default −32768 and 32767, `lo ≤ hi`. The row is 48 px, like a `TEXTBOX`. `SPIN` adds Rosanne's spinner (`ob_spinner`) beside the field; each up/down click changes the shown number by 1 within `lo..hi` (the runtime applies it: ROSAN283 says spinner values are not recorded by Rosanne). Values move like a `TEXTBOX`, with two rules:
1. Before a button or menu handler runs, the field must hold a whole number from `lo` to `hi` (optional `-`, digits). Otherwise the handler does **not** run: an alert says `caption: enter a whole number from lo to hi` (or `Enter a whole number from lo to hi` without a caption), the field is put back to the last valid number it showed, and it gets the focus — so the next button or menu choice is not refused again. Before a `TIMER` handler, an invalid field is simply left alone and `N` keeps its value.
2. After a handler, the field is redrawn only if the handler changed `N`. A handler setting `N` outside `lo..hi` stops the program: `Runtime error: number out of range at line N` (N = the `NUMBERBOX` line).

**Questions.** `Answer = ASK(text, "b1", "b2" [, "b3"])` shows Rosanne's alert (`os_alert`) with 2 or 3 buttons and stores 1, 2 or 3 — the button chosen — in the INTEGER `Answer`. `ASK` may only be the whole right-hand side of an assignment to an INTEGER variable. `text` is any STRING expression, budgeted like a dynamic `MESSAGE` against **100** bytes; button captions are ASCII literals of 1 to 10 characters. The first button also answers to Return and the Green key; the last to Stop and the Red key. If Rosanne refuses the alert, `Runtime error: the question could not be shown at line N`.

**Beep.** `BEEP` sounds Rosanne's beep (`os_beep`).

**Focus.** `FOCUS Name` moves the keyboard focus (`os_set_focus`) to the `TEXTBOX`, `NUMBERBOX` or `CHECKBOX` bound to `Name`. It takes effect when the handler returns, or when its window next opens; `Name` must be bound in exactly one window.

**Button keys.** `BUTTON "caption", Handler [, DEFAULT] [, KEY k]…` gives a button up to three more keys, `k` one of `GREEN`, `RED`, `BLUE`, `YELLOW`, `STOP`, `HELP`, `F1`…`F8` (CONSTBIO key codes, shift state ignored). A key may belong to only one button in a window (`DEFAULT` holds Return). A key press runs the handler exactly like a click (§5, M5d).

**Menus.** A program with at least one `WINDOW` may declare up to **8** menus, each a block:
```
MENU "File"
  ITEM "New", NewOrder, KEY "N"
  ITEM "-"
  ITEM "Sound", ToggleSound, TICK SoundOn
END MENU
```
The menu bar shows Rosanne's Tasks menu first (`os_ddm_get_tasks`), then the program's menus in source order (`os_ddm_define`, `os_ddm_display`), built in the app workspace at #2400–#2BFF of block #80. Every window of such a program allows menus while it is open (global `ddm_enable` = 1). Each `ITEM` runs its `SUB` when chosen, exactly like a button (values read, handler, values shown). `ITEM "-"` is a divider line. `KEY "X"` (a letter or digit) makes Ctrl+X choose the item. `TICK Flag` shows the BOOLEAN `Flag` (declared by the `TICK` if needed) as a tick beside the item: the runtime sets the tick from `Flag` when the first window opens and after every handler (`os_ddm_put_entry_status`); the handler decides what choosing the item does to `Flag`. Limits (policy, conservative): menu title ≤ 12 characters, item text ≤ 20, printable ASCII without `|`; ≤ 20 items per menu including dividers; the Tasks menu plus the program's menus must fit the 2048-byte area (`Runtime error: the menus are too large` otherwise — never cut). *Assumption checked by UIPROBE P1:* the Tasks menu is title 0 and the program's menus are titles 1..n, with dividers counted as items.

**Timer.** `TIMER Handler, EVERY n` (top level, at most one, `n` an integer literal 1..3599 seconds) runs `Handler` every `n` seconds while a window is open (Rosanne timer 0, repeating; `os_set_timer`). Since M13, `TIMER Handler, EVERY n TICKS` gives the interval in sixteenths of a second instead (n 1..32767, §5.15). It starts when the first window opens. The statements `TIMER OFF` and `TIMER ON` stop and restart it. A timer handler runs between other events, never during one, with the same value movement as a button handler (rule 1 above for number fields). The timer is stopped before the program exits.

**What Phase 1 does not define:** greying menu items or controls, raw keyboard or mouse events (M9 added them for a CANVAS: `MOUSE` and `KEYS` handlers, §5.6; M13 added `KEYDOWN`, §5.15), double-clicks, nested (modal) windows, window positions other than the two sizes, text fields over 63 characters or several lines, and any font other than Rosanne's dialog defaults.

### 5.2 M6 Phase 2 — arrays and data-rich controls

*Evidence status:* documented contracts (ROSAN283 `ob_list`, `ob_vscroll`, `ob_hscroll`, `ob_dropbutton`; NIKMACRO `n_list_box`; MACROS `bb_droplist`), simulator and independent-core runs only — **not XAnne-verified**. UIPROBE2.PRG and `docs/M6-PHASE2-ACCEPTANCE.md` check them. Programs that use none of these features compile to the bytes they had before.

**Arrays.** `DIM Name(n) AS INTEGER|STRING|BOOLEAN` (n an integer literal 1..250) declares a one-dimensional, 1-based array; a STRING array's elements each have the program's string capacity. `Name(i)` reads an element anywhere an expression may appear; `Name(i) = value` assigns one (`ASK` may not be assigned to an element). The index is any INTEGER expression; outside 1..n the program stops with `Runtime error: index out of range at line N`. An array name is never usable without an index, may not be bound to a control (except as the items of a `LIST`/`CHOICE`), and may not reuse a built-in function's name.

**Lists.** `LIST Sel, Items$, Count [, ROWS r] [, CHANGE H] [, ACTION H2]` shows the first `Count` elements of the STRING array `Items$` in a framed list of `r` rows (2..12, default 5; 16 px per row, font 7) with a vertical scroll bar, and binds the INTEGER `Sel` (declared by the `LIST` if needed): 0 = nothing selected, 1..Count = that item. `Count` is an INTEGER variable or literal (literal: 0..n). Rows past `Count` are blank (owner XAnne, M7 retest: Rosanne draws every visible row from the item table, so the runtime points unused rows at an empty text). Clicking an item selects it (Rosanne records the selection); `Sel` is read before every handler like a field. After every handler the list is rebuilt from the array and `Count` (so changed texts appear), keeping the visible rows unless the handler changed `Sel`, in which case the list scrolls to show the new selection. `CHANGE H` runs `H` after the user selects an item; `ACTION H2` runs `H2` on a double-click (without `ACTION`, a double-click runs `CHANGE`) — **KI-25: XAnne reports a double-click on a list as two ordinary clicks (EVPROBE), so ACTION never runs there.** The clause is kept for a Rosanne that reports `obev_dclick`; programs should offer a button for the same action. The scroll bar's arrows step one row, its track one page (`r` rows), and dragging its handle moves proportionally; the runtime applies these itself (ROSAN283: scroll bars are not recorded by Rosanne) and scrolling never changes `Sel`. Errors, at the `LIST` line: `Count` outside 0..n — `Runtime error: list count out of range`; `Sel` outside 0..Count — `Runtime error: list position out of range`; a shown item over 24 characters — `Runtime error: string too long`; a shown item with a character outside printable ASCII — `Runtime error: list text has an unsupported character`.

**Drop-down choices.** `CHOICE Sel, Items$, Count [, "caption"] [, CHANGE H]` shows a framed readout with Rosanne's drop button; clicking the button opens a list of up to 6 rows below it; choosing an item sets `Sel` and the readout. A CHOICE always shows one item: `Sel` must be 1..Count and `Count` at least 1 whenever the window shows it (a literal `Count` of 0 is a compile-time error), otherwise the program stops with `Runtime error: a CHOICE must show an item from 1 to its count at line N`. Rosanne has no safe "none" state: a drop button given current #FFFF froze XAnne when opened (owner, UIPROBE3 F), so a new INTEGER's default 0 must be set before the window opens. Rosanne writes the readout itself (UIPROBE2 U1, U6). Rebuilding and the other errors are as for `LIST`. The drop-down list must fit inside the window (else a compile-time error naming the CHOICE).

**Sliders.** `SLIDER V, MIN lo, MAX hi [, "caption"] [, CHANGE H]` shows a horizontal scroll bar (280 px) and binds the INTEGER `V` (lo, hi integer literals, 1 ≤ hi − lo ≤ 250). Arrows change `V` by 1, the track by max(1, (hi − lo) / 10), dragging the handle sets it proportionally, always within lo..hi; `CHANGE H` runs after each change. The value lives in the runtime (Rosanne does not record scroll bars); after a handler the slider is redrawn only if `V` changed. `V` outside lo..hi when shown: `Runtime error: number out of range at line N`. At most 16 sliders per program.

**Change handlers.** `CHANGE`/`ACTION` handlers run when the event has been handled, with the same value movement as a button handler, except that a `NUMBERBOX` holding invalid text is left alone (as before a `TIMER` handler). After each scroll step the runtime discards input queued while the control was redrawn (`os_flush_events`, as for spinners). *Known limitation (owner XAnne, as for spinners in Phase 1):* one click on a slider arrow sometimes moves it by more than one step; the cause is unproven.

**What Phase 2 does not define:** multi-selection lists, lists of other types than STRING, two-dimensional arrays, keyboard navigation guarantees for lists (whatever Rosanne does with keys on a list is reported but not specified), and vertical sliders.

### 5.3 M7 — procedures, constants, SELECT CASE, loops, built-ins

*Evidence status:* simulator, memory checker and independent Z80 core only — **not XAnne-tested**. Programs that use none of these features compile to the bytes they had before (40 accepted executables byte-identical). Implementation: `pbas/lower.py` rewrites procedures, CONST and SELECT CASE into the statements of §5–§6.

**Procedures with parameters.** `SUB Name(a AS INTEGER, b$, c AS BOOLEAN)` declares typed parameters; a `$` name without `AS` is STRING. `CALL Name(x, y)` passes values (by value: the procedure gets copies). The argument count must match, and each argument must have the parameter's type (`cannot assign … to … variable X (in Name)`). A STRING parameter has the program's string capacity; a longer value is the usual `string too long` runtime error at the CALL. `CALL Name` and `CALL Name()` call a SUB without parameters. A SUB with parameters, or a FUNCTION, cannot be a BUTTON, ITEM, TIMER or CHANGE/ACTION handler.

**Functions.** `FUNCTION Name(params) AS type … END FUNCTION` returns a value with `RETURN expr` (which also leaves the function). `EXIT FUNCTION` leaves it too. A function that ends without RETURN returns 0, "", FALSE (or 0.0). Call it in any expression: `X = Twice(Y) + 1`. Rules:
- **Order:** the calls in a statement run *before* the statement, left to right, innermost first, each result held in its own temporary. A call in the right operand of `AND`/`OR` runs only when that operand is needed (§3): since M13 the compiler turns `a AND F(x)` into `T = a`, `IF T THEN T = F(x)` (and `a OR F(x)` into `IF NOT T …`), when the AND/OR is plainly BOOLEAN (one side a comparison, `NOT`, `TRUE`/`FALSE` or a FUNCTION AS BOOLEAN). Otherwise (before M13, always) such a call is a compile error; compute it in a separate statement. A WHILE condition's calls are re-run before every test.
- **No recursion** (direct or indirect): compile error naming the cycle. Parameters, locals and results have static storage (one copy per procedure), so the M5c rule stands; at most 16 procedures may be active at once.
- `CASE` values may not call a FUNCTION.

**Local variables.** `LOCAL Name AS type` inside a SUB or FUNCTION declares a variable visible only there, reset to 0 / "" / FALSE each time the procedure starts. It hides a global of the same name inside the procedure. LOCAL arrays are not supported (use a global DIM). `DIM` keeps its meaning everywhere: it always declares a global, as in earlier milestones. Parameters behave like locals that are set by the caller.

**Constants.** `CONST Name = literal` (top level; an INTEGER, STRING, BOOLEAN or REAL literal, optionally signed) gives a name to a value. Every use is replaced by the literal, so a CONST can be a STEP or a CASE value. A CONST cannot be assigned or declared again. Since M13 a parameter or LOCAL may have a CONST's name, as it may have a global variable's: inside that procedure the name is the parameter or LOCAL, everywhere else the CONST (so a library's parameter names never clash with a program's constants).

**SELECT CASE.**
```
SELECT CASE expr
CASE 1, 3, 5            ' equal to any of the values
CASE 10 TO 20           ' within the range, inclusive
CASE IS >= 100          ' a comparison (=, <>, <, <=, >, >=)
CASE ELSE               ' optional, last
END SELECT
```
- `expr` is evaluated once; CASE values must have its type.
- The first matching CASE runs, and only that one. CASE ELSE runs if none matched; no match and no CASE ELSE does nothing.
- Statements between `SELECT CASE` and the first `CASE` are not allowed (a compile error; up to M13 the compiler accepted them and never ran them, §5.16).

**Loops.**
- `FOR … STEP s` accepts any non-zero INTEGER constant (a literal or CONST). The loop runs while the counter has not passed the limit and never wraps past −32768/32767 (`FOR I = 32760 TO 32767 STEP 4` runs 32760 and 32764).
- `EXIT FOR` and `EXIT WHILE` leave the innermost enclosing loop of that kind in the same procedure.

**Integer bit operators.** `AND`, `OR`, `NOT` and the new `XOR` take two BOOLEANs (logical; AND/OR still short-circuit) or two INTEGERs (bitwise on the 16-bit two's-complement value, both operands evaluated): `12 AND 10` = 8, `NOT 0` = −1. Mixed BOOLEAN/INTEGER is a compile error. `XOR` binds more loosely than `OR`. `XOR` is now a reserved word.

**New built-in functions.**
- `ABS(n)` (`ABS(-32768)` stays −32768, wrapping as in §2), `SGN(n)` (−1, 0, 1).
- `MIN(a, b)`, `MAX(a, b)`.
- `SHL(x, n)` / `SHR(x, n)`: logical shift. n ≥ 16 gives 0; n < 0 is `Runtime error: number out of range`.
- `RND(n)`: a pseudo-random INTEGER 1..n (n ≥ 1, else `number out of range`). It uses a 16-bit xorshift generator, so the sequence is reproducible: the same sequence every run until `RANDOMIZE seed` (seed 0 means seed 1). `RANDOMIZE` with no seed mixes in the Z80 refresh register: varying, not cryptographic.
- `TRIM$(s)`, `LTRIM$(s)`, `RTRIM$(s)`: remove spaces (code 32 only). The argument is built in the destination first, so it must fit there.
- `SPACE$(n)`, `STRING$(n, code)`: n copies of a space or of character `code` (1..255). A negative computed n is the substring runtime error; a computed n may produce at most 127 characters.

- Unreachable statements after `END` are an error; every block (`IF`, `WHILE`, `FOR`, `SUB`) must be closed; `ELSE`/`NEXT name` matching follows POC rules (error on mismatch, counter name optional but checked when given).

### 5.4 M8 — BANKED arrays and STRING * n

- **Evidence status.**
  - Documented Rosanne contracts: ROSAN283 `os_get_mem`, `os_get_mem_ownerid`, `os_copy_24bit`, `os_release_mem`, "NEVER use RAM which you haven't officially got from the OS".
  - **XAnne-verified** (owner, M8 final acceptance: MEMPROB2, BANKTEST, CONTBOOK, RECORDS), after the KI-34 correction for Rosanne's end-of-last-block copy carry. Emulator only, no real hardware.
  - Programs that use neither feature compile to the bytes they had before.

**STRING * n.**

- **Syntax.** `DIM S$ AS STRING * n` and `DIM A$(k) AS STRING * n` give that variable or array its own capacity: n characters (1..126), n + 1 bytes. Every other string keeps the program-wide capacity (`--string-capacity`, §4).
- **Behaviour.** Everything else is as for any STRING: the overflow rules of §4 apply with that capacity.
- **TEXTBOX.** A `TEXTBOX` bound to such a variable accepts at most n characters.
  - `* n` must appear on the `DIM`, and that `DIM` must come before any `TEXTBOX` or `LABEL` that names the variable (a compile error otherwise).
  - `LOCAL` and parameters have no `* n` form.
- **Why.** It lets a program spend 25 bytes on a 24-character name instead of the program-wide 64. M8's examples rely on it to fit.

**BANKED arrays.**

- **Syntax.** `DIM A(k) AS INTEGER|BOOLEAN|REAL|STRING [* n] BANKED` (k 1..32767) keeps the array outside the program's 16K, in 16K blocks of RAM that the program gets from Rosanne when it starts.
  - `BANKED` is a word only in this position. A variable named `Banked` is still allowed.
  - Only arrays can be BANKED.
- **Use.** Elements are used exactly like ordinary elements: in expressions, as assignment targets, in `PRINT #` and as the target of `LINE INPUT #`, and in procedures and handlers.
- **Element size and blocks.** The element size is 2 bytes (INTEGER, BOOLEAN), 5 (REAL) or n + 1 (STRING * n; else the program-wide capacity).
  - A block holds 16384 div size elements, and an element never crosses a block end.
  - Each BANKED array has its own blocks.
  - All BANKED arrays together may use at most **32 blocks (512K)**, a compile-time check.
- **Start-up.** Before the first statement the program asks Rosanne for all the blocks at once.
  - It checks that each block is RAM and belongs to the program (the owner of the program's own block).
  - It clears them: every element starts as 0, or as the empty string.
  - If fewer blocks are given than needed, it gives back the ones it got and stops with `Runtime error: not enough free memory for BANKED arrays at line N`, where N is the line of the first BANKED `DIM`.
  - A block that is not RAM, or that belongs to someone else, is treated the same way: it is never written.
- **Lifetime.** The blocks are given back on every way a program ends: `END`, `EXIT`, a runtime error, or the system Quit (Tasks → Exit).
- **Indexes.** Outside 1..k the program stops with `Runtime error: index out of range at line N`, as for ordinary arrays.
- **Limits.**
  - **Reads per statement.** At most **4 BANKED elements** may be read by one statement (a compile error otherwise: copy some into variables first). The runtime keeps four copies at a time; a fifth would overwrite the first while it is still in use.
  - **LIST and CHOICE.** They cannot show a BANKED array, because their rows point into the program's own memory (compile error). Copy the rows to show into an ordinary array, as `examples/contacts_m8.pbas` does with one page.
  - **No passing whole arrays.** There are no whole-array operations, and an array cannot be a parameter (as for ordinary arrays).
  - **Speed.** Each element access is a Rosanne copy call (`os_copy_24bit`). It is much slower than an ordinary element, so a loop over thousands of elements takes noticeably longer.
- **Errors.**
  - **At compile time:**
    - `only an array can be BANKED`;
    - `a BANKED array has 1 to 32767 elements`;
    - `an array has 1 to 250 elements, got N (a larger array can be BANKED)`;
    - `BANKED arrays may use at most 32 16K blocks together (512K)`;
    - `LIST cannot show the BANKED array …` (or `CHOICE`);
    - `this statement reads N BANKED array elements; at most 4 are allowed`;
    - `STRING * n holds 1 to 126 characters`.
  - **At run time:**
    - `not enough free memory for BANKED arrays`;
    - `a BANKED array block could not be copied` (Rosanne refused a copy; the program stops and releases its blocks).

**Program image.** The program's main line, ordinary variables, GUI definitions and the runtime have to fit the first 16K block (#4000–#7FFF). Banked data does not count against it. Since M9, SUB and FUNCTION code does not have to fit either: see §5.5 (code banks).

**Smaller programs (M8 build change).** A program that uses REAL now includes only the parts of the REAL library it can reach.

- Results are unchanged; images are smaller (JOURNAL: 2,973 bytes less).
- `tools/build.py --whole-real-library` builds as M7 did, byte for byte.

### 5.5 M9 — code banks (programs larger than 16K)

*Evidence status:* simulator and independent-core evidence. The two Rosanne contracts it rests on — a program can read the rest of its own `.PRG` into RAM it got from the OS and run code from it at #8000, and an OS call from there returns there — passed in XAnne with the hand-written CODEPROBE (M8). **XAnne (owner, M9):** BANKPROB A0–A7 passed. It covered event handlers, dialogs, alerts, timer, menu and file calls from banked code, an error exit, a relaunch, and no leaked block. MDEDIT (one bank) passed E1–E10 (RUNTIME-RESULTS "M9 owner XAnne").

- **What changes for the programmer: nothing in the source.** A program whose image would exceed 16K is built with its SUBs and FUNCTIONs in *code banks*; the language is the same and no bank number ever appears in a program.
- **Build option** `tools/build.py --code-banks auto|always|never` (default `auto`): `auto` builds one 16K image when the program fits — exactly the bytes it had before M9 — and code banks only when it does not; `always` banks every procedure (probes and tests); `never` keeps the M8 behaviour (an error when the image is over 16K). `--code-bank-limit BYTES` (64..15872) caps a bank, to spread a small program over several banks.
- **Placement.** Every SUB and FUNCTION goes to a bank. Banks are filled first-fit in decreasing order of procedure size (ties in source order), deterministically: the same source always gives the same file. A `<name>.map` file beside the `.asm` lists every bank, its procedures and their sizes.
- **What stays in the first 16K (the resident part):** the main line, all variables and data, dialog and menu definitions, the runtime, and an 8-byte stub per procedure. If that part alone is over 16K: compile error `the resident part is N bytes …` (move work from the main line into SUBs, or large arrays to BANKED).
- **Limits.** A single procedure must fit one bank: at most 15,866 bytes of code (`procedure is N bytes of code, over the …-byte limit of one code bank` at its line — split it). At most 16 banks (about 250K of procedures).
- **Running.** When the program starts it asks Rosanne for one 16K block per bank (before any BANKED array), checks each is RAM and its own, reads its own `.PRG` file from the folder it was started from (the first 16K is skipped, each bank read in pieces of at most 8K) and checks each bank (marker and checksum). A call to a procedure in another bank maps that bank at #8000 and maps the caller's block back when it returns; handlers, menus, the timer and runtime errors work as before.
- **Start-up errors** (the program then ends, every block given back): `Runtime error: not enough free memory for the program's code`; `Runtime error: the program's code could not be read from its file` (the file is missing, renamed, damaged or shorter than built). A code-banked program must be run under its own file name from its own folder: copying only part of the file, or renaming it after it has started, is not supported.
- **Cost.** A call into another bank costs two BIOS calls more than an ordinary call; the banks are read once, at start.
- **M11: the runtime bank** (`tools/build.py --runtime-banks all|SECTION,...`; `pbas.prg.build(runtime_sections=...)`). The code of chosen runtime sections goes to one more code bank, loaded and checked like the others; their data stays resident, and each routine used from outside the bank keeps its name as a 6-byte resident entry that maps the bank, runs the routine with every register and flag as the caller left them, and maps back the previous block. Movable sections: DB, CANVAS, CVLINE, CVCELL, FILES, FIO, FNAME, NUMBERS, MENUS, LIST, CHOICE, SLIDER, and since M12–M13 BITMAP, BMPFILE, POINT, PAGE and BMPPART (only those a program uses are present; `all` = every movable one; `pbas/rtbank.py` MOVABLE is the list). Nothing in the source changes; without the option a program builds exactly as before. A routine that would be entered by a jump, or would leave by jumping into a resident loop, stays resident (docs/M11-ARCHITECTURE.md §2.2). Cost: a call from outside the bank into it costs three BIOS calls more. The resident-overflow error suggests the option. *Evidence status:* simulator (behaviour identical to the plain build through whole CONTACTS III and MDEDIT II sessions) and independent core; **not XAnne-tested** (docs/M11-ACCEPTANCE.md).

### 5.6 M9 — CANVAS, drawing and canvas events

*Evidence status:* **XAnne-accepted (owner, M9):** GFXPROBE G1–G7, UIBENCH and GFXBENCH, after the Rosanne 1.12 corrections KI-46 (grey 0..7; result in carry) and KI-49 (sloped lines as runs). The keys reaching KEYS are the G4 table (KI-41). Not measured in XAnne: drawing speed.

**Declaration.** `CANVAS width, height [, PAINT P] [, MOUSE M] [, KEYS K]` in a `WINDOW` adds a drawing area: a white box with a 1-pixel black frame, stacked in source order like the other rows (height + 8 px), at x = 26. width and height are integer literals, 16..568 and 16..300; it must fit its window (a normal window holds 330 px across, a LARGE one 568). A program has at most one CANVAS. `P`, `M`, `K` are SUBs without parameters. `CANVAS` and `DRAW` are statement words only at the start of a statement; programs may still use them as names.

**Coordinates.** Pixels inside the frame: (0, 0) is the top-left drawing pixel, x grows right, y down, up to width − 1 and height − 1. **Every drawing must lie inside the canvas** — otherwise the program stops with `Runtime error: drawing outside the canvas at line N` (nothing is drawn, nothing is clipped silently). The only exception is text, which is cut at the right edge (below).

**Drawing statements** (each needs the canvas's window to be on screen: `Runtime error: the canvas is not on screen at line N` otherwise, e.g. in the main line before the window opens):

| statement | draws |
|---|---|
| `DRAW CLEAR` | the whole canvas white |
| `DRAW FILL x, y, w, h [, shade]` | a filled rectangle; shade 0 (black, default) .. 8 (white), Rosanne's grey levels (`Runtime error: a shade is 0 to 8`); 8 is drawn as a white block, 0..7 as Rosanne's grey patterns (KI-46) |
| `DRAW INVERT x, y, w, h` | every pixel of the rectangle flipped (selections, carets) |
| `DRAW BOX x, y, w, h` | a 1-pixel outline of the rectangle |
| `DRAW LINE x1, y1, x2, y2` | a line between two points of the canvas, both included; in XOR ink each of its pixels is inverted once |
| `DRAW PIXEL x, y` | one pixel |
| `DRAW TEXT x, y, text$` | text in Rosanne's dialog font 7, its top-left at x, y; a whole line (16 px) must fit below y |
| `DRAW TEXT x, y, text$, cell` | M11: the same text on a fixed grid — each character drawn on its own at x + i × cell. cell is 11 .. 64 (`Runtime error: a text cell is 11 to 64 pixels`); only the characters whose cells fit before the right edge are drawn; a space's cell is left as it is. **Not recommended for text people read** (owner, XAnne): font 7 is proportional (3–13 px a character), so text on an 11 px grid looks letter-spaced, and the twelve glyphs wider than 11 px reach into the next cell. Each character is a separate OS call. Use `DRAW TEXT x, y, text$` and `TEXTWIDTH` instead (docs/M11-CORRECTIVE.md) |
| `DRAW SCROLL x, y, w, h, dx, dy` | the rectangle's contents move by dx, dy (\|dx\| < w, \|dy\| < h); what moves out is lost, the uncovered strip becomes white |
| `DRAW INK BLACK` / `WHITE` / `XOR` | the ink for LINE, PIXEL and BOX (XOR flips pixels); TEXT is drawn black on white, or XOR with `INK XOR` |

**Measuring text (M11 corrective).** `TEXTWIDTH(s$)` is the width in pixels of `s$` as `DRAW TEXT` draws it (font 7, characters outside 32..223 as `?`), from Rosanne's `os_dialog_string_width`. Rosanne 1.12 reports an error flag on every call but returns the correct width (docs/M11-CORRECTIVE.md §3: matched exactly against the font's own advances), so the flag is ignored. Widths add up: `TEXTWIDTH(a$ + b$) = TEXTWIDTH(a$) + TEXTWIDTH(b$)`, so a caret before character n of a line drawn at x is at `x + TEXTWIDTH(LEFT$(line$, n))`. TEXTWIDTH needs no canvas. *Verified in XAnne (RENDPRB W1: eight strings, each width matching its drawn text).* Text of the program's own, measured this way, is how MDEDIT III and `lib/listview.pbas` place selections, carets and columns.

**The clock (M11 corrective).** `SECONDS` is minutes × 60 + seconds of the PcW16's clock (0..3599, from `bios_gettime`), for timing: an interval is `(SECONDS - start + 3600) MOD 3600` seconds while it is under an hour. A variable of the program's own called `Seconds` keeps its meaning.

w = 0 or h = 0 draws nothing. **Text** shows at most (width − x) div 11 characters (11 px is the widest glyph of font 7; Rosanne's width call does not work in XAnne, M5d), so narrow text may stop short of the edge (M11: `TEXTWIDTH` measures text exactly, below); characters outside 32..223 are shown as `?`. Drawing is done with Rosanne's direct screen calls and the BIOS graphics calls (`docs/M9-GRAPHICS-UI-API.md`); the mouse pointer is hidden while the BIOS draws.

**PAINT.** Runs when the canvas's window opens, and again after any handler during which an alert (`MESSAGE`, `ASK`, a file report) was shown — Rosanne does not say whether it restores what an alert covered. An alert shown by PAINT itself does not cause another PAINT. Programs should draw everything in PAINT. *M10 (KI-59):* a handler that runs `SHOW` for the canvas's window must not draw after it: the window opens when the handler returns, and drawing before that stops the program with "the canvas is not on screen". PAINT runs when the window opens.

**MOUSE.** Runs on a left-button press inside the canvas (`MOUSEEVENT` = 1), on each mouse movement with the button still down after such a press (2, a drag; the position may then be outside the canvas), and on the release (3). `MOUSEX`, `MOUSEY` give the position in canvas coordinates. A press is recognised from Rosanne's raw mouse event or from a click on the canvas's frame object (then the position is `os_get_mouse_xy`). Double-clicks are not reported as such (KI-25).

**KEYS.** Runs for every key Rosanne passes to the program while the canvas's window is open: `KEYCODE` is the key's code (ROSAN283 Appendix A: printable characters as themselves; Return 13, Backspace 8, Tab 9, Delete 229, Up 224, Down 225, Left 226, Right 227, Home 230, End 231, PgUp 232, PgDn 233, Stop 254, f1–f8 241–248), `KEYSHIFT` the shift state (1 Shift, 2 Alt, 4 Ctrl, 16 keypad). The cursor keys and Space that Rosanne reports on a focused button (`obev_curup` … `obev_curpgdn`, `obev_focfire`) arrive as the same codes (shift 0). Keys that belong to a button (`DEFAULT` = Return, `KEY` keys), to a menu (Ctrl+letter), or to a text field with the focus are not passed to KEYS. *Which keys XAnne passes, and in which form, is for GFXPROBE (G4).*

`MOUSEX`, `MOUSEY`, `MOUSEEVENT`, `KEYCODE`, `KEYSHIFT` are INTEGER values usable in any expression of a program with a CANVAS (a compile error otherwise); they keep the last event's values.

**Not defined (M9):** other fonts, text width measurement, clipping, circles and arcs, bitmaps (M12: §5.12), more than one canvas, vertical scroll bars, double-clicks, the right and centre mouse buttons.

### 5.7 M9 — TEXT buffers

*Evidence status:* simulator and independent-core evidence only. The file calls are the XAnne-proven M7 ones (one-byte `os_read_file`, `os_write_file`); mapping a data block at #8000 is the CODEPROBE mechanism. **XAnne-accepted (owner, M9):** MDEDIT E1–E10 loaded, edited and saved EDTEST.MD. The saved file is byte-identical to `artifacts/m9/edtest_expected.md`, through STRING-named TEXT SAVE / KILL / NAME. A save to a write-protected disk (E11(c)) was not run.

**Declaration.** `DIM D AS TEXT * bytes` (1..65535) declares a text buffer: up to `bytes` bytes of a document, kept in 16K blocks the program owns (they count towards the 32-block BANKED limit of §5.4 and are got, checked and given back like BANKED arrays). A TEXT buffer is only ever used through the statements and functions below; it cannot be assigned, compared or passed.

**Bytes and lines.** The buffer holds a document's bytes **exactly** — CR, LF, tabs, zero bytes and bytes over 127 included — so loading and saving an unchanged document gives the same bytes. A line ends at LF; a CR right before that LF belongs to the line's end. The last line has no end (a document ending with a line end has an empty last line). `TEXTLINES(D)` = number of LFs + 1 (an empty buffer has one empty line). Line numbers count from 1; columns are byte positions from 1, and a line's length excludes its end.

| | |
|---|---|
| `TEXT LOAD D, name` | empties D, then reads the whole file into it. `IOERR`: 0, a Rosanne code (2 not found …), or **246** if the file is larger than D (D is then empty) |
| `TEXT SAVE D, name` | writes D's bytes to the file, creating or replacing it (`IOERR` as for `PRINT #`, e.g. 163 disk full) |
| `TEXT CLEAR D` | empties D |
| `TEXT INSERT D, n, col, s$` | inserts s$ in line n before column col (1..length + 1); s$ may not contain CR or LF |
| `TEXT DELETE D, n, col, count` | deletes count bytes of line n from column col; all within the line |
| `TEXT SPLIT D, n, col` | ends line n before column col (1..length + 1): the rest becomes line n + 1. The new line end is of line n's own kind (CR LF or LF); for the last line, of the kind the loaded file used first (CR LF if it had none) |
| `TEXT JOIN D, n` | removes line n's end, joining line n + 1 to it (n < TEXTLINES) |
| `TEXTLINES(D)` | INTEGER, number of lines |
| `TEXTLEN(D, n)` | INTEGER, length of line n |
| `TEXTGET$(D, n, col, count)` | STRING, at most count bytes of line n from col (1..length + 1); fewer at the line's end; a zero byte comes back as `?` |
| `TEXTFIND(D, s$, n, col)` | INTEGER, the line where s$ next occurs at or after line n, column col (case matters; never across a line end); 0 if not found or s$ is empty |
| `TEXTCOL(D)` | INTEGER, the column of the last TEXTFIND's match (0 after none) |
| `TEXTCHANGED(D)` | BOOLEAN, TRUE after an edit until the next LOAD, good SAVE or CLEAR |
| `TEXTFREE(D)`, `TEXTSIZE(D)` | INTEGER, bytes free and bytes used (at most 32767 is reported) |

Positions out of range stop the program with `Runtime error: text position out of range at line N`; an insertion or split that does not fit, with `Runtime error: the TEXT buffer is full at line N` (check `TEXTFREE` first); CR or LF in `TEXT INSERT` text, with `Runtime error: TEXT INSERT text has a line break at line N`.

**M10 additions: ranges and two buffers.**

A *range* is written `n1, c1, n2, c2`. It runs from line n1, column c1 up to, but not including, line n2, column c2. Rules:
- each column is 1..length + 1 of its line;
- the start may not be after the end;
- a range covers the line ends inside it whole: a column never falls between a CR and its LF.

| | |
|---|---|
| `TEXT REMOVE D, n1, c1, n2, c2` | Deletes the range. The line ends inside it go, so lines n1..n2 join. |
| `TEXT COPY Dst, Src` | Dst becomes exactly Src's bytes, and takes Src's line-end style for later SPLITs. |
| `TEXT COPY Dst, Src, n1, c1, n2, c2` | Dst becomes exactly the range's bytes (a clipboard), and takes Src's style. |
| `TEXT PASTE Dst, n, col, Src` | Inserts all of Src's bytes, line ends included, before line n's column col. |
| `TEXTSAME(A, B)` | BOOLEAN: TRUE if the two buffers hold the same bytes. Style and changed flag are not compared. |

- **Two different buffers:** COPY and PASTE need two different buffers (a compile error otherwise).
- **Errors leave the buffers unchanged:**
  - a bad position is the position error;
  - a destination too small is `the TEXT buffer is full`, raised before anything changes.
- **TEXTCHANGED:** an empty REMOVE or PASTE changes nothing and does not set it.
- **Speed:** bytes move between buffers in pieces of 128 through the resident area, one Rosanne block mapping per piece and buffer. Simulator only; XAnne speed is not measured.
- **Evidence:** a Python model on random edits across 16K block ends (`tests/test_m10_text.py`); the independent core; mutation tests (11 of 12 caught; the 12th changes no behaviour). **XAnne:** exercised by MDEDIT II's clipboard and undo / redo (owner Session 2R S4, S5, S9, S11 passed); no dedicated probe.

**File names as strings (M9).** `TEXT LOAD`, `TEXT SAVE`, `KILL` and `NAME … AS …` accept any STRING expression as a file name, checked when the statement runs: a DOS 8.3 name (`[A-Z0-9_]{1,8}.[A-Z0-9]{1,3}`, lower case allowed and made upper case), not a device name (CON, PRN, AUX, NUL, COM1–9, LPT1–9). Otherwise nothing happens and `IOERR` is **247**. Since M13 `OPEN` does too (an invalid name sets IOERR 247 and opens nothing). `FILESAVE` and `FILELOAD` still take literals.

**Speed and limits.** Loading reads one byte per Rosanne call (the M7 method: Rosanne's registers at the end of a file are not reliable, M4) — about as fast as `LINE INPUT #`; saving writes whole runs. The first edit far from the previous one moves the buffer's gap, in 128-byte pieces. Lines are not limited in length; one TEXTGET$ returns at most what fits the STRING it is assigned to.

### 5.8 M10 — records (TYPE)

```
TYPE Contact
    Id AS INTEGER
    Name AS STRING * 40
    Balance AS REAL
    Active AS BOOLEAN
END TYPE

DIM Person AS Contact
DIM Spare AS Contact
DIM Shelf(20) AS Contact                ' resident: at most 250 elements (§5.2)
DIM People(600) AS Contact BANKED       ' in owned 16K blocks (§5.4)

Person.Id = 1
Person.Name = "Example Person"
Spare = Person                          ' a whole-record copy
People(7) = Person
People(7).Telephone = …                 ' (a field the TYPE declares)
MESSAGE People(7).Name + STR$(People(7).Id)
```

**TYPE.**
- Declared at the top level: `TYPE Name`, one `Field AS type` per line, then `END TYPE`. A TYPE may be used before or after its declaration.
- **Fields.**
  - **Types:** INTEGER, REAL, BOOLEAN, or `STRING * n` (1 ≤ n ≤ 126; a STRING field must state n).
  - **Names:** a field name may be a keyword (`Label`, `Text`): it is always written after a record and a dot. The `$` rule applies (`N$` must be STRING).
  - **Not supported:** records inside records, arrays inside records, and a TYPE with no fields. Each is a compile error.

**Layout (fixed, documented; database files depend on it, §5.9).**
- Fields are in declaration order, with no padding. Each field's size:
  - INTEGER: 2 bytes, little-endian;
  - BOOLEAN: 2 bytes, 0 / 1, like the variable (§2);
  - REAL: 5 bytes (§3.1);
  - `STRING * n`: n + 1 bytes, NUL-terminated.
- A record is at most **512 bytes**.
- **The bytes after a STRING field's NUL are always zero.** A record's bytes therefore depend only on its field values: a new record is all zero, and every STRING assignment to a field clears its tail.

**Use.**
- `R.Field` and `A(i).Field` are variables of the field's type, usable anywhere such a variable is: in expressions, as the target of `=`, and with every STRING rule of §4. A value that cannot fit is `string too long` at run time, never cut.
- A whole record is used in two places only:
  - an assignment from another record of the **same TYPE** (`A = B`, `A(i) = B`, `A = B(j)`, `A(i) = B(j)`), which copies all of its bytes;
  - a parameter or FUNCTION result (below).

  Anything else (in an expression, MESSAGE, PRINT #, a FOR counter, a binding) is a compile error naming the record and its TYPE. Records are not compared whole; compare fields.

**Arrays of records.**
- Resident arrays hold at most 250 elements and count against the 16K image.
- A BANKED array of records holds up to 32767 elements, in the shared 32-block (512K) budget of §5.4. An element never crosses a 16K block end.
- An index outside 1..n is `index out of range`, as for every array.
- A BANKED record read (a field of `A(i)`, or `A(i)` copied whole) counts as one of the four BANKED reads a statement may make (§5.4).
- **Resident cost:** a program with a BANKED array of records keeps five record-sized windows in the resident image (§5.4's windows are as large as the largest element).

**Procedures.**
- `SUB S(X AS Contact)` receives a **copy** (parameters are static variables, §5.3); changing `X` does not change the argument.
- A FUNCTION may return a record (`FUNCTION Make(…) AS Contact` with `RETURN T`). Its value may be assigned to a record (`P = Make(1)`) but not used directly with a field: assign it first.
- `LOCAL T AS Contact` starts as an all-zero record on every call.

*Evidence status:* simulator, memory checker and mutation tests (`tests/test_m10_records.py`, 15 tests; 9/9 mutants caught). **XAnne:** exercised by DBPROBE and CONTACTS III (BANKED record arrays, fields, whole-record copies; owner sessions passed); no dedicated record probe. The generated code uses only XAnne-proven mechanisms (ordinary variables, M6 array indexing, M8 BANKED windows, `ldir`).

### 5.9 M10 — databases (DB)

```
TYPE Contact
    Id AS INTEGER                       ' the first field: the record's identifier
    Name AS STRING * 40
    Phone AS STRING * 20
END TYPE
DIM People(500) AS Contact BANKED       ' the database: a BANKED array of records
DIM Count AS INTEGER                    ' ... and its record count

DB LOAD People, Count, "PEOPLE.PDB"     ' Count = the records read; IOERR, DBRECOVERED
DB NEW People, Count                    ' Count + 1, a cleared record with the next Id
People(Count).Name = "Example Person"
K = DBFIND(People, Count, 17)           ' the element whose Id is 17, else 0
DB DELETE People, Count, K              ' removes element K, keeping the order
DB SAVE People, Count, "PEOPLE.PDB"     ' safe replacement; IOERR
```

**The database.**
- A database is a **BANKED array of records** (§5.4, §5.8) together with an INTEGER variable holding its record count. The records in use are elements 1..Count.
- Each statement names the array. For `LOAD`, `NEW` and `DELETE`, Count must be a plain INTEGER variable, because the statement sets it.
- **Count.** A count outside 0..the array's length is `index out of range`, since the count is the program's value, not the file's.
- **The file.** A database is read and written whole. Its size is bounded by the array, so there is no partial or record-by-record file access.

**Identifiers.**
- `DB NEW` and `DBFIND` use the TYPE's **first field**, which must be INTEGER (otherwise a compile error).
- `DB NEW` gives each new record the database's *next identifier* (1, 2, 3, …). The next identifier is saved in the file and restored by `DB LOAD`, so an identifier is never reused after a delete.
- `DBNEXTID(Array)` is the identifier the next `DB NEW` will give.
- Identifiers run from 1 to 32767. After 32767 has been given, `DB NEW` reports IOERR 252.
- The program may still assign the first field itself. `DBFIND` then finds the first element holding that value.

**Statements and functions.**

| Form | Effect |
|---|---|
| `DB LOAD A, Count, name$` | Reads the file into elements 1..n. Count = n. IOERR, DBRECOVERED (below). |
| `DB SAVE A, Count, name$` | Writes elements 1..Count with the safe replacement below. IOERR. |
| `DB NEW A, Count` | If Count < the array's length: element Count + 1 is cleared (every field zero / empty), its first field gets the next identifier, Count increases, IOERR 0. Otherwise IOERR 252 and nothing changes. |
| `DB DELETE A, Count, k` | Element k (1..Count, else `index out of range`) is removed. Later elements move down one, keeping their order. The old last element is cleared, and Count decreases. IOERR is not changed. |
| `DBFIND(A, Count, id)` | The first element 1..Count whose first field equals id, else 0. |
| `DBNEXTID(A)` | The next identifier. |
| `DBRECOVERED` | Which file the last `DB LOAD` read: 0 the file itself, 1 its `.NEW`, 2 its `.BAK`. |

**File names.**
- A name is a literal or a STRING, with the rules of §5.7 ("File names as strings") and §7.
- The database uses two companion files beside it: the name with its extension replaced by **`.NEW`** (the save's temporary file) and by **`.BAK`** (the previous version).
- A database's own name may not have the extension `.NEW` or `.BAK`. For a literal this is a compile error; for a STRING it is IOERR 247.
- *Data safety:* `DB SAVE` replaces the file and its `.BAK`, and writes and deletes the `.NEW`. Choose a name that is not one of your own documents.
- Files that share a name and differ only in extension share these companions: FORM.DSN and FORM.PBI both use FORM.BAK and FORM.NEW (KI-91). Up to M13 a `DB SAVE` or `BITMAP SAVE` of one replaced the other's backup. **Since M14** a save first reads the first bytes of any existing `NAME.NEW` and `NAME.BAK` (step 0 below): one that is another kind of file (not "PBI1" for a bitmap; not "PDB1" with this TYPE's signature for a database) belongs to another file, and the save does nothing and sets **IOERR 253**. A companion shorter than its 4-byte magic counts as a leftover and is replaced. Two files of the same kind (FORM.PBI and FORM.IMG, both pictures) still share companions. A program that keeps several files under one name writes the others through a temporary name of their own and renames it into place (examples/lib/files.pbas `SafeReplace`, as DESIGNER does).

**Safe replacement (`DB SAVE`).**

| Step | Action | If it fails |
|---|---|---|
| 0 | (M14) Check that `NAME.NEW` and `NAME.BAK`, where they exist, are this save's kind (above). | IOERR 253 (or the read's code); nothing changed |
| 1 | Write `NAME.NEW`. | |
| 2 | Read `NAME.NEW` back and check it (header, length, check bytes, nothing after the end). | |
| 3 | Delete `NAME.BAK` ("not found" is fine). M14: when the file itself is not there (a first save, or step 5 failed last time), steps 3 and 4 are skipped, so `NAME.BAK` is kept. | |
| 4 | Rename the file to `NAME.BAK` ("not found" is fine: a first save). | |
| 5 | Rename `NAME.NEW` to the file. | |

- **A failure in steps 1–4** deletes `NAME.NEW` and leaves the file as it was. If step 4 fails, the old `NAME.BAK` has already been deleted.
- **A failure in step 5** leaves the new data in `NAME.NEW` and the previous version in `NAME.BAK`. `DB LOAD` reads the new data from `NAME.NEW` (DBRECOVERED = 1).
- IOERR is 0, or the code of the first failure.
- The OS call list (`Supporting Docs/OSCALLS.INC.txt`) has no file flush or sync call: the data counts as safe once it has been closed and read back.

**Loading and recovery (`DB LOAD`).**
- `DB LOAD` tries, in order, the file, `NAME.NEW`, and `NAME.BAK`. It uses the first one that reads back whole and valid. Count is that file's count, DBRECOVERED says which file it was, and IOERR is 0.
- **M14:** the companions are tried only when the file itself is missing, is not a database (248) or is damaged (251). A file that is whole but cannot be loaded here — another TYPE (249) or version (250), more records than the array holds (252), or a read error — is reported with that code, as "none is valid" below, and no older copy is loaded over it. (Up to M13 any failure fell back to an older copy with IOERR 0, and a program that then saved replaced the newer file.)
- **M14:** a record is valid only if each STRING field has its terminating 0 within the field (otherwise 251). Up to M13 a file with a correct check but a field without its 0 was loaded, and the field then read past its end.
- **Recovery is not an error.** A program should tell its user when DBRECOVERED is not 0, and save again.
- **If none is valid:** Count = 0, the next identifier is 1, DBRECOVERED is 0, and IOERR is the error of the first file that exists, or 2 if none exists.
- **Elements after Count are unchanged.** After a failed file, the elements it reached may hold that file's bytes; a later valid file is then loaded over them.

**IOERR codes**, in addition to §7.1's Rosanne codes:

| Code | Meaning |
|---|---|
| 247 | Invalid name, or a `.NEW` / `.BAK` extension |
| 248 | Not a database |
| 249 | Another TYPE: the field list or record size differs |
| 250 | Another format version (version, flags or reserved bytes) |
| 251 | Damaged: the check bytes differ, the file is shorter than its count, or bytes follow the end |
| 252 | More records than the array holds (`LOAD`), or the array or the identifiers are full (`NEW`) |
| 253 | (M14) `SAVE`: `NAME.NEW` or `NAME.BAK` belongs to another file with the same name (KI-91); nothing was changed |

**The PDB1 file format** (little-endian):

| Offset | Size | Content |
|---|---|---|
| 0 | 4 | `PDB1` |
| 4 | 1 | version 1 |
| 5 | 1 | flags 0 |
| 6 | 2 | record size |
| 8 | 2 | count |
| 10 | 2 | next identifier |
| 12 | 2 | TYPE signature |
| 14 | 2 | 0 |
| 16 | count × size | the records, in the §5.8 layout |
| end | 4 | check: s1, s2 |

- **TYPE signature:** the CRC-16/CCITT-FALSE (polynomial #1021, initial #FFFF) of the TYPE's field list, written as `NAME:I;NAME:S40;NAME:R;NAME:B` with fields in order and names in upper case. `S40` is `STRING * 40`.
- **Check:** over every byte of the header and the records, starting from 0, s1 = s1 + byte and s2 = s2 + s1, both modulo 65536. Together with the length rules, this detects any changed, missing or extra byte.
- The format is fixed, so a database can be checked on a host with `tools/pdbcheck.py`.

**Limits.**
- A whole database is in memory: at most 32767 records, and the array's blocks are taken from the 512K budget of §5.4.
- Changing a TYPE makes its old files unreadable (249). There is no automatic conversion.
- `DB LOAD` costs, per record, one read of at most 128 bytes for every 128 bytes of the record, plus one block copy.
- Saving writes each record once, then reads the whole file back.

*Evidence status:*
- **Simulator:** memory checker, fault injection at every filing step and mutation tests (`tests/test_m10_db.py`, 28 tests; 22/22 mutants caught).
- **XAnne (owner, Rosanne 1.12):** DBPROBE D0–D8 passed. This verifies that an `os_read_file` of 2–128 bytes ending exactly at the end of the file returns no carry (D2, KI-57), and that saving, the `.BAK` rotation and recovery from `.BAK` and `.NEW` work as specified (D1–D5). CONTACTS III C6–C8 passed, including recovery from `.BAK` when the file is damaged (KI-61). The "no valid copy" path (IOERR of the first file, Count 0) is simulator-tested only.

### 5.10 M10 — sorting and searching a database

```
DIM ByName(250) AS INTEGER                         ' an index: element numbers
DIM Found AS INTEGER
DB SORT People, Count, ByName, Name, NOCASE        ' ByName(1..Count) in name order
DB SORT People, Count, ByName, Balance, DESC       ' largest first
DB SEARCH People, Count, ByName, Found, Phone, "0161"   ' ByName(1..Found) = the matches
DB SORT People, Found, ByName, Name, KEEP          ' ... then those matches in name order
FOR I = 1 TO Count
    P = ByName(I)                                  ' then People(P).Name, …
NEXT I
```

**The index.**
- The records are never moved. An *index* receives element numbers instead.
- The index is a resident INTEGER array, at most 250 entries (§5.2). It must have at least Count entries; otherwise `index out of range`.
- Entries after those filled are not changed.
- A BANKED index is a compile error. *Limitation:* a database of more than 250 records cannot be sorted or searched as a whole.

**DB SORT A, Count, Index, Field[, DESC][, NOCASE][, KEEP]**
- Sets Index(1..Count) to the element numbers 1..Count, ordered by Field: ascending, or descending with DESC.
- **Stable:** records with equal keys stay in element order, in both directions.
- **KEEP** sorts the entries already in Index(1..Count) instead of starting from 1..Count. Each entry must be an element number of the array; otherwise `index out of range`. Equal keys keep their order in the index. Uses:
  - **two-key order:** sort by the second key, then by the first with KEEP;
  - **sorted search results:** `DB SEARCH`, then `DB SORT A, Found, Index, Field, KEEP`.
- **Order:**
  - INTEGER: signed;
  - REAL: numeric;
  - STRING: unsigned byte order, with a prefix before the longer text (as `<` in §3). With NOCASE, `a`..`z` compare as `A`..`Z`; no other byte is folded.
- The field may be any INTEGER, REAL or STRING field (not BOOLEAN).

**DB SEARCH A, Count, Index, Found, Field, text$[, NOCASE]**
- Index(1..Found) receives, in element order, the elements 1..Count whose STRING Field contains text$. Found is set to their number.
- An empty text$ matches every element. NOCASE folds as above.
- text$ is any STRING expression of at most 127 characters; a longer one is `string too long`, never cut.

**Cost.** A sort is a binary insertion over the index:
- one field read per comparison (an `os_copy_24bit` of the field), about n·log2(n) comparisons, plus moves of the index itself;
- 250 records: under 2,800 field reads in the simulator (`tests/test_m10_sort.py`).

A search reads each record's field once. Times on XAnne or a PcW16 are not yet measured.

*Evidence status:* simulator, memory checker, a Python model of the contract on random databases, and mutation tests (`tests/test_m10_sort.py`, 10 tests; 15/15 mutants caught). **XAnne:** DBPROBE D7 (200 records by name, NOCASE, then a search: `found=38`) and CONTACTS III C2, C3 passed; times not measured.

### 5.11 M10 — INCLUDE

```
INCLUDE "lib/forms.pbas"      ' on a line of its own, outside any SUB
```

**Inclusion is textual.** The line is replaced by the file's text, read relative to the folder of the file that contains the INCLUDE line. Libraries may include other libraries. What an included file may contain is decided by the ordinary rules, as if its text were written in place. It is normally TYPEs, CONSTs, DIMs, and SUB and FUNCTION definitions.

**Rules (compile errors):**
- the file must exist and be UTF-8;
- it must have fewer than 1000 lines;
- it may not have BASIC line numbers;
- each file may be included only once, which also rules out cycles;
- at most as many files as fit below line 32767 (below).

**Line numbers:**
- **The main file** keeps its own line numbers.
- **The k-th included file** (in the order the INCLUDE lines are reached) is numbered from B + 1000·(k−1) + 1, where B is the first multiple of 1000 above the main file's last line.
- **Example:** in a 480-line program, line 45 of the first library is program line 1045.
- **Runtime errors** report this program line ("at line 1045"). The build prints each included file's range (`included: lib/forms.pbas: lines 1001..1999`).
- **Compile errors** name the file and its own line (`lib/forms.pbas:45:3: …`).
- **Limitation:** messages that quote another line ("first declared at line …") give the program line.

*Evidence status:* compiler tests (`tests/test_m10_text.py`). Inclusion happens on the host, so nothing changes on the PcW16.

### 5.12 M12 — BITMAPs and POINT

*Evidence status:* **simulator and static only** until the owner runs BMPPROBE (docs/M12-GRAPHICS-FINDINGS.md). The screen layout (80 bytes a row, bit 7 the leftmost pixel, a set bit white) and the BIOS bitmap calls come from ROSAN283 and a static reading of PCW045.SYS.

**Declaration.** `DIM Name AS BITMAP * width, height` declares a bitmap: a rectangle of pixels kept in a 16K memory block of its own (like a TEXT buffer, it counts towards the program's blocks, §5.4). width is 1..568 and height 1..300 (the largest canvas), and its bytes, (width + 7) \ 8 × height, must fit one block of 16384 (`DIM B AS BITMAP * 568, 230` is the largest full-width one). A bitmap is not an array element or a record field; since M13 it can be a procedure's parameter (§5.14). A new bitmap is white, and its size (`BITMAPW`, `BITMAPH`) is the declared one.

**Statements** (GET and PUT need a CANVAS, and its window on screen, like `DRAW`):

| statement | does |
|---|---|
| `BITMAP GET Name, x, y` | copies the canvas rectangle at x, y of the bitmap's current size into the bitmap |
| `BITMAP GET Name, x, y, w, h` | copies the w × h rectangle at x, y; its bytes ((w + 7) \ 8 × h) must fit the bitmap's (its declared bytes, so another shape of the same size fits too); the bitmap's size becomes w × h |
| `BITMAP PUT Name, x, y` | draws the bitmap with its top-left corner at x, y: every pixel black or white as it was captured, whatever `DRAW INK` says (the ink and mode are put back) |
| `BITMAP SAVE Name, file$` | writes the bitmap (its current size) to a PBI1 file (docs/M12-BITMAP-FORMAT.md), with the database's safe replacement (§5.9): NAME.NEW is written and read back, the old file becomes NAME.BAK, NAME.NEW becomes the file |
| `BITMAP LOAD Name, file$` | reads a PBI1 file into the bitmap; its size becomes the file's |

Every rectangle must lie inside the canvas (`Runtime error: drawing outside the canvas at line N`; nothing is drawn or captured). A GET larger than the bitmap stops the program: `Runtime error: the rectangle is larger than the BITMAP at line N`.

**Files.** SAVE and LOAD set `IOERR` (0 = done) and never stop the program: a Rosanne code, 247 a name ending .NEW or .BAK (refused at compile time for a literal), 248 not a PBI1 file, 250 another version of the format, 251 damaged (its check, its length, or bytes after the end), 252 larger than the bitmap, 253 (M14) NAME.NEW or NAME.BAK belongs to another file (§5.9). A failed LOAD leaves the bitmap's size unchanged but its pixels may have been partly replaced (draw it only after `IOERR = 0`). LOAD reads the file only; unlike `DB LOAD` it does not look for NAME.NEW or NAME.BAK. A failed SAVE leaves the old file, or both copies, as a failed `DB SAVE` does.

**Functions.** `BITMAPW(Name)`, `BITMAPH(Name)`: the bitmap's current width and height. `POINT(x, y)`: the canvas pixel at x, y, 1 black or 0 white (Rosanne's `bios_getpxl`); it needs a CANVAS (compile error otherwise), the window on screen and the point inside the canvas, but no BITMAP.

**Not defined (M12):** colours other than black and white (the screen has one bit a pixel; grey shades are patterns, `DRAW FILL`), transparent PUT (M13 adds it: `BITMAP MASK`, §5.14), scaling, rotation, bitmaps in arrays or records, other file formats (tools/pbicheck.py converts PBI1 to and from PBM on a PC).

### 5.13 M12 — printing (PAGE)

*Evidence status:* **static and simulator only** until the owner prints in XAnne (Session 2). The calls are ROSAN283's print meta-file and typo-font functions (95–105, 83–91), used in the order Rosanne's own Shopping List uses them (docs/M12-PRINTING.md). `os_print_screen` and the stripe calls (164–167) are empty in Rosanne 1.12, so screens and bitmaps cannot be printed.

A program prints one page at a time. `PAGE` is a statement word only when one of the operations below follows it, so programs may still use `PAGE` as a name.

| statement | does |
|---|---|
| `PAGE NEW` | starts an empty A4 page (portrait, half-inch margins) in 10-point plain text; a page still open is discarded |
| `PAGE FONT size [, BOLD]` | the text that follows in Rosanne's Times typeface (the first typeface listed if there is no Times) at size 6, 8, 10, 11, 12, 14, 18, 24, 36 or 72 points (a literal outside the list is a compile error, a value a runtime error: `a print size is …`) |
| `PAGE TEXT x, y, text$` | the text with the top of its line at x, y; characters outside 32..255 print as `?` |
| `PAGE LINE x1, y1, x2, y2 [, t]` | a horizontal or vertical line t points thick (1 by default, 1..72), below or to the right of the points (`Runtime error: a printed line is horizontal or vertical`); a line of no length prints nothing |
| `PAGE BOX x, y, w, h` | a rectangle's outline, one point thick, inside the rectangle |
| `PAGE FILL x, y, w, h` | a black rectangle; w or h 0 prints nothing |
| `PAGE PRINT` | sends the page to the printer and closes it |
| `PAGE CLOSE` | discards the page (nothing happens without one) |

**Coordinates** are whole points (1/72 inch) from the top left of the printable area: x 0..522, y 0..765. Everything printed must lie inside it, a text line with its whole height and width, otherwise the program stops: `Runtime error: printing outside the page at line N`. Nothing is clipped or cut. Every statement but `NEW` and `CLOSE` needs an open page: `Runtime error: no page is open (PAGE NEW) at line N`. A page still open when the program ends is discarded.

**Measuring.** `PAGEWIDTH(text$)` is the printed width of `text$` in points in the current font, rounded up, for wrapping and right-aligning (`examples/printdemo.pbas`). Widths add up within a point per part. It needs an open page.

**Results.** `PAGE NEW`, `FONT`, `TEXT`, `LINE`, `BOX`, `FILL` and `PRINT` set `IOERR` (0 = done) to Rosanne's answer and never stop the program for it:
- `PAGE NEW`: 7 not enough memory, 2 no typeface;
- `PAGE FONT`: 1 typeface missing, 2 size refused, 7 not enough memory;
- `PAGE PRINT`: 1 not enough memory to print, 2 font not found, 3 too many fonts, 4 stopped by the user, 5 printer in use, 6 no valid printer set up.

The printer is the one chosen in the PcW16's Setup; Rosanne prints at its resolution.

**Geometry.** Each line, fill and box side prints as exactly its rectangle, to within one printer dot at any resolution.
- This holds although Rosanne 1.12's printer driver lengthens a horizontal line by its thickness and shortens a vertical one at the top. The runtime allows for both.
- It holds since the M12 corrective; the builds before it printed every fill h points too wide (docs/M12-PRINTING.md §6, KI-79).

**Not defined (M12):** other paper sizes, landscape, typefaces by name, italic, sloped lines, pictures, more than one page at a time, preview on screen.

### 5.14 M13 — parts of bitmaps, masks and BITMAP parameters

*Evidence status:* **static and simulator only** until the owner runs SPRPROBE in XAnne (docs/M13-ACCEPTANCE.md). The masked plot is ROSAN283's `bios_plotmaskedbitmap` (#2F); which mask colour draws comes from a static reading of PCW045.SYS (docs/M13-AUDIT.md §3).

**Parts.** `BITMAP PUT Name, x, y, sx, sy, w, h` draws only the w × h rectangle of the bitmap whose top-left corner is sx, sy in the bitmap, with that corner at x, y on the canvas. The part must lie inside the bitmap's current size (`Runtime error: the part is outside the BITMAP at line N`) and its place on the canvas inside the canvas (`drawing outside the canvas`, as in §5.12). Nothing is drawn after either error. A part is how a program keeps many images (icons, animation frames) in one bitmap: tools/pbimage.py `sheet` builds such a strip from PNG files (docs/M13-GRAPHICS-ASSETS.md).

**Masks.** `BITMAP MASK Image, Mask, x, y` draws Image through Mask: where the mask pixel is **white** the image's pixel is drawn (black or white); where it is **black** the canvas keeps its own pixel. The mask is an ordinary BITMAP of at least the image's size, its pixels matched to the image's from the top left. `BITMAP MASK Image, Mask, x, y, sx, sy, w, h` does the same for a part; the part must lie inside both bitmaps. A mask made with `pbimage.py ... --mask` follows this convention (white = drawn).

PUT and MASK draw every pixel black or white whatever `DRAW INK` and the drawing mode say, and put the ink and mode back; the mouse pointer is hidden while they draw.

*Speed:* a part from the left edge of a bitmap as wide as the bitmap (and its mask) is drawn straight from the bitmap's block; any other part is copied a strip of rows at a time into a work area and shifted, which is slower (docs/M13-SPRITES.md).

**BITMAP parameters.** A SUB or FUNCTION may take a bitmap: `SUB Show(Pic AS BITMAP, X AS INTEGER)`. The argument must be a BITMAP's name (a DIM'd bitmap or the caller's own BITMAP parameter); `Pic` then names that bitmap, so a GET or LOAD through it changes the caller's bitmap (by reference, unlike every other parameter, §5.1). A BITMAP parameter cannot be assigned (`Pic is a BITMAP parameter: pass it a BITMAP's name`). This is what lets the M13 libraries (examples/lib/toolbar.pbas, sprite.pbas) draw from a program's own images.

### 5.15 M13 — ticks, the clock in sixteenths, and held keys

*Evidence status:*
- **XAnne (owner, M13 first sessions, Rosanne 1.12, Graphics acceleration off):** KEYDOWN reported Left 99, Right 100, Up 101, Down 98, Space 41, A 28, and Left with Space "41 99", with and without the runtime bank. A `TIMER … EVERY 1 TICKS` brought 35 events in 10 s idle (160 asked for) and 32 with drawing in its handler.
- **XAnne (owner, M13 corrective retest):** the clock probe saw CLOCKTICKS go back twice in 2 s with steps of 16–17/16 s; a 1/16 s Rosanne timer brought 89–90 events in 10 s and JUMPER paused about once a second. Both come from XAnne's 1/256 s byte not being in step with its seconds (docs/M13-RESPONSIVENESS.md), which the rules below allow for.
- **Static (PCW045.SYS):** the key numbers, from the keyboard interrupt's table at block 6 #6A31; how Rosanne times and posts timer events (block 6 #6830, #6958, #6C4C); the clock (`bios_gettime`, call #B0 = #0E53: port #F9, the 1/256 s byte, then the seconds, minutes and hours, with #F9 read again only to catch its wrap during the read; #0E92 is the date).
- **Simulator:** the corrected programs, on a model of that clock and of Rosanne's timer service; what XAnne shows with them is the owner's retest (docs/M13-ACCEPTANCE.md RT6).

**Ticks.** `TIMER Handler, EVERY n TICKS` runs the handler every n sixteenths of a second (n an INTEGER literal 1..32767). Everything else is as for `EVERY n` seconds (§5.1): one timer, `TIMER OFF`/`TIMER ON`, handlers between events.
- For n up to 240 (15 s), the program's event loop runs the timer itself (M13 responsiveness). It compares `CLOCKTICKS` with the time the handler is due before each look for an event, and looks with `os_get_event`, which returns when nothing is pending (`os_wait_event`, which other programs use, does not return until an event comes: with no input the timer never ran, owner RT6). When due it runs the handler, and the next one is due n sixteenths later.
- A handler that falls more than an interval behind (a long handler, a dialog, the system's own work) is not run again to catch up: the next one is due an interval from then, so late intervals are dropped, never queued. In XAnne a `TIMER … EVERY 1 TICKS` gave 142–154 runs in 10 s (owner, RT7), while a program stepping by the clock did all 80 of its 2/16 s steps.
- For n over 240 the timer is a Rosanne timer (`os_set_timer`), as `EVERY n` seconds is.
- **The handler runs are still not a count of time.** A handler can take longer than the interval, and a Rosanne timer merges intervals it could not deliver (one "due" flag per timer, re-armed from when it noticed; static), and in XAnne stopped for up to a second, once a second, because of its clock (owner). So a program must never count events as time. To move things at a steady speed, read the clock (`CLOCKTICKS`) and do as many steps as the time passed covers: examples/lib/pace.pbas does this, with a limit on how many steps one event may catch up.
- Up to the M13 corrective builds `EVERY n TICKS` was always a Rosanne timer; tools/build.py `--legacy-timing` rebuilds those executables.

**The clock.** `CLOCKTICKS` (M13 corrective) is the PcW16 clock in sixteenths of a second within the minute, 0..959.
- It is seconds × 16 + the sixteenths of the 1/256 s byte counted from the moment the seconds last changed (M13 responsiveness). On a clock whose byte wraps with the seconds that is the byte \ 16. In XAnne it wraps elsewhere in the second, and the byte itself made CLOCKTICKS step back and leap (owner, C1).
- The runtime takes the byte's value at the change from the first read after it, when the read before it was within 1/16 s (the closest such pair it has seen). A TIMER of TICKS reads the clock every few hundred instructions, and `SECONDS` reads it too, so in a program with one (or one waiting on `SECONDS`) the change is known within a second of the start. Until then, and in a program that reads the clock less often, the fraction is the byte's own.
- Within a second CLOCKTICKS never goes back, so it goes back only at the minute.
- An interval is `(CLOCKTICKS - start + 960) MOD 960` sixteenths while it is under a minute. Its seconds are the ones `SECONDS` reads (XAnne-proven).
- A variable of the program's own called `ClockTicks` keeps its meaning.

**Held keys.** `KEYDOWN(code)` is TRUE while that key is held down, now (no event needed), so a timer handler can move a sprite for as long as a key is held, and several keys can be down at once. The code is 0..127; another value stops the program: `Runtime error: a key code is 0 to 127 at line N`.

The code is the number Rosanne's keyboard interrupt keeps the key's state under:
- for most keys, its PS/2 set-2 scan code (A 28, Space 41, Esc 118, the keypad's 4 / 6 / 8 / 2 107 / 116 / 117 / 114);
- for the keys sent with an #E0 prefix, a number from Rosanne's table: Left 99, Right 100, Up 101, Down 98, Home 110, End 106, PgUp 94, PgDn 95, Insert 80, Delete 81, keypad Enter 92, keypad / 109, right Ctrl 19, right Alt 16, Print Screen 57.

examples/lib/keys.pbas names them all (`SC_LEFT`, `SC_KP4`, `SC_A`, …): use the names, not the numbers. Up to M13's first owner build the library gave the cursor keys the keypad's numbers, from a misreading of that table, so they did nothing in XAnne. A canvas's `KEYS` handler and `KEYCODE` (§5.6) are a different numbering: characters (Left is 226 there), with the keyboard's repeat, for typing and commands. A key pressed and released between two timer events may never be seen held; a game that must not miss a tap also takes it from KEYS (examples/jumper.pbas).

**Menu shortcuts (M13 corrective).** A menu `ITEM` without `KEY` used to be given the hotkey word #0000. Rosanne's hotkey search (block 6 #7446) reads each title's hotkey words up to a #0000 and then starts on the next title. So every shortcut after such an item, in its title and in every later title, was missed or counted against the wrong title (owner: PAINT II Ctrl+Z/Y/C/V/Q and DESIGNER Ctrl+D/F did nothing; Ctrl+S, before the first item without `KEY`, worked). Such an item now gets the word #FF00: ASCII 0 with shift state #FF, which no key produces. Accepted executables are rebuilt with `--legacy-menu-hotkeys` to keep their bytes (KI-89).

**Not defined (M13):** how fine the clock's sixteenths are on real hardware and in XAnne (TIMEPRB C1), the timer's rate on real hardware, sound.

### 5.16 M14 — rules made stricter, and corrections

*Evidence status:* compiler and simulator (tests/test_m14_hardening.py, test_m14_filesafety.py, test_m14_real.py). The runtime corrections (file safety, REAL rounding) await the owner's XAnne retest (docs/M14-ACCEPTANCE.md). Each is listed in docs/M14-DEFECT-REGISTER.md.

**Compile-time rules the compiler now enforces as this specification already stated.** Each was accepted by the M13 compiler and did nothing, or something else, at run time:
- assigning a TEXT buffer to another (`T1 = T2`, §5.7), a BITMAP to another, or anything to a BITMAP parameter (§5.14): compile errors;
- statements between `SELECT CASE` and its first `CASE` (§5.3): a compile error.

**Names and the built-in functions.**
- A FUNCTION may not have a built-in function's name (`FUNCTION Min(…)`, `FUNCTION Len(…)`): a compile error. Up to M13 it silently replaced the built-in.
- A CONST may not have the name of a built-in that takes no arguments (`PI`, `SECONDS`, `CLOCKTICKS`, `IOERR`, `MOUSEX`, `MOUSEY`, `MOUSEEVENT`, `KEYCODE`, `KEYSHIFT`, `DBRECOVERED`).
- A variable, parameter or LOCAL with such a name is allowed (programs accepted earlier use them), but hides the built-in where it is visible, and the compiler warns.
- A SUB named like a statement word (`SHOW`) must be run with `CALL`; the error message says so.

**Other compile-time checks.**
- A literal index outside an array's declared bounds (`A(0)`, `A(11)` for `DIM A(10)`) is a compile error; a computed one is the runtime index error (§8).
- A `DIM` inside a SUB or FUNCTION is allowed and still declares a global (§4, §5.3); the compiler warns.
- A FUNCTION declared without `()` is called with `()`; the message for a call without them says so.
- `LINE INPUT #` reads into a STRING variable or STRING array element only; a record field is refused with a message naming the rule (read into a STRING, then assign it).
- A `DIM` after the first use of its variable is accepted: the declaration applies to the whole program, wherever it is written.

**What `check` checks.** `pcw16basic check` (and `python3 -m pbas check`) runs everything `build` runs except the assembler and the final memory fit: the syntax, the types, the window layout and code generation, and prints the same warnings. A program `check` accepts builds unless its resident part does not fit the 16K block (§8).

**Runtime corrections** (from M14; `tools/build.py --legacy-file-safety` and `--legacy-real-rounding` rebuild the M13 code, only to reproduce accepted executables byte for byte):
- `DB SAVE` and `BITMAP SAVE` refuse, with IOERR 253, to overwrite or delete a `NAME.NEW` or `NAME.BAK` that belongs to another file of the same name, and keep `NAME.BAK` when the file itself is missing (§5.9).
- `DB LOAD` falls back to `NAME.NEW` or `NAME.BAK` only when the file is missing, not a database or damaged, and takes a STRING field without its terminating 0 as damage (§5.9).
- REAL `+` and `-` are correctly rounded in every case (§3.1).

**Not changed.** Programs that use none of these constructs compile to the bytes they had at M13-End (tools/diffbuild.py). A program with `DB LOAD`, `DB SAVE` or `BITMAP SAVE`, or with REAL arithmetic, compiles to new bytes.

## 6. Statements

| Statement | Semantics | Stage-1 limits (basis) |
|---|---|---|
| `WINDOW "title" [, LARGE]` | declares the dialog (M3a: implemented, see §5) | one unnamed window per program, or (M6) 2..8 named ones (§5.1); title ≤ 35 chars (policy, POC-measured); fixed 360×240 layout at screen 140,110 (policy, POC-proven); needs ≥ 1 `BUTTON` (M3a) |
| `LABEL "text"` / `LABEL Name$` | static text row (M3a); **M5d:** with a STRING variable, a row showing the variable, updated when a handler returns (§5) | ≤ 8 per dialog (language policy), as many as fit the layout (32-px rows, §5); literal text ≤ 47 chars (policy; ROSAN283 allows 128) — keep it ordinary text, risk R-LABELW; **a shown value ≤ 24 printable ASCII characters (M5d recovery, §5)** |
| `TEXTBOX name [, "caption"]` | single-line edit bound to the STRING `name` (M3b: implemented; sync rules §5) | caption ≤ 34 chars (policy); capacity ≤ 64 in M3b (policy; doc max 128); as many as fit the layout (§5); the field is a framed 300×25 px box |
| `CHECKBOX name [, "caption"]` | tick box bound to the BOOLEAN `name` (M3b: implemented; sync rules §5) | caption ≤ 34 chars (policy); ≤ 8 per dialog (policy) and as many as fit the layout (§5) |
| `BUTTON "cap", H [, DEFAULT] [, KEY k]…` | click handler (M3a: implemented, see §5); **M5d:** `DEFAULT` also runs it on the Return key (§5); **M6:** `KEY` adds Green/Red/Blue/Yellow/Stop/Help/F1–F8 (§5.1) | **1..6** (M5d: two rows of up to 3); at most one `DEFAULT`. Zero buttons is a compile error (no verified close path, R-DLG); caption ≤ 14 chars (policy; ROSAN283 allows 32) |
| `RADIO v, "a", "b" [, …]` | **M6:** option group bound to the INTEGER `v` (0 none, 1..n), §5.1 | 2..6 options, 24 px each; captions ≤ 34 chars; ≤ 16 groups per window |
| `NUMBERBOX v [, "cap"] [, MIN a] [, MAX b] [, SPIN]` | **M6:** whole-number field bound to the INTEGER `v`, optional spinner, §5.1 | 6 characters (`-`, digits); 48-px row; caption ≤ 34 chars |
| `v = ASK(text, "b1", "b2" [, "b3"])` | **M6:** question alert; `v` = 1..n, §5.1 | text budget 100 bytes; captions 1..10 chars |
| `BEEP` / `FOCUS v` | **M6:** Rosanne's beep / move the focus to `v`'s control, §5.1 | `FOCUS`: `v` bound in exactly one window |
| `MENU "t"` … `ITEM "text", H [, KEY "X"] [, TICK b]` … `END MENU` | **M6:** menu bar entries, §5.1 | ≤ 8 menus, ≤ 20 items each; title ≤ 12, item ≤ 20 chars |
| `TIMER H, EVERY n` / `TIMER ON` / `TIMER OFF` | **M6:** repeating timer, §5.1 | one per program; n 1..3599 seconds, or `EVERY n TICKS` 1..32767 sixteenths (M13, §5.15) |
| `WINDOW Name, "t" [, LARGE]` / `SHOW Name` | **M6:** 2..8 named windows, one on screen at a time, §5.1 | `LARGE` = 600×400 |
| `MESSAGE expr` | alert dialog | literal text ≤ 250 bytes (policy); dynamic text budgeted against a 160-byte alert buffer: literal bytes + Σ(capacities of referenced variables) + 6 per `STR$` must fit (replaces POC's magic 120/32 numbers; M5a: only text counts — a substring counts its source, integer arguments such as `LEN(B$)` add nothing); dynamic parts: any STRING expression (M5a) |
| `DIM`, assignment | exact type match, exact capacity rule | — |
| `DIM A(k) AS type [* n] BANKED` / `DIM S$ AS STRING * n` | **M8:** arrays in owned 16K RAM blocks; per-variable string capacity, §5.4 | BANKED: k 1..32767, 512K in all, ≤ 4 BANKED reads per statement, not shown by LIST/CHOICE; `* n`: 1..126 |
| `IF cond THEN … [ELSE …] END IF` | cond must be BOOLEAN | incl. `X$ = ""` / `X$ <> ""` (POC-proven) |
| `WHILE cond … WEND` | top-tested; zero iterations allowed (POC-proven) | BOOLEAN cond |
| `FOR i = a TO b [STEP s] … NEXT [i]` | inclusive; bounds evaluated once; Stage 1: `STEP` ±1; M7: any non-zero INTEGER constant (§5.3); never wraps past −32768/32767 (POC-proven) | INTEGER counter, declared |
| `FILESAVE "NAME.EXT", value$` | write a STRING (variable or expression) to a file, replacing it (M4: implemented, §7) | literal DOS 8.3 name, validated at compile time; folder/drive are build options (default floppy `\PCW\FOLDER01`); value ≤ 127 bytes (compile-time bound); **replaces an existing file without prompting — documented hazard**; one alert reports the outcome |
| `FILELOAD "NAME.EXT", var$` | replace a STRING variable with a file's contents (M4: implemented, §7); a TEXTBOX-bound variable is redrawn by the §5 sync | a file longer than capacity − 1 bytes, or containing a zero byte, is **refused** (never cut); on any failure the variable is unchanged and no file is created; one alert reports the outcome |
| `PRINT expr` | — | **not in Stage 1**; fails with a clear error (output model undecided; will not be retrofitted as an alias for `MESSAGE`) |
| `CALL Name[(args)]` | runs `SUB Name`, then continues (M5c, §5); M7: with arguments (§5.3) | no recursion; ≤ 16 procedures active at once (policy) |
| `EXIT` / `EXIT SUB` | end the program / return from the current SUB (M5c, §5) | `EXIT SUB` only inside a `SUB` |
| `END` | ends program (closes dialog/files first) | mandatory, final |

Not in the language: `GOTO`, `INPUT`, `DATA`/`READ`, `PRINT` to the screen. (Arrays, user FUNCTIONs, locals and SELECT CASE, not in Stage 1, were added in M6–M7: §5.2, §5.3.)

### 6.1 M3b specification ambiguities and their resolutions

| # | Ambiguity in the earlier text | Resolution |
|---|---|---|
| 1 | When do bound values move? (spec only said CHECKBOX is "synced before each handler runs") | The five-point table in §5: open → controls; click → variables, then handler; return → changed controls; no other movement. |
| 2 | Does a handler's change to a bound variable show on screen? | Yes, when the handler returns, for controls whose value differs (TEXTBOX and CHECKBOX alike). The TEXTBOX shows exactly the new text: nothing of the previous text may remain visible (the first M3b build broke this in XAnne — fixed by redrawing the field's background box first; see ARCHITECTURE "TEXTBOX redraw"). |
| 3 | Two controls bound to the same variable (the frontend accepted a repeated `TEXTBOX X$`) | Compile error: one control per variable — otherwise "which control wins" would be arbitrary. `DIM` plus one control is fine. |
| 4 | TEXTBOX size: "capacity ≤ 128 (doc)" vs. the v0.5.2 failure with larger/empty fields | Max length = capacity − 1, the full slot reserved in the definition (see ARCHITECTURE M3b), capacity ≤ 64 in M3b. |
| 5 | Where do controls go, and in what order? (spec: fixed layout, caps "pending auto-layout") | Source-order rows with fixed heights and a fit check (§5); caps become geometric. |
| 6 | Unsaved edits at exit | Discarded; there is no implicit sync on `EXIT`/`om_exit` (the program is ending). |
| 7 | `TEXTBOX name$` vs `TEXTBOX name` | Unchanged frontend rule: any STRING variable may be bound; the `$` suffix is not required (a `$` name must be STRING, a CHECKBOX may not use one). |

Open questions that only XAnne can answer are listed with the M3b scripts in `RUNTIME-RESULTS.md` (V1–V6).

## 7. File operations contract

**Implemented in M4 and accepted in XAnne** (RUNTIME-RESULTS "M4 FINAL").
Observed: a missing folder can also surface as `error #05` rather than
`folder not found`, depending on the operation (P2 note). Rosanne contracts are cited from ROSAN283.DOC
"THE FILING FUNCTIONS"; where that text is silent the behaviour below is a
decision, marked *(XAnne question Fn)* until the owner's run confirms it.

**Statements.**

- `FILESAVE "NAME.EXT", value` — `value` is any STRING expression allowed in
  a MESSAGE value (literals, variables, `STR$`, substrings, `+`). Its
  longest possible length must be ≤ **127 bytes** (checked at compile time
  with the §4 length bounds; otherwise a positioned error). The file is
  created, or an existing file of that name **replaced**, and holds exactly
  the text's bytes: no terminator, no line ending, no conversion. An empty
  string makes an empty (0-byte) file *(F6)*. "Replaced" means the old
  contents are gone even if they were longer (F1, **confirmed in XAnne**:
  `os_open_file` for write truncates — ROUNDTRP left exactly `Short` after
  a 19-byte file).
- **Load timing in a window.** FILELOAD shows its alert while the handler is
  still running; a TEXTBOX bound to the loaded variable is redrawn when the
  handler returns (§5), i.e. after the alert is dismissed. (The POC Notes
  build redrew first and alerted second.)
- `FILELOAD "NAME.EXT", var` — `var` must be a STRING variable (capacity C).
  On success `var` holds exactly the file's bytes followed by a NUL. The
  file must hold **at most C − 1 bytes and no zero byte**; anything else is
  a failure. On **every** failure `var` keeps its previous value, nothing
  is truncated, and no file is created.
- Both are ordinary statements: main line, procedures, handlers, loops. A
  TEXTBOX-bound destination is shown through the §5 sync — redrawn when the
  handler returns, or shown when the window opens if loaded by the main line.

**File names.** For `FILESAVE` and `FILELOAD`, a string literal (or a CONST) matching `[A-Z0-9_]{1,8}.[A-Z0-9]{1,3}`
(case-insensitive; the compiler upper-cases it, DOS names being
case-insensitive). The DOS device names `CON`, `PRN`, `AUX`, `NUL`,
`CLOCK$`, `COM1`–`COM9`, `LPT1`–`LPT9` are refused (policy: whether Rosanne
treats them as devices is undocumented). The other file statements (TEXT, KILL, NAME since M9; OPEN since M13; DB and BITMAP) also accept a STRING expression, checked when the statement runs (§5.7, IOERR 247).

**Location (build options, not source).** `tools/build.py --drive=floppy
--folder=\PATH` (defaults: floppy, `\PCW\FOLDER01` — the POC's XAnne-proven
location). The folder is an absolute DOS path of 8.3 components, ≤ 63
characters (`os_set_cwd`: "#BA Too Big - new path exceeds 64 chars"), `\`
alone is the root. It must already exist: programs never create folders.
`--drive=flash` is refused in M4: flash folders are numbered (`os_set_flashfolder`
"B = 0..16"), `os_set_cwd` is "DOS-compatible floppy only", and flash file
naming is defined in the Ranger "Low-Level Disk Interface" document, which is
not available. The drive and folder are emitted as program data
(`PB_FILE_DEVICE`, `pb_file_path`); each operation selects them again
(`os_set_device`, `os_set_cwd`), so nothing depends on what another program
left selected.

**Reporting.** Every `FILESAVE`/`FILELOAD` shows exactly one alert, then the
program continues (a file failure is not a runtime error):

| Outcome | Alert |
|---|---|
| saved / loaded | `File saved: NAME.EXT` / `File loaded: NAME.EXT` |
| failure | `File not saved: NAME.EXT (reason)` / `File not loaded: NAME.EXT (reason)` |

| Reason | Cause |
|---|---|
| `folder not found` | `os_set_cwd` "#03 Path Not Found" |
| `not found` | (load) `os_open_file` "#02 File Not Found" |
| `longer than N characters` | (load) the file has more than N = C − 1 bytes |
| `not text` | (load) the file contains a zero byte |
| `drive error` | `os_set_device` failed |
| `error #XX` | any other Rosanne error code, in hex as ROSAN283 writes it (e.g. `#13` write protected, `#A3` disk full, `#05` access denied) |

The POC's Notes-specific texts ("Note saved", "File load failed") are not
used: the alerts belong to the language, not to one program.

**Failure semantics and data-loss hazards (documented, not hidden).**

- A failed load never changes the variable or any file.
- A save that fails *after* `os_open_file` succeeded (write or close error)
  may leave the file empty or partial: the old contents may already be gone.
  The alert says the save failed. There is no write-to-temporary-then-rename
  in M4 (it needs delete/rename calls whose behaviour on this disk is
  unverified) — a candidate for a later milestone.
- `FILESAVE` replaces without asking. Programs and acceptance tests use
  their own file names; nothing in the compiler knows any file name.

**Runtime contract (ROSAN283).** Each operation: `os_set_device` (B=1
floppy), `os_set_cwd` (path copied to the bottom-quarter workspace at #2100,
"AP may use #2000...#2FFF"), name/extension copied to #2100/#2120,
`os_open_file`, transfer, `os_close_file` — every opened file is closed
before the statement ends, on every path (and `os_app_exit` "automatically
closes any opened read and/or write files"). **Load (M4 repair):** one
byte per `os_read_file` call, byte i to buffer + i, counting the calls that
return NC; the first carry with A = #A1 ends the file, any other code is an
error; the C-th successful read proves the file too long. Only the carry flag
and A are used: the #A1 values of BDE/CHL ("BDE = amount NOT loaded, CHL =
filesize") did not match that reading in XAnne (RUNTIME-RESULTS, M4 result)
and are ignored. The buffer is 640 bytes, enough for byte 126 plus a
"remainder of the last 512-/510-byte block" fill of up to 511 bytes under
either reading of that rule. Then the zero-byte check, then the copy through
the guarded string writer (§4). Save writes through
`os_write_file` from the app bank (CHL = bios_getmem1 bank : address, BDE =
length); an empty text skips the write call (a 0 length is undocumented).

**Tests.** All host-side test tooling uses the simulator's in-memory disk and
never touches user data; XAnne scripts use disposable `PB*` names, a
disposable folder for the Notes parity run, and host backups.

### 7.1 M7 — sequential files

*Evidence status:*
- **Reading and writing** reuse the M4 calls (`os_open_file`, `os_read_file` one byte at a time, `os_write_file`, `os_close_file`), which are XAnne-proven.
- **Delete and rename** (`os_delete_file` fn 153, `os_rename_file` fn 154) are documented but **not yet XAnne-tested**.
- Everything else is simulator and independent-core evidence only.

**Statements.** File names are 8.3 names, as in §7, in the program's build-time folder: a literal, or (KILL and NAME since M9, OPEN since M13) any STRING expression (§5.7).

| statement | effect |
|---|---|
| `OPEN "N.EXT" FOR INPUT AS #c` | open an existing file for reading (`c` is 1 or 2); since M13 the name may be any STRING expression, checked when the statement runs (IOERR 247: not opened) |
| `OPEN "N.EXT" FOR OUTPUT AS #c` | create the file, or **replace** an existing one (Rosanne truncates on open, M4 F1) |
| `PRINT #c, value` | write one line: the text of a STRING (at most 127 characters), or of a number as `STR$` gives it, followed by CR LF |
| `LINE INPUT #c, s$` / `LINE INPUT #c, a$(i)` | read the next line (up to LF; CR dropped) into a STRING variable or element |
| `EOF(c)` | TRUE unless channel `c` is open for INPUT and has something left to read |
| `CLOSE #c` / `CLOSE` | close one channel / every open channel |
| `KILL "N.EXT"` | delete a file |
| `NAME "OLD.EXT" AS "NEW.EXT"` | rename a file (not onto an existing name) |
| `IOERR` | INTEGER: the outcome of the last OPEN, CLOSE, PRINT #, LINE INPUT #, KILL or NAME |

**Errors never stop the program.** Each file statement sets `IOERR` to 0 on success, or to one of these codes:

| IOERR | meaning |
|---|---|
| 2 | file not found |
| 3 | folder not found |
| 4 | too many open files: only one file may be open for reading and one for writing (ROSAN283 #04) |
| 5 | access denied: a read-only file (ROSAN283). What Rosanne does when an *open* file is deleted or renamed is not documented — close it first (the simulator assumes 5) |
| 19 (#13) | disk write-protected |
| 80 (#50) | the new name already exists |
| 163 (#A3) | disk full |
| any other Rosanne code | as ROSAN283 lists it |
| 240 | drive error |
| 241 | channel already open |
| 242 | channel not open, or not open for that direction |
| 243 | the line is longer than the variable can hold: the rest of the line is skipped |
| 244 | the line contains a zero byte: skipped |
| 245 | nothing left to read |

A failed LINE INPUT leaves its variable unchanged, and nothing is ever truncated. `EOF` does not change `IOERR`. `EOF` and `IOERR` are compile errors in a program without OPEN, KILL or NAME.

**Safe replacement** (programs choose it; the language does not hide it):
1. Write `NAME.TMP`.
2. Check `IOERR` after every `PRINT #` and after `CLOSE`.
3. `KILL` the old file; `IOERR` 2 is fine if it did not exist.
4. `NAME` the temporary file to the real name.

A program that finds only `NAME.TMP` at start-up can recover from it (see `examples/contacts.pbas`).

**Limits:**
- Floppy only.
- No APPEND, no random access, no seek: `os_set_ptr` is flash-only, and opening for write always truncates.
- At most one file open for reading and one for writing.
- File names are literals.
- A line holds at most 127 characters when written. When read, it must fit the variable (capacity − 1).
- `FILESAVE`/`FILELOAD` (§7) still work. While a channel of the same direction is open, Rosanne refuses their open (#04) and they report it in their alert.

## 8. Error model

**Compile time**

- Every lexer, parser, semantic and codegen failure is an error carrying line, column and a message stating the rule violated — no silent acceptance, no partial programs, no uncaught compiler exception.
- "Not yet supported" is a first-class diagnostic naming the statement/operator and the spec section. It must never be possible to produce a `.PRG` from an invalid program.
- Implementation limits (M2.1, policy; each is a positioned compile error when exceeded):
  - an expression may be at most **100** levels deep (operators, parentheses, calls; a chain `a + b + c …` counts one level per operand);
  - blocks (`IF`/`WHILE`/`FOR`/`SUB`) may be nested at most **64** deep;
  - **M5c:** at most **16** procedures may be active at once through `CALL` (§5), and a procedure may not call itself directly or indirectly;
  - the resident part of the program must fit the first 16K bank, **#4000–#7FFF (16,384 bytes including the 256-byte prefix)**. Since M9 the code of SUBs and FUNCTIONs (§5.5), and since M11 movable runtime sections, can live in further code banks; only the resident part must fit. Stage 1 required the whole image to fit. Basis: ROSAN283 'Memory Layout' documents only the starting block being switched into the 2nd quarter ("Switching in further blocks of your app is up to you"), and 'Addressing' defines 24-bit OS pointers as a bank number plus a 14-bit address, which the runtime forms from that one bank. Larger images need a documented loader contract and a different pointer scheme first.

**Run time (M2.1)**

- A string that does not fit its destination at run time (§4) stops the program with a modal alert reading exactly `Runtime error: string too long at line N`, where N is the `.pbas` source line (physical line, counting from 1) of the statement that was building the string. After the alert is dismissed the program exits through `os_app_exit`, the same path as `END` (which also closes any open files, ROSAN283).
- **M5a:** a computed substring count below 0 or `MID$` start below 1 stops the program with `Runtime error: substring position out of range at line N` (same alert-then-exit path; M5b: also a computed `INSTR` start below 1).
- **M5b:** `Runtime error: division by zero at line N` (`/`, `MOD`); `Runtime error: number out of range at line N` (`VAL`); `Runtime error: character code out of range at line N` (`CHR$`). Programs that must not stop can test first (`IF B <> 0 THEN …`; keep typed numbers short).
- **M5d:** `Runtime error: label text has an unsupported character at line N` (a dynamic `LABEL` value with a character outside printable ASCII, §5); a value over 24 characters is `string too long`.
- **M6 Phase 1:** `Runtime error: option number out of range at line N` (`RADIO`); `Runtime error: number out of range at line N` (`NUMBERBOX` set outside its `MIN`..`MAX`); `Runtime error: the question could not be shown at line N` (`ASK`); `Runtime error: the menus are too large` (menu area full); `Runtime error: the timer could not be started` (`os_set_timer` refused). Invalid text typed into a `NUMBERBOX` is not an error: the handler is not run and an alert asks for a valid number (§5.1).
- **M7 REAL (§3.1):** `Runtime error: number out of range at line N` (a result beyond about 1.7E+38, `CINT` outside the INTEGER range, `REALVAL` of too large a number, `SIN`/`COS`/`TAN` beyond 51000, `EXP` above about 88); `Runtime error: division by zero at line N` (`/` by 0.0, `0 ^` a negative); `Runtime error: function argument out of range at line N` (`SQR` of a negative, `LOG` of 0 or a negative, a negative number to a non-whole power).
- **M8 (§5.4):** `Runtime error: not enough free memory for BANKED arrays at line N` (start-up; N = the first BANKED `DIM`); `Runtime error: a BANKED array block could not be copied at line N`. Both release the program's blocks before it ends.
- There is no error recovery (`ON ERROR` etc.): a runtime error ends the program. File statements report through IOERR instead (§7.1, §5.9).

## 9. Parity notes (vs POC behaviour)

- **New:** main-line executable statements coexist with `WINDOW` (fixes the dead `logic.pbas` case); literal `32768` rejected; string capacity configurable; multiple TEXTBOXes within layout limits (pending XAnne); caps are policy constants with stated bases.
- **Changed (M2.1):** a string that does not fit is a compile error or a reported runtime error (§4, §8), never silently truncated; programs must fit the first 16K bank; expression/block nesting limits (§8).
- **Changed/narrowed:** STRING `<`/`<=`/`>`/`>=` comparisons rejected (accepted by POC frontend, implemented by no backend); `/` same; widget-count caps temporarily retained as policy (see table) with a milestone gate to lift them.
- **Changed (M4):** file alerts are the language's generic texts naming the file and the reason (`File saved: NOTE.TXT`, `File not loaded: NOTE.TXT (not found)`), not the POC's Notes-specific `Note saved` / `File load failed`; `FILELOAD` refuses a file longer than the variable instead of keeping its first 32 bytes; any STRING variable (not only a TEXTBOX one) may be loaded; the folder is a build option. The POC `notes_v051.pbas` compiles unchanged.
- **Same:** everything listed as POC-proven above, including the inclusive FOR semantics, `STEP ±1` restriction, empty-string tests, substring edge behaviour, success/failure alerts for file operations, and the fail-loud unsupported-construct policy.

## 10. Non-goals

Still not part of the language: several windows on screen at once (one at a time, §5.1); dynamic UI creation; `PRINT`/screen text output; recursion; `GOTO`; runtime error recovery (runtime errors are reported and end the program, §8); real-hardware guarantees (XAnne is the validation target; hardware claims require hardware tests).

Stage 1 also listed arrays, locals, parameters, user functions, procedure arguments and raw keyboard and mouse events. They were added later: arrays in M6 (§5.2), procedures with parameters, locals and FUNCTIONs in M7 (§5.3), and the CANVAS's MOUSE and KEYS handlers in M9 (§5.6).
