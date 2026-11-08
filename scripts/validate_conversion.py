#!/usr/bin/env python3
"""Validate source parity, build settings, artifacts, and key ELF properties."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True

import inspect_uvprojx as inspector


def NormalizePath(path: Path) -> str:
    value = str(path.resolve(strict=False))
    return os.path.normcase(value)


def LoadTarget(project: Path, targetName: str | None) -> dict[str, object]:
    root = ET.parse(project).getroot()
    for element in root.iter():
        if "}" in element.tag:
            element.tag = element.tag.rsplit("}", 1)[1]
    targets = [inspector.TargetEntry(node, project.parent) for node in root.findall("./Targets/Target")]
    if targetName:
        targets = [target for target in targets if target["name"] == targetName]
    if len(targets) != 1:
        names = ", ".join(str(target["name"]) for target in targets)
        raise ValueError(f"expected one target, found {len(targets)}: {names}")
    return targets[0]


def ParseSubstitutions(values: list[str], baseDir: Path) -> dict[str, str]:
    substitutions = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"invalid source substitution: {value}")
        oldValue, newValue = value.split("=", 1)
        oldPath = Path(oldValue)
        newPath = Path(newValue)
        if not oldPath.is_absolute():
            oldPath = baseDir / oldPath
        if not newPath.is_absolute():
            newPath = baseDir / newPath
        substitutions[NormalizePath(oldPath)] = NormalizePath(newPath)
    return substitutions


def CollectCommandSettings(entry: dict[str, object]) -> tuple[set[str], set[str]]:
    if "arguments" in entry:
        tokens = [str(value) for value in entry["arguments"]]
    else:
        tokens = shlex.split(str(entry.get("command", "")), posix=False)
    defines = set()
    includes = set()
    index = 0
    directory = Path(str(entry.get("directory", ".")))
    while index < len(tokens):
        token = tokens[index].strip('"')
        if token in {"-I", "-isystem"} and index + 1 < len(tokens):
            index += 1
            includePath = Path(tokens[index].strip('"'))
            if not includePath.is_absolute():
                includePath = directory / includePath
            includes.add(NormalizePath(includePath))
        elif token.startswith("-I") and len(token) > 2:
            includePath = Path(token[2:].strip('"'))
            if not includePath.is_absolute():
                includePath = directory / includePath
            includes.add(NormalizePath(includePath))
        elif token == "-D" and index + 1 < len(tokens):
            index += 1
            defines.add(tokens[index].strip('"'))
        elif token.startswith("-D") and len(token) > 2:
            defines.add(token[2:].strip('"'))
        index += 1
    return defines, includes


def ExpectedSettingsBySource(target: dict[str, object], substitutions: dict[str, str]) -> dict[str, tuple[set[str], set[str]]]:
    targetDefines = set(str(value) for value in target["c_controls"]["defines"])
    targetIncludes = set(NormalizePath(Path(str(value))) for value in target["c_controls"]["include_paths"])
    settings = {}
    for group in target["groups"]:
        groupDefines = targetDefines | set(str(value) for value in group["c_controls"]["defines"])
        groupIncludes = targetIncludes | set(NormalizePath(Path(str(value))) for value in group["c_controls"]["include_paths"])
        for item in group["files"]:
            if item["include_in_build"] == "0":
                continue
            source = NormalizePath(Path(str(item["resolved_path"])))
            source = substitutions.get(source, source)
            defines = groupDefines | set(str(value) for value in item["c_controls"]["defines"])
            includes = groupIncludes | set(NormalizePath(Path(str(value))) for value in item["c_controls"]["include_paths"])
            settings[source] = (defines, includes)
    return settings


def RunTool(command: list[str]) -> str:
    completed = subprocess.run(command, check=True, text=True, capture_output=True, errors="replace")
    return completed.stdout + completed.stderr


def ReadLinkMetadata(buildDir: Path) -> str:
    contents = []
    ninjaFile = buildDir / "build.ninja"
    if ninjaFile.is_file():
        contents.append(ninjaFile.read_text(encoding="utf-8", errors="ignore"))
    for linkFile in buildDir.glob("CMakeFiles/**/link.txt"):
        contents.append(linkFile.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(contents)


def ValidateElf(elfPath: Path, target: dict[str, object], errors: list[str], warnings: list[str]) -> dict[str, object]:
    details: dict[str, object] = {}
    readelf = shutil.which("arm-none-eabi-readelf")
    nm = shutil.which("arm-none-eabi-nm")
    sizeTool = shutil.which("arm-none-eabi-size")
    if not readelf or not nm:
        warnings.append("gnu arm readelf or nm is unavailable; elf checks skipped")
        return details
    header = RunTool([readelf, "-h", "-l", "-S", str(elfPath)])
    symbolsOutput = RunTool([nm, "-n", str(elfPath)])
    details["machine_arm"] = "Machine:" in header and "ARM" in header
    details["soft_float_abi"] = "soft-float ABI" in header
    details["hard_float_abi"] = "hard-float ABI" in header
    details["rwx_segment"] = re.search(r"\bRWE\b", header) is not None
    if not details["machine_arm"]:
        errors.append("elf machine is not arm")
    if details["rwx_segment"]:
        errors.append("elf contains an rwx load segment")
    symbols = {}
    for line in symbolsOutput.splitlines():
        match = re.match(r"^([0-9a-fA-F]+)\s+\w\s+(.+)$", line.strip())
        if match:
            symbols[match.group(2)] = int(match.group(1), 16)
    vectorAddress = symbols.get("g_pfnVectors", symbols.get("__Vectors"))
    resetAddress = symbols.get("Reset_Handler")
    details["vector_address"] = f"0x{vectorAddress:08x}" if vectorAddress is not None else None
    details["reset_handler"] = f"0x{resetAddress:08x}" if resetAddress is not None else None
    if vectorAddress is None:
        errors.append("vector table symbol not found")
    if resetAddress is None:
        errors.append("reset_handler symbol not found")
    regions = target.get("memory_regions", [])
    flashRegions = [region for region in regions if str(region["name"]).upper().startswith("IROM")]
    ramRegions = [region for region in regions if str(region["name"]).upper().startswith("IRAM")]
    if vectorAddress is not None and flashRegions:
        flashOrigin = int(str(flashRegions[0]["start_address"]), 0)
        if vectorAddress != flashOrigin:
            errors.append(f"vector table is 0x{vectorAddress:08x}, expected 0x{flashOrigin:08x}")
    stackAddress = symbols.get("_estack", symbols.get("__initial_sp"))
    details["stack_top"] = f"0x{stackAddress:08x}" if stackAddress is not None else None
    if stackAddress is not None and ramRegions:
        ramOrigin = int(str(ramRegions[0]["start_address"]), 0)
        ramSize = int(ramRegions[0]["size_bytes"])
        if stackAddress != ramOrigin + ramSize:
            warnings.append(f"stack top is 0x{stackAddress:08x}; primary keil iram ends at 0x{ramOrigin + ramSize:08x}")
    if sizeTool:
        sizeOutput = RunTool([sizeTool, "--format=berkeley", str(elfPath)])
        for line in reversed(sizeOutput.splitlines()):
            sizeMatch = re.match(r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+\d+\s+\S+\s+.+$", line)
            if sizeMatch:
                textSize, dataSize, bssSize = (int(value) for value in sizeMatch.groups())
                details["size"] = {
                    "text": textSize,
                    "data": dataSize,
                    "bss": bssSize,
                    "flash_load_bytes": textSize + dataSize,
                    "berkeley_data_bss_bytes": dataSize + bssSize,
                }
                break
    return details


def ParseArguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path, help="path to the keil .uvprojx")
    parser.add_argument("compile_commands", type=Path, help="path to cmake compile_commands.json")
    parser.add_argument("--target", help="keil target name")
    parser.add_argument("--source-substitution", action="append", default=[], metavar="OLD=NEW", help="replace a keil source with a compiler-specific source")
    parser.add_argument("--elf", type=Path, help="linked elf file; also enables artifact and elf checks")
    parser.add_argument("--json", action="store_true", help="emit json instead of a text summary")
    return parser.parse_args()


def Main() -> int:
    args = ParseArguments()
    project = args.project.resolve()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        target = LoadTarget(project, args.target)
        substitutions = ParseSubstitutions(args.source_substitution, Path.cwd())
        commands = json.loads(args.compile_commands.read_text(encoding="utf-8"))
    except (OSError, ET.ParseError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    expectedSources = []
    for group in target["groups"]:
        for item in group["files"]:
            if item["include_in_build"] != "0":
                source = NormalizePath(Path(str(item["resolved_path"])))
                expectedSources.append(substitutions.get(source, source))
    actualSources = [NormalizePath(Path(str(entry["file"]))) for entry in commands]
    expectedSet = set(expectedSources)
    actualSet = set(actualSources)
    missingSources = sorted(expectedSet - actualSet)
    extraSources = sorted(actualSet - expectedSet)
    duplicateCount = len(actualSources) - len(actualSet)
    if missingSources:
        errors.append(f"missing sources: {missingSources}")
    if extraSources:
        errors.append(f"extra sources: {extraSources}")
    if duplicateCount:
        errors.append(f"duplicate compile entries: {duplicateCount}")

    actualSettings = {}
    for entry in commands:
        defines, includes = CollectCommandSettings(entry)
        source = NormalizePath(Path(str(entry["file"])))
        if source in actualSettings:
            oldDefines, oldIncludes = actualSettings[source]
            defines.update(oldDefines)
            includes.update(oldIncludes)
        actualSettings[source] = (defines, includes)
    expectedSettings = ExpectedSettingsBySource(target, substitutions)
    missingDefines = []
    missingIncludes = []
    for source, (expectedDefines, expectedIncludes) in expectedSettings.items():
        actualDefines, actualIncludes = actualSettings.get(source, (set(), set()))
        missingDefines.extend(f"{source}: {value}" for value in sorted(expectedDefines - actualDefines))
        missingIncludes.extend(f"{source}: {value}" for value in sorted(expectedIncludes - actualIncludes))
    if missingDefines:
        errors.append(f"missing defines: {missingDefines}")
    if missingIncludes:
        errors.append(f"missing include directories: {missingIncludes}")

    artifacts = {}
    elfDetails = {}
    if args.elf:
        elfPath = args.elf.resolve()
        baseName = elfPath.name[:-4] if elfPath.name.lower().endswith(".elf") else elfPath.stem
        candidates = {
            "elf": elfPath,
            "bin": elfPath.parent / f"{baseName}.bin",
            "hex": elfPath.parent / f"{baseName}.hex",
            "map": elfPath.parent / f"{baseName}.map",
        }
        for name, path in candidates.items():
            artifacts[name] = str(path)
            if not path.is_file():
                errors.append(f"missing artifact: {path}")
        if elfPath.is_file():
            try:
                elfDetails = ValidateElf(elfPath, target, errors, warnings)
            except (OSError, subprocess.CalledProcessError) as error:
                errors.append(f"elf inspection failed: {error}")
        linkMetadata = ReadLinkMetadata(args.compile_commands.resolve().parent)
        sourceUsage = target.get("source_usage", {})
        if sourceUsage.get("printf_float_format") and "_printf_float" not in linkMetadata:
            warnings.append("active floating-point printf format detected without _printf_float; confirm a custom formatter or intentional omission")
        if sourceUsage.get("fputc") and not sourceUsage.get("gcc_write_syscall"):
            warnings.append("fputc is present without a gcc _write syscall; confirm that newlib output is intentionally discarded or retargeted elsewhere")
        keilSize = target.get("keil_build", {}).get("size", {})
        gnuSize = elfDetails.get("size", {})
        if keilSize and gnuSize:
            keilFlash = int(keilSize["flash_bytes"])
            keilRam = int(keilSize["ram_bytes"])
            gnuFlash = int(gnuSize["flash_load_bytes"])
            gnuRam = int(gnuSize["berkeley_data_bss_bytes"])
            if gnuFlash > keilFlash * 1.25:
                warnings.append(f"gnu flash load is {gnuFlash} bytes versus keil {keilFlash} bytes; review runtime and library selections")
            if gnuRam > keilRam * 1.25:
                warnings.append(f"gnu berkeley data+bss is {gnuRam} bytes versus keil rw+zi {keilRam} bytes; compare heap, stack, retained sections, and runtime state")

    result = {
        "target": target["name"],
        "source_parity": {
            "expected": len(expectedSources),
            "actual": len(actualSources),
            "unique_actual": len(actualSet),
            "missing": missingSources,
            "extra": extraSources,
            "duplicates": duplicateCount,
        },
        "settings": {
            "missing_defines": missingDefines,
            "missing_include_directories": missingIncludes,
        },
        "artifacts": artifacts,
        "elf": elfDetails,
        "warnings": warnings,
        "errors": errors,
    }
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"target: {target['name']}")
        print(f"sources: expected={len(expectedSources)} actual={len(actualSources)} unique={len(actualSet)}")
        print(f"settings: missing_defines={len(missingDefines)} missing_includes={len(missingIncludes)}")
        print(f"artifacts: checked={len(artifacts)}")
        for warning in warnings:
            print(f"warning: {warning}")
        for error in errors:
            print(f"error: {error}")
        print("validation: passed" if not errors else "validation: failed")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(Main())
