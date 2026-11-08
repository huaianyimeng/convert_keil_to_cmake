import sys
import os
import re
import subprocess

QUOTES = chr(34) + chr(39)

CPUID_NAMES = {
    0x410FC240: "ARM Cortex-M4",
    0x410FC241: "ARM Cortex-M4",
    0x410CC200: "ARM Cortex-M0+",
    0x410CB200: "ARM Cortex-M0",
    0x410FC230: "ARM Cortex-M3",
    0x411FC231: "ARM Cortex-M3 r1p1 (STM32F1)",
    0x410FD200: "ARM Cortex-M7",
}

STM32_IDCODE_NAMES = {
    0x413: "STM32F405xx/STM32F407xx",
    0x419: "STM32F42xxx/STM32F43xxx",
    0x411: "STM32F2xx",
    0x410: "STM32F1xx (STM32F103CB)",
}

def resolve_cmake_var(var_expr, content, resolved):
    if var_expr in resolved:
        return resolved[var_expr]
    pat = re.compile(r"set\s*\(\s*" + re.escape(var_expr) + r"\s+(\S+)", re.IGNORECASE)
    m = pat.search(content)
    if m:
        val = m.group(1).strip(QUOTES)
        if val.startswith("${") and val.endswith("}"):
            inner = val[2:-1]
            val = resolve_cmake_var(inner, content, resolved)
        resolved[var_expr] = val
        return val
    proj = re.search(r"project\s*\(\s*(\w+)", content, re.IGNORECASE)
    if proj and var_expr in ("PROJECT_NAME", "CMAKE_PROJECT_NAME"):
        resolved[var_expr] = proj.group(1)
        return proj.group(1)
    return None

def get_target_name(workspace):
    cmakelists = os.path.join(workspace, "CMakeLists.txt")
    if not os.path.isfile(cmakelists):
        print(f"ERROR: CMakeLists.txt not found at {cmakelists}", file=sys.stderr)
        sys.exit(1)
    with open(cmakelists, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    resolved = {}
    m = re.search(r"add_executable\s*\(\s*(\S+)\s", content)
    if not m:
        print("ERROR: cannot find add_executable in CMakeLists.txt", file=sys.stderr)
        sys.exit(1)
    raw = m.group(1)
    for s in [".elf", ".hex", ".bin", ".axf"]:
        if raw.endswith(s):
            raw = raw[:-len(s)]
            break
    if raw.startswith("${") and raw.endswith("}"):
        var_name = raw[2:-1]
        name = resolve_cmake_var(var_name, content, resolved)
        if not name:
            print(f"ERROR: cannot resolve CMake variable {raw} in CMakeLists.txt", file=sys.stderr)
            sys.exit(1)
        return name
    return raw.strip(QUOTES)

def run_jlink(workspace, device, interface, speed, script_name):
    target = get_target_name(workspace)
    build_dir = os.path.join(workspace, "build")
    hex_path = os.path.join(build_dir, f"{target}.hex")

    if script_name == "flash":
        if not os.path.isfile(hex_path):
            print(f"ERROR: {hex_path} not found. Build first.", file=sys.stderr)
            sys.exit(1)
        commands = f"loadfile {hex_path}\nr\ngo\nexit\n"
    elif script_name == "erase":
        commands = "erase\nr\nexit\n"
    else:
        print(f"ERROR: unknown script '{script_name}'", file=sys.stderr)
        sys.exit(1)

    cmd = [
        "JLink.exe",
        "-AutoConnect", "1",
        "-Device", device,
        "-If", interface,
        "-Speed", str(speed),
        "-ExitOnError", "1",
    ]
    print(f"[J-Link] Device={device} If={interface} Speed={speed} Action={script_name}")
    if script_name == "flash":
        print(f"[J-Link] Target: {target}.hex")
    print("-" * 50)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=sys.stdout, stderr=sys.stderr, text=True)
    proc.communicate(input=commands)
    sys.exit(proc.returncode)

def read_mem32(output, address):
    m = re.search(r"%08X\s*=\s*(?:0x)?([0-9A-Fa-f]+)" % address, output, re.IGNORECASE)
    if m:
        return int(m.group(1), 16)
    return None

def detect_chip(device, interface, speed):
    commands = "mem32 0xE000ED00 1\nmem32 0xE0042000 1\nexit\n"
    cmd = [
        "JLink.exe",
        "-AutoConnect", "1",
        "-Device", device,
        "-If", interface,
        "-Speed", str(speed),
        "-ExitOnError", "1",
    ]
    print("[J-Link] Chip Detection")
    print(f"[J-Link] Device={device} If={interface} Speed={speed}")
    print("-" * 50)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    output, _ = proc.communicate(input=commands)
    low = output.lower()
    # -ExitOnError 1 makes J-Link print "will now exit on Error"; that line is
    # NOT a connect failure. Judge the link by the real failure text and by the
    # CPUID read result instead of scanning for the bare word "error".
    failed = proc.returncode != 0 or "cannot connect to target" in low
    cpuid = read_mem32(output, 0xE000ED00)
    idcode = read_mem32(output, 0xE0042000)
    if failed or cpuid is None:
        print("ERROR: J-Link cannot connect to target.")
        print("Possible causes: SWD cable reversed, broken wire, chip not powered, wrong device name.")
        print("Chip detection: FAILED")
        sys.exit(1)
    print("J-Link connected successfully.")
    cpuid_name = CPUID_NAMES.get(cpuid, "UNKNOWN")
    print(f"CPUID (0xE000ED00): 0x{cpuid:08X} -> {cpuid_name}")
    id_low = (idcode & 0xFFF) if idcode is not None else 0
    id_name = STM32_IDCODE_NAMES.get(id_low, "UNKNOWN")
    id_val = idcode if idcode is not None else 0
    print(f"IDCODE (0xE0042000): 0x{id_val:08X} -> {id_name}")
    print("Chip detection: PASSED")

if __name__ == "__main__":
    workspace = os.environ.get("WORKSPACE_FOLDER") or os.getcwd()
    device = os.environ.get("STM32_DEVICE") or "STM32F407VE"
    interface = os.environ.get("STM32_INTERFACE") or "swd"
    speed = int(os.environ.get("STM32_SPEED") or "4000")
    script_name = sys.argv[1] if len(sys.argv) > 1 else "flash"
    if script_name == "detect":
        detect_chip(device, interface, speed)
    else:
        run_jlink(workspace, device, interface, speed, script_name)
