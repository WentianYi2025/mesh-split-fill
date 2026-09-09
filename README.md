# mesh-split-fill

面向 Windows 和 macOS 的 Codex 三维网格拆件与补洞技能，使用 Blender 完成检查、模型处理与真实过程记录。

## 工作流

- 先固定完整拆件清单，包括小装饰、背面附件、左右件和需要保留的开口。
- 拆分与补面共用接缝设计；先验证困难样件，再批量处理同类接口。
- 对互补接口使用同一份补片数据并反转绕序，避免独立求解后无法贴合。
- 使用源文件和契约哈希追踪变更，记录候选质量与有限返修次数。
- 提前固定过程图的案例、步骤、视角和版式，保存真实中间网格与渲染。

## 安装

下载本仓库中的 `mesh-split-fill-v1.0.0.zip` 并解压，运行：

```text
python mesh-split-fill/scripts/install.py
```

macOS 通常使用 `python3`。也可以把完整 `mesh-split-fill` 目录放进 `~/.codex/skills/`；设置了 `CODEX_HOME` 时使用其下的 `skills/`。

如果下载的是整个仓库源码，请把仓库文件夹命名为 `mesh-split-fill`，或在仓库目录运行 `python scripts/install.py`。

新会话中调用：

```text
使用 $mesh-split-fill 处理这个模型，先固定完整拆件清单、接缝策略和过程图方案，再验证样件并批量执行。
```

## 条件与验证

- Python 3.10+；基础工具只用标准库。
- Blender 4.2+ 为接口兼容目标；基础几何处理不依赖独显。
- Windows 11、Python 3.12.9、Blender 5.2.1 已实测；macOS 路径逻辑有测试，尚未真机验证。
- 24 项测试通过；独立非角色壳体示例完成拆分、共享接口封口、Blender 重读和两步真实过程页。

```text
python scripts/runtime.py doctor
python -m unittest discover -s tests -v
```

设置 `BLENDER_TEST_PATH` 可执行 Blender 集成测试，否则相关测试跳过。

## 能力边界

这是代理执行的工作流与基础工具包，不是对任意模型保证一键成功的自动分割或补洞应用。复杂语义标签、曲面补片构造、拼接和严格相交检查需要任务适配器。内置检查器只做拓扑预检；没有执行的检查明确标记为 `not_checked`，不能据此宣称几何无自交或严格 G2 连续。

过程页工具输出自包含 HTML；PNG/PDF 需要另行渲染和视觉核查。

## 文档

- [技能入口](SKILL.md)
- [Windows / macOS 部署](references/deployment.md)
- [清单、冻结、候选与过程图](references/workflow.md)
- [几何方法与验收边界](references/geometry.md)

本仓库不包含用户原模型、私人任务日志或设备专用二进制依赖。
