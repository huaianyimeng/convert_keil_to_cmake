#!/usr/bin/env python3
"""Check project build prerequisites without installing or changing anything."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import shutil
import subprocess
import sys


@dataclass(frozen=True)
class Tool:
    command: str
    description: str
    required: bool = True
    version_args: tuple[str, ...] = ("--version",)


TOOLS = (
    Tool("cmake", "cmake configure and build driver"),
    Tool("ninja", "ninja build tool"),
    Tool("arm-none-eabi-gcc", "gnu arm c compiler"),
    Tool("arm-none-eabi-objcopy", "gnu arm firmware converter"),
    Tool("arm-none-eabi-size", "gnu arm size reporter"),
    Tool("arm-none-eabi-nm", "gnu arm symbol inspector"),
    Tool("arm-none-eabi-readelf", "gnu arm elf inspector"),
    Tool("arm-none-eabi-g++", "gnu arm c++ compiler", required=False),
    Tool("JLink.exe", "segger j-link commander (flash/erase)", required=False),
    Tool("JLinkGDBServerCL.exe", "segger j-link gdb server (debug)", required=False),
    Tool("arm-none-eabi-gdb", "gnu arm debugger (live waveform expression resolving)", required=False),
    Tool("winpty", "pty wrapper for streaming j-link reads (live waveform)", required=False),
)


def ReadVersion(executable: str, versionArgs: tuple[str, ...]) -> str:
    try:
        result = subprocess.run([executable, *versionArgs], capture_output=True, text=True, errors="replace", timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    output = result.stdout or result.stderr
    return next((line.strip() for line in output.splitlines() if line.strip()), "")


def CheckTool(tool: Tool) -> dict[str, object]:
    executable = shutil.which(tool.command)
    return {
        **asdict(tool),
        "found": executable is not None,
        "path": str(Path(executable).resolve()) if executable else "",
        "version": ReadVersion(executable, tool.version_args) if executable else "",
    }


def ParseArguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit json")
    return parser.parse_args()


def Main() -> int:
    args = ParseArguments()
    results = [CheckTool(tool) for tool in TOOLS]
    missingRequired = [result for result in results if result["required"] and not result["found"]]
    missingOptional = [result for result in results if not result["required"] and not result["found"]]
    report = {
        "python": {
            "path": str(Path(sys.executable).resolve()),
            "version": sys.version.split()[0],
        },
        "tools": results,
        "summary": {
            "missing_required": len(missingRequired),
            "missing_optional": len(missingOptional),
            "status": "ready" if not missingRequired else "missing_required_tools",
        },
    }
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"python: found: {report['python']['version']}")
        print(f"path: {report['python']['path']}")
        for result in results:
            level = "required" if result["required"] else "optional"
            state = "found" if result["found"] else "missing"
            version = f": {result['version']}" if result["version"] else ""
            print(f"{result['command']}: {state}: {level}{version}")
            if result["path"]:
                print(f"path: {result['path']}")
        print(f"missing required: {len(missingRequired)}")
        print(f"missing optional: {len(missingOptional)}")
        print(f"status: {report['summary']['status']}")
        if missingRequired:
            print("next action: request installation authorization or use generation-only mode")
    return 0 if not missingRequired else 1


if __name__ == "__main__":
    raise SystemExit(Main())
