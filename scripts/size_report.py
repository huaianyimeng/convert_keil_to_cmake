#!/usr/bin/env python3
"""Print FLASH / RAM usage bars with percentages after a firmware link.

Bundled with the convert-keil-to-cmake skill. Copy this file into the generated
project's ``scripts/`` directory and call it from the ELF target's POST_BUILD.

Normal output is pure ASCII so it renders correctly in the Windows cmd code page.
All capacities come from the linker script's MEMORY block, so changing a device's
memory layout never desynchronises the report.

Typical invocation (from the generated project root)::

    python scripts/size_report.py build/firmware.elf cmake/stm32-flash.ld
    python scripts/size_report.py build/firmware.elf cmake/stm32-flash.ld --detail

Use --flash-region / --ram-region for non-standard MEMORY names, --reserve to
override the heap+stack reservation, and --static-only for the pure static RAM
figure (data + bss without reservation).
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path


DEFAULT_BAR_WIDTH = 20
HEAP_SYMBOL_NAMES = ("_Min_Heap_Size", "__Heap_Size", "__heap_size", "_heap_size", "HEAP_SIZE")
STACK_SYMBOL_NAMES = ("_Min_Stack_Size", "__Stack_Size", "__stack_size", "_stack_size", "STACK_SIZE")
RESERVED_SECTION_HINTS = ("heap", "stack")


def parse_number(value: str) -> int:
    """Parse linker-script numbers such as 0x20000, 131072, 128K, or 1M."""
    match = re.fullmatch(r"(0[xX][0-9a-fA-F]+|\d+)([kKmM]?)", value.strip())
    if not match:
        raise ValueError(f"cannot parse linker number: {value!r}")
    literal = match.group(1)
    number = int(literal, 16) if literal.lower().startswith("0x") else int(literal, 10)
    suffix = match.group(2).lower()
    if suffix == "k":
        number *= 1024
    elif suffix == "m":
        number *= 1024 * 1024
    return number


def parse_linker_script(path: Path) -> tuple[dict[str, int], int]:
    """Return MEMORY region lengths and the heap+stack reservation from an LD script."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"/\*.*?\*/", " ", raw, flags=re.DOTALL)
    memory = re.search(r"\bMEMORY\s*\{(.*?)\}", text, re.IGNORECASE | re.DOTALL)
    if not memory:
        raise ValueError(f"no MEMORY block in {path}")

    regions: dict[str, int] = {}
    for match in re.finditer(
        r"(\w+)\s*\([^)]*\)\s*:\s*ORIGIN\s*=\s*([^,]+),\s*LENGTH\s*=\s*([^\s},]+)",
        memory.group(1),
        re.IGNORECASE,
    ):
        regions[match.group(1).upper()] = parse_number(match.group(3))

    def symbol(names: tuple[str, ...]) -> int:
        for name in names:
            found = re.search(r"\b" + re.escape(name) + r"\s*=\s*([^;]+);", text)
            if found:
                try:
                    return parse_number(found.group(1))
                except ValueError:
                    continue
        return 0

    return regions, symbol(HEAP_SYMBOL_NAMES) + symbol(STACK_SYMBOL_NAMES)


def pick_region(
    regions: dict[str, int],
    explicit: str | None,
    exact_names: tuple[str, ...],
    keywords: tuple[str, ...],
    label: str,
) -> int:
    """Resolve a MEMORY region by explicit name, exact name, then name keyword."""
    if explicit:
        key = explicit.upper()
        if key not in regions:
            raise ValueError(
                f"{label} region {explicit!r} not found; MEMORY has: {', '.join(sorted(regions)) or 'none'}"
            )
        return regions[key]
    for name in exact_names:
        if name in regions:
            return regions[name]
    for name, length in regions.items():
        if any(keyword in name.upper() for keyword in keywords):
            return length
    raise ValueError(
        f"cannot identify the {label} MEMORY region; pass --{label}-region NAME. "
        f"MEMORY has: {', '.join(sorted(regions)) or 'none'}"
    )


def size_tool_path(explicit: str | None) -> str:
    tool = explicit or shutil.which("arm-none-eabi-size")
    if not tool:
        raise RuntimeError("arm-none-eabi-size not found (run the project environment checker)")
    return tool


def run_size(tool: str, options: list[str], elf: Path) -> str:
    result = subprocess.run(
        [tool, *options, str(elf)],
        capture_output=True, text=True, errors="replace", check=True,
    )
    return result.stdout


def berkeley_sizes(output: str) -> tuple[int, int, int]:
    """Return (text, data, bss) from 'size --format=berkeley'."""
    for line in reversed(output.splitlines()):
        parts = line.split()
        if len(parts) >= 3 and all(part.isdigit() for part in parts[:3]):
            return int(parts[0]), int(parts[1]), int(parts[2])
    raise ValueError("cannot parse berkeley size output")


def section_sizes(output: str) -> dict[str, int]:
    """Return section -> size from 'size --format=sysv' (-A)."""
    sections: dict[str, int] = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith(".") and parts[1].isdigit():
            sections[parts[0]] = int(parts[1])
    return sections


def reserved_section_bytes(sections: dict[str, int]) -> int:
    """Bytes of NOBITS heap/stack reservation sections already counted inside bss."""
    return sum(
        size
        for name, size in sections.items()
        if name.lower().startswith(".") and any(hint in name.lower() for hint in RESERVED_SECTION_HINTS)
    )


def render_bar(used: int, total: int, width: int) -> str:
    ratio = used / total if total > 0 else 0.0
    filled = int(round(ratio * width))
    filled = max(0, min(width, filled))
    return "[" + ">" * filled + " " * (width - filled) + "]"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf", type=Path, help="linked ELF file")
    parser.add_argument("linker_script", type=Path, help="GNU LD script containing the MEMORY block")
    parser.add_argument("--size-tool", default=None, help="path/name of arm-none-eabi-size")
    parser.add_argument("--bar-width", type=int, default=DEFAULT_BAR_WIDTH, help="progress bar cells (default 20)")
    parser.add_argument("--flash-region", default=None, help="MEMORY region name to use as FLASH capacity")
    parser.add_argument("--ram-region", default=None, help="MEMORY region name to use as RAM capacity")
    parser.add_argument("--reserve", type=parse_number, default=None, help="override heap+stack reservation in bytes")
    parser.add_argument("--static-only", action="store_true", help="exclude heap/stack reservation from RAM used")
    parser.add_argument("--detail", action="store_true", help="print the section breakdown")
    args = parser.parse_args()

    try:
        tool = size_tool_path(args.size_tool)
        text, data, bss = berkeley_sizes(run_size(tool, ["--format=berkeley"], args.elf))
        sections = section_sizes(run_size(tool, ["-A"], args.elf))
        regions, ld_reserved = parse_linker_script(args.linker_script)
        flash_total = pick_region(
            regions, args.flash_region, ("FLASH", "IROM1", "IROM", "ROM"), ("FLASH", "ROM"), "flash"
        )
        ram_total = pick_region(
            regions, args.ram_region, ("RAM", "IRAM1", "IRAM", "DRAM"), ("RAM",), "ram"
        )
        if flash_total <= 0 or ram_total <= 0:
            raise ValueError(f"invalid MEMORY capacities: flash={flash_total}, ram={ram_total}")
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"size_report: {error}", file=sys.stderr)
        return 1

    # GNU size counts NOBITS sections inside bss, so a ._user_heap_stack style
    # reservation is already in `bss`. Remove it once, then add the reservation
    # back explicitly. Without this step the heap/stack bytes are counted twice.
    reserved_in_bss = reserved_section_bytes(sections)
    static_bss = max(0, bss - reserved_in_bss)
    requested = ld_reserved if args.reserve is None else args.reserve
    if args.static_only:
        reserved = 0
        ram_used = data + static_bss
    else:
        reserved = max(requested, reserved_in_bss)
        ram_used = data + static_bss + reserved
    flash_used = text + data

    flash_pct = 100.0 * flash_used / flash_total
    ram_pct = 100.0 * ram_used / ram_total
    width = max(1, args.bar_width)

    print(f"flash {render_bar(flash_used, flash_total, width)} ({flash_pct:4.1f}%) "
          f"used: {flash_used / 1024:5.1f} KB, total: {flash_total / 1024:5.1f} KB")
    print(f"ram   {render_bar(ram_used, ram_total, width)} ({ram_pct:4.1f}%) "
          f"used: {ram_used / 1024:5.1f} KB, total: {ram_total / 1024:5.1f} KB")

    if args.detail:
        print(f"detail: text={text} data={data} bss={bss} "
              f"(static_bss={static_bss}, reserved_in_bss={reserved_in_bss})")
        print(f"        flash={flash_used}/{flash_total} B  ram={ram_used}/{ram_total} B  reserved={reserved} B")
        print(f"        ld_reserved={ld_reserved} B  regions={regions}")
        bin_image = args.elf.with_suffix(".bin")
        if bin_image.is_file():
            size = bin_image.stat().st_size
            print(f"        {bin_image.name}={size} B (matches flash used: {'yes' if size == flash_used else 'no'})")
        print("        KB = KiB (1024 bytes); RAM includes heap/stack reservation unless --static-only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
