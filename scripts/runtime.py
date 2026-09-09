#!/usr/bin/env python3
"""Small, dependency-free launcher for the bundled Blender helper scripts."""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional

MIN_BLENDER_VERSION = (4, 2)
PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def blender_candidates() -> Iterable[Path]:
    """Return plausible Blender executables in precedence order (not existence-filtered)."""
    if os.name == "nt":
        program_files = [os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")]
        for base in filter(None, program_files):
            root = Path(base)
            yield from sorted(root.glob("Blender Foundation/Blender*/blender.exe"), reverse=True)
            # Keep the conventional Steam location even before Blender is installed;
            # find_blender() is responsible for filtering non-existent candidates.
            yield root / "Steam" / "steamapps" / "common" / "Blender" / "blender.exe"
    elif sys.platform == "darwin":
        for root in (Path("/Applications"), Path.home() / "Applications"):
            yield root / "Blender.app" / "Contents" / "MacOS" / "Blender"
            yield from sorted(root.glob("Blender*.app/Contents/MacOS/Blender"), reverse=True)


def find_blender(explicit: Optional[str] = None) -> Optional[Path]:
    choices = []
    if explicit:
        choices.append(Path(explicit).expanduser())
    elif os.environ.get("BLENDER_PATH"):
        choices.append(Path(os.environ["BLENDER_PATH"]).expanduser())
    else:
        found = shutil.which("blender") or shutil.which("Blender")
        if found:
            choices.append(Path(found))
        choices.extend(blender_candidates())
    for candidate in choices:
        if candidate.is_file():
            return candidate.resolve()
    return None


def blender_version(blender: Path) -> tuple[Optional[tuple[int, int, int]], str]:
    try:
        result = subprocess.run(
            [str(blender), "--version"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=20, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, str(exc)
    text = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
    match = re.search(r"Blender\s+(\d+)\.(\d+)(?:\.(\d+))?", text)
    if not match:
        return None, text.strip() or "Blender did not report a parseable version"
    return (int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)), text.strip()


def available_threads(requested: Optional[int]) -> int:
    maximum = max(1, os.cpu_count() or 1)
    if requested is None:
        return min(4, maximum)
    if requested < 1:
        raise ValueError("--threads must be at least 1")
    return min(requested, maximum)


def require_supported_blender(explicit: Optional[str]) -> Path:
    blender = find_blender(explicit)
    if blender is None:
        raise RuntimeError("Blender was not found; pass --blender or set BLENDER_PATH")
    version, detail = blender_version(blender)
    if version is None:
        raise RuntimeError("Could not determine Blender version for %s: %s" % (blender, detail))
    if version[:2] < MIN_BLENDER_VERSION:
        raise RuntimeError("Blender %d.%d is too old; version 4.2 or newer is required" % version[:2])
    return blender


def command_doctor(args: argparse.Namespace) -> int:
    blender = find_blender(args.blender)
    report = {
        "python": {"executable": sys.executable, "version": platform.python_version()},
        "platform": {"system": platform.system(), "release": platform.release()},
        "cpu_threads_available": max(1, os.cpu_count() or 1),
        "blender": {"path": str(blender) if blender else None, "minimum_version": "4.2", "supported": False},
        "notes": ["Designed for Windows and macOS; only capabilities detected on this host are reported."],
    }
    if blender:
        version, detail = blender_version(blender)
        report["blender"].update({"version": ".".join(map(str, version)) if version else None,
                                  "supported": bool(version and version[:2] >= MIN_BLENDER_VERSION)})
        if version is None:
            report["blender"]["error"] = detail
    else:
        report["blender"]["error"] = "not found"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["blender"]["supported"] else 1


def command_run(args: argparse.Namespace) -> int:
    try:
        threads = available_threads(args.threads)
        blender = require_supported_blender(args.blender)
    except (ValueError, RuntimeError) as exc:
        print("runtime: " + str(exc), file=sys.stderr)
        return 2
    script = Path(args.script).expanduser().resolve()
    if not script.is_file():
        print("runtime: script does not exist: " + str(script), file=sys.stderr)
        return 2
    log = Path(args.log).expanduser().resolve()
    if log == script:
        print("runtime: --log must not be the script path", file=sys.stderr)
        return 2
    try:
        log.relative_to(PACKAGE_ROOT)
    except ValueError:
        pass
    else:
        print("runtime: --log must be outside the skill directory", file=sys.stderr)
        return 2
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        command = [str(blender), "--background", "--factory-startup", "--disable-autoexec",
                   "--threads", str(threads), "--python-exit-code", "7", "--python", str(script), "--"]
        script_args = args.script_args[1:] if args.script_args[:1] == ["--"] else args.script_args
        command.extend(script_args)
        with log.open("x", encoding="utf-8", errors="replace") as stream:
            stream.write("# " + subprocess.list2cmdline(command) + "\n")
            stream.flush()
            result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
                                    shell=False, check=False)
    except FileExistsError:
        print("runtime: log already exists; choose a new --log path", file=sys.stderr)
        return 2
    except OSError as exc:
        print("runtime: failed to start Blender: " + str(exc), file=sys.stderr)
        return 2
    return result.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="report actual local Blender availability")
    doctor.add_argument("--blender", help="explicit Blender executable")
    doctor.set_defaults(handler=command_doctor)
    run = commands.add_parser("run", help="run a Blender Python script without a shell")
    run.add_argument("--blender", help="explicit Blender executable")
    run.add_argument("--threads", type=int, help="CPU threads to use (capped at available CPUs)")
    run.add_argument("--log", required=True, help="log file, outside this skill directory")
    run.add_argument("script", help="Blender Python script")
    run.add_argument("script_args", nargs=argparse.REMAINDER, help="arguments supplied after -- to the script")
    run.set_defaults(handler=command_run)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
