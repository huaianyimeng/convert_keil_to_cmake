#!/usr/bin/env python3
"""Extract a normalized, read-only inventory from a Keil uVision project."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


def Text(node: ET.Element | None, path: str, default: str = "") -> str:
    if node is None:
        return default
    value = node.findtext(path)
    return value.strip() if value else default


def SplitValues(value: str, separator: str) -> list[str]:
    return [item.strip() for item in value.split(separator) if item.strip()]


def ResolvePath(project_dir: Path, value: str) -> str:
    if not value:
        return ""
    normalized = value.replace("\\", "/")
    if "$" in normalized or "%" in normalized:
        return normalized
    candidate = Path(normalized)
    if not candidate.is_absolute():
        candidate = project_dir / candidate
    return str(candidate.resolve(strict=False))


def Controls(node: ET.Element | None, project_dir: Path) -> dict[str, object]:
    various = node.find("VariousControls") if node is not None else None
    include_value = Text(various, "IncludePath")
    return {
        "defines": SplitValues(Text(various, "Define"), ","),
        "undefines": SplitValues(Text(various, "Undefine"), ","),
        "include_paths": [ResolvePath(project_dir, value) for value in SplitValues(include_value, ";")],
        "misc_controls": Text(various, "MiscControls"),
        "optimization": Text(node, "Optim"),
        "warning_level": Text(node, "wLevel"),
    }


def MemoryRegions(node: ET.Element | None) -> list[dict[str, object]]:
    regions = []
    memories = node.find("OnChipMemories") if node is not None else None
    if memories is None:
        return regions
    for memory in memories:
        if re.fullmatch(r"I(?:RAM|ROM)\d*", memory.tag, re.IGNORECASE) is None:
            continue
        startValue = Text(memory, "StartAddress")
        sizeValue = Text(memory, "Size")
        try:
            startAddress = int(startValue, 0)
            size = int(sizeValue, 0)
        except ValueError:
            continue
        if size == 0:
            continue
        regions.append({
            "name": memory.tag,
            "type": Text(memory, "Type"),
            "start_address": f"0x{startAddress:08x}",
            "size": f"0x{size:x}",
            "size_bytes": size,
            "end_address": f"0x{startAddress + size - 1:08x}",
        })
    return regions


def ExistingOutputs(project_dir: Path, outputDir: str, outputName: str) -> dict[str, str]:
    directory = Path(outputDir) if outputDir else project_dir
    candidates = {
        "scatter_file": directory / f"{outputName}.sct",
        "map_file": directory / f"{outputName}.map",
        "build_log": directory / f"{outputName}.build_log.htm",
        "axf_file": directory / f"{outputName}.axf",
        "hex_file": directory / f"{outputName}.hex",
    }
    return {name: str(path.resolve(strict=False)) for name, path in candidates.items() if path.is_file()}


def ParseBuildSummary(outputs: dict[str, str]) -> dict[str, object]:
    logPath = outputs.get("build_log")
    if not logPath:
        return {}
    try:
        content = Path(logPath).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}
    sizeMatch = re.search(r"Program Size:\s*Code=(\d+)\s+RO-data=(\d+)\s+RW-data=(\d+)\s+ZI-data=(\d+)", content)
    compilerMatch = re.search(r"Toolchain:\s*(.*?)\s+Version:\s*([^\r\n<]+)", content)
    cCompilerMatch = re.search(r"C Compiler:\s*(\S+)\s+V([^\r\n<]+)", content)
    summary: dict[str, object] = {}
    if compilerMatch:
        summary["toolchain"] = compilerMatch.group(1).strip()
        summary["toolchain_version"] = compilerMatch.group(2).strip()
    if cCompilerMatch:
        summary["c_compiler"] = cCompilerMatch.group(1).strip()
        summary["c_compiler_version"] = cCompilerMatch.group(2).strip()
    if sizeMatch:
        code, roData, rwData, ziData = (int(value) for value in sizeMatch.groups())
        summary["size"] = {
            "code": code,
            "ro_data": roData,
            "rw_data": rwData,
            "zi_data": ziData,
            "flash_bytes": code + roData + rwData,
            "ram_bytes": rwData + ziData,
        }
    return summary


def StripComments(content: str) -> str:
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    return re.sub(r"//[^\r\n]*", "", content)


def ScanSourceUsage(files: list[dict[str, object]]) -> dict[str, object]:
    usage = {
        "printf": False,
        "printf_float_format": False,
        "fputc": False,
        "gcc_write_syscall": False,
        "semihosting_marker": False,
        "no_semihosting_marker": False,
    }
    for item in files:
        if item["include_in_build"] == "0":
            continue
        path = Path(str(item["resolved_path"]))
        if path.suffix.lower() not in {".c", ".cc", ".cpp", ".h", ".hpp"}:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        content = StripComments(content)
        usage["printf"] = usage["printf"] or re.search(r"\b(?:f|s|sn|v)?printf\s*\(", content) is not None
        formatStrings = re.findall(r"\b(?:f|s|sn|v)?printf\s*\([^\"\n]*\"([^\"\n]*)\"", content)
        hasFloatFormat = any(re.search(r"%(?:[-+ #0]*\d*(?:\.\d+)?)?[aAeEfFgG]", value) for value in formatStrings)
        usage["printf_float_format"] = usage["printf_float_format"] or hasFloatFormat
        usage["fputc"] = usage["fputc"] or re.search(r"\bfputc\s*\(", content) is not None
        usage["gcc_write_syscall"] = usage["gcc_write_syscall"] or re.search(r"\b_write\s*\(", content) is not None
        usage["semihosting_marker"] = usage["semihosting_marker"] or re.search(r"__semihosting|\bBKPT\b", content) is not None
        usage["no_semihosting_marker"] = usage["no_semihosting_marker"] or "__use_no_semihosting" in content
    return usage


def FileEntry(node: ET.Element, project_dir: Path) -> dict[str, object]:
    option = node.find("FileOption")
    common = option.find("CommonProperty") if option is not None else None
    arm = option.find("FileArmAds") if option is not None else None
    raw_path = Text(node, "FilePath")
    return {
        "name": Text(node, "FileName"),
        "type": Text(node, "FileType"),
        "path": raw_path.replace("\\", "/"),
        "resolved_path": ResolvePath(project_dir, raw_path),
        "include_in_build": Text(common, "IncludeInBuild", "1"),
        "c_controls": Controls(arm.find("Cads") if arm is not None else None, project_dir),
        "asm_controls": Controls(arm.find("Aads") if arm is not None else None, project_dir),
    }


def TargetEntry(node: ET.Element, project_dir: Path) -> dict[str, object]:
    option = node.find("TargetOption")
    common = option.find("TargetCommonOption") if option is not None else None
    arm = option.find("TargetArmAds") if option is not None else None
    cads = arm.find("Cads") if arm is not None else None
    aads = arm.find("Aads") if arm is not None else None
    ldads = arm.find("LDads") if arm is not None else None
    adsMisc = arm.find("ArmAdsMisc") if arm is not None else None
    groups = []
    for group in node.findall("./Groups/Group"):
        groupOption = group.find("GroupOption")
        groupArm = groupOption.find("GroupArmAds") if groupOption is not None else None
        groups.append({
            "name": Text(group, "GroupName"),
            "c_controls": Controls(groupArm.find("Cads") if groupArm is not None else None, project_dir),
            "asm_controls": Controls(groupArm.find("Aads") if groupArm is not None else None, project_dir),
            "files": [FileEntry(item, project_dir) for item in group.findall("./Files/File")],
        })
    files = [item for group in groups for item in group["files"]]
    scatter = Text(ldads, "ScatterFile")
    outputDir = ResolvePath(project_dir, Text(common, "OutputDirectory"))
    outputName = Text(common, "OutputName")
    outputs = ExistingOutputs(project_dir, outputDir, outputName)
    return {
        "name": Text(node, "TargetName"),
        "device": Text(common, "Device"),
        "vendor": Text(common, "Vendor"),
        "cpu": Text(common, "Cpu"),
        "toolchain": "armclang" if Text(option, "uAC6") == "1" else "armcc_or_legacy",
        "runtime": {
            "microlib": Text(adsMisc, "useUlib") == "1",
        },
        "memory_regions": MemoryRegions(adsMisc),
        "output": {
            "directory": outputDir,
            "name": outputName,
            "create_hex": Text(common, "CreateHexFile"),
            "create_batch": Text(common, "CreateBatchFile"),
        },
        "existing_outputs": outputs,
        "keil_build": ParseBuildSummary(outputs),
        "c_controls": Controls(cads, project_dir),
        "asm_controls": Controls(aads, project_dir),
        "linker": {
            "scatter_file": ResolvePath(project_dir, scatter),
            "misc_controls": Text(ldads, "Misc"),
            "use_memory_layout_from_target_dialog": Text(ldads, "umfTarg"),
        },
        "summary": {
            "group_count": len(groups),
            "file_count": len(files),
            "included_file_count": sum(item["include_in_build"] != "0" for item in files),
        },
        "source_usage": ScanSourceUsage(files),
        "groups": groups,
    }


def ParseArguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path, help="path to a .uvprojx file")
    parser.add_argument("--target", help="emit only the named target")
    parser.add_argument("--output", type=Path, help="write JSON to this file instead of stdout")
    return parser.parse_args()


def Main() -> int:
    args = ParseArguments()
    project = args.project.resolve()
    try:
        root = ET.parse(project).getroot()
    except (OSError, ET.ParseError) as error:
        print(f"error: cannot read keil project: {error}", file=sys.stderr)
        return 2

    for element in root.iter():
        if "}" in element.tag:
            element.tag = element.tag.rsplit("}", 1)[1]

    targets = [TargetEntry(node, project.parent) for node in root.findall("./Targets/Target")]
    if args.target:
        targets = [target for target in targets if target["name"] == args.target]
        if not targets:
            print(f"error: target not found: {args.target}", file=sys.stderr)
            return 3

    result = {
        "project": str(project),
        "targets": targets,
    }
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(Main())
