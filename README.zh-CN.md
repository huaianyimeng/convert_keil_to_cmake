# Keil 转 CMake

简体中文 | [English](README.md)

这是一个面向 AI Agent 的技能，用于将 Keil MDK/uVision 嵌入式项目转换为可复现的 CMake 构建，通常使用 Ninja 和 GNU Arm Embedded 工具链。

## 功能特点

- 读取 `.uvprojx` 中的目标、源文件、包含路径、宏定义、排除项、内存区域、运行库设置和已有 Keil 产物。
- 将 CPU/FPU/ABI、优化、启动文件、RTOS 移植层、运行库和链接布局转换为 GCC/CMake 配置。
- 生成清晰的 CMake 文件、固件产物、环境检查脚本和简短的中英文编译说明。
- 支持“已验证”和“已生成、未验证”两种交付模式。
- 成功编译后，可比对源文件集合、编译设置、固件产物和关键 ELF 属性。
- 每次链接后输出 ASCII 格式的 FLASH/RAM 占用条与百分比，容量直接取自链接脚本。
- 自动附带浏览器实时波形工具 `scripts/live_waveform.py`：把 CORTEX LIVE WATCH 的表达式画成多通道彩色曲线，支持 C 表达式、60 fps 平滑滚动与 CSV 导出，不暂停 CPU。
- 在一个全新的独立目录中生成完整工程（含全部复制的源码树），不向 Keil 源工程写入任何文件；并验证工程整体搬移后仍可独立编译。
- 未经用户明确授权，绝不安装或下载缺失工具，也不修改 `PATH`。

## 使用要求

- 支持 Codex 风格 Skill 的 AI Agent。
- Python 3.10 或更高版本，用于运行随附的检查和验证脚本。
- 包含 `.uvprojx` 文件的 Keil 项目。
- 仅在需要或能够执行构建验证时，才要求安装 CMake、构建工具和目标工具链。

如果缺少构建工具，但项目仍可静态分析，Agent 可以继续生成文件，并将结果明确标记为“已生成、未验证”。

## 安装

克隆或下载本仓库，然后将 `convert-keil-to-cmake` 目录放置在以下任一位置：

- 个人 Codex Skill 目录，例如 `$CODEX_HOME/skills/convert-keil-to-cmake`；或
- 项目的 `.agents/skills/convert-keil-to-cmake` 目录。

请保持 `SKILL.md`、`scripts/`、`references/`、`assets/` 和 `agents/` 目录结构完整。

## 使用方法

使用 Agent 打开 Keil 项目目录，然后输入：

```text
使用 $convert-keil-to-cmake 将当前 Keil 项目转换为 CMake。
```

如果只想生成文件而不进行本机构建验证：

```text
使用 $convert-keil-to-cmake 只生成 CMake 文件，并将结果标记为未验证。
```

当项目只有一个目标，或生产目标非常明确时，Agent 会直接选择；只有多个目标存在实质差异且无法判断时才会询问用户。

所有生成文件都写入一个全新的独立目录（默认是与 Keil 工程平级的 `<工程名>Cmake`），绝不写入 Keil 源工程目录；也可显式指定目标路径。整个迁移过程中 Keil 原工程保持只读。

## 项目生成文件

实际目录结构会遵循原项目风格，典型转换结果包括：

| 文件 | 用途 |
| --- | --- |
| `CMakeLists.txt` | 主构建配置 |
| `cmake/arm-none-eabi-gcc.cmake` | GNU Arm 工具链配置 |
| `cmake/*.ld` | 项目没有可用 GNU 链接脚本时生成的链接脚本 |
| `check_build_env.py`、`.bat` 或 `.sh` | 项目内只诊断、不安装软件的环境检查脚本 |
| `CMAKE_BUILD.md` | 简短的中英文编译方法和产物说明 |
| `scripts/size_report.py` | 构建后 FLASH/RAM 占用条、百分比与段明细报告 |
| `scripts/live_waveform.py` | CORTEX LIVE WATCH 表达式的浏览器实时波形（多通道彩色、C 表达式、CSV 导出） |
| `build/*.elf`、`*.bin`、`*.hex`、`*.map` | 完成验证构建后生成的固件及分析文件 |

文档只会列出转换项目实际支持的产物。

## 验证状态

| 状态 | 含义 |
| --- | --- |
| `已验证 / validated` | 环境检查、干净配置、编译、链接、预期产物和转换验证均已通过 |
| `已生成、未验证 / generated, unverified` | 已生成并静态检查构建文件，但部分运行验证无法执行或按要求跳过 |

生成的 `CMAKE_BUILD.md` 会列出准确的编译命令、产物、缺失工具和后续待执行检查。

## 随附工具

只读检查 Keil 项目：

```text
python scripts/inspect_uvprojx.py path/to/project.uvprojx --target "Target Name"
```

验证已完成的 CMake 构建：

```text
python scripts/validate_conversion.py path/to/project.uvprojx build/compile_commands.json --elf build/firmware.elf
```

如果 GCC 使用了不同的启动文件、RTOS 移植层或系统调用实现，可以重复使用 `--source-substitution old=new` 声明替换关系。

## 安全与适用范围

- 除非用户明确要求，否则保留原 Keil 项目，不删除也不重写。
- 环境检查脚本只进行诊断，不安装软件，不修改系统。
- Scatter 文件按照行为和内存布局转换，不进行机械式语法替换。
- 多段内存、Bootloader、Overlay、外部存储器和专有库需要结合具体项目审查。

Agent 工作流程请参阅 [SKILL.md](SKILL.md)，详细转换规则请参阅 [conversion-reference.md](references/conversion-reference.md)。

## 开源许可证

本项目采用 [MIT License](LICENSE) 开源。
