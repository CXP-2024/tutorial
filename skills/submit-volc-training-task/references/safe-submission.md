# 维护工具：预检、一次提交与只读恢复

入口是 `scripts/training_submit.py`，依赖 Python 3.10+ 和 PyYAML。它使用已安装的 CLI；不安装 SDK，不创建凭据，不修改平台权限、挂载或训练配置。脚本不设置任务来源、队列、GPU 数量或训练超参的默认值，继续采用用户选择和来源任务的实际配置。

## 在数据处理中提前检查

用户已要求后续训练时，可先执行以下只读查询，无须等最终数据配置生成：

```bash
python scripts/training_submit.py inspect-source \
  --source-id "$SOURCE_ID" --region "$REGION" \
  --record "$RECORD_DIR/source-access.json"
```

可用 `--cli /absolute/path/to/executable` 指定实际入口。自动发现按 `volc`、`mlp` 及 `volc` 同目录的 `mlp` 检查；逐一核验 `ml_task submit/list/get --help` 的必要参数，顶层帮助不能冒充子命令可用。查询返回必须包含指定来源 ID。结果明确标记 `create_permission_verified=false`。

认证依次使用已有完整 `VOLC_ACCESS_KEY_ID/VOLC_SECRET_ACCESS_KEY`、已有 `TOS_AK/TOS_SK`，否则让 CLI 使用自己的既有配置，并将其来源记为未检查。显式传入 `--credential-script PATH` 时，才允许在环境缺少上述成对凭据后读取该文件中的 `TOS_AK/TOS_SK` 字面量赋值；不执行脚本，不解析命令替换。环境认证需要的临时 INI 仅含地域，退出即清理。调用者身份保持 `unknown`，这些来源说明不能证明账号是本机用户名、开发机所有者或模板创建人。

## 离线预检

先按主 SKILL 完成来源导出、资源核对和三个训练字段的精确替换。保留私有目录中的真实配置，权限设为 `0600`；脱敏导出只能用于展示，不能用于提交。维护工具提交配置的字节保持不变，并用临时私有副本避免提交时配置被改写。

把当前对话已有的真实授权记为 JSON，不再向已授权的用户重复询问：

```json
{
  "actor": "user",
  "authorized": true,
  "source_id": "t-selected-source",
  "task_name": "chosen-platform-name",
  "basis": "记录用户实际提出的创建请求及其上下文，不填凭据。"
}
```

根据真实启动脚本、最终任务配置和模型路径整理依赖清单。它是检查输入，不能用虚构的路径清单替代依赖分析。`access` 是所需读写模式；`minimum_mount_scope=true` 只用于已经核实最小必要挂载范围的情况。

```json
{
  "minimum_mount_scope": true,
  "dependencies": [
    {"role": "code", "path": "/workspace/project", "access": "read"},
    {"role": "data", "path": "/datasets/selected", "access": "read"},
    {"role": "model", "path": "/models/checkpoint", "access": "read"},
    {"role": "output", "path": "/results/new-run", "access": "write"},
    {"role": "cache", "path": "/tmp/training-cache", "access": "write", "storage": "container_local"}
  ]
}
```

清单逐项匹配最深层 `MountPath`，检查本机当前可读性或可写父目录，标出未使用的模板挂载，拒绝只读挂载上的写入需求。声称 `minimum_mount_scope=true` 时不能仍含未使用挂载；未声称最小范围时保留用户选择并报告多余项，不自动裁剪。容器本地依赖须明确标注。检查结果不证明未来任务 UID 的访问权限，也不证明平台用户、用户组或队列的挂载授权。切换代码只读前，另查启动过程和缓存是否写代码目录；必要的缓存调整应显式记录，并在环境初始化之后生效。需要 `ReadOnly` 时核验当前 CLI/API 支持，配置值使用布尔值，不盲加可能被忽略的字段。

```bash
python scripts/training_submit.py preflight \
  --config "$PRIVATE_CONFIG" --authorization "$AUTHORIZATION_JSON" \
  --requirements "$DEPENDENCIES_JSON" --source-id "$SOURCE_ID" \
  --name "$PLATFORM_NAME" --task "$HYDRA_TASK" --region "$REGION" \
  --priority "$VERIFIED_PRIORITY" --output-path "$NEW_OUTPUT_PATH" \
  --journal "$PRIVATE_JOURNAL" --record "$RECORD_DIR/plan.json"
```

`--exp-name`、`--card` 缺省使用 Hydra task 的最后一段；它们只用于核验已经准备的命令，不重写输入。优先级从来源详情和用户选择取得，CLI 导出缺失时显式提供；省略参数不会被工具擅自补成某个固定档位。`--statuses` 缺省为当前 legacy CLI 的八种状态；CLI/API 状态集合发生变化时按实际完整集合更新参数。

预检不调用任务 API，记录工具、CLI、配置、授权及依赖清单的内容摘要。它不能代替数据完整性、归一化统计或真实样本验收。原始配置含敏感内容，放在私有临时目录；展示和日志使用预检记录，不展示配置全文。

## 一次提交

```bash
python scripts/training_submit.py submit \
  --plan "$RECORD_DIR/plan.json" --intent "$PRIVATE_JOURNAL/attempt-001.json"
```

同一任务名必须始终使用同一个私有 journal，建议同一工作区共用该目录。工具按地域和任务名保存持久 claim，并用文件锁阻止本工具的并发创建；每次 intent 用 `O_EXCL` 新建，旧记录不覆盖。这不能约束绕开工具、使用另一 journal 或其他客户端发出的请求。

提交前重新核对计划输入、完整状态分页精确查名和输出路径不存在。只有这些检查通过，才记录一次提交调用并调用 CLI；响应取得新 ID 后立即按该 ID 查询验证。工具原样提交已核验配置，不加 GPU、不改超参、不取消任务，也不自动重试 create。记录中的一次调用是在外部操作前持久化的意图；进程崩溃或启动失败时，不能据此断言平台已经创建。

stdout/stderr 仅在内存中解析。失败保存固定错误码、退出码和有限的脱敏短原因；过滤密钥、配置全文、敏感字段行、URL 与长不透明值，保留受检挂载路径、访问模式和安全 API 错误码。日志中缺少原因应明确说明，不能用猜测补齐。

最小必要挂载仍出现明确 ACL 拒绝时，intent 状态为 `blocked_minimum_mount_acl`。报告当前实例、子目录、访问模式、队列和能确定的认证来源，请用户或管理员修复既有 API 主体的访问权限，或提供正确认证；不自行授权、不反复提交，也不搬运代码来规避 ACL。

## 结果不明与恢复

```bash
python scripts/training_submit.py recover \
  --intent "$PRIVATE_JOURNAL/attempt-001.json" \
  --record "$RECORD_DIR/readonly-recovery-001.json"
```

非零返回、超时、JSON 缺失或验证失败，都先进行只读查询。恢复查询保留原 intent，使用其固定地域、唯一名称和状态集合，分页收集所有精确同名项并检查输出是否出现。即使私有提交 YAML 已清理，也能根据历史计划执行这次只读身份查询；不会重跑训练或改变原状态。

有任务或输出时停止创建，核实该任务；已知 ID 始终保留，不根据一次空列表丢弃。凭据或查询可见范围发生变化时，空列表不证明原请求未创建，需进一步核实，不能据此盲目恢复。

确认未创建且具体问题已修复后，沿用用户已授权范围，使用新计划和独立 intent：预检增加 `--recovery readonly-recovery-001.json --recovery-reason "具体修复及证据"`，再显式调用 `submit`。旧恢复证据只可解析当前 claim，不能反复复用。若此前是最小 ACL 阻断，还必须有用户提供的外部修复依据：在新的授权记录写 `access_restored=true` 和 `access_restored_basis`；这两个字段记录真实信息，不能由助手为了通过检查自行填为真。

`submitted_and_get_verified` 仅表示平台任务存在。继续按主 SKILL 监控平台状态；平台 Running 与日志中实际训练 step 分别报告。

## 本地验证

```bash
python -m unittest discover -s tests -v
python scripts/training_submit.py --help
```

测试只启动临时 fake CLI，覆盖未创建失败的恢复、已创建但响应丢失、分页后的同名任务、同名并发锁、配置与输出碰撞、ACL 停止及密钥抑制；不使用实际平台或真实凭据。

## 非训练短任务入口

提交工作区/环境smoke时，预检加 `--workload command --entrypoint-file /private/reviewed-entrypoint.txt`，不传 `--task`。入口文件必须与配置 `Entrypoint` 精确一致（忽略首尾空白），并被计划内容摘要固定；后续修改会阻止提交。其余授权、source-id、依赖、输出、journal、查名和恢复机制不变。默认training模式仍核对三个训练字段；不能用command模式绕过正式训练验收。
