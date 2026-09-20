# 火山训练任务提交 Skill

适用于 Codex 的火山机器学习平台任务提交技能，支持正式训练和自动退出的 CUDA smoke 测试。包含 GalaxeaFM worktree 启动约定、认证配置、挂载预检、一次提交保护和失败后的只读恢复。

## 安装

需要 Python 3.10+、PyYAML 和已安装的火山 CLI（`volc` 或支持相同子命令的 `mlp`）。在本仓库根目录执行：

```bash
mkdir -p ~/.codex/skills
cp -R skills/submit-volc-training-task ~/.codex/skills/
```

已有同名 skill 时先备份，再合并或替换；不要直接覆盖本地自定义内容。新开 Codex 会话后使用 `$submit-volc-training-task`。

## 本机认证

优先使用已有 CLI 配置，或运行 `volc configure`。如果其 IAM 校验报 `iam:ListAccessKeys` 权限不足，可在自己的终端执行：

```bash
python3 ~/.codex/skills/submit-volc-training-task/scripts/configure_local_credentials.py --region cn-beijing
```

AK/SK 隐藏输入并保存到本机 `~/.volc/credentials`，文件权限为 0600。不要把密钥粘贴到对话或提交到仓库。此脚本只保存配置，后续仍须通过任务/队列只读查询验证权限；不授予或绕过平台权限。区域按实际任务修改。

## 使用示例

```text
使用 $submit-volc-training-task，为当前 worktree 向指定队列提交一个
单卡 CUDA smoke 测试，检查代码导入和独立输出写入，并查询最终状态。
```

正式训练需给出任务配置、目标队列及必要的镜像/挂载来源，先完成项目要求的数据和短训练验收。技能中的绝对路径、队列 ID 和历史任务仅是本次 GalaxeaFM 适配的实例；换环境后重新核实，不能直接照搬。smoke 成功不等于完整训练验收。

- [技能入口](../skills/submit-volc-training-task/SKILL.md)
- [预检、一次提交与恢复](../skills/submit-volc-training-task/references/safe-submission.md)
- [Worktree 约定与实测兼容问题](../skills/submit-volc-training-task/references/galaxea-worktree.md)

## 本地检查

```bash
python3 -m unittest discover -s skills/submit-volc-training-task/tests -v
```

测试使用 fake CLI，不创建真实云任务。发布版本不包含本机认证、任务私有配置、运行日志和 Python 缓存。
