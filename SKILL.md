---
name: convert-keil-to-cmake
description: Convert Keil MDK/uVision embedded projects into reproducible CMake builds, normally using Ninja and an Arm GNU toolchain, with concise bilingual build documentation. Use for `.uvprojx` or `.uvoptx` migration, Keil-to-GCC flag and linker-script translation, source/include/define extraction, startup and RTOS port selection, firmware artifact generation, standalone self-contained output directory generation, post-build FLASH/RAM usage bars with percentages, prerequisite checking, generation-only delivery, user build guidance, parity checks between an existing Keil target and a new CMake target, VSCode IDE integration, chip detection, or one-click build/flash/erase/program/detect/debug setup, plus a portable live waveform viewer that turns Cortex Live Watch expressions into real-time browser curves. 触发词：Keil 转 CMake、MDK 迁移、.uvprojx、arm-none-eabi、生成 CMakeLists.txt、FLASH/RAM 占用率、编译占用百分比、独立目录、自包含工程、不污染源工程、J-Link 一键编译/烧录/调试、实时波形、Live Watch 波形、表达式波形、J-Scope 替代。
user-invocable: true
disable-model-invocation: false
---

# Convert Keil to CMake

Create a maintainable CMake build that preserves the selected Keil target's firmware behavior while separating compiler-specific implementation details. Generate VSCode integration so the user gets one-click build, rebuild, flash, erase, and debug without typing commands.


## Skill 资源根目录（WorkBuddy 安装适配）

本 Skill 已安装为 WorkBuddy 用户级技能，资源根目录为：

`C:/Users/16034/.workbuddy/skills/convert-keil-to-cmake`

下文所有 `scripts/`、`references/`、`assets/` 开头的路径都相对于该根目录。执行脚本或复制模板时**直接使用绝对路径**，例如：

- `python "C:/Users/16034/.workbuddy/skills/convert-keil-to-cmake/scripts/inspect_uvprojx.py" <project.uvprojx> [--target <name>]`
- `python "C:/Users/16034/.workbuddy/skills/convert-keil-to-cmake/scripts/validate_conversion.py" <project.uvprojx> <build/compile_commands.json> --elf <build/firmware.elf>`
- 参考文档：`C:/Users/16034/.workbuddy/skills/convert-keil-to-cmake/references/conversion-reference.md`
- 模板目录：`C:/Users/16034/.workbuddy/skills/convert-keil-to-cmake/assets/cmake/` 与 `C:/Users/16034/.workbuddy/skills/convert-keil-to-cmake/assets/vscode/`
- 占用报告脚本：`C:/Users/16034/.workbuddy/skills/convert-keil-to-cmake/scripts/size_report.py`（复制到项目 `scripts/` 目录）
- 独立性检查脚本：`C:/Users/16034/.workbuddy/skills/convert-keil-to-cmake/scripts/check_standalone.py`（迁移时调用，不复制到生成工程）
- 实时波形脚本：`C:/Users/16034/.workbuddy/skills/convert-keil-to-cmake/scripts/live_waveform.py`（复制到项目 `scripts/` 目录，配套 `live_waveform` 任务，见 "Live Waveform Viewer"）

不要把当前工作目录切换到 skill 根目录；**更不要在 Keil 源工程目录内写入任何生成物**。迁移产物必须全部生成在一个全新的独立输出目录（见 "Standalone Output Directory"），原 Keil 目录在整个迁移过程中视为只读。运行时也可用 `${CODEBUDDY_SKILL_DIR}`（等价别名 `${CLAUDE_SKILL_DIR}`）指代该目录。

调用方式：在对话框输入 `/convert-keil-to-cmake <Keil 工程路径或 .uvprojx 路径>` 手动触发，参数通过 `$ARGUMENTS` 传入；未带参数时先在当前工作区查找 `.uvprojx` 再开始迁移。也可以直接用自然语言描述需求（如「把这个 Keil 工程转成 CMake」），AI 会自动识别并加载本技能。

## Workflow

1. Locate `.uvprojx`, `.uvoptx`, startup files, scatter files, linker scripts, device packs, and existing build scripts. Do not edit generated IDE output directories.
2. **Choose the standalone output directory before writing any file.** Use the user-specified folder; otherwise create a brand-new sibling of the Keil project root named `<KeilProjectName>Cmake` (for example `motor_board` -> `motorBoardCmake`) and state the choice. Never place generated files inside the Keil tree, never merge into a populated directory, and treat the Keil tree as read-only. See "Standalone Output Directory".
3. Ask for a target only when the project contains multiple materially different targets and the requested target cannot be inferred. Otherwise select the single target or the clearly named production target and state the choice.
4. Run `python "C:/Users/16034/.workbuddy/skills/convert-keil-to-cmake/scripts/inspect_uvprojx.py" <project.uvprojx> [--target <name>]` (absolute path above). Treat its JSON as an inventory, then verify paths and target/file overrides against the XML. Pay particular attention to `runtime`, `memory_regions`, `existing_outputs`, `keil_build`, and `source_usage`.
5. Read [references/conversion-reference.md](C:/Users/16034/.workbuddy/skills/convert-keil-to-cmake/references/conversion-reference.md) before translating toolchain, CPU/FPU/ABI, optimization, scatter, library, startup, assembly, RTOS settings, or IDE/flash integration.
6. Copy [assets/cmake/check_build_env.py](C:/Users/16034/.workbuddy/skills/convert-keil-to-cmake/assets/cmake/check_build_env.py) into the project root as `check_build_env.py`, then tailor its required and optional tools to the selected generator, languages, toolchain, artifact steps, and existing project conventions. The template already includes optional J-Link tools (`JLink.exe`, `JLinkGDBServerCL.exe`); keep them optional unless the user's requested build inherently requires flashing. When Python is not a viable project prerequisite, generate an equivalent `check_build_env.bat` on Windows or `check_build_env.sh` on POSIX instead. Generate one appropriate checker, not every variant.
7. Run the project-local checker before configuring. It must only inspect and report: it must not download software, invoke an installer or package manager, modify `PATH`, or change machine-wide state. Never install missing prerequisites without the user's explicit authorization.
8. If required tools are missing, or the user requests no build, continue with **generation-only, unverified** mode when static project information is sufficient. Generate and statically review the migration files, but do not claim configure, compile, link, artifact, ELF, or parity validation. Report every missing prerequisite and the exact later verification commands.
9. Reuse [assets/cmake/](C:/Users/16034/.workbuddy/skills/convert-keil-to-cmake/assets/cmake/) as a starting point when the repository has no stronger CMake convention. Use `stm32-flash.ld.in` only for a simple single-Flash/single-RAM layout. Replace every `@...@` placeholder; remove unused sections instead of leaving speculative code. Generate every file inside that standalone directory. Copy the complete active source tree (compiled sources, headers, startup, linker scripts, libraries, generated code) into it while preserving the relative directory layout, so no build path points back to the Keil tree.
10. Generate a root `CMakeLists.txt`, a GNU Arm toolchain file, and a small host build wrapper only when useful. Follow the repository's established naming and directory organization. Copy [scripts/size_report.py](C:/Users/16034/.workbuddy/skills/convert-keil-to-cmake/scripts/size_report.py) into the project's `scripts/` directory and wire it into the ELF target's `POST_BUILD` as shown in [assets/cmake/CMakeLists.txt.in](C:/Users/16034/.workbuddy/skills/convert-keil-to-cmake/assets/cmake/CMakeLists.txt.in); see "Firmware Size Reporting" below. Use only `${CMAKE_CURRENT_SOURCE_DIR}`-relative paths; never emit an absolute Keil-tree path into generated build files.
11. In normal validation mode, configure from a new build directory with `CMAKE_EXPORT_COMPILE_COMMANDS=ON`, build, and compare sources, defines, includes, artifacts, memory layout, and size with Keil. Fix errors rather than suppressing warnings globally. Build from the standalone directory, run `check_standalone.py`, and perform a relocation build: copy the standalone folder to a different location, delete its `build/`, then configure and build from scratch.
12. Run `python "C:/Users/16034/.workbuddy/skills/convert-keil-to-cmake/scripts/validate_conversion.py" <project.uvprojx> <build/compile_commands.json> --elf <build/firmware.elf>` after a successful link. Pass each intentional compiler-specific replacement as `--source-substitution <keil-path>=<gnu-path>`. Point the validator at the Keil copies inside the standalone directory, not at the original `.uvprojx` (see the path-parity trap in "Standalone Output Directory"), and keep `--source-substitution` for compiler-specific replacements.
13. Generate VSCode integration files for one-click build, flash, and debug. Copy [assets/vscode/settings.json.in](C:/Users/16034/.workbuddy/skills/convert-keil-to-cmake/assets/vscode/settings.json.in), [assets/vscode/tasks.json.in](C:/Users/16034/.workbuddy/skills/convert-keil-to-cmake/assets/vscode/tasks.json.in), and [assets/vscode/launch.json.in](C:/Users/16034/.workbuddy/skills/convert-keil-to-cmake/assets/vscode/launch.json.in) into the project's `.vscode/` directory (strip the `.in` suffix). Replace every `@...@` placeholder with project-specific values:
    - `@TOOLCHAIN_FILE@` — path to the generated toolchain file relative to workspace root (e.g. `cmake/arm-none-eabi-gcc.cmake`);
    - `@JLINK_DEVICE@` — the J-Link device name from the `.uvprojx` Device field (e.g. `STM32F407VE`);
    - `@JLINK_INTERFACE@` — `swd` or `jtag` (default `swd`);
    - `@JLINK_SPEED@` — integer speed in kHz (default `4000`);
    - `@ARM_TOOLCHAIN_PATH@` — absolute path to the `bin` directory of the Arm GNU toolchain, for Cortex-Debug `armToolchainPath`. Use the actual path if known from the environment checker; otherwise leave the placeholder and document it as a TODO for the user.
    - `executable` must use `${command:cmake.launchTargetPath}` — never `${command:cmake.buildTargetName}.elf`, which resolves to the CMake aggregate target `all` and produces a broken `build/all.elf` path on F5. `launchTargetPath` returns the ELF of the target selected via `Ctrl+Shift+P → CMake: Set Launch/Debug Target`; this selection is remembered per workspace, so switching projects or firmware names requires no file edits. Document this one-time selection step in `CMAKE_BUILD.md`.
    - Keep the `liveWatch` block (`"enabled": true, "samplesPerSecond": 10`) from the template so the CORTEX LIVE WATCH panel is available: users can watch global/static variables in real time while the target runs, without halting. Document that locals and core registers still require a pause, that only global/static variables are supported, and that the feature requires Cortex-Debug v1.6+. The portable `scripts/live_waveform.py` reuses this block's `samplesPerSecond` and the stored expression list; see "Live Waveform Viewer".
    Then copy [scripts/jlink_flash.py](C:/Users/16034/.workbuddy/skills/convert-keil-to-cmake/scripts/jlink_flash.py) into the project's `scripts/` directory. This script auto-detects the target name from `CMakeLists.txt` and reads device/interface/speed from the `stm32.*` VSCode settings via environment variables. The user only needs to change `stm32.device` in `.vscode/settings.json` when switching to a different MCU. In addition to the `.vscode` files and `jlink_flash.py`, add 6 custom targets to the generated `CMakeLists.txt` so they appear in the CMake Tools sidebar and each has a matching VSCode task. The 6 targets are:
    - `build_project` — compile (`cmake --build build --target all`), no hardware dependency;
    - `rebuild` — clean then rebuild (`all`), no hardware dependency;
    - `clean_project` — remove build artifacts (`clean`), no hardware dependency;
    - `erase_program_verify` — compile + erase + program + verify in one step, `DEPENDS` the ELF target;
    - `erase` — full-chip erase via J-Link;
    - `detect` — read the ARM CPUID and STM32 IDCODE registers to confirm chip connectivity.
    Finally copy [scripts/live_waveform.py](C:/Users/16034/.workbuddy/skills/convert-keil-to-cmake/scripts/live_waveform.py) into the project's `scripts/` directory and keep the `live_waveform` task from `assets/vscode/tasks.json.in`. Add the bilingual `实时波形 / Live Waveform` section from `assets/cmake/CMAKE_BUILD.md.in`. See "Live Waveform Viewer" below. This tool is plain Python, not a CMake custom target, so the 6 CMake targets above stay unchanged. Verify with `python scripts/live_waveform.py --list-symbols` (no hardware needed); a full `--headless --duration 5` run needs the board and a free J-Link.
14. After generation and any available validation, create a concise project-root `CMAKE_BUILD.md` from [assets/cmake/CMAKE_BUILD.md.in](C:/Users/16034/.workbuddy/skills/convert-keil-to-cmake/assets/cmake/CMAKE_BUILD.md.in). Write every user-facing section in both Chinese and English, replace all placeholders, and ensure commands and artifact paths exactly match the generated project. Include flash and debug commands when VSCode integration is generated. Do not report the migration complete until this handoff document exists. State explicitly that the directory is fully standalone and that the original Keil project is untouched.

## Standalone Output Directory

Treat the original Keil tree as read-only. Every migration must deliver a brand-new, self-contained project directory instead of mixing generated files into the Keil project. The generated folder must open directly as its own project and still build after being copied to any location.

- **Destination.** Use the user-specified folder when given; otherwise create a sibling of the Keil project root named `<KeilProjectName>Cmake` (for example `motor_board` -> `motorBoardCmake`) and state the choice. Never generate inside the Keil tree, and never merge into a directory that already contains files.
- **Copy the full active source tree.** Copy every compiled C/C++/ASM file, every header and configuration header, GNU startup, linker script, prebuilt library, generated source, and asset into the new directory. Preserve the original relative layout so paths such as `../Core/Inc` still resolve inside it. Copying whole vendor directories (`Core/`, `Drivers/`, `CMSIS/`) is acceptable; keep CMake source lists explicit so unused alternate ports are never compiled.
- **Keep paths local.** Use `${CMAKE_CURRENT_SOURCE_DIR}` / `${CMAKE_SOURCE_DIR}` in CMake and `${workspaceFolder}` in VSCode. Never emit an absolute Keil-tree path into build files. Absolute paths to the Arm toolchain, J-Link, or Python are external tooling, not a dependency on the Keil tree.
- **Keep the Keil tree clean.** Write no inventory JSON, log, `build/` directory, or template into it. Put scratch files in the system temp directory or the new project's `build/`. Optionally copy `.uvprojx`/`.uvoptx` into `<output>/MDK-ARM/` as audit-only files and state that the build never reads them.
- **Validate independence.** Run `check_standalone.py` (command below). In validated mode, also copy the entire output directory to a different location, delete its `build/`, and configure and build from scratch there. In generation-only mode, still copy the full tree and run the static checker, but mark the relocation build unperformed.

**`validate_conversion.py` path-parity trap.** That validator compares absolute resolved paths for sources and include directories. Running it against the original `.uvprojx` while the CMake project lives elsewhere reports all sources, defines, and includes as missing. Run it against the Keil copies placed at `<output>/MDK-ARM/`, where `../Core/...` resolves inside the standalone tree, and keep `--source-substitution` for compiler-specific replacements such as the GNU startup file. Never fabricate parity by rewriting the validator's expectations.

Checker command (run from anywhere; the script stays in the skill, do not copy it into the generated project):

```text
python "C:/Users/16034/.workbuddy/skills/convert-keil-to-cmake/scripts/check_standalone.py" --source <keil-tree> --output <standalone-dir>
```

It checks directory separation, scans build-related text files for source-tree paths, verifies every compile unit and include directory stays inside the output, and confirms a real source tree was copied. It skips the compile-database check when no build has been run, so generation-only migrations still get a meaningful result. See [references/conversion-reference.md](C:/Users/16034/.workbuddy/skills/convert-keil-to-cmake/references/conversion-reference.md) for implementation details.

## VSCode Integration

The generated `.vscode/` directory provides:

| File | Purpose | User action |
| --- | --- | --- |
| `settings.json` | CMake Tools config (toolchain, generator, build dir) + `stm32.*` device settings | Change `stm32.device` when switching MCU |
| `tasks.json` | One shell task per CMake custom target, plus the standalone `live_waveform` waveform task | `Ctrl+Shift+P` → `Tasks: Run Task` → pick a target label |
| `launch.json` | Cortex-Debug J-Link debug config with `liveWatch` enabled | Press `F5` to debug, auto stops at `main` |

The `live_waveform` task is the only one not backed by a CMake custom target: it runs `scripts/live_waveform.py` directly and needs a free J-Link. See "Live Waveform Viewer".

The generated `CMakeLists.txt` adds 6 custom targets, which appear in the CMake Tools sidebar **Build target** dropdown. The Project Outline sidebar and the Run Task list expose exactly the same 6 operations, so both entry points are functionally identical:

| CMake target | Operation | Purpose | Hardware dependency |
| --- | --- | --- | --- |
| `build_project` | `cmake --build build --target all` | compile all targets | no |
| `rebuild` | clean then `all` | clean + rebuild | no |
| `clean_project` | `cmake --build build --target clean` | remove build artifacts | no |
| `erase_program_verify` | compile + J-Link `loadfile` | erase + program + verify in one step; `DEPENDS` the ELF target | yes |
| `erase` | J-Link full-chip erase | clear the whole flash | yes |
| `detect` | J-Link `mem32` read | read ARM CPUID (`0xE000ED00`) and STM32 IDCODE (`0xE0042000`) to confirm connectivity and chip model | yes |

`build` and `clean` are CMake built-in targets and cannot be overridden, so the compile and clean targets are named `build_project` and `clean_project`; `rebuild` is not a built-in target so it keeps its name.

Required VSCode extensions (document in `CMAKE_BUILD.md`):
- **CMake Tools** (`ms-vscode.cmake-tools`) — Build/Rebuild/Clean via status bar
- **Cortex-Debug** (`marus25.cortex-debug`) — J-Link GDB debug via `F5`

The `scripts/jlink_flash.py` is portable: it auto-detects the firmware target name from `CMakeLists.txt` by resolving `add_executable(${PROJECT_NAME}.elf ...)` or literal names. It reads `STM32_DEVICE`, `STM32_INTERFACE`, and `STM32_SPEED` environment variables, which the VSCode tasks inject from `stm32.*` settings. When migrating to a new project, only `stm32.device` in `settings.json` needs updating.

## Live Waveform Viewer / 实时波形

Every generated project ships `scripts/live_waveform.py`. J-Scope plots raw variables only; this tool plots **C expressions** taken from CORTEX LIVE WATCH as coloured, smoothly scrolling real-time curves in a browser, with zero third-party Python packages.

### What the migration must generate

1. Copy `scripts/live_waveform.py` from this skill to `<output>/scripts/live_waveform.py` unchanged. It is project-agnostic: never bake in a firmware name, MCU, linker script path, or application variable.
2. `.vscode/launch.json` keeps `"liveWatch": {"enabled": true, "samplesPerSecond": 10}` plus a comment pointing at the waveform task. Use `"showDevDebugOutput": "none"` so 10 Hz sampling does not flood the debug console.
3. `.vscode/settings.json` gets `"cortex-debug.liveWatchRefreshRate": 300`.
4. `.vscode/tasks.json` keeps the `live_waveform` task (`python ${workspaceFolder}/scripts/live_waveform.py`). It is a standalone Python tool, **not** one of the 6 CMake custom targets.
5. `CMAKE_BUILD.md` includes the bilingual `实时波形 / Live Waveform` section with exact commands and the J-Link exclusivity warning.
6. `check_build_env.py` lists `arm-none-eabi-gdb` and `winpty` as **optional** tools; missing ones must never fail the build check.

中文：以上 6 项必须由迁移流程自动产出，不能要求用户事后手工补文件。

### How the tool adapts to a new project

- ELF: auto-detect `build/*.elf` (or `--elf`); linker script: `cmake/*.ld` (or `--ld`); GDB: PATH, `armToolchainPath` in `launch.json`, or `--gdb`.
- The RAM window is parsed from the linker script's `MEMORY` block (RAM-like region preferred); override with `--ram-start` / `--ram-size` for unusual layouts.
- Expressions come from, in order: `--expr`, the Cortex-Debug `livewatch.watchTree` in VS Code workspaceState (VS Code encodes the drive colon as `%3A`, so always `unquote()` before comparing), then `auto_expressions()`: up to 4 unique 1/2/4-byte global/static scalars from the ELF, preferring BSS and dynamic-looking names. `--list-symbols` prints candidates offline.
- Device/interface/speed come from `stm32.*` in `settings.json`, sample rate from `liveWatch.samplesPerSecond`, and browser poll defaults to `min(1000/rate, cortex-debug.liveWatchRefreshRate)`; an explicit `--refresh` always wins.

### Runtime design (keep these invariants when editing the tool)

- J-Link Commander's stdout is **fully buffered** on a plain pipe; drive it through `winpty -Xallow-non-tty -Xplain` so reads stream with about 30 ms latency. `JLink.exe`'s `Log` command writes API traces without values, short sessions cost about 147 ms each, and `JLink_x64.dll`'s `JLINK_Connect` is not safe from 64-bit Python — do not substitute these.
- Resolve each expression once with `arm-none-eabi-gdb -batch` (`&ref` / `sizeof` / `ptype`) into address, width and signedness; at runtime only read memory and evaluate locally. Reject addresses outside RAM, because offline pointer chains through a pointer cannot be resolved.
- Group variables into address clusters (gap ≤ 64 B) and issue **one `mem8` read per cluster**, then unpack with `int.from_bytes(..., "little", signed=...)`. One or two commands per sample keeps 10–20 Hz stable. Background RAM reads never halt the CPU.
- Browser UI: `requestAnimationFrame` (~60 fps) driven by a continuous clock, **not** "last data point time" — otherwise the whole curve jumps discretely at every poll. Poll at the sample rate and resize the canvas only when its size actually changes.
- J-Link is exclusive: the waveform tool and a VS Code F5 session cannot run together. Cortex-Debug exposes no external feed of Live Watch values, so this tool is its own observation endpoint (the same model as J-Scope).

### Validation

```text
python scripts/live_waveform.py --list-symbols
python scripts/live_waveform.py --headless --duration 5
python scripts/live_waveform.py --rate 20 --expr "<global variable>"
```

`--list-symbols` runs offline. `--headless` prints sample count and interval statistics; expect roughly `rate × duration` points, a mean interval of `1000/rate` ms, and jitter well below one period. In generation-only mode only the offline check is expected; never claim a hardware run was performed.

## Firmware Size Reporting

Generate a post-link FLASH/RAM usage report for every migrated project. Copy `scripts/size_report.py` into the project's `scripts/` directory and wire it into the ELF target's `POST_BUILD` (already present in `assets/cmake/CMakeLists.txt.in`):

```cmake
COMMAND python ${CMAKE_SOURCE_DIR}/scripts/size_report.py
    $<TARGET_FILE:${PROJECT_NAME}.elf> ${LINKER_SCRIPT}
    --size-tool ${CMAKE_SIZE}
```

Preserve these invariants instead of re-deriving ad hoc numbers:

- Flash used = `text + data`; RAM used = `data + static bss + heap/stack reservation` (reservation included by default). Read capacities from the linker script's `MEMORY` block at report time; never hard-code totals in CMake or in the script.
- GNU `size` already counts NOBITS heap/stack reservation sections (for example `._user_heap_stack`) inside `bss`. Subtract those bytes once before adding the reservation back, or the reservation is counted twice. Confirm with `arm-none-eabi-size -A <elf>`.
- Pass `--flash-region NAME` / `--ram-region NAME` for non-standard MEMORY names, `--reserve BYTES` for a custom reservation, `--static-only` for the pure static RAM figure, and `--bar-width N` for a wider bar. Document multi-region layouts rather than silently picking one bank.
- Keep `POST_BUILD` as the only trigger: it runs on the first build, `rebuild`, and any relink, and stays silent on incremental no-work builds. Do not add a custom target that prints on every invocation.
- Keep output pure ASCII (20-cell `>` bars, one decimal place, `KB` = KiB) so the Windows cmd code page renders it correctly.

In validated mode, cross-check printed flash used against the `.bin` size (`--detail` does this) and state in `CMAKE_BUILD.md` whether RAM includes the heap/stack reservation. In generation-only mode, still generate the script and the command, but use the format illustration from `CMAKE_BUILD.md.in` instead of measured numbers. When the project cannot use Python at all, provide an equivalent deterministic report or explicitly omit this step and say so in the handoff document.

## Authorization and Completion Status

- Treat software installation as a separate, state-changing action. Detecting a missing command does not authorize installing or downloading it. Ask for explicit authorization before using an installer or package manager, changing `PATH`, or modifying machine-wide configuration; state the proposed tool, source, scope, and command first.
- Do not make an installation quiet, unattended, or hidden merely to keep the migration moving. If authorization is not given, preserve the diagnostic result and use generation-only mode when possible.
- Report **validated** only after the project checker passes, `check_standalone.py` passes, a clean configure and build succeeds, a relocated copy also builds from scratch, the firmware links, expected artifacts exist, and `validate_conversion.py` passes.
- Report **generated, unverified** when CMake files and the project checker were generated and statically reviewed but any required configure, build, link, artifact, ELF, or parity check was not completed. This is a usable handoff state, not a validated migration.
- If even generation cannot be completed because essential project data or a parsing runtime is unavailable, report the concrete blocker instead of labeling the result generated or validated.

## User Handoff Document

- Keep `CMAKE_BUILD.md` short and task-oriented. Include only status, prerequisites/environment check, exact configure/build commands, primary artifacts, flash/debug commands, and important validation limits or remaining differences.
- Present Chinese first and English immediately after it within each section. Do not create separate language files, duplicate long logs, narrate the migration history, or paste full source/define/include inventories.
- State either **已验证 / validated** or **已生成、未验证 / generated, unverified** prominently. In unverified mode, name the missing tools and unperformed checks without implying successful compilation.
- Describe each primary artifact by path and purpose, normally `.elf`, `.bin`, `.hex`, `.map`, and any project-specific packaged image that is actually generated. Do not document hypothetical outputs.
- Use commands that can be copied from the repository root. Include the project-local environment checker command before configure/build, and document optional clean, flash, or package commands only when those actions exist.
- When VSCode integration is generated, include a section listing required VSCode extensions and one-click actions (Build via status bar, Flash via Task, Debug via F5).
- Include the bilingual `资源占用 / Resource Usage` section from `CMAKE_BUILD.md.in`, replace `@SIZE_REPORT_DETAIL_COMMAND@` with the real `python scripts/size_report.py <elf> <ld> --detail` command for the generated project, and state the RAM convention (whether the heap/stack reservation is included).
- Include the bilingual `独立工程 / Standalone Project` section from `CMAKE_BUILD.md.in` and state that all sources and headers live inside the folder, that the original Keil tree is untouched, and that the folder can be copied elsewhere and built without modification.

## Conversion Rules

- Make the Keil target the source of truth for source membership and preprocessor settings. Make the MCU datasheet, pack files, startup code, and scatter file the source of truth for architecture and memory layout.
- Preserve source groups as readable CMake module lists. Use explicit lists for startup, HAL/LL drivers, middleware ports, syscall stubs, and other mutually exclusive implementations. Use `GLOB` only where the repository already accepts automatic discovery.
- Keep compiler-specific files separate. Select GNU startup/assembly, GCC RTOS ports, and GCC syscall implementations; never compile Arm Compiler and GCC variants together.
- Prefer target-scoped CMake commands. Keep CPU flags identical across C, C++, assembly, and link steps. Enable ASM explicitly.
- Translate the scatter file deliberately. Reuse an existing validated GNU `.ld` script when present; otherwise create one from the actual memory regions and section rules. Never infer flash origin from total device capacity alone.
- Preserve optimization and debug intent, but do not mechanically copy Arm Compiler flags into GCC. Record any semantic mismatch that cannot be reproduced exactly.
- Avoid conflicting CMake build-type flags such as an implicit `-O3` followed by a target `-Os`. Control or document the effective final optimization and do not add `NDEBUG` unless it matches the selected Keil target.
- Map Keil MicroLIB deliberately. Inspect `printf`, floating-point formats, `fputc`, `_write`, semihosting markers, and available Flash before selecting newlib, newlib-nano, `_printf_float`, `nosys`, or a GCC syscall implementation.
- Generate `.elf`, `.bin`, `.hex`, `.map`, and a FLASH/RAM usage report (percentages plus ASCII progress bars) from `scripts/size_report.py` in `POST_BUILD`. Preserve additional packaging, signing, OTA, flashing, or simulator steps only when they already belong to the project or the user requests them.
- Keep the project-local environment checker diagnostic-only and version-controlled with the generated build files. Required tools must match the normal build path; deployment/debug tools should be optional unless the requested build inherently requires them.
- Do not change application C/C++ code merely to make migration easier unless a genuine compiler portability issue is found. Keep such fixes small and explain them.
- Do not delete or rewrite the Keil project unless explicitly requested. A migration should remain auditable.
- Generate every artifact in a brand-new standalone directory; keep the Keil tree read-only and never mix old and new files. See "Standalone Output Directory".

## Required Validation

- Confirm every intended Keil source is represented once and every excluded or alternate-toolchain source remains excluded.
- Confirm defines and include directories, including file/group overrides where relevant.
- Confirm MCU core, instruction set, FPU, float ABI, startup object, interrupt vectors, linker entry point, and memory origin/length.
- Confirm the selected RTOS, CMSIS, HAL/LL, USB, filesystem, C library, and syscall variants.
- Classify diagnostics as migration errors, pre-existing application warnings, or expected runtime/toolchain warnings. Do not hide behavior-affecting warnings.
- In validated mode, build from a clean directory and require successful configure and link. Inspect the map and size output; verify `.bin` and `.hex` generation. In generation-only mode, mark all of these checks unperformed.
- When Keil CLI is available, build the same target and compare error count, warnings that affect behavior, code/data size, and key symbols. If hardware is available and flashing is authorized, perform the project's normal smoke check.
- Report what was migrated, validation performed, remaining differences, and exact build command.
- Verify `CMAKE_BUILD.md` is bilingual, concise, free of template placeholders, and consistent with the actual generator, toolchain file, target name, build directory, and artifact paths.
- Compare Flash load bytes and RAM components separately. State whether reported RAM includes `.data`, `.bss`, heap, stack, retained sections, or runtime state.
- In validated mode, confirm the usage report prints on the first build and after `rebuild`, stays silent on a no-work incremental build, and that its flash-used value equals the `.bin` file size. In generation-only mode, mark these checks unperformed.
- Run `check_standalone.py` and confirm no build file references the Keil tree, every compile unit and include directory stays inside the output, and the copied source tree is complete. In validated mode, also relocate the whole output directory and rebuild from scratch; mark that check unperformed in generation-only mode.

## Repository Style Baseline

When no local convention exists, use the style derived from the reference project:

- a brand-new standalone project root containing the complete copied source tree, with no build path pointing back to the original Keil directory;
- one readable root build definition with named directory variables and module source collections;
- Ninja out-of-source builds with `arm-none-eabi-gcc`, `objcopy`, and `size`;
- a dedicated simulator/host branch only if the original repository already supports it;
- explicit device definitions, GCC middleware ports, startup assembly, and linker script;
- post-build firmware formats, map/size diagnostics, and FLASH/RAM usage bars with percentages;
- `compile_commands.json`, linker-script `LINK_DEPENDS`, and declared post-build byproducts;
- a thin wrapper for clean, build, package, copy, or flash actions, keeping optional deployment actions separate from compilation;
- a `.vscode/` directory with CMake Tools settings, 6 J-Link/build tasks matching the CMake targets, and a Cortex-Debug launch config for one-click build, flash, and debug;
- a root `CMakeLists.txt` that declares 6 custom targets (`build_project`, `rebuild`, `clean_project`, `erase_program_verify`, `erase`, `detect`) for compile, clean, J-Link flashing, full-chip erase, and chip detection, mirroring the VSCode tasks exactly;
- a portable `scripts/jlink_flash.py` that auto-detects the target name from `CMakeLists.txt` and reads device settings from VSCode configuration;
- a portable `scripts/size_report.py` that reads MEMORY capacities from the LD script, avoids double counting NOBITS heap/stack reservations, and prints ASCII usage bars only when a link occurs;
- a portable `scripts/live_waveform.py` plus the `live_waveform` VSCode task that turn Cortex Live Watch expressions into browser waveforms without halting the CPU, auto-discovering the ELF, linker script, GDB and starter scalars from the generated project.
