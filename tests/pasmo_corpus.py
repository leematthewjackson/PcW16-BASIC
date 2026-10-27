"""A corpus of small programs for the M14 rule "check accepts it => Pasmo never fails on it".

Each snippet is (declarations, statements) using one facility. It is placed in
four contexts: the main line of a program with no window, a SUB called from
the main line, a button handler in a window with no canvas, and a button
handler in a window with a canvas. ``programs()`` yields (name, source).

A program the front end refuses is not a failure here (a positioned compile
error is the right outcome); a build that fails with "pasmo failed" is,
because the user wrote valid BASIC and got an assembler error
(tests/test_m14_pasmo.py; tools/rtdeps.py checks the runtime side).
"""
from __future__ import annotations

# (name, declarations, statements); statements are indented into SUBs
SNIPPETS = [
    # strings and numbers
    ("len", "DIM I AS INTEGER", "I = LEN(\"ab\")"),
    ("str", "DIM S$ AS STRING", "S$ = STR$(12)"),
    ("left", "DIM S$ AS STRING", "S$ = LEFT$(\"abc\", 2)"),
    ("right", "DIM S$ AS STRING", "S$ = RIGHT$(\"abc\", 2)"),
    ("mid", "DIM S$ AS STRING", "S$ = MID$(\"abc\", 2, 1)"),
    ("val", "DIM I AS INTEGER", "I = VAL(\"12\")"),
    ("asc", "DIM I AS INTEGER", "I = ASC(\"A\")"),
    ("chr", "DIM S$ AS STRING", "S$ = CHR$(65)"),
    ("instr", "DIM I AS INTEGER", "I = INSTR(\"abc\", \"b\")"),
    ("ucase", "DIM S$ AS STRING", "S$ = UCASE$(\"abc\")"),
    ("lcase", "DIM S$ AS STRING", "S$ = LCASE$(\"ABC\")"),
    ("abs", "DIM I AS INTEGER", "I = ABS(-3)"),
    ("sgn", "DIM I AS INTEGER", "I = SGN(-3)"),
    ("min", "DIM I AS INTEGER", "I = MIN(1, 2)"),
    ("max", "DIM I AS INTEGER", "I = MAX(1, 2)"),
    ("rnd", "DIM I AS INTEGER", "I = RND(6)"),
    ("randomize", "", "RANDOMIZE 7"),
    ("shl", "DIM I AS INTEGER", "I = SHL(1, 3)"),
    ("shr", "DIM I AS INTEGER", "I = SHR(8, 3)"),
    ("trim", "DIM S$ AS STRING", "S$ = TRIM$(\" a \")"),
    ("ltrim", "DIM S$ AS STRING", "S$ = LTRIM$(\" a\")"),
    ("rtrim", "DIM S$ AS STRING", "S$ = RTRIM$(\"a \")"),
    ("space", "DIM S$ AS STRING", "S$ = SPACE$(3)"),
    ("string", "DIM S$ AS STRING", "S$ = STRING$(3, 42)"),
    ("divmod", "DIM I AS INTEGER", "I = 7 / 2 + 7 MOD 2"),
    ("bits", "DIM I AS INTEGER", "I = (12 AND 10) OR (1 XOR 3)"),
    ("compare", "DIM B AS BOOLEAN", "B = \"a\" < \"b\""),
    ("concat", "DIM S$ AS STRING", "S$ = \"a\" + STR$(1) + \"b\""),
    ("real", "DIM R AS REAL", "R = 1.5 * 2"),
    ("sqr", "DIM R AS REAL", "R = SQR(2.0)"),
    ("sin", "DIM R AS REAL", "R = SIN(1.0)"),
    ("cos", "DIM R AS REAL", "R = COS(1.0)"),
    ("tan", "DIM R AS REAL", "R = TAN(1.0)"),
    ("atn", "DIM R AS REAL", "R = ATN(1.0)"),
    ("log", "DIM R AS REAL", "R = LOG(2.0)"),
    ("exp", "DIM R AS REAL", "R = EXP(1.0)"),
    ("int", "DIM R AS REAL", "R = INT(2.5)"),
    ("fix", "DIM R AS REAL", "R = FIX(-2.5)"),
    ("toreal", "DIM R AS REAL", "R = REAL(3)"),
    ("cint", "DIM I AS INTEGER", "I = CINT(2.5)"),
    ("realval", "DIM R AS REAL", "R = REALVAL(\"2.5\")"),
    ("isnum", "DIM B AS BOOLEAN", "B = ISNUM(\"2.5\")"),
    ("pi", "DIM R AS REAL", "R = PI"),
    ("power", "DIM R AS REAL", "R = 2 ^ 3"),
    ("strreal", "DIM S$ AS STRING", "S$ = STR$(2.5)"),
    ("seconds", "DIM I AS INTEGER", "I = SECONDS"),
    ("clockticks", "DIM I AS INTEGER", "I = CLOCKTICKS"),
    ("keydown", "DIM B AS BOOLEAN", "B = KEYDOWN(41)"),
    ("textwidth", "DIM I AS INTEGER", "I = TEXTWIDTH(\"abc\")"),
    ("pagewidth", "DIM I AS INTEGER", "I = PAGEWIDTH(\"abc\")"),
    ("const", "CONST N = 3\nDIM I AS INTEGER", "I = N"),
    ("select", "DIM I AS INTEGER",
     "SELECT CASE I\nCASE 1\nI = 2\nCASE 2 TO 4\nI = 3\nCASE ELSE\nI = 0\nEND SELECT"),
    ("forstep", "DIM I AS INTEGER", "FOR I = 10 TO 1 STEP -3\nNEXT I"),
    ("while", "DIM I AS INTEGER", "WHILE I < 3\nI = I + 1\nWEND"),
    ("exitfor", "DIM I AS INTEGER", "FOR I = 1 TO 5\nIF I = 3 THEN\nEXIT FOR\nEND IF\nNEXT I"),
    ("message", "", "MESSAGE \"hello\""),
    ("message_dyn", "DIM S$ AS STRING", "S$ = \"x\"\nMESSAGE \"v \" + S$"),
    ("beep", "", "BEEP"),
    ("ask", "DIM A AS INTEGER", "A = ASK(\"Go?\", \"Yes\", \"No\")"),
    # arrays and records
    ("array", "DIM A(5) AS INTEGER\nDIM I AS INTEGER", "A(2) = 3\nI = A(2)"),
    ("sarray", "DIM A$(3) AS STRING", "A$(1) = \"x\""),
    ("banked", "DIM B(300) AS INTEGER BANKED", "B(299) = 4"),
    ("fixedstr", "DIM S AS STRING * 8", "S = \"abc\""),
    ("record", "TYPE P\nId AS INTEGER\nName AS STRING * 10\nEND TYPE\nDIM X AS P", "X.Id = 1\nX.Name = \"a\""),
    ("recarray", "TYPE P\nId AS INTEGER\nEND TYPE\nDIM X(3) AS P", "X(1).Id = 1"),
    # files
    ("filesave", "", "FILESAVE \"PBTEST.TXT\", \"abc\""),
    ("fileload", "DIM S$ AS STRING", "FILELOAD \"PBTEST.TXT\", S$"),
    ("open_out", "", "OPEN \"PBTEST.TXT\" FOR OUTPUT AS #2\nPRINT #2, \"x\"\nCLOSE #2"),
    ("open_in", "DIM S$ AS STRING",
     "OPEN \"PBTEST.TXT\" FOR INPUT AS #1\nWHILE NOT EOF(1)\nLINE INPUT #1, S$\nWEND\nCLOSE #1"),
    ("ioerr", "DIM I AS INTEGER", "KILL \"PBTEST.TXT\"\nI = IOERR"),
    ("name", "", "NAME \"PBTEST.TXT\" AS \"PBTEST2.TXT\""),
    ("kill", "", "KILL \"PBTEST.TXT\""),
    # text buffers
    ("text", "DIM T AS TEXT * 200", "TEXT CLEAR T\nTEXT INSERT T, 1, 1, \"abc\""),
    ("textfn", "DIM T AS TEXT * 200\nDIM I AS INTEGER", "I = TEXTLINES(T) + TEXTLEN(T, 1) + TEXTFREE(T)"),
    ("textget", "DIM T AS TEXT * 200\nDIM S$ AS STRING", "S$ = TEXTGET$(T, 1, 1, 3)"),
    ("textsave", "DIM T AS TEXT * 200", "TEXT SAVE T, \"PBTEST.TXT\""),
    ("textload", "DIM T AS TEXT * 200", "TEXT LOAD T, \"PBTEST.TXT\""),
    ("textcopy", "DIM T AS TEXT * 200\nDIM U AS TEXT * 200", "TEXT COPY T, U, 1, 1, 1, 2"),
    # databases
    ("db", "TYPE P\nId AS INTEGER\nName AS STRING * 10\nEND TYPE\nDIM D(10) AS P BANKED\nDIM N AS INTEGER",
     "DB LOAD D, N, \"PBTEST.PDB\"\nDB SAVE D, N, \"PBTEST.PDB\""),
    ("dbrecovered", "TYPE P\nId AS INTEGER\nEND TYPE\nDIM D(10) AS P BANKED\nDIM N AS INTEGER\nDIM B AS BOOLEAN",
     "B = DBRECOVERED"),
    # bitmaps
    ("bitmap", "DIM B AS BITMAP * 16, 16", "BITMAP SAVE B, \"PBTEST.PBI\""),
    ("bitmapwh", "DIM B AS BITMAP * 16, 16\nDIM I AS INTEGER", "I = BITMAPW(B) + BITMAPH(B)"),
    ("bmpload", "DIM B AS BITMAP * 16, 16", "BITMAP LOAD B, \"PBTEST.PBI\""),
    # printing
    ("page", "", "PAGE NEW\nPAGE FONT 12\nPAGE TEXT 10, 10, \"x\"\nPAGE LINE 1, 1, 100, 1\nPAGE CLOSE"),
    ("pagefill", "", "PAGE NEW\nPAGE FILL 10, 10, 50, 50\nPAGE CLOSE"),
]

# facilities that need a canvas (they are tried only in the canvas context,
# and in the others to make sure the front end refuses them cleanly)
CANVAS_SNIPPETS = [
    ("draw", "", "DRAW CLEAR\nDRAW BOX 1, 1, 10, 10\nDRAW LINE 1, 1, 20, 9\nDRAW FILL 2, 2, 5, 5, 3"),
    ("drawtext", "", "DRAW TEXT 1, 1, \"hi\""),
    ("drawcell", "", "DRAW TEXT 1, 1, \"hi\", 12"),
    ("drawink", "", "DRAW INK XOR\nDRAW PIXEL 3, 3\nDRAW INK BLACK"),
    ("scroll", "", "DRAW SCROLL 0, 0, 50, 20, 2, 0"),
    ("point", "DIM I AS INTEGER", "I = POINT(2, 2)"),
    ("bmpget", "DIM B AS BITMAP * 16, 16", "BITMAP GET B, 0, 0\nBITMAP PUT B, 2, 2"),
    ("bmppart", "DIM B AS BITMAP * 16, 16", "BITMAP PUT B, 2, 2, 0, 0, 8, 8"),
    ("bmpmask", "DIM B AS BITMAP * 16, 16\nDIM M AS BITMAP * 16, 16", "BITMAP MASK B, M, 2, 2"),
]

# whole programs: procedures with parameters of every kind, and libraries
WHOLE = [
    ("bmpparam", """SUB Show2(P AS BITMAP)
    BITMAP PUT P, 0, 0
END SUB
WINDOW "W"
CANVAS 64, 32
BUTTON "Quit", Quit
SUB Quit
    EXIT
END SUB
END
"""),
    ("textsub", """DIM T AS TEXT * 100
SUB Fill
    TEXT CLEAR T
    TEXT INSERT T, 1, 1, "x"
END SUB
CALL Fill
END
"""),
    ("recparam", """TYPE P
    Id AS INTEGER
END TYPE
SUB Bump(X AS P)
    X.Id = X.Id + 1
END SUB
DIM Q AS P
CALL Bump(Q)
END
"""),
    ("funcs", """FUNCTION Twice(N AS INTEGER) AS INTEGER
    RETURN N * 2
END FUNCTION
FUNCTION Greet$(S AS STRING) AS STRING
    RETURN "Hi " + S
END FUNCTION
FUNCTION Half(R AS REAL) AS REAL
    RETURN R / 2
END FUNCTION
DIM I AS INTEGER
DIM S$ AS STRING
DIM R AS REAL
I = Twice(3)
S$ = Greet$("a")
R = Half(3.0)
END
"""),
    ("keysonly", """INCLUDE "lib/keys.pbas"
DIM I AS INTEGER
I = SC_LEFT
END
"""),
    ("spritelib", """INCLUDE "lib/sprite.pbas"
WINDOW "W"
CANVAS 64, 32
BUTTON "Quit", Quit
SUB Quit
    EXIT
END SUB
END
"""),
    ("toolbarlib", """INCLUDE "lib/toolbar.pbas"
WINDOW "W"
CANVAS 64, 32
BUTTON "Quit", Quit
SUB Quit
    EXIT
END SUB
END
"""),
]


def _contexts(decls: str, body: str):
    sub_body = "\n".join("    " + ln for ln in body.splitlines())
    yield "main", f"{decls}\n{body}\nEND\n"
    yield "sub", f"{decls}\nSUB P\n{sub_body}\nEND SUB\nCALL P\nEND\n"
    yield "window", (f"{decls}\nWINDOW \"W\"\nBUTTON \"Go\", Go\nBUTTON \"Quit\", Quit\n"
                     f"SUB Go\n{sub_body}\nEND SUB\nSUB Quit\n    EXIT\nEND SUB\nEND\n")
    yield "canvas", (f"{decls}\nWINDOW \"W\", LARGE\nCANVAS 100, 50\nBUTTON \"Go\", Go\nBUTTON \"Quit\", Quit\n"
                     f"SUB Go\n{sub_body}\nEND SUB\nSUB Quit\n    EXIT\nEND SUB\nEND\n")


def programs():
    for name, decls, body in SNIPPETS + CANVAS_SNIPPETS:
        for ctx, src in _contexts(decls, body):
            yield f"{name}-{ctx}", src
    for name, src in WHOLE:
        yield name, src
