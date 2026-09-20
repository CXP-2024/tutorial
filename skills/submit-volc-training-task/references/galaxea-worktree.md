# GalaxeaFM worktree 与队列短任务

## 本工作区配置

当前适配对象：`/efm-vepfs/group-jt/intern/pcx/galaxea_g05/.worktrees/post-train-implicit-middle-layer-memory`。
实验根：`superpowers/2026-07-22_131100-implicit-middle-layer-memory`。
用户指定测试队列：`research-h20-96g-128`。这是此次目标，不把它强制用于未来不同用户/实验。

实际路径以调用时 Git worktree 和用户指令为准。不要因文件名仍叫 same_host 就假设一定在同一设备上运行。

## 启动环境

1. 在提交机解析 worktree 的绝对路径及主仓路径，核对二者都被作业挂载覆盖。共享worktree的.git通常指向主仓，因此容器里只挂worktree可能无法使用git元数据；训练不依赖git时可预先解析路径并把确定值写入入口。
2. 需要本项目环境时 source 主仓 `startg05.sh`；结束后 cd 回 worktree，重设 PYTHONPATH，并恢复平台原有 CUDA_VISIBLE_DEVICES（原本未设置则 unset）。不要打印整个环境或 source 脚本内容。
3. Python采用经核验的现有解释器；不要临时安装新CUDA/torch来完成提交测试。初始化脚本和虚拟环境也需要挂载。缓存优先写容器临时目录或实验独立目录。
4. 正式训练采用任务YAML，不把模板中的其他任务超参整体覆盖进来；不传GPU数字给finetune.sh。

## 队列 test/smoke

- 只验证任务创建/调度、代码和环境可读、独立输出可写及少量CUDA运算；不把成功视为完整训练可用。
- 优先1 worker × 1 GPU；若队列只支持整机，先从队列/模板核实最小可申请规格，再说明实际资源规模，不能从队列名字猜资源字段。
- 使用唯一平台名，例如 `implicit-memory-test-<UTC时间>`，输出位于实验 `outputs/volc_submission_test_<UTC时间>/run/`。
- 使用 shell `timeout` 给入口设置几分钟硬上限，关闭自动重试，正常结束即释放资源。排队时间不受入口timeout限制。
- 不构造训练YAML、不加载数据或checkpoint；可直接使用审阅过的shell入口及Python检查器。平台配置仍必须来自CLI实际schema与真实镜像/挂载，不能靠占位镜像提交。
- 导出含环境变量的模板只能保存到权限0700私有目录，文件0600；报告只展示脱敏字段。
- 维护工具 command 模式仍要求真实模板source_id、授权记录、依赖清单、输出防碰撞、精确查名与一次提交。真实训练继续默认training模式。

## 认证缺失

先验证CLI具体子命令。若提示 `AccessKeyId or SecretAccessKey is empty`，明确记录“未完成认证，尚未提交”，请求用户提供已有配置路径或在本机配置认证；不要要求在对话粘贴密钥，不把EDP凭据或托管access_token猜作可用AK/SK，也不修改托管token文件。

若 `volc configure` 明确返回 `AccessDenied ... iam:ListAccessKeys`，说明IAM校验请求到达服务但缺少列密钥权限，不等于网络断开，也不能由此断言机器学习平台无权限。检查credentials/config是否保存。用户已有AK/SK时，可由用户在其终端运行 `python3 scripts/configure_local_credentials.py --region <实际区域>` 隐藏输入并保存官方CLI配置格式（0600），不调用无关IAM校验；随后只读查询目标任务/队列检验实际权限。助手不接收聊天中的SK，不自动授予IAM权限。该方式不绕过机器学习平台API授权；若实际资源API拒绝仍按拒绝处理。

## 2026-09-20 实测的 CLI 兼容细节

- `ListResourceQueues` 核实北京 `research-h20-96g-128` 为 `q-20250724211051-sp57k`；未来调用仍需重新核实。资源 API `ListResourceClaimOptions` 返回单卡 `ml.pni3ln.4xlarge`。
- v1.2.55 能导出 `Flavor: custom`，却可能拒绝原样提交，报“不支持完全自定义的资源规格”。短测试改用已查询到的固定规格 `TaskRoleSpecs[].Flavor: ml.pni3ln.4xlarge`，移除自定义 `ResourceSpec` 后成功创建。失败后先完整状态精确查名，再按新的恢复计划提交，不盲目重试。
- 规格目录值不等于实际任务分配：本次目录显示16 CPU/224 GiB，提交后任务详情显示10 vCPU/220 GiB/1 H20；对外报告以任务实际详情为准。
- 主仓 `.venv/bin/python` 指向开发机 `/root/.local/share/uv/python/...`，该目标未必存在于作业镜像。smoke入口优先共享虚拟环境，缺失时使用镜像的python3，并在result.json记录实际解释器和torch版本。此回退不能证明完整训练依赖兼容，正式训练需另验。
- 模板包含多个不相关挂载；本次只保留Vepfs `vepfs-cnbjcf1bae8ce469`，将SubPath收窄到 `group-jt/intern/pcx/galaxea_g05`，对应同名绝对MountPath，覆盖环境、worktree及输出。平台已接受此任务创建，仍需任务实际运行检验读写。

本次任务 `t-20260920155450-hlkzw` 最终Success（2026-09-20 07:55:57 UTC）。共享输出验证单H20 CUDA、worktree模块路径、共享venv torch2.7.1+cu128和写入均通过；未触发解释器回退。仅作为该镜像/挂载组合的smoke证据，不能外推到其他镜像或完整训练。
