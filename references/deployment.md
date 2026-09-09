# Windows / macOS 部署

## 安装技能

解压发布包，把完整 `mesh-split-fill` 目录放入 Codex 个人技能目录：

- Windows：`%USERPROFILE%\.codex\skills\mesh-split-fill`
- macOS：`~/.codex/skills/mesh-split-fill`
- 如果配置了 `CODEX_HOME`，改用其下的 `skills/mesh-split-fill`。

可直接调用 `python mesh-split-fill/scripts/install.py`（macOS 通常为 `python3`）。默认遇已有技能拒绝覆盖；更新时用 `--replace`，旧目录会保留到技能目录旁的 `skill-backups/`，避免被重复发现。它只安装本技能，不改变模型、权限、MCP 或其它技能。

新会话中使用 `$mesh-split-fill`。当前会话若还未刷新技能目录，可直接请代理读取安装目录的 SKILL.md。

## 运行条件

- 主机 Python 3.10+，基础工具仅用标准库。
- Blender 4.2+ 的 Python 批处理接口；基础工作不需 CUDA、Metal、显卡或商业重拓扑插件。
- 本次 Windows 11 + Python 3.12.9 + Blender 5.2.1 已做小型实际调用；macOS 路径逻辑有单元验证，但尚未在 Mac 真机执行。Blender 4.2 是接口兼容目标，不能视为每个版本都实测通过。
- 大网格需要相应内存，不以固定显存阈值声称能处理任意规模。先读取统计，估计内存，必要时分件/分块。默认最多4线程，可显式修改。

## 检测与调用

```text
python SKILL_DIR/scripts/runtime.py doctor
python SKILL_DIR/scripts/runtime.py doctor --blender "/path/to/blender"
python SKILL_DIR/scripts/runtime.py run --threads 4 --log JOB/inspect.log SKILL_DIR/scripts/blender_inspect.py -- --input MODEL --output JOB/inspection.json
```

候选顺序：显式 `--blender`，`BLENDER_PATH`，PATH，平台常见安装位置。显式路径或环境变量配置错误时返回错误，避免误用另一安装。Windows 查 Blender Foundation/Steam；Mac 查 `/Applications/Blender*.app/Contents/MacOS/Blender` 与用户 Applications。不要求把可执行文件加入系统 PATH。

所有参数通过参数列表传递，路径有空格时在终端加引号；不经 shell 拼接执行。运行于独立后台 Blender，禁用输入工程的自动脚本执行，默认保持现有桌面 Blender 会话不受影响。日志、检查报告使用新文件名，拒绝覆盖已有文件。

内置预检支持 OBJ、BLEND，STL/PLY 依赖对应 importer 是否可用，缺少即明确失败；其它格式先用已验证且保留属性的适配器转换，记录转换误差与丢失属性。OBJ 导入固定 identity 轴向并关闭自动验证；BLEND 保留物体矩阵，不 apply transform。报告读取原始 Mesh 数据，不包含未应用修改器的最终形状，若需要最终外观必须另存 evaluated mesh 并保留来源关系。

## 可选求解依赖

复杂补片可能需要 NumPy、SciPy 或约束三角化库。先查询**实际执行求解的 Python** 中是否存在并记录版本。宿主 Python 的包不等于 Blender Python 的包；不得把 Windows `.pyd` 复制到 Mac，也不能混用 Intel/Apple Silicon 的二进制。优先在独立虚拟环境中求解，通过 NPZ/JSON 与 Blender 交换，或选已安装的 Blender 原生方法。

只有任务确实需要时才安装对应平台依赖；不要启动时一律安装大依赖、不修改共享 ComfyUI 环境、不下载不明 vendor 二进制。缺依赖时可继续检查和清单设计，但不得把缺少的求解或验收标记为完成。

## 便携性与验收

源文件路径与程序位置分开；任务资源优先相对 JOB，路径变化后更新 source.path、重新冻结并重读验证。字体使用系统字体回退，不硬编码 Windows 字体。渲染视角和爆炸位移由模型包围盒、真实前向及用户视图推导，不能固定角色坐标。

在新设备上先运行 doctor，再运行小模型预检与测试：

```text
python -m unittest discover -s SKILL_DIR/tests -v
```

设置 `BLENDER_TEST_PATH` 指向可执行文件可运行 Blender 集成测试。测试不会处理用户大模型；纯Python测试不需要Blender。每次报告准确列明哪些真机已测、哪些仅路径模拟、哪些跳过。

API参考：[Blender命令行](https://docs.blender.org/manual/en/latest/advanced/command_line/arguments.html)、[WM导入与保存](https://docs.blender.org/api/current/bpy.ops.wm.html)、[BMesh](https://docs.blender.org/api/current/bmesh.ops.html)。运行时以本机RNA能力检测和小样件结果为准。
