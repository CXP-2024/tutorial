# Codex 切换供应商后恢复本地历史记录

这份教程记录一次实际排查：Codex 切换模型供应商之后，GUI 和 CLI 里的历史记录突然像是消失了，但本地文件其实还在。最终原因是历史元数据里的 `model_provider` 和当前配置里的 provider 名不一致，Codex 在列历史时按 provider 做了过滤。

这里以把历史统一迁回自定义 provider `OpenAI` 为例。`OpenAI` 是自定义名字，和 Codex 内置保留 provider `openai` 不是同一个东西。

## 现象

切换供应商或中转地址后，可能出现这些情况：

- Codex GUI 里只剩项目/文件夹，看不到旧 thread。
- `codex resume --all` 只显示很少几条记录。
- `~/.codex/sessions` 里的 JSONL 文件还在。
- `~/.codex/state_5.sqlite` 里的 thread 记录也还在。
- `codex doctor` 可能提示 rollout 文件和 DB 数量正常，但当前 provider 下看不到旧历史。

核心判断：如果本地 rollout 文件和 SQLite 索引都还在，历史大概率没有丢，只是被 provider 元数据过滤了。

## 关键背景

Codex 历史至少涉及两类本地数据：

- `~/.codex/sessions` 和 `~/.codex/archived_sessions`：每条会话的 rollout JSONL 文件。
- `~/.codex/state_5.sqlite`：线程索引库，其中 `threads.model_provider` 会记录 provider 名。

rollout JSONL 的第一行通常也有 `session_meta`，里面会有类似字段：

```json
"model_provider":"openai"
```

如果当前 `~/.codex/config.toml` 使用的是：

```toml
model_provider = "OpenAI"
```

但旧历史文件和 SQLite 里写的是：

```text
openai
```

那么 Codex 可能只列出当前 provider 对应的历史，旧记录看起来就像消失了。

还要注意：小写 `openai` 是 Codex 内置保留 provider ID。不要写下面这种配置：

```toml
[model_providers.openai]
```

新版 Codex 会报错，因为内置 provider 不能被自定义覆盖。

## 推荐配置：使用大写 OpenAI 作为自定义 provider

如果你的中转站或第三方服务兼容 OpenAI Responses API，可以用自定义 provider 名，例如 `OpenAI`：

```toml
model_provider = "OpenAI"
model = "gpt-5.5"
review_model = "gpt-5.5"

[model_providers.OpenAI]
name = "OpenAI"
base_url = "https://YOUR_COMPATIBLE_RESPONSES_BASE_URL"
wire_api = "responses"
requires_openai_auth = true
```

不要在教程、GitHub 或公开仓库里提交真实 API key。`base_url` 如果是私人中转地址，也建议用占位符或内部文档保存。

## 1. 先做只读检查

先确认当前配置：

```bash
sed -n '1,40p' ~/.codex/config.toml
```

检查 SQLite 里每个 provider 有多少 thread：

```bash
sqlite3 ~/.codex/state_5.sqlite \
  "select model_provider, count(*) from threads group by model_provider order by count(*) desc;"
```

检查 rollout JSONL 里还有多少小写 `openai`：

```bash
rg -l '"model_provider":"openai"' ~/.codex/sessions ~/.codex/archived_sessions | wc -l
```

检查大写 `OpenAI`：

```bash
rg -l '"model_provider":"OpenAI"' ~/.codex/sessions ~/.codex/archived_sessions | wc -l
```

如果你看到 SQLite 里大部分是 `openai`，但当前配置是 `OpenAI`，这就是典型的不一致。

## 2. 备份配置、SQLite 和 rollout 文件

先准备备份目录：

```bash
mkdir -p ~/codex-provider-restore-backup
```

备份配置和 SQLite：

```bash
cp ~/.codex/config.toml ~/codex-provider-restore-backup/config.toml.before
cp ~/.codex/state_5.sqlite ~/codex-provider-restore-backup/state_5.sqlite.before
```

生成需要迁移的 rollout 文件清单：

```bash
rg -l '"model_provider":"openai"' ~/.codex/sessions ~/.codex/archived_sessions \
  > ~/codex-provider-restore-backup/files.txt
```

打包备份这些 JSONL：

```bash
tar -czf ~/codex-provider-restore-backup/rollouts-openai-before.tgz \
  -T ~/codex-provider-restore-backup/files.txt
```

这一步很重要。后续只改元数据字段，但备份能保证可以回滚。

## 3. 把 rollout JSONL 元数据改回 OpenAI

用 `xargs` 读取清单，避免把换行路径直接塞进 shell 命令导致路径被当成命令执行：

```bash
xargs perl -0pi -e 's/"model_provider":"openai"/"model_provider":"OpenAI"/g' \
  < ~/codex-provider-restore-backup/files.txt
```

这条命令只替换 JSONL 里的短字段值，不会修改聊天正文中的自然语言内容。

## 4. 同步 SQLite 线程索引

把 SQLite 里的 `threads.model_provider` 也统一成 `OpenAI`：

```bash
sqlite3 ~/.codex/state_5.sqlite \
  "update threads set model_provider='OpenAI' where model_provider='openai';"
```

然后验证：

```bash
sqlite3 ~/.codex/state_5.sqlite \
  "select model_provider, count(*) from threads group by model_provider order by count(*) desc;"
```

理想结果是所有 thread 都在 `OpenAI` 下。

## 5. 验证 Codex 状态

先看 JSONL 是否还有小写 provider：

```bash
rg -l '"model_provider":"openai"' ~/.codex/sessions ~/.codex/archived_sessions | wc -l
```

结果应该是 `0`。

再看大写 provider：

```bash
rg -l '"model_provider":"OpenAI"' ~/.codex/sessions ~/.codex/archived_sessions | wc -l
```

然后运行：

```bash
codex doctor
```

重点看这些项：

- `state DB ... integrity ok`
- `rollout files and state DB thread inventory agree`
- `default model provider OpenAI`
- `rollout DB model providers OpenAI=<数量>`
- `config.toml parse ok`
- 当前 provider endpoint reachable

最后测试历史列表：

```bash
codex resume --all
```

如果列表重新出现，说明恢复完成。

## 6. 常见问题

### 为什么只改 SQLite 不够

因为 Codex 会扫描 rollout JSONL，并用 JSONL 里的 `session_meta.model_provider` 回填或校验 SQLite。只改 `state_5.sqlite` 可能被旧 JSONL 元数据再次覆盖。

所以要同时改两处：

- rollout JSONL 的 `"model_provider":"openai"`
- SQLite 的 `threads.model_provider`

### 为什么不用小写 openai

小写 `openai` 是 Codex 内置 provider ID。可以使用内置 provider，但不能通过 `[model_providers.openai]` 覆盖它。

如果你要用自定义中转地址，并且当前方案是自定义 provider，就保持一个稳定的名字，例如：

```toml
model_provider = "OpenAI"
```

以后换供应商时尽量只改：

```toml
base_url = "https://NEW_BASE_URL"
```

不要频繁改 `model_provider` 名字。Codex 会把这个名字当作历史归属标签。

### `openai_base_url` 方案为什么可能不适合

有些版本支持：

```toml
model_provider = "openai"
openai_base_url = "https://YOUR_BASE_URL"
```

这个方案理论上能保留内置 `openai` 历史桶。但如果实际使用中发现不稳定、鉴权不匹配、或和你的中转站不兼容，就回到自定义 provider `OpenAI` 更直接。

本教程记录的是回到大写 `OpenAI` 的恢复方案。

### 如何回滚

如果迁移后需要回滚，可以用备份：

```bash
cp ~/codex-provider-restore-backup/config.toml.before ~/.codex/config.toml
cp ~/codex-provider-restore-backup/state_5.sqlite.before ~/.codex/state_5.sqlite
```

rollout JSONL 可以从 `rollouts-openai-before.tgz` 解包恢复。恢复前建议先关闭正在运行的 Codex GUI/CLI，避免同时写入状态库。

## 最短流程

如果已经确认当前配置使用 `OpenAI`，并且要把所有旧历史也迁回 `OpenAI`：

```bash
mkdir -p ~/codex-provider-restore-backup

cp ~/.codex/config.toml ~/codex-provider-restore-backup/config.toml.before
cp ~/.codex/state_5.sqlite ~/codex-provider-restore-backup/state_5.sqlite.before

rg -l '"model_provider":"openai"' ~/.codex/sessions ~/.codex/archived_sessions \
  > ~/codex-provider-restore-backup/files.txt

tar -czf ~/codex-provider-restore-backup/rollouts-openai-before.tgz \
  -T ~/codex-provider-restore-backup/files.txt

xargs perl -0pi -e 's/"model_provider":"openai"/"model_provider":"OpenAI"/g' \
  < ~/codex-provider-restore-backup/files.txt

sqlite3 ~/.codex/state_5.sqlite \
  "update threads set model_provider='OpenAI' where model_provider='openai';"

codex doctor
codex resume --all
```

这次实际恢复的核心经验就是一句话：历史不是只存在 SQLite 里，rollout JSONL 的 provider 元数据同样会影响 Codex 是否展示旧会话。
