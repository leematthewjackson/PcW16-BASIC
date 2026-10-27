# Tutorial 1: a first program

This tutorial builds a small Rosanne application: a window with a status line, a text field, two buttons and a menu. It takes about a quarter of an hour. You need only this repository, Python and Pasmo ([install.md](install.md)). If you have not built anything yet, [first-program.md](first-program.md) is a shorter start.

*Evidence:* this program builds, and the project's simulator runs it in the test suite (`tests/test_m13_tutorials.py`). Pressing **Greet** with the field empty gives `Type your name first`, and with `Ann` typed it gives `Hello, Ann`. **No XAnne run of this program is recorded**, and it has not been tested on a real PcW16.

## The program

The program is `examples/tutorial/t1_hello.pbas`:

<!-- file: examples/tutorial/t1_hello.pbas -->
```basic
' Tutorial 1: a window with a label, a text field, buttons and a menu.
DIM Name$ AS STRING * 20
DIM Greeting$ AS STRING * 24
DIM Count AS INTEGER

WINDOW Main, "HELLO", LARGE
LABEL Greeting$
TEXTBOX Name$, "Your name"
BUTTON "Greet", Greet, DEFAULT
BUTTON "Quit", Quit

MENU "File"
    ITEM "Greet", Greet, KEY "G"
    ITEM "Quit", Quit, KEY "Q"
END MENU

SUB Greet
    Count = Count + 1
    IF LEN(Name$) = 0 THEN
        Greeting$ = "Type your name first"
    ELSE
        Greeting$ = LEFT$("Hello, " + Name$, 24)
    END IF
END SUB

SUB Quit
    EXIT
END SUB

Greeting$ = "Hello!"
END
```

Build it from the repository folder:

```sh
python3 pcw16basic build examples/tutorial/t1_hello.pbas     # -> build/t1_hello.prg
```

Copy `build/t1_hello.prg` into XAnne as `T1HELLO.PRG` and start it from the File Manager ([running-in-xanne.md](running-in-xanne.md)). The program needs no other files, and it writes none. `programs/T1HELLO.PRG` is the same program, prebuilt, byte for byte.

## What you should see

A large window titled `HELLO`. At the top is the status line `Hello!`, and below it a text field captioned `Your name`. Under those are the **Greet** and **Quit** buttons, and there is a **File** menu with **Greet** (Ctrl+G) and **Quit** (Ctrl+Q).

## What each part does

- **DIM** declares the variables. `Name$` holds at most 20 characters, `Greeting$` 24 (the most a LABEL shows), and `Count` is a whole number. Every variable must be declared before it is used. A control can also declare the variable it is bound to: a `TEXTBOX Name$` with no `DIM` would declare `Name$` itself ([manual/02-variables-and-types.md](manual/02-variables-and-types.md)).
- **WINDOW Main, "HELLO", LARGE** starts the window. The lines after it, up to the next WINDOW, are its contents from the top: a `LABEL` that shows a variable, a `TEXTBOX` bound to `Name$`, and two `BUTTON`s. `DEFAULT` makes Return press **Greet** when no text field is being edited.
- **MENU ... END MENU** adds a menu. `KEY "G"` gives an item the shortcut Ctrl+G.
- **SUB Greet** runs when **Greet** is pressed or chosen from the menu. Just before it runs, the field's text is copied into `Name$`. Just after it returns, the label shows the new `Greeting$`. Values move between variables and controls at these points only ([../LANGUAGE-SPEC.md](../LANGUAGE-SPEC.md) §5; [manual/10-windows-and-controls.md](manual/10-windows-and-controls.md)).
- **The main line** is the statements outside the SUBs. It runs once, at the start, before the window opens. Its `END` ends the main line. Then the window opens and waits for the user.
- **EXIT** closes the window and ends the program.

## Try

1. Press **Greet** with the field empty. Then type a name and press **Greet** again. Whether Return, pressed while you are typing in the field, also presses the default button is not defined, so use the button or Ctrl+G.
2. Count the greetings: change the `ELSE` branch to `Greeting$ = "Hello #" + STR$(Count)`.
3. Make a mistake on purpose. Change the last line but one to `Greting$ = "Hello!"`, and check the program:
   ```sh
   python3 pcw16basic check examples/tutorial/t1_hello.pbas
   ```
   ```text
   examples/tutorial/t1_hello.pbas:30:1: undefined variable GRETING$; declare it with DIM or a UI binding
   ```
   The compiler names the file, the line and the column, and says what is wrong. Nothing is built. `check` covers syntax, types, the window's layout and code generation, but only `build` checks that the program fits the PcW16's memory, so always build before you copy ([first-program.md](first-program.md#5-check-and-build)).
4. Make the greeting too long. Replace `LEFT$("Hello, " + Name$, 24)` with `"Hello, " + Name$`, build, and greet a long name such as `Alexandra Smithson`. The program stops with `Runtime error: string too long at line 22`, because 25 characters do not fit `Greeting$`. PcW16 BASIC never cuts text short without telling you: `LEFT$` cuts it on purpose. (The simulator shows this error; it has not been tried in XAnne.)

Next: [Tutorial 2](TUTORIAL-2-GRAPHICS.md) draws on a canvas, with icons made from a PNG picture.
