# Keil MDK to CMake Conversion Reference

## Contents

- Project inventory
- Standalone output directory
- Environment prerequisites and completion states
- Toolchain and architecture
- Sources, overrides, and language handling
- Includes and definitions
- Linker and memory layout
- Libraries and runtime
- Firmware size and usage reporting
- Windows and CMake invocation
- Bilingual build handoff
- Middleware and generated code
- Validation and common failures
- VSCode IDE integration and flashing

## Project inventory

Read the selected `<Target>` in `.uvprojx`. Capture:

- `TargetName`, `Device`, `Vendor`, `Cpu`, output name and output directory;
- `uAC6` or other toolchain selector;
- target C, assembly, and linker controls;
- every group, file path, file type, build exclusion, and file-level option;
- include paths, defines, undefines, misc controls, optimization, warning level;
- scatter file, library inputs, output format requests, and user commands.
- `useUlib`, target-dialog memory regions, and `umfTarg` generated-scatter selection;
- existing `.sct`, `.map`, `.axf`, `.hex`, and build log files in the Keil output directory.

Resolve file paths relative to the `.uvprojx` directory, not the shell working directory. Keil paths may use backslashes, environment variables, pack variables, or absolute Windows paths. Replace machine-specific pack paths with repository-relative paths or a documented CMake cache variable. When the migration targets a standalone output directory, resolve these paths against the Keil copy inside that directory (see "Standalone output directory"), never against the original tree.

`.uvoptx` mostly contains per-user debug and UI state. Read it only for requested debug/flash integration; do not treat it as the compile source of truth.

When `ScatterFile` is empty and `umfTarg` is enabled, inspect the generated `<output-directory>/<output-name>.sct`. The target-dialog `IROM` and `IRAM` fields remain the primary memory inventory, while the generated scatter file and map confirm actual section placement.

## Standalone output directory

Every migration writes into a brand-new directory that is separate from the Keil project. The old in-place behaviour mixed `CMakeLists.txt`, `.vscode/`, build files, and vendor sources into the Keil tree; that makes changes hard to audit and leaves two build systems fighting over the same files.

### Choosing and populating the destination

- Prefer an explicit user path. Otherwise create a sibling of the Keil project root named `<KeilProjectName>Cmake` (for example `D:/work/motor_board` -> `D:/work/motorBoardCmake`) and state the choice. If it already contains files, ask instead of merging.
- Copy, do not reference. The output must contain every compiled source, header, configuration header, GNU startup file, linker script, static library, generated source, and asset that the build reads. Copy whole vendor trees (`Core/`, `Drivers/`, `CMSIS/`, middleware) when practical; explicit CMake source lists still prevent unused alternate ports from being compiled.
- Preserve relative layout. Keil paths such as `../Core/Inc` and `../Drivers/...` resolve relative to the `.uvprojx` directory. Recreate the same directory levels inside the output so those references keep resolving locally. A stray `../../` that escapes the output directory is a migration defect.
- Keep the Keil tree read-only: write no inventory JSON, log, `build/`, or template there. Use the system temp directory or `<output>/build/` for scratch data.

### Path rules

- CMake: `${CMAKE_CURRENT_SOURCE_DIR}`, `${CMAKE_SOURCE_DIR}`, `${CMAKE_BINARY_DIR}` only. VSCode: `${workspaceFolder}`. Never emit an absolute Keil-tree path into `CMakeLists.txt`, toolchain files, linker scripts, tasks, wrappers, or docs.
- Absolute paths to the Arm toolchain, Ninja, Python, or J-Link are external tool locations, not dependencies on the Keil project. Document them (for example `armToolchainPath` in `launch.json`) as machine-specific settings.
- A stale `build/` cache can retain old absolute paths. Delete `build/` and reconfigure after any directory move.

### Audit copies and `validate_conversion.py`

Optionally copy `.uvprojx` and `.uvoptx` into `<output>/MDK-ARM/` as audit-only files, and state that the build never reads them. This also solves a subtle validator problem: `validate_conversion.py` compares **absolute resolved paths** for sources and include directories. Pointing it at the original `.uvprojx` while the CMake project lives in a new directory makes every source, define, and include look missing. With the copies at `<output>/MDK-ARM/`, the relative `../Core/...` entries resolve inside the standalone tree and parity checks work normally:

```text
python ".../scripts/validate_conversion.py" <output>/MDK-ARM/project.uvprojx <output>/build/compile_commands.json --elf <output>/build/firmware.elf --source-substitution <keil-startup>=<gnu-startup>
```

Keep `--source-substitution` for compiler-specific replacements (GNU startup, RTOS ports, syscalls). Do not edit the validator or invent substitutions to hide real membership differences.

### Independence verification

Run the static checker after generation and again after the build, so `compile_commands.json` is included:

```text
python ".../scripts/check_standalone.py" --source <keil-tree> --output <standalone-dir>
python ".../scripts/check_standalone.py" --source <keil-tree> --output <standalone-dir> --json
```

It reports directory separation, source-tree path references in build-related text files, compile units and include directories that escape the output, the presence of a real copied source tree, and the minimum generated files. Keil audit copies are excluded from the path scan and listed in the report. Without `compile_commands.json` that check is skipped, so generation-only migrations still get a usable result.

In validated mode, also perform an empirical relocation build: copy the entire output directory to a different location, delete the copied `build/`, configure and build from scratch, and confirm the generated `compile_commands.json`, `build.ninja`, and `CMakeCache.txt` contain no path to the Keil tree. Static scanning alone cannot prove that a relocated copy builds. Common failures at this stage are `..` include paths escaping the new root, hard-coded absolute include paths in a copied configuration header, a stale CMake cache, and a linker script that still points at the Keil output directory.

## Environment prerequisites and completion states

Every migration must add a diagnostic environment checker to the project root. Start from `assets/cmake/check_build_env.py` and tailor `TOOLS` to the build that is actually generated:

- retain `cmake` and the selected generator (`ninja`, `make`, or another project tool), but do not require both Ninja and Make;
- require the selected C compiler and only require a C++ compiler when active C++ sources or link requirements exist;
- require binutils used by normal post-build or validation commands, such as `objcopy`, `size`, `nm`, and `readelf`;
- include packaging or code-generation commands when the normal build invokes them;
- classify flashing, debugging, simulation, and deployment commands as optional unless the user's requested build inherently includes those actions.

Prefer the standard-library Python checker because it works on Windows and POSIX and has no third-party dependency. If Python cannot reasonably be a project prerequisite, generate one native equivalent appropriate to the host convention: `check_build_env.bat` for Windows or `check_build_env.sh` for POSIX. An equivalent checker must print each command's found/missing state, resolved path and usable version when available, distinguish required from optional tools, return nonzero for missing required tools, and avoid modifying the environment.

The checker is diagnostic-only. It must never download an archive, call `winget`, Chocolatey, Scoop, a Linux package manager, Homebrew, an installer, or a toolchain setup program. It must not edit user/system `PATH`, environment variables, profiles, registries, or machine-wide configuration. Any such action requires a separate explanation and explicit user authorization stating the tool, source, scope, and intended command. Lack of authorization is not permission to install quietly.

Use the checker result to choose one of these outcomes:

| Status | Minimum evidence | Reporting rule |
| --- | --- | --- |
| `validated` | Checker passes; clean CMake configure/build/link succeeds; expected outputs exist; conversion validator passes | May report a validated migration and include the reproduced build command |
| `generated, unverified` | Build files and checker are generated and statically reviewed, but one or more runtime validations are unavailable or intentionally skipped | List missing tools and unperformed checks; provide exact commands for later verification; never imply build success |
| blocked before generation | Essential target data cannot be obtained or files cannot be generated safely | Report the blocker and do not use either completion label |

Generation-only mode is valid when the user explicitly requests it or required tools are missing and installation has not been authorized. Static review should still cover paths, CMake syntax structure, placeholder removal, source inventory mapping, architecture flags, memory values, and command consistency wherever the available project data permits. Do not fabricate `compile_commands.json`, ELF inspection, size results, or parity evidence.

## Toolchain and architecture

Translate architecture from the actual device/core configuration:

| Keil intent | Typical GNU Arm option |
| --- | --- |
| Cortex-M0/M0+ | `-mcpu=cortex-m0` / `-mcpu=cortex-m0plus` |
| Cortex-M3 | `-mcpu=cortex-m3` |
| Cortex-M4 without FP use | `-mcpu=cortex-m4 -mfloat-abi=soft` |
| Cortex-M4F single precision | `-mcpu=cortex-m4 -mfpu=fpv4-sp-d16 -mfloat-abi=<softfp|hard>` |
| Cortex-M7 FPv5 | device-dependent `-mfpu=fpv5-...` plus matching ABI |
| Thumb Cortex-M | `-mthumb` when required by the selected GCC/toolchain behavior |

Do not guess `hard` versus `softfp`. All linked prebuilt libraries must use a compatible ABI. Apply architecture flags to compile, assembly, and link commands.

Use a toolchain file so compiler selection occurs before `project()`. Set `CMAKE_SYSTEM_NAME Generic`, `CMAKE_SYSTEM_PROCESSOR arm`, compilers, binutils, and `CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY`.

Map optimization by intent: Keil debug-oriented levels to `-Og -g3`, size-oriented levels to `-Os`, and speed-oriented levels to `-O2` or `-O3` only when behavior and size are checked. There is no safe numeric one-to-one mapping between Arm Compiler and GCC optimization levels.

CMake build types may inject their own flags. Confirm the final compile command rather than assuming a later target option is the only optimization setting. Avoid silently combining `Release` defaults such as `-O3 -DNDEBUG` with a different target-scoped optimization.

## Sources, overrides, and language handling

Preserve exact membership first. Good module boundaries usually follow Keil groups or repository directories, but group names are organizational and may not match paths.

Treat these as explicit selections:

- startup files and vector tables;
- RTOS portable layer and heap implementation;
- compiler-specific fault handlers and intrinsics;
- semihosting, syscall, and retarget implementations;
- HAL/LL driver subset;
- middleware ports and generated sources;
- files excluded from the selected target.

Enable `C CXX ASM` only as needed. For preprocessed assembly use `.S` or set source language/options deliberately. Do not relabel assembly as C merely to force compilation. Translate file-level defines/options with `set_source_files_properties()` or `set_property(SOURCE ... PROPERTY COMPILE_OPTIONS ...)` only when they affect the selected build.

Prefer explicit source lists for fragile selections. If adopting the reference repository's glob style, use narrow module globs and keep alternate ports explicit. Avoid recursive globs across vendor trees containing examples or multiple architectures.

## Includes and definitions

Convert target include paths to `target_include_directories(<target> PRIVATE ...)` and comma-separated Keil defines to `target_compile_definitions(<target> PRIVATE ...)`. Normalize paths through CMake variables such as `SOURCE_DIR`, `CMSIS_DIR`, and `HAL_DIR`.

Preserve meaningful macro values and quoting. Examples include device macros, driver selection, oscillator values, RTOS configuration, and middleware configuration headers. Do not propagate IDE-only or Arm-Compiler-only macros unless GCC code also requires them.

File and group overrides can add or replace target settings. Inspect them before assuming target-level lists are complete.

## Linker and memory layout

Arm scatter files and GNU linker scripts use different languages. Translate concepts, not syntax:

- load/execution regions -> `MEMORY` regions and output sections;
- reset/start address -> flash `ORIGIN` and vector placement;
- RW/ZI regions -> `.data`, `.bss`, special RAM sections, and copy/zero tables;
- no-init/retained sections -> `NOLOAD` sections;
- absolute/overlay sections -> explicit section addresses and assertions;
- stack/heap -> startup/runtime-compatible symbols and reserved sections;
- discarded/retained input -> `/DISCARD/` and `KEEP()`.

Cross-check addresses with bootloader reservations, OTA slots, external memory, option bytes, and the startup code. Add linker `ASSERT()` checks for critical bounds when the original layout has equivalent constraints.

For a simple single-Flash/single-RAM target, the bundled `stm32-flash.ld.in` provides the usual vector, code, data, BSS, constructor, heap, and stack sections. Do not use it unchanged for multi-bank RAM, external memory, bootloader handoff, overlays, retained memory, or custom load addresses. Use explicit `PHDRS` or inspect program headers to prevent writable-executable load segments. Mark the linker script as a CMake `LINK_DEPENDS` input so editing it relinks the target.

Typical GNU link options include the validated `.ld` script, `-Wl,-Map=<name>.map`, `-Wl,--gc-sections`, and a compatible runtime spec. Use `-ffunction-sections -fdata-sections` only when section garbage collection is intended.

## Libraries and runtime

Keil microlib is not GNU newlib-nano. Select runtime behavior explicitly. `--specs=nano.specs`, `--specs=nosys.specs`, semihosting, `_printf_float`, C++ support libraries, and custom syscalls all change behavior or size. Add only what the project needs.

Use this decision guide, then verify the linked map and behavior:

| Keil/runtime usage | GNU starting point |
| --- | --- |
| MicroLIB with no standard I/O | `nano.specs`; add `nosys.specs` only when host I/O is intentionally absent |
| Integer-only `printf` | newlib-nano without `_printf_float` |
| Floating-point `printf` | measure with `_printf_float`; it can add substantial code and heap state |
| `fputc` UART retarget | implement or select the GCC `_write` path; `fputc` alone does not retarget newlib |
| `fputc` discards output | preserve the no-output behavior deliberately and document any formatting omission |
| Semihosting | select the matching runtime specs and verify debugger dependence |

Scan active sources for `printf` format strings, `fputc`, `_write`, semihosting markers, allocation, and C++ runtime use. Compare the result with available Flash and RAM before choosing specs. Do not force floating-point formatting solely because a dormant or discarded debug print contains `%f`.

Check prebuilt `.lib`/`.a` files for object format, architecture, FPU ABI, compiler ABI, and licensing/source availability. Arm Compiler libraries are not automatically link-compatible with GCC. Prefer rebuilding third-party source with the selected toolchain.

Keep link ordering and circular dependencies in mind. Prefer CMake targets; use a linker group only where static library cycles require it.

## Firmware size and usage reporting

Every generated project prints two ASCII usage bars after a successful link. Example from an STM32F103CB migration:

```text
flash [>>>>                ] (19.0%) used:  24.3 KB, total: 128.0 KB
ram   [>>>>                ] (20.9%) used:   4.2 KB, total:  20.0 KB
```

Copy `scripts/size_report.py` into the project's `scripts/` directory and call it from the ELF target's `POST_BUILD` as shown in `assets/cmake/CMakeLists.txt.in`. It replaces the bare `arm-none-eabi-size --format=berkeley` command. Formula:

- Flash used = `text + data`, the load image, normally equal to the `.bin` size (`--detail` cross-checks this).
- RAM used = `data + static bss + heap/stack reservation`. The reservation comes from the LD script's heap/stack symbols (`_Min_Heap_Size`/`_Min_Stack_Size` and common variants); `--reserve` overrides it and `--static-only` drops it.
- Capacities come from the LD script's `MEMORY` block, parsed at report time. Never hard-code totals in CMake or in the report script: one source of truth keeps percentages correct after a device or bootloader-offset change.

**Do not double count the reservation.** GNU `size` includes SHT_NOBITS sections in `bss`, so a GNU-LD `._user_heap_stack` section (or any `.heap*` / `.stack*` section) is already part of the reported `bss`. A naive `data + bss + heap + stack` counts those bytes twice. Find the reserved bytes with `size -A <elf>` (`--format=sysv`), subtract them from `bss`, then add the reservation back once. Confirm that the reserved section size matches the LD heap+stack symbols; when they differ because of alignment padding, use the larger value.

Region names resolve as `FLASH`/`RAM` first, then by `IROM`/`ROM`/`IRAM` keywords. For multi-region layouts (bootloader slots, dual-bank flash, CCMRAM, external RAM), pass `--flash-region NAME` and `--ram-region NAME` in the POST_BUILD command, or document which region the percentages describe. One pair of bars cannot describe multiple RAM banks; add a second invocation or state the limitation in `CMAKE_BUILD.md`.

`POST_BUILD` runs only when the link step runs: the first build, `rebuild`, and any source change forcing a relink. Incremental builds with no work print nothing. This is intentional; do not add a custom target that prints on every invocation. Keep the report in `POST_BUILD` and document the on-demand form `python scripts/size_report.py <elf> <ld> --detail`.

Keep output pure ASCII (`>`, spaces, ASCII labels). Chinese punctuation and ANSI color codes can garble under the Windows cmd code page. `--bar-width N` increases bar resolution when two percentages fall in the same cell.

In generation-only mode, still copy the script and wire the POST_BUILD command, but never paste measured numbers into `CMAKE_BUILD.md`: use the format illustration from `CMAKE_BUILD.md.in` and mark the values unverified.

## Windows and CMake invocation

Check `cmake`, `ninja`, `arm-none-eabi-gcc`, `arm-none-eabi-objcopy`, `arm-none-eabi-size`, `arm-none-eabi-nm`, and `arm-none-eabi-readelf` before configuring. On PowerShell, quote the entire `-D` argument:

```powershell
cmake -S . -B build -G Ninja "-DCMAKE_TOOLCHAIN_FILE=cmake/arm-none-eabi-gcc.cmake"
cmake --build build
```

Use a new build directory when changing the toolchain. A stale cache can retain a host compiler, old ABI, or old linker script.

## Bilingual build handoff

Generate `CMAKE_BUILD.md` in the project root after the build files are ready and after any available validation. Start from `assets/cmake/CMAKE_BUILD.md.in`, but adapt its commands, paths, output rows, and wording to the project rather than preserving unused placeholders.

Keep the document concise and independently usable by someone who did not observe the conversion. Each section must contain Chinese followed immediately by its English equivalent. Use one bilingual file instead of separate Chinese and English documents.

The document must contain:

- the selected target and completion status: `已验证 / validated` or `已生成、未验证 / generated, unverified`;
- the project-local environment checker command and a short prerequisite summary;
- exact repository-root configure and build commands, including generator and toolchain file;
- actual primary firmware outputs with paths and one-line purposes;
- a short validation result, or missing prerequisites and exact commands still requiring execution;
- an explicit statement that the folder is standalone: sources copied in, Keil tree untouched, and the folder still buildable after being moved.

Include clean, package, flash, simulator, or deployment commands only when the generated project actually supports them. Do not paste tool output, exhaustive file lists, migration history, or generic CMake tutorials. Remove rows for artifacts that are not generated and add project-specific packaged outputs only when verified by the build definition.

Before handoff, search the document for unreplaced `@...@` tokens and compare every command/path with `CMakeLists.txt`, the toolchain file, and the selected build directory. A successful build does not excuse stale documentation, and generation-only status must never be worded as successful compilation.

## Middleware and generated code

Select the GCC-specific portable implementation for FreeRTOS or another RTOS. Match Cortex-M variant and FPU port. Preserve the selected heap file exactly.

For CMSIS, HAL/LL, USB, FatFS, networking, and UI libraries, include only the project's active source subset and configuration headers. Do not build bundled examples, templates, tests, or alternate device families.

Generated code may be regenerated by CubeMX or another tool. Keep edits outside generated zones when possible, and integrate existing regeneration rules rather than forking generated files silently.

## Validation and common failures

Compare the Keil and CMake source sets by normalized resolved path. Then check:

- duplicate startup/vector definitions;
- wrong RTOS port or heap source;
- missing device macro or configuration header;
- incompatible FPU ABI in a library;
- lost file-level override;
- incorrect flash origin caused by a bootloader offset;
- `.s` syntax written for armasm rather than GNU assembler;
- scatter features omitted from the GNU linker script;
- syscall duplication or unexpected semihosting;
- CMake compiler selection performed after `project()`;
- stale CMake cache masking a toolchain change;
- generated files that still reference the original Keil tree, or an output directory that cannot build after relocation.

Use a clean configure and verbose build when diagnosing. Inspect the ELF with `arm-none-eabi-size`, `nm`, `objdump -h`, and `readelf` as appropriate. Compare the map files and confirm reset handler, vector table, stack symbol, data copy boundaries, BSS boundaries, and firmware image start.

Enable `CMAKE_EXPORT_COMPILE_COMMANDS` and run `scripts/validate_conversion.py` for deterministic source, define, include, artifact, vector, stack, and program-header checks. Provide explicit source substitutions for GNU startup, RTOS ports, syscalls, or other compiler-specific replacements. Treat a successful link with wrong source membership as a failed migration.

Compare size using explicit categories rather than raw tool totals:

- Flash load bytes: code, read-only data, and initialized data load image;
- static RAM: initialized data and zero-initialized data;
- reserved RAM: heap, stack, retained/no-load regions, and runtime state.

Classify warnings in the final report as migration-induced, pre-existing application issues exposed by GCC, or expected runtime warnings such as intentionally absent host syscalls.

## VSCode IDE integration and flashing

Every migration should generate a `.vscode/` directory so the user can build, flash, and debug from the VSCode GUI without typing commands. Use the templates in `assets/vscode/` as a starting point.

### Placeholder mapping

| Placeholder | Source | Example |
| --- | --- | --- |
| `@TOOLCHAIN_FILE@` | path to the generated toolchain file, relative to workspace root | `cmake/arm-none-eabi-gcc.cmake` |
| `@JLINK_DEVICE@` | J-Link device name from `.uvprojx` Device field; shared by `.vscode/settings.json` and `CMakeLists.txt` custom targets | `STM32F407VE` |
| `@JLINK_INTERFACE@` | debug interface, `swd` or `jtag`; shared by `.vscode/settings.json` and `CMakeLists.txt` custom targets | `swd` |
| `@JLINK_SPEED@` | integer speed in kHz; shared by `.vscode/settings.json` and `CMakeLists.txt` custom targets | `4000` |
| `@ARM_TOOLCHAIN_PATH@` | absolute path to the `bin` directory of the Arm GNU toolchain | `D:\arm-gcc-tool-chain\...\bin` |

### settings.json

Configures CMake Tools to use the generated toolchain file, Ninja generator, and `${workspaceFolder}/build` directory. Adds `stm32.*` custom settings that tasks and launch configs read dynamically:

- `stm32.device` — J-Link device name (the only setting the user changes when switching MCU);
- `stm32.interface` — `swd` or `jtag`;
- `stm32.speed` — J-Link speed in kHz.

All paths use `${workspaceFolder}` relative references — no hardcoded absolute paths.

### tasks.json

Defines 6 shell tasks, one per CMake custom target, plus the standalone `live_waveform` task (see "Live waveform viewer"). Each CMake-backed task runs `cmake --build ${workspaceFolder}/build --target <name>`, and the task label matches the CMake target name exactly:

- **erase_program_verify** — compile + erase + program + verify via J-Link (the script subcommand is still `flash`);
- **erase** — full-chip erase via J-Link;
- **detect** — reads the ARM CPUID and STM32 IDCODE registers via JLink.exe to confirm chip connectivity;
- **build_project** — compile all targets (no hardware required);
- **rebuild** — clean then rebuild all (no hardware required);
- **clean_project** — remove build artifacts (no hardware required).

Every CMake-backed task is `cmake --build build --target <name>`, so the Run Task list and the CMake Tools Project Outline sidebar are functionally identical. The `live_waveform` task is the sole exception: it runs `python ${workspaceFolder}/scripts/live_waveform.py` directly and is not a CMake target. The user runs them via `Ctrl+Shift+P` → `Tasks: Run Task`.

### launch.json

Configures Cortex-Debug (`marus25.cortex-debug` extension) for J-Link GDB debugging:

- `executable` — `${command:cmake.launchTargetPath}` (never `cmake.buildTargetName`, which resolves to the `all` aggregate target and yields a broken `build/all.elf`);
- `liveWatch` — `{"enabled": true, "samplesPerSecond": 10}`, consumed by both the CORTEX LIVE WATCH panel and `scripts/live_waveform.py`;
- `device` / `interface` — read from `${config:stm32.*}` settings;
- `serverpath` — `JLinkGDBServerCL.exe` (resolved from PATH);
- `armToolchainPath` — absolute path to the GCC toolchain bin directory;
- `runToEntryPoint` — `main` (auto-stops at main on launch).

The user presses `F5` to start debugging.

### CMake custom targets

The generated `CMakeLists.txt` declares 6 `add_custom_target()` entries. The `build_project`, `rebuild`, and `clean_project` targets run `cmake --build` internally and need no hardware; the `erase_program_verify`, `erase`, and `detect` targets call `scripts/jlink_flash.py`. The J-Link targets are wired through `@JLINK_DEVICE@`, `@JLINK_INTERFACE@`, and `@JLINK_SPEED@` and pass `WORKSPACE_FOLDER=${CMAKE_SOURCE_DIR}` to the script:

| Target | Subcommand / command | Behavior | Hardware |
| --- | --- | --- | --- |
| `build_project` | `cmake --build build --target all` | Compile all targets | no |
| `rebuild` | `cmake --build build --target clean` then `all` | Clean then rebuild all | no |
| `clean_project` | `cmake --build build --target clean` | Remove build artifacts | no |
| `erase_program_verify` | `flash` | Compiles the firmware (declared with `DEPENDS ${PROJECT_NAME}.elf`), then runs J-Link `loadfile` to perform erase + program + verify in one step | yes |
| `erase` | `erase` | Runs J-Link `erase` for a full-chip erase | yes |
| `detect` | `detect` | Runs J-Link `mem32` to read the ARM CPUID and STM32 IDCODE registers and report connectivity and chip model | yes |

`build` and `clean` are CMake built-in targets and cannot be overridden, so the compile and clean targets are named `build_project` and `clean_project`; `rebuild` is not a built-in target so it keeps its name.

These targets appear in the VSCode CMake Tools sidebar **Build target** dropdown next to the firmware ELF target. Because each has a matching task in `tasks.json` that runs `cmake --build build --target <name>`, the Project Outline sidebar and the Run Task list are functionally identical, giving one-click build/clean/rebuild/program/erase/detect without typing commands.

### J-Link Commander `mem32`

`detect_chip()` drives `JLink.exe` with two `mem32` reads, then `exit`:

```text
mem32 0xE000ED00 1
mem32 0xE0042000 1
exit
```

`mem32 <address>` with a count of `1` reads one 32-bit word at the given address. `read_mem32()` parses the `0xE000ED00 = 0x...` style lines from the captured output. Because `JLink.exe` is invoked with `-ExitOnError 1` and `-AutoConnect 1`, a failed connect returns a nonzero exit code. The detect routine treats a nonzero exit, a `cannot connect`/`error`/`failed` message, or a missing CPUID value as a failure and reports the likely causes: SWD cable reversed, broken wire, chip not powered, or wrong device name.

### CPUID and IDCODE register mapping

| Register | Address | Reading | Mapping |
| --- | --- | --- | --- |
| ARM CPUID | `0xE000ED00` | full 32-bit value | `CPUID_NAMES` maps value to core, e.g. `0x410FC240` → `ARM Cortex-M4`, `0x410FC241` → `ARM Cortex-M4`, `0x410CC200` → `ARM Cortex-M0+`, `0x410CB200` → `ARM Cortex-M0`, `0x410FC230` → `ARM Cortex-M3`, `0x410FD200` → `ARM Cortex-M7` |
| STM32 IDCODE | `0xE0042000` | low 12 bits (`value & 0xFFF`) | `STM32_IDCODE_NAMES` maps the bits to a device family, e.g. `0x413` → `STM32F405xx/STM32F407xx`, `0x419` → `STM32F42xxx/STM32F43xxx`, `0x411` → `STM32F2xx` |

On success the detect routine prints `Chip detection: PASSED`; on failure it prints `Chip detection: FAILED`.

### jlink_flash.py

A portable Python script (standard library only, no third-party dependencies) that:

1. Auto-detects the firmware target name from `CMakeLists.txt` by resolving `add_executable(${PROJECT_NAME}.elf ...)` or literal names (supports `set(VAR ...)` variable chains and `project()` implicit `PROJECT_NAME`);
2. Reads `STM32_DEVICE`, `STM32_INTERFACE`, `STM32_SPEED` from environment variables (injected by VSCode tasks from `stm32.*` settings);
3. Invokes `JLink.exe` with `loadfile` (flash), `erase`, or `mem32` (detect) commands;
4. Parses `mem32` output in `detect` mode to report the CPUID/IDCODE values and passes or fails chip detection;
5. Requires `JLink.exe` in PATH.

When migrating to a new project, copy this script as-is — no modifications needed. The target name is auto-detected; only `stm32.device` in `.vscode/settings.json` needs updating for a different MCU.

### J-Link device name mapping

The J-Link device name comes from the Keil `.uvprojx` `<Device>` field. Common mappings:

| Keil Device | J-Link Device Name |
| --- | --- |
| STM32F103C8 | `STM32F103C8` |
| STM32F407VETx | `STM32F407VE` |
| STM32H743VITx | `STM32H743VI` |

Strip the package suffix (`Tx`, `Ux`, etc.) and use the base part number. Verify the exact name in SEGGER's device database or J-Link Configurator if unsure.

### Live waveform viewer

Every generated project also ships `scripts/live_waveform.py` and the `live_waveform` VSCode task. It reads CORTEX LIVE WATCH expressions (persisted by Cortex-Debug in workspaceState under `marus25.cortex-debug` / `livewatch.watchTree`; VS Code encodes the drive colon as `%3A`, so `unquote()` before comparing), resolves them offline with `arm-none-eabi-gdb` to RAM addresses, and samples those addresses in the background through J-Link while the CPU keeps running. A browser Canvas draws each channel in a different colour with `requestAnimationFrame` scrolling.

- Rate: `liveWatch.samplesPerSecond` (10 Hz). Browser poll: `min(1000/rate, cortex-debug.liveWatchRefreshRate)`; an explicit `--refresh` overrides it. Polling at the sample rate plus a continuous clock avoids the "curve jumps every 300 ms" artifact.
- Data path: `winpty -Xallow-non-tty -Xplain JLink.exe ...`, because J-Link Commander stdout is fully buffered on a plain pipe. One `mem8` read per address cluster (gap ≤ 64 B), unpacked locally with `int.from_bytes`, keeps 10–20 Hz stable.
- Project-agnostic discovery: `build/*.elf`, `cmake/*.ld`, `arm-none-eabi-gdb` from PATH or `armToolchainPath`, and up to 4 auto-picked 1/2/4-byte scalars from the ELF when the Live Watch list is empty. Overrides: `--elf`, `--ld`, `--gdb`, `--ram-start`, `--ram-size`, `--expr`, `--list-symbols`.
- Limits: J-Link is exclusive, so the tool cannot run beside an F5 debug session. Expressions must resolve to RAM scalars; offline pointer chains are rejected. The tool is a standalone Python task, not a CMake custom target.
- Offline validation: `python scripts/live_waveform.py --list-symbols`. Hardware validation: `python scripts/live_waveform.py --headless --duration 5` prints the achieved rate and interval jitter.

### Required VSCode extensions

Document these in `CMAKE_BUILD.md`:

| Extension | ID | Purpose |
| --- | --- | --- |
| CMake Tools | `ms-vscode.cmake-tools` | Build/Rebuild/Clean via status bar, configure管理 |
| Cortex-Debug | `marus25.cortex-debug` | J-Link GDB debug via `F5`, register/peripheral view |

### Toolchain PATH persistence

For the generated VSCode integration to work without per-session PATH setup, the toolchain binaries must be in the system or user PATH. This includes:

- `arm-none-eabi-gcc` and binutils (from Arm GNU Toolchain);
- `ninja` (from Ninja build system);
- `cmake` (from CMake, or pip-installed);
- `JLink.exe` and `JLinkGDBServerCL.exe` (from SEGGER JLink installation).

On Windows, set these via System Properties → Environment Variables → User `Path`, or via PowerShell:
```powershell
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\path\to\toolchain\bin", "User")
```

The environment checker (`check_build_env.py`) diagnoses whether tools are in PATH but never modifies PATH itself. If tools are missing, report them and request explicit authorization before installing or changing PATH.
