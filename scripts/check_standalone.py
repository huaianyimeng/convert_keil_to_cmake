#!/usr/bin/env python3
"""Verify that a converted CMake project is a fully standalone directory.

The check is deliberately static and read-only. It verifies that:

* the output directory is separate from the original Keil tree;
* no build-related text file inside the output references the original Keil tree;
* every compile unit (and every include directory) from compile_commands.json
  stays inside the output directory;
* the output actually carries a self-contained source/header tree;
* the minimum generated project files exist.

Keil audit copies (``*.uvprojx``, ``*.uvoptx``, ``*.uvguix.*``) are excluded
from the reference scan because the build never reads them; they are still
listed in the report so the exclusion is visible.

Usage::

    python check_standalone.py --source <keil-tree> --output <standalone-dir>
    python check_standalone.py --source <keil-tree> --output <standalone-dir> --json

``--source`` may be repeated, for example for both the outer project folder and
the inner ``MDK-ARM`` folder. ``--compile-commands`` defaults to
``<output>/build/compile_commands.json`` and is skipped when it does not exist
(which is expected in generation-only mode).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
from pathlib import Path


SKIP_DIR_NAMES = {".git", "__pycache__", ".idea", "node_modules", ".svn"}
AUDIT_SUFFIXES = (".uvprojx", ".uvoptx", ".uvproj", ".uvopt")
SOURCE_SUFFIXES = {".c", ".h", ".s", ".cpp", ".hpp", ".cc", ".cxx", ".ld", ".sct"}
MAX_TEXT_BYTES = 8 * 1024 * 1024
MAX_REPORTED_HITS = 20


def norm_path(path: Path) -> str:
    """Normalize an absolute path for case-insensitive, slash-based matching."""
    value = os.path.normcase(os.path.normpath(str(path.resolve(strict=False)))).replace("\\", "/")
    return re.sub(r"/+", "/", value)


def norm_text(text: str) -> str:
    # Collapse mixed/repeated separators too: MSYS and UNC paths often appear
    # as D://project//... while Keil files use D:\project\...
    value = os.path.normcase(text).replace("\\", "/")
    return re.sub(r"/+", "/", value)


def is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve(strict=False).relative_to(parent.resolve(strict=False))
        return True
    except ValueError:
        return False


def is_audit_copy(name: str) -> bool:
    lower = name.lower()
    return lower.endswith(AUDIT_SUFFIXES) or ".uvguix." in lower or lower.endswith(".uvguix")


def iter_text_files(root: Path):
    """Yield (path, text) for readable text files, skipping binaries and audit copies."""
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in SKIP_DIR_NAMES for part in relative.parts[:-1]):
            continue
        if is_audit_copy(path.name):
            continue
        try:
            if path.stat().st_size > MAX_TEXT_BYTES:
                continue
            data = path.read_bytes()
        except OSError:
            continue
        if b"\x00" in data:
            continue
        yield path, data.decode("utf-8", errors="replace")


def find_references(text: str, needles: list[str]) -> list[tuple[str, int]]:
    """Return (needle, line number) for each source-tree path occurrence."""
    normalized = norm_text(text)
    hits: list[tuple[str, int]] = []
    for needle in needles:
        # Allow a following slash (a child path) but reject characters that
        # would make this a different, longer directory name (motor_boardCmake).
        pattern = re.escape(needle) + r"(?=[^A-Za-z0-9_.-]|$)"
        for match in re.finditer(pattern, normalized):
            line = normalized.count("\n", 0, match.start()) + 1
            hits.append((needle, line))
    return hits


def command_tokens(entry: dict) -> list[str]:
    if "arguments" in entry:
        return [str(value) for value in entry["arguments"]]
    return shlex.split(str(entry.get("command", "")), posix=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", required=True,
                        help="original Keil tree (repeatable); never written to")
    parser.add_argument("--output", required=True, help="standalone converted project directory")
    parser.add_argument("--compile-commands", default=None,
                        help="defaults to <output>/build/compile_commands.json")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = parser.parse_args()

    output = Path(args.output)
    sources = [Path(item) for item in args.source]
    if not output.is_dir():
        print(f"standalone: output directory does not exist: {output}", file=sys.stderr)
        return 2

    checks: dict[str, object] = {}
    errors: list[str] = []
    warnings: list[str] = []

    # 1. Directory separation: never generate inside the Keil source tree.
    separation_errors = []
    for source in sources:
        if norm_path(output) == norm_path(source):
            separation_errors.append(f"output is the Keil source directory: {source}")
        elif is_within(output, source):
            separation_errors.append(f"output is inside the Keil source tree: {source}")
        elif is_within(source, output):
            separation_errors.append(f"Keil source tree is inside the output directory: {source}")
    checks["directory_separation"] = "pass" if not separation_errors else "fail"
    errors.extend(separation_errors)

    # 2. No textual reference to the Keil tree in generated/build files.
    needles = sorted({norm_path(source) for source in sources}, key=len, reverse=True)
    audit_copies: list[str] = []
    for path in sorted(output.rglob("*")):
        if path.is_file() and is_audit_copy(path.name):
            audit_copies.append(path.relative_to(output).as_posix())
    hits: list[str] = []
    scanned = 0
    for path, text in iter_text_files(output):
        scanned += 1
        for needle, line in find_references(text, needles):
            hits.append(f"{path.relative_to(output).as_posix()}:{line} -> {needle}")
    checks["no_source_tree_references"] = "pass" if not hits else "fail"
    checks["files_scanned"] = scanned
    if hits:
        errors.append(f"{len(hits)} references to the original Keil tree found in build files")
    if audit_copies:
        warnings.append(f"{len(audit_copies)} Keil audit copies excluded from the scan (build never reads them)")

    # 3. Compile units and include directories stay inside the output.
    cc_path = Path(args.compile_commands) if args.compile_commands else output / "build" / "compile_commands.json"
    if cc_path.is_file():
        try:
            entries = json.loads(cc_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            checks["compile_commands"] = "fail"
            errors.append(f"cannot read compile_commands.json: {error}")
            entries = []
        if entries or checks.get("compile_commands") != "fail":
            outside_sources: list[str] = []
            external_includes: set[str] = set()
            for entry in entries:
                directory = Path(str(entry.get("directory", ".")))
                source_file = Path(str(entry["file"]))
                if not source_file.is_absolute():
                    source_file = directory / source_file
                if not is_within(source_file, output):
                    outside_sources.append(str(source_file))
                tokens = [token.strip('"') for token in command_tokens(entry)]
                for index, token in enumerate(tokens):
                    include: Path | None = None
                    if token in ("-I", "-isystem") and index + 1 < len(tokens):
                        include = Path(tokens[index + 1].strip('"'))
                    elif token.startswith("-I") and len(token) > 2:
                        include = Path(token[2:])
                    elif token.startswith("-isystem") and len(token) > 8:
                        include = Path(token[8:])
                    if include is None:
                        continue
                    if not include.is_absolute():
                        include = directory / include
                    if is_within(include, output):
                        continue
                    if any(is_within(include, source) for source in sources):
                        outside_sources.append(f"include: {include}")
                    else:
                        external_includes.add(str(include.resolve(strict=False)))
            checks["compile_commands"] = "pass" if not outside_sources else "fail"
            checks["compile_units"] = len(entries)
            errors.extend(outside_sources[:MAX_REPORTED_HITS])
            for item in sorted(external_includes)[:MAX_REPORTED_HITS]:
                warnings.append(f"external include directory (verify it is a toolchain/system path): {item}")
    else:
        checks["compile_commands"] = "skip"
        warnings.append("no compile_commands.json; build has not been run yet (generation-only mode)")

    # 4. A real source/header tree must have been copied into the output.
    source_count = 0
    for path in output.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(output)
        if relative.parts and relative.parts[0].lower() == "build":
            continue
        if path.suffix.lower() in SOURCE_SUFFIXES:
            source_count += 1
    checks["source_files_inside_output"] = source_count
    if source_count == 0:
        checks["self_contained_sources"] = "fail"
        errors.append("no C/C++/ASM/header/linker sources copied into the output directory")
    else:
        checks["self_contained_sources"] = "pass"

    # 5. Minimum generated project files.
    missing = [name for name in ("CMakeLists.txt", "CMAKE_BUILD.md") if not (output / name).is_file()]
    checks["required_files"] = "pass" if not missing else "fail"
    errors.extend(f"missing generated file: {name}" for name in missing)

    status = "pass" if not errors else "fail"
    report = {
        "status": status,
        "source_directories": [norm_path(source) for source in sources],
        "output_directory": norm_path(output),
        "checks": checks,
        "audit_copies_excluded": audit_copies,
        "reference_hits": hits[:MAX_REPORTED_HITS],
        "errors": errors[:MAX_REPORTED_HITS],
        "warnings": warnings[:MAX_REPORTED_HITS],
    }

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print("standalone check")
        print(f"output: {report['output_directory']}")
        for source in report["source_directories"]:
            print(f"source: {source}")
        for key in ("directory_separation", "no_source_tree_references", "compile_commands",
                    "self_contained_sources", "required_files"):
            print(f"[{str(checks.get(key, 'skip')).upper()}] {key}")
        print(f"files scanned: {scanned}; compile units: {checks.get('compile_units', 0)}; "
              f"source/header files: {source_count}")
        for item in hits[:MAX_REPORTED_HITS]:
            print(f"  reference: {item}")
        for item in warnings[:MAX_REPORTED_HITS]:
            print(f"warning: {item}")
        for item in errors[:MAX_REPORTED_HITS]:
            print(f"error: {item}")
        print(f"status: {status.upper()}")
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
