"""M4 FILESAVE / FILELOAD tests (LANGUAGE-SPEC.md section 7).

Frontend and option tests need nothing but Python. The behaviour tests build
each program with the real pipeline (Pasmo) and run it on ``tests/z80sim.py``
under the M2.1 memory checker (``tests/memguard.py``), against the
simulator's in-memory ``Disk``: no test reads or writes a host file, so no
user data can be touched. The model's filing functions follow ROSAN283
"THE FILING FUNCTIONS"; where the document is silent (does opening for
write truncate? hypothesis H-TRUNC) the model states its assumption. None
of this is XAnne evidence (TESTING-STRATEGY.md).
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import z80sim
from memguard import guarded_run, string_var
from pbas import SourceError, check_source
from pbas.files import (
    DEFAULT_FOLDER,
    FileLocation,
    FileLocationError,
    descriptor_bytes,
    make_location,
    normalise_folder,
)
from test_controls import numbers
from toolchain import requires_files, requires_pasmo

ROOT = Path(__file__).resolve().parent.parent
POC = ROOT.parent / "POC"
F01 = DEFAULT_FOLDER
FN_SET_CWD = z80sim.FN_OS_SET_CWD
FN_OPEN = z80sim.FN_OS_OPEN_FILE
FN_WRITE = z80sim.FN_OS_WRITE_FILE


def example(name: str) -> str:
    return (ROOT / "examples" / f"{name}.pbas").read_text(encoding="utf-8")


def disk_with(files=None, **kwargs) -> z80sim.Disk:
    """A model disk whose files are given as {"NAME.EXT": bytes} in F01."""
    return z80sim.Disk(files={(F01, k): v for k, v in (files or {}).items()}, **kwargs)


# ------------------------------------------------------------------ frontend
class FileNameTests(unittest.TestCase):
    def reject(self, source: str) -> SourceError:
        with self.assertRaises(SourceError) as caught:
            check_source(source)
        return caught.exception

    def test_valid_names(self):
        for name in ("A.B", "NOTE.TXT", "PBRTRIP.TXT", "ABCDEFGH.XYZ", "A_1.T2", "note.txt"):
            with self.subTest(name=name):
                check_source(f'DIM S$ AS STRING\nFILESAVE "{name}", S$\nFILELOAD "{name}", S$\nEND\n')

    def test_invalid_names_are_positioned(self):
        for name in ("NOTE", "ABCDEFGHI.TXT", "NOTE.TEXT", "NO TE.TXT", "NO-TE.TXT",
                     "A\\\\B.TXT", ".TXT", "A.", "A.B.C", ""):
            with self.subTest(name=name):
                err = self.reject(f'DIM S$ AS STRING\nFILESAVE "{name}", S$\nEND\n')
                self.assertEqual((err.line, err.column), (2, 10))
                self.assertIn("DOS 8.3", err.message)

    def test_device_names_are_refused(self):
        for name in ("CON.TXT", "nul.dat", "LPT1.TXT", "COM3.X"):
            with self.subTest(name=name):
                err = self.reject(f'DIM S$ AS STRING\nFILELOAD "{name}", S$\nEND\n')
                self.assertIn("device name", err.message)
        check_source('DIM S$ AS STRING\nFILESAVE "CONSOLE.TXT", S$\nEND\n')  # only exact names

    def test_name_must_be_a_literal(self):
        err = self.reject('DIM S$ AS STRING\nDIM N$ AS STRING\nFILESAVE N$, S$\nEND\n')
        self.assertIn("written in the program as a string", err.message)  # M14 (D12): the message names the rule

    def test_names_are_upper_cased_into_the_descriptor(self):
        self.assertEqual(descriptor_bytes("note.txt"), b"NOTE\0.TXT\0")
        self.assertEqual(descriptor_bytes("A_1.T2"), b"A_1\0.T2\0")


class FileValueTests(unittest.TestCase):
    def reject(self, source: str, capacity: int = 64) -> SourceError:
        with self.assertRaises(SourceError) as caught:
            check_source(source, string_capacity=capacity)
        return caught.exception

    def test_fileload_needs_a_string_variable(self):
        for target in ("N", '"x"', "S$ + S$", 'LEFT$(S$, 1)'):
            with self.subTest(target=target):
                err = self.reject(f'DIM S$ AS STRING\nDIM N AS INTEGER\nFILELOAD "A.TXT", {target}\nEND\n')
                self.assertIn("string variable", err.message)

    def test_filesave_needs_a_string(self):
        err = self.reject('DIM N AS INTEGER\nFILESAVE "A.TXT", N\nEND\n')
        self.assertIn("FILESAVE expects STRING", err.message)

    def test_filesave_value_bound(self):
        # 63 + 63 + 1 = 127 bytes fits the file buffer exactly; one more may not.
        check_source('DIM A$ AS STRING\nDIM B$ AS STRING\nFILESAVE "A.TXT", A$ + B$ + "!"\nEND\n')
        err = self.reject('DIM A$ AS STRING\nDIM B$ AS STRING\nFILESAVE "A.TXT", A$ + B$ + "!!"\nEND\n')
        self.assertEqual((err.line, err.column), (3, 1))
        self.assertIn("may be up to 128 bytes; a file written by FILESAVE holds at most 127", err.message)
        check_source(f'FILESAVE "A.TXT", "{"x" * 127}"\nEND\n')
        self.reject(f'FILESAVE "A.TXT", "{"x" * 128}"\nEND\n')


class FileLocationTests(unittest.TestCase):
    def test_defaults_are_the_poc_location(self):
        self.assertEqual(make_location(), FileLocation("floppy", "\\PCW\\FOLDER01"))
        self.assertEqual(make_location().device, 1)

    def test_folder_normalisation(self):
        self.assertEqual(normalise_folder("/pcw/folder01"), "\\PCW\\FOLDER01")
        self.assertEqual(normalise_folder("\\PCW\\PBTEST\\"), "\\PCW\\PBTEST")
        self.assertEqual(normalise_folder("\\"), "\\")
        self.assertEqual(normalise_folder("\\A.B\\C_1"), "\\A.B\\C_1")

    def test_invalid_folders(self):
        for folder in ("PCW\\FOLDER01", "\\PCW\\TOOLONGNAME", "\\PCW\\A B", "\\PCW\\\\X",
                       "\\" + "\\".join(["ABCDEFGH"] * 8), "C:\\PCW"):
            with self.subTest(folder=folder), self.assertRaises(FileLocationError):
                normalise_folder(folder)

    def test_drives(self):
        with self.assertRaisesRegex(FileLocationError, "flash is not supported: "):  # M14 (D13)
            make_location("flash")
        with self.assertRaisesRegex(FileLocationError, "must be 'floppy'"):
            make_location("C")
        self.assertEqual(make_location("FLOPPY").drive, "floppy")

    def test_build_cli_reports_a_bad_folder_without_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            for option, message in ((["--folder", "PCW"], "absolute path"),
                                    (["--drive", "flash"], "flash is not supported")):
                proc = subprocess.run(
                    [sys.executable, str(ROOT / "tools" / "build.py"),
                     str(ROOT / "examples" / "missing_file.pbas"), "--out-dir", str(out), *option],
                    capture_output=True, text=True,
                )
                self.assertEqual(proc.returncode, 1)
                self.assertIn(message, proc.stderr)
                self.assertFalse(out.exists())


# ----------------------------------------------------------------- behaviour
@requires_pasmo
class FileBehaviourTests(unittest.TestCase):
    maxDiff = None

    def run_files(self, source, disk=None, events=None, capacity=64, location=None):
        disk = disk if disk is not None else disk_with()
        run = guarded_run(source, string_capacity=capacity, events=events, disk=disk, location=location)
        self.assertEqual(run.violations, [], "memory-boundary violations")
        # resource cleanup: nothing is ever left open, at exit or otherwise
        self.assertIsNone(disk.open_read, "a file was left open for read")
        self.assertIsNone(disk.open_write, "a file was left open for write")
        if run.cpu.exited:
            self.assertEqual(disk.open_at_exit, (None, None))
        return run, disk

    # --- save / load of plain STRING variables
    def test_round_trip_writes_exact_bytes(self):
        run, disk = self.run_files(
            'DIM A$ AS STRING\nDIM B$ AS STRING\nA$ = "Hello PcW16"\n'
            'FILESAVE "T1.TXT", A$\nFILELOAD "T1.TXT", B$\nMESSAGE B$\nEND\n'
        )
        self.assertEqual(disk.file("T1.TXT"), b"Hello PcW16")  # no NUL, no line ending
        self.assertEqual(run.alerts, ["File saved: T1.TXT", "File loaded: T1.TXT", "Hello PcW16"])
        self.assertEqual(string_var(run, "B$"), "Hello PcW16")

    def test_os_arguments(self):
        run, _ = self.run_files('DIM A$ AS STRING\nFILESAVE "t1.txt", A$\nFILELOAD "T1.TXT", A$\nEND\n')
        log = run.cpu.os_log
        self.assertEqual([d for fn, d in log if fn == FN_SET_CWD], [F01, F01])
        self.assertEqual([d for fn, d in log if fn == FN_OPEN], [("T1.TXT", 1), ("T1.TXT", 0)])
        self.assertEqual([d for fn, d in log if fn == z80sim.FN_OS_SET_DEVICE], [1, 1])
        # an empty string is saved without an os_write_file call
        self.assertEqual([d for fn, d in log if fn == FN_WRITE], [])

    def test_empty_string_and_empty_file(self):
        run, disk = self.run_files(
            'DIM A$ AS STRING\nA$ = "x"\nFILESAVE "E.TXT", ""\nFILELOAD "E.TXT", A$\n'
            'MESSAGE "[" + A$ + "]"\nEND\n'
        )
        self.assertEqual(disk.file("E.TXT"), b"")
        self.assertEqual(run.alerts, ["File saved: E.TXT", "File loaded: E.TXT", "[]"])

    def test_bytes_are_kept_exactly(self):
        data = bytes(range(1, 64))  # every non-zero byte value up to 63, control codes included
        run, _ = self.run_files(
            'DIM A$ AS STRING\nDIM B$ AS STRING\nFILELOAD "BIN.DAT", A$\n'
            'FILESAVE "COPY.DAT", A$\nEND\n',
            disk=disk_with({"BIN.DAT": data}),
        )
        self.assertEqual(run.cpu.disk.file("COPY.DAT"), data)
        high = bytes([0xA3, 0x80, 0xFF, 0x41])
        run, disk = self.run_files(
            'DIM A$ AS STRING\nFILELOAD "HI.DAT", A$\nFILESAVE "HI2.DAT", A$\nEND\n',
            disk=disk_with({"HI.DAT": high}),
        )
        self.assertEqual(disk.file("HI2.DAT"), high)

    def test_filesave_of_an_expression(self):
        run, disk = self.run_files(
            'DIM N AS INTEGER\nDIM W$ AS STRING\nN = -321\nW$ = "abcdef"\n'
            'FILESAVE "X.TXT", "N=" + STR$(N) + ";" + MID$(W$, 2, 3)\nEND\n'
        )
        self.assertEqual(disk.file("X.TXT"), b"N=-321;bcd")

    # --- missing files and folders
    def test_missing_file_is_reported_and_not_created(self):
        run, disk = self.run_files(example("missing_file"))
        self.assertEqual(run.alerts, [
            "File not loaded: PBNOFILE.TXT (not found)",
            "Still running; Got$ is unchanged",
            "File not loaded: PBNOFILE.TXT (not found)",
            "Second try done; Got$ is unchanged",
        ])
        self.assertEqual(disk.files, {})
        self.assertNotIn(1, [d[1] for fn, d in run.cpu.os_log if fn == FN_OPEN])  # never opened for write
        self.assertTrue(run.cpu.exited)

    def test_missing_folder(self):
        location = make_location(folder="\\PCW\\PBNOFLDR")
        run, disk = self.run_files(example("missing_file"), location=location)
        self.assertEqual(run.alerts[0], "File not loaded: PBNOFILE.TXT (folder not found)")
        run, disk = self.run_files('DIM A$ AS STRING\nA$ = "x"\nFILESAVE "A.TXT", A$\nEND\n', location=location)
        self.assertEqual(run.alerts, ["File not saved: A.TXT (folder not found)"])
        self.assertEqual(disk.files, {})  # nothing created anywhere

    def test_other_folders_and_root(self):
        for folder in ("\\PCW\\PBTEST", "\\", "\\DATA\\SUB_1"):
            with self.subTest(folder=folder):
                disk = z80sim.Disk(folders=("\\", "\\PCW", "\\PCW\\PBTEST", "\\DATA", "\\DATA\\SUB_1"))
                run, _ = self.run_files(
                    'DIM A$ AS STRING\nA$ = "here"\nFILESAVE "W.TXT", A$\nA$ = ""\n'
                    'FILELOAD "W.TXT", A$\nMESSAGE A$\nEND\n',
                    disk=disk, location=make_location(folder=folder),
                )
                self.assertEqual(disk.files, {(folder, "W.TXT"): b"here"})
                self.assertEqual(run.alerts[-1], "here")
                self.assertEqual([d for fn, d in run.cpu.os_log if fn == FN_SET_CWD], [folder, folder])

    # --- overwrite and repeated saves
    def test_repeated_saves_replace_the_file(self):
        run, disk = self.run_files(example("file_roundtrip"))
        self.assertEqual(run.alerts, [
            "File saved: PBRTRIP.TXT", "File loaded: PBRTRIP.TXT",
            "Trip 1 OK: PcW16 round trip 42 (19 letters)",
            "File saved: PBRTRIP.TXT", "File loaded: PBRTRIP.TXT",
            "Trip 2 OK: Short (5 letters)",
        ])
        self.assertEqual(disk.files, {(F01, "PBRTRIP.TXT"): b"Short"})

    def test_round_trip_detects_a_non_truncating_open(self):
        # If Rosanne's open-for-write overwrote in place instead of
        # truncating (the alternative to H-TRUNC; ROSAN283 is silent), the
        # example must say so rather than pass: XAnne question F1.
        run, disk = self.run_files(example("file_roundtrip"), disk=disk_with(truncate_on_open=False))
        self.assertEqual(run.alerts[-1], "Trip 2 MISMATCH: Short round trip 42")
        self.assertEqual(disk.file("PBRTRIP.TXT"), b"Short round trip 42")

    def test_only_the_named_file_is_written(self):
        other = {"NOTE.TXT": b"owner's note", "PBMEMO.TXT": b"keep"}
        run, disk = self.run_files(example("file_roundtrip"), disk=disk_with(dict(other)))
        for name, data in other.items():
            self.assertEqual(disk.file(name), data, name)

    # --- capacity limits
    def test_capacity_limits(self):
        for capacity in (2, 4, 64, 127):
            fits = b"y" * (capacity - 1)
            for data, ok in ((fits, True), (fits + b"z", False), (b"q" * 500, False), (b"r" * 1200, False)):
                with self.subTest(capacity=capacity, size=len(data)):
                    run, _ = self.run_files(
                        'DIM A$ AS STRING\nA$ = "k"\nFILELOAD "L.TXT", A$\nMESSAGE A$\nEND\n',
                        disk=disk_with({"L.TXT": data}), capacity=capacity,
                    )
                    if ok:
                        self.assertEqual(run.alerts[0], "File loaded: L.TXT")
                        self.assertEqual(string_var(run, "A$"), fits.decode())
                    else:
                        self.assertEqual(
                            run.alerts[0],
                            f"File not loaded: L.TXT (longer than {capacity - 1} characters)",
                        )
                        self.assertEqual(string_var(run, "A$"), "k")  # unchanged

    def test_file_limits_example(self):
        disk = disk_with({
            "PBEXACT.TXT": b"E" * 63, "PBLONG.TXT": b"L" * 64, "PBZERO.TXT": b"ab\0cd",
        })
        run, _ = self.run_files(example("file_limits"), disk=disk)
        self.assertEqual(run.alerts, [
            "File loaded: PBEXACT.TXT", "PBEXACT gives 63 letters",
            "File not loaded: PBLONG.TXT (longer than 63 characters)", "After PBLONG: start",
            "File not loaded: PBZERO.TXT (not text)", "After PBZERO: start",
        ])

    # --- OS failures: reported, cleaned up, nothing changed
    def test_failures_are_reported_and_closed(self):
        save = 'DIM A$ AS STRING\nA$ = "data"\nFILESAVE "F.TXT", A$\nMESSAGE "after"\nEND\n'
        load = 'DIM A$ AS STRING\nA$ = "keep"\nFILELOAD "F.TXT", A$\nMESSAGE A$\nEND\n'
        cases = [
            (save, {z80sim.FN_OS_SET_DEVICE: 1}, "File not saved: F.TXT (drive error)"),
            (save, {z80sim.FN_OS_SET_CWD: 0xB7}, "File not saved: F.TXT (error #B7)"),
            (save, {FN_OPEN: 0x13}, "File not saved: F.TXT (error #13)"),
            (save, {FN_WRITE: 0xA3}, "File not saved: F.TXT (error #A3)"),
            (save, {z80sim.FN_OS_CLOSE_FILE: 0xD1}, "File not saved: F.TXT (error #D1)"),
            (load, {FN_OPEN: 0x05}, "File not loaded: F.TXT (error #05)"),
            (load, {z80sim.FN_OS_READ_FILE: 0x08}, "File not loaded: F.TXT (error #08)"),
            (load, {z80sim.FN_OS_CLOSE_FILE: 0x02}, "File not loaded: F.TXT (error #02)"),
        ]
        for source, faults, alert in cases:
            with self.subTest(alert=alert):
                disk = disk_with({"F.TXT": b"old"}, faults=faults)
                run, _ = self.run_files(source, disk=disk)
                self.assertEqual(run.alerts, [alert, "keep" if source is load else "after"])
                self.assertTrue(run.cpu.exited, "the program carries on after a file failure")

    # --- M4 repair: XAnne ROUNDTRP gave "(read error)" on every load
    def test_owner_roundtrip_session_xanne_regression(self):
        # Owner, XAnne: ROUNDTRP.PRG showed "File not loaded: PBRTRIP.TXT
        # (read error)" twice and both trips MISMATCH, while the file held
        # exactly "Short". Rosanne returned #A1 with BDE/CHL values that did
        # not fit ROSAN283's wording; the M4 runtime trusted them. The
        # repaired load must give the expected session whatever they hold.
        for mode in ("unspecified", "documented"):
            with self.subTest(eof_registers=mode):
                run, disk = self.run_files(example("file_roundtrip"), disk=disk_with(eof_registers=mode))
                self.assertEqual(run.alerts, [
                    "File saved: PBRTRIP.TXT", "File loaded: PBRTRIP.TXT",
                    "Trip 1 OK: PcW16 round trip 42 (19 letters)",
                    "File saved: PBRTRIP.TXT", "File loaded: PBRTRIP.TXT",
                    "Trip 2 OK: Short (5 letters)",
                ])
                self.assertEqual(disk.file("PBRTRIP.TXT"), b"Short")

    def test_load_outcome_does_not_depend_on_eof_registers(self):
        source = 'DIM A$ AS STRING\nA$ = "keep"\nFILELOAD "F.TXT", A$\nMESSAGE "[" + A$ + "]"\nEND\n'
        cases = {
            b"": ["File loaded: F.TXT", "[]"],
            b"x": ["File loaded: F.TXT", "[x]"],
            b"Short": ["File loaded: F.TXT", "[Short]"],
            b"E" * 63: ["File loaded: F.TXT", "[" + "E" * 63 + "]"],
            b"L" * 64: ["File not loaded: F.TXT (longer than 63 characters)", "[keep]"],
            b"Q" * 600: ["File not loaded: F.TXT (longer than 63 characters)", "[keep]"],
            b"ab\0cd": ["File not loaded: F.TXT (not text)", "[keep]"],
        }
        for data, alerts in cases.items():
            for mode in ("unspecified", "documented"):
                with self.subTest(size=len(data), eof_registers=mode):
                    run, _ = self.run_files(source, disk=disk_with({"F.TXT": data}, eof_registers=mode))
                    self.assertEqual(run.alerts, alerts)

    def test_one_byte_per_read_and_bounded_read_count(self):
        # Each os_read_file asks for exactly 1 byte; a fitting file takes
        # length + 1 reads (the last one ends the file), a too-long file
        # exactly capacity reads, never more.
        source = 'DIM A$ AS STRING\nFILELOAD "F.TXT", A$\nEND\n'
        for data, reads in ((b"", 1), (b"Short", 6), (b"E" * 63, 64), (b"L" * 64, 64), (b"Q" * 600, 64)):
            with self.subTest(size=len(data)):
                run, _ = self.run_files(source, disk=disk_with({"F.TXT": data}))
                lengths = [d for fn, d in run.cpu.os_log if fn == z80sim.FN_OS_READ_FILE]
                self.assertEqual(lengths, [1] * reads)

    # --- GUI: repeated handler use, TEXTBOX refresh
    def test_mini_notes_session(self):
        source = example("mini_notes")
        n = numbers(source)
        disk = disk_with()
        run, _ = self.run_files(source, disk=disk, events=[
            ("click", n["Load"]),                       # nothing saved yet
            ("edit", n["MEMO$"], "Buy stamps"), ("click", n["Save"]),
            ("edit", n["MEMO$"], "something else entirely"), ("click", n["Load"]),
        ])
        self.assertEqual(run.alerts, [
            "File not loaded: PBMEMO.TXT (not found)",
            "File saved: PBMEMO.TXT", "File loaded: PBMEMO.TXT",
        ])
        self.assertEqual(run.cpu.control_text(n["MEMO$"], shown=True), "Buy stamps")  # redrawn (M3b)
        self.assertEqual(disk.file("PBMEMO.TXT"), b"Buy stamps")
        # clear the field, save the empty memo, reload
        run, _ = self.run_files(source, disk=disk, events=[
            ("click", n["Load"]), ("edit", n["MEMO$"], ""), ("click", n["Save"]),
            ("edit", n["MEMO$"], "typed but not saved"), ("click", n["Load"]),
            ("click", n["Quit"]),
        ])
        self.assertEqual(run.cpu.control_text(n["MEMO$"], shown=True), "")
        self.assertEqual(disk.file("PBMEMO.TXT"), b"")
        self.assertTrue(run.cpu.exited)

    def test_relaunch_keeps_the_saved_memo(self):
        source = example("mini_notes")
        n = numbers(source)
        disk = disk_with()
        self.run_files(source, disk=disk, events=[
            ("edit", n["MEMO$"], "kept across runs"), ("click", n["Save"]), ("click", n["Quit"]),
        ])
        run, _ = self.run_files(source, disk=disk, events=[("click", n["Load"])])
        self.assertEqual(run.cpu.control_text(n["MEMO$"], shown=True), "kept across runs")

    def test_repeated_operations_from_handlers(self):
        source = example("mini_notes")
        n = numbers(source)
        events = []
        for i in range(6):
            events += [("edit", n["MEMO$"], f"memo {i}" * (i + 1)), ("click", n["Save"]), ("click", n["Load"])]
        run, disk = self.run_files(source, events=events)
        self.assertEqual(len(run.alerts), 12)
        self.assertEqual(disk.file("PBMEMO.TXT"), ("memo 5" * 6).encode())
        self.assertEqual(run.cpu.control_text(n["MEMO$"], shown=True), "memo 5" * 6)

    def test_textbox_load_of_a_shorter_text_is_redrawn_cleanly(self):
        # M3b redraw regression through FILELOAD: a shorter loaded text must
        # not leave the end of the longer one visible.
        source = example("mini_notes")
        n = numbers(source)
        run, _ = self.run_files(source, disk=disk_with({"PBMEMO.TXT": b"Amstr"}), events=[
            ("edit", n["MEMO$"], "Amstrad PcW16"), ("click", n["Load"]),
        ])
        self.assertEqual(run.cpu.control_text(n["MEMO$"], shown=True), "Amstr")

    def test_main_line_load_before_the_window(self):
        source = (
            'DIM Memo$ AS STRING\nFILELOAD "PBMEMO.TXT", Memo$\nWINDOW "W"\n'
            'TEXTBOX Memo$\nBUTTON "Quit", Q\nSUB Q\nEXIT\nEND SUB\nEND\n'
        )
        n = numbers(source)
        run, _ = self.run_files(source, disk=disk_with({"PBMEMO.TXT": b"from disk"}))
        self.assertEqual(run.alerts, ["File loaded: PBMEMO.TXT"])
        self.assertEqual(run.cpu.control_text(n["MEMO$"], shown=True), "from disk")

    def test_failed_load_leaves_a_bound_textbox_alone(self):
        source = example("mini_notes")
        n = numbers(source)
        run, _ = self.run_files(source, disk=disk_with({"PBMEMO.TXT": b"x" * 64}), events=[
            ("edit", n["MEMO$"], "mine"), ("click", n["Load"]),
        ])
        self.assertEqual(run.alerts, ["File not loaded: PBMEMO.TXT (longer than 63 characters)"])
        self.assertEqual(run.cpu.control_text(n["MEMO$"], shown=True), "mine")
        self.assertNotIn(z80sim.FN_OS_OBJECT_UPDATE, [fn for fn, _ in run.cpu.os_log])


# ------------------------------------------------------- XAnne diagnostic
@requires_pasmo
class ReadDiagnosticTests(unittest.TestCase):
    """developer-tests/readdiag.asm (M4 repair): the owner runs it in XAnne, so it must
    be read-only and must survive missing files. Model run only."""

    def run_diag(self, files, mode="unspecified"):
        with tempfile.TemporaryDirectory() as tmp:
            prg = Path(tmp) / "readdiag.prg"
            subprocess.run(["pasmo", "--bin", str(ROOT / "developer-tests" / "readdiag.asm"), str(prg)],
                           check=True, capture_output=True)
            disk = disk_with(dict(files), eof_registers=mode)
            cpu = z80sim.run(prg, disk=disk)
        self.assertTrue(cpu.exited)
        self.assertEqual(disk.files, {(F01, k): v for k, v in files.items()}, "the diagnostic changed a file")
        self.assertEqual([d[1] for fn, d in cpu.os_log if fn == FN_OPEN and d[1] != 0], [], "opened for write")
        self.assertNotIn(FN_WRITE, [fn for fn, _ in cpu.os_log])
        self.assertIsNone(disk.open_read)
        return cpu.alerts

    def test_reports_the_documented_values_on_the_documented_model(self):
        alerts = self.run_diag({"PBRTRIP.TXT": b"Short", "PBEMPTY.TXT": b""}, mode="documented")
        self.assertEqual(len(alerts), 15)
        self.assertEqual(alerts[0], "D1 results: A1")
        self.assertEqual(alerts[1], "D1 last: Cy=1 A=A1 BDE=00003B CHL=000005")
        self.assertTrue(alerts[2].startswith("D1 buf: 53 68 6F 72 74"))
        self.assertEqual(alerts[6], "D3 results: NC NC NC NC NC A1")
        self.assertEqual(alerts[12], "D5 results: A1")

    def test_missing_files_are_reported_not_created(self):
        alerts = self.run_diag({})
        self.assertEqual(alerts, [f"D{i} open failed A=02" for i in range(1, 6)])


# ------------------------------------------------------------- Notes parity
@requires_pasmo
@requires_files(POC / "examples" / "notes_v051.pbas", what="the prototype's example programs")  # M14
class NotesParityTests(unittest.TestCase):
    """The POC v0.5.1 programs, read-only, through the production compiler.

    The acceptance workflow of POC/README-v0.5.1.md: "Type Hello PcW16,
    Save, Exit, relaunch, Load. Confirm field shows Hello PcW16. Edit it,
    Save ... The Load button should not create a file if one is missing."
    The production alerts differ from the POC's Notes-specific "Note saved"
    / "Note loaded": they are the language's generic file alerts.
    """

    def run_notes(self, disk, events):
        source = (POC / "examples" / "notes_v051.pbas").read_text(encoding="utf-8")
        n = numbers(source)
        run = guarded_run(source, events=events(n), disk=disk)
        self.assertEqual(run.violations, [])
        self.assertIsNone(disk.open_read)
        self.assertIsNone(disk.open_write)
        return run, n

    def test_v051_workflow(self):
        disk = disk_with()
        run, n = self.run_notes(disk, lambda n: [
            ("click", n["Load"]),
            ("edit", n["NOTE$"], "Hello PcW16"), ("click", n["Save"]), ("click", n["Exit"]),
        ])
        self.assertEqual(run.alerts, ["File not loaded: NOTE.TXT (not found)", "File saved: NOTE.TXT"])
        self.assertEqual(disk.files, {(F01, "NOTE.TXT"): b"Hello PcW16"})
        run, n = self.run_notes(disk, lambda n: [  # relaunch
            ("click", n["Load"]),
            ("edit", n["NOTE$"], "Hello again"), ("click", n["Save"]), ("click", n["Exit"]),
        ])
        self.assertEqual(run.alerts, ["File loaded: NOTE.TXT", "File saved: NOTE.TXT"])
        self.assertEqual(disk.file("NOTE.TXT"), b"Hello again")
        self.assertTrue(run.cpu.exited)

    def test_v051_load_shows_the_note(self):
        disk = disk_with({"NOTE.TXT": b"Hello PcW16"})
        run, n = self.run_notes(disk, lambda n: [("click", n["Load"])])
        self.assertEqual(run.cpu.control_text(n["NOTE$"], shown=True), "Hello PcW16")

    def test_poc_programs_build_unchanged(self):
        for name in ("notes_v051", "note_saver"):
            with self.subTest(name=name):
                guarded_run((POC / "examples" / f"{name}.pbas").read_text(encoding="utf-8"),
                            events=[], disk=disk_with())


if __name__ == "__main__":
    unittest.main()
