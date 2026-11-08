# Convert Keil to CMake

[简体中文](README.zh-CN.md) | English

An AI-agent skill for converting Keil MDK/uVision embedded projects into reproducible CMake builds, typically using Ninja and the GNU Arm Embedded toolchain.

## Features

- Reads `.uvprojx` targets, sources, include paths, definitions, exclusions, memory regions, runtime settings, and existing Keil outputs.
- Translates CPU/FPU/ABI, optimization, startup, RTOS port, runtime, and linker-layout intent to GCC/CMake.
- Generates readable CMake files, firmware artifacts, an environment checker, and a concise bilingual build guide.
- Supports `validated` and `generated, unverified` delivery modes.
- Compares source membership, compile settings, artifacts, and key ELF properties after a successful build.
- Prints ASCII FLASH/RAM usage bars with percentages after each link, with capacities read from the linker script.
- Ships a browser live waveform viewer (`scripts/live_waveform.py`) that plots CORTEX LIVE WATCH expressions as multi-channel coloured curves, supports C expressions, smooth 60 fps scrolling and CSV export without halting the CPU.
- Generates a brand-new standalone project directory with a complete copied source tree, leaving the Keil project untouched; verifies the result can build after being relocated.
- Never installs or downloads missing tools, or changes `PATH`, without explicit user authorization.

## Requirements

- An AI agent that supports Codex-style skills.
- Python 3.10 or later for the bundled inspection and validation scripts.
- A Keil project containing a `.uvprojx` file.
- CMake, a build generator, and the target toolchain only when build validation is requested or available.

Missing build tools do not prevent file generation when the project can be analyzed statically. The result is then clearly marked `generated, unverified`.

## Installation

Clone or download this repository, then place the `convert-keil-to-cmake` directory in either:

- your personal Codex skills directory, such as `$CODEX_HOME/skills/convert-keil-to-cmake`; or
- a project's `.agents/skills/convert-keil-to-cmake` directory.

Keep `SKILL.md`, `scripts/`, `references/`, `assets/`, and `agents/` together.

## Usage

Open the Keil project directory with your agent and ask:

```text
Use $convert-keil-to-cmake to convert the current Keil project to CMake.
```

For generation without local build validation:

```text
Use $convert-keil-to-cmake to generate the CMake files only and mark the result unverified.
```

The agent selects the only or clearly intended target. It asks for a target only when multiple materially different targets are ambiguous.

Generated files always go into a brand-new standalone directory (by default a sibling named `<KeilProjectName>Cmake`), never into the Keil project tree. Supply a destination explicitly to control the path. The Keil project stays read-only throughout the migration.

## Generated Project Files

The exact layout follows the source repository, but a typical conversion includes:

| File | Purpose |
| --- | --- |
| `CMakeLists.txt` | Main build definition |
| `cmake/arm-none-eabi-gcc.cmake` | GNU Arm toolchain selection |
| `cmake/*.ld` | GNU linker script when the project does not already provide one |
| `check_build_env.py`, `.bat`, or `.sh` | Project-local, diagnostic-only prerequisite checker |
| `CMAKE_BUILD.md` | Concise Chinese and English build instructions and artifact summary |
| `scripts/size_report.py` | Post-build FLASH/RAM usage bars, percentages, and optional section breakdown |
| `scripts/live_waveform.py` | Browser live waveform of CORTEX LIVE WATCH expressions (multi-channel colours, C expressions, CSV export) |
| `build/*.elf`, `*.bin`, `*.hex`, `*.map` | Firmware and analysis outputs after a validated build |

Only outputs actually supported by the converted project are documented.

## Validation Status

| Status | Meaning |
| --- | --- |
| `validated` | Environment check, clean configure/build/link, expected artifacts, and conversion validation passed |
| `generated, unverified` | Build files were generated and statically reviewed, but one or more runtime checks were unavailable or intentionally skipped |

The generated `CMAKE_BUILD.md` lists exact build commands, artifacts, missing prerequisites, and checks still required.

## Bundled Tools

Inspect a project without modifying it:

```text
python scripts/inspect_uvprojx.py path/to/project.uvprojx --target "Target Name"
```

Validate a completed CMake build:

```text
python scripts/validate_conversion.py path/to/project.uvprojx build/compile_commands.json --elf build/firmware.elf
```

Compiler-specific startup, RTOS, or syscall replacements can be declared with repeated `--source-substitution old=new` options.

## Safety and Scope

- The Keil project remains intact unless the user explicitly requests otherwise.
- Environment checkers diagnose only; they do not install software or modify the machine.
- Scatter files are translated by behavior and memory layout, not by mechanical syntax conversion.
- Multi-bank memory, bootloaders, overlays, external memory, and proprietary libraries require project-specific review.

See [SKILL.md](SKILL.md) for the agent workflow and [conversion-reference.md](references/conversion-reference.md) for detailed conversion guidance.

## License

This project is released under the [MIT License](LICENSE).
