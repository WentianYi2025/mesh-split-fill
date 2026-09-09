# 任务契约、缓存与过程图

`init` 生成草稿；编辑 `job.json` 后 `validate` 检查字段，`freeze` 保存不可变的内容寻址快照；`check` 在修改前确认输入和契约没有改变。无需额外确认已授权的工作。每个任务由一位协调者写清单与候选记录；并行代理只写独立部件目录。

```text
python SKILL_DIR/scripts/job.py init --input MODEL --job-dir JOB
python SKILL_DIR/scripts/job.py validate --job-dir JOB
python SKILL_DIR/scripts/job.py freeze --job-dir JOB
python SKILL_DIR/scripts/job.py check --job-dir JOB
```

将 `MODEL`、`JOB`、`SKILL_DIR` 替换为本机真实路径，有空格时加引号。Windows 用 `python`，macOS 通常用 `python3`。

## 填写字段

|字段|含义|
|---|---|
|source.path / sha256|源文件路径（可相对 JOB）和真实 SHA-256，init 自动建立|
|inventory.complete / expected_count / unresolved|完整性结论、目标件数、尚缺的语义决定|
|parts|每件的 id、name、evidence、preserve_openings 列表|
|seams|每缝 id、parts、action、profile、boundary_evidence|
|constraints|preserve_coordinates=true；surface_policy 为 preserve 或 local_transition；units、axis_evidence、relative_tolerance|
|storyboard|enabled、layout（steps/comparison）、output_format（html/png/pdf）、cases|

`evidence` 与 `boundary_evidence` 可指向具体视图、用户要求、检查报告和边界索引。JSON 不会自动识别语义；结构校验通过不代表清单视觉完整。没有接缝允许 `seams=[]`，但所有应处理接缝必须人工/代理核实后登记。

例如新模型里两件外壳的互补接口（名字不是固定要求）：

```json
{
  "parts": [
    {"id":"shell","name":"主壳","evidence":"用户清单及原始背视图","preserve_openings":["散热通道"]},
    {"id":"cover","name":"盖板","evidence":"用户清单及正视图","preserve_openings":[]}
  ],
  "seams": [
    {"id":"cover_joint","parts":["shell","cover"],"action":"complement","profile":"dome","boundary_evidence":"inspection/cover_joint.json：共同边界点序"}
  ]
}
```

action：leave_open/fill/complement；profile：none/planar/dome/strip/curvature。profile 是本次意图和方法分支，**不是内置自动求解器枚举**。同一复杂模型可混用不同方法。几何库的调用见 [geometry.md](geometry.md)。

## 候选与重试

```text
python SKILL_DIR/scripts/job.py record --job-dir JOB --seam cover_joint --strategy recut-band-v1 --outcome fail --seconds 42 --metrics metrics.json --script adapter.py --artifact candidate.npz --note "过渡带存在反折，下一次改变边链配对"
```

`metrics.json` 是实际报告对象，建议包括局部裸边、顶点面扇、退化面、严格相交、切线误差、修改范围与原有瑕疵差异。未知项目用 `not_checked`。`outcome=pass` 只是记录调用者的结论，不由记录器证明质量；有关键未检查项使用 incomplete。默认第二次失败记录保留，第三次相同策略记录拒绝；**执行候选前先读 candidates.json**，不要做完第三次才发现超限。

契约更新生成新快照；新的 hash 不能成为无意义重试的借口。只变更文字、图注时，保留几何验收并用明确子任务输入键追踪复用依据；默认整个契约缓存键变化是保守失效策略。

## 缓存

```text
python SKILL_DIR/scripts/job.py cache-key --job-dir JOB --file input.npz --file adapter.py --file solver_module.py --parameters parameters.json --runtime "Blender 5.2.1; Python 3.12; numpy VERSION; Windows x64"
```

文件按传入顺序计算内容哈希；列出全部依赖，parameters 包含阈值、变换、种子、求解精度与输出格式。返回键只用于索引，**工具不自动管理缓存或决定命中**：检查候选产物仍存在且 SHA-256 匹配、验收覆盖相同修改区、原有瑕疵基线一致，才能复用。换设备默认重做运行时预检和最终重读验证，不能仅复制旧 pass。

## 固定过程图

任务初期指定案例与步骤，例如：

```json
{
  "enabled":true,"layout":"steps","output_format":"html",
  "cases":[{"id":"joint","title":"盖板接口如何生成","part_ids":["shell","cover"],"view":"固定后侧正交视角",
    "steps":["原始洞口","整理共同边界","建立补片","优化过渡带","网格验收","最终表面"]}]
}
```

运行过程中在 JOB 内保存每步真实网格（blend/obj/npz等）和 PNG/JPEG 渲染。在 `evidence.json` 给每个案例/步骤**恰好一条**记录：

```json
{
  "contract_sha256":"从freeze.json复制实际值",
  "items":[{"case_id":"joint","step":1,"image":"snapshots/joint-01.png","mesh":"snapshots/joint-01.npz","caption":"原始洞口存在短边，尚未新增补面"}]
}
```

示例仅展示一条，执行时补齐全部步骤。路径相对 JOB；可附 `image_sha256`、`mesh_sha256` 锁定证据。助手必须核查图像与网格对应，排版程序只验证存在、格式和哈希，不能证明图像语义真实性。

```text
python SKILL_DIR/scripts/storyboard.py --job-dir JOB --evidence JOB/evidence.json --output JOB/process.html
```

输出自包含 HTML（内嵌图片、系统字体、来源和哈希），不需联网。steps 为三列、comparison 为两列，窄屏自动纵排。PNG/PDF 是后续明确的渲染步骤；没有渲染器时说明 HTML 已完成而所需图片格式尚未完成。不要把 HTML 改扩展名假装 PNG。最终输出前检查视图一致、步骤未冒用最终网格、图注符合报告、中文字体、缩放、裁切和左右件布局。
