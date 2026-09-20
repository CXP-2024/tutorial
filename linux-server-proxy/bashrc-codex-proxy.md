# Bash 按需开启代理，Codex 默认使用代理

先完成[主教程](README.md)中的 Mihomo 安装和配置。本文使用 `~/proxy-test/bin/mihomo`、`~/proxy-test/mihomo/config.yaml`、tmux 会话 `proxy-test` 和本机端口 `7890`。配置应包含 `mixed-port: 7890`、`allow-lan: false`、`bind-address: 127.0.0.1`。

普通终端通过 `proxy_on` / `proxy_off` 切换；Codex 单独从 `~/.codex/.env` 读取代理配置。此方式已在 Linux Codex CLI 0.154.0 上验证，更新到 0.155.1 后配置仍保留。

## 1. 关闭自动加载环境和代理

先备份，再编辑自己的 `.bashrc`：

```bash
cp -p ~/.bashrc ~/.bashrc.backup-$(date +%Y%m%d-%H%M%S)
nano ~/.bashrc
```

注释不再需要的自动激活语句，例如 `source /path/to/venv/bin/activate`、`conda activate ...`、`source ~/proxy-test/env.sh`，以及顶层的 `export http_proxy=...`、`https_proxy`、`all_proxy` 等大小写代理变量。

如果希望完全关闭 Conda 的自动初始化，注释 `# >>> conda initialize >>>` 到 `# <<< conda initialize <<<` 的整个区块；只注释其中一部分可能破坏 shell 语法。之后需要 Conda 时，手动加载实际安装目录中的 `etc/profile.d/conda.sh`。若只想关闭 base 自动激活，可保留初始化区块并执行 `conda config --set auto_activate_base false`。

按用途处理 source 语句，不要一并删除 NVM、补全或平台所需的初始化。若 tmux 使用自定义 rc 文件，也需移除其中自动加载代理环境的语句。

## 2. 安装终端开关

在本仓库根目录执行：

```bash
mkdir -p ~/proxy-test
cp linux-server-proxy/proxy-functions.sh ~/proxy-test/functions.sh
```

在 `.bashrc` 末尾添加一次：

```bash
source "$HOME/proxy-test/functions.sh"
```

这一行只定义函数，不会开启代理或激活 Python 环境。检查并加载：

```bash
bash -n ~/.bashrc
source ~/.bashrc
proxy_off
proxy_on
curl --max-time 20 https://ipinfo.io/json
proxy_off
```

`proxy_on` 检查本机端口；未监听时尝试在 tmux 中启动 Mihomo，然后设置当前终端代理。端口已被其他程序占用时，应先用 `ss -lntp | grep ':7890'` 检查；端口可连接不等于代理可用。

`proxy_off` 清除当前终端的代理变量，不停止后台代理，不改变其他终端或已经运行的进程。国内流量是否直连由 Mihomo 的规则决定。

旧终端继承的环境不会因编辑 `.bashrc` 自动消失，应执行 `proxy_off`。若曾用 `tmux set-environment` 保存代理，还需清除对应的全局及会话环境，例如：

```bash
for name in http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY ws_proxy wss_proxy WS_PROXY WSS_PROXY no_proxy NO_PROXY; do
    tmux set-environment -gu "$name"
    tmux set-environment -u -t work "$name"
done
```

将 `work` 换成实际会话名。已打开的 pane 仍需自行执行 `proxy_off`。

## 3. Codex 独立的默认代理

先启动后台代理：

```bash
proxy_on
mkdir -p ~/.codex
```

把 [codex.env.example](codex.env.example) 中的变量合并到 `~/.codex/.env`。已有文件先备份，更新同名变量，保留其他配置；不要直接覆盖已有文件，也不要把这个实际 `.env` 提交到仓库。

```bash
chmod 600 ~/.codex/.env
proxy_off
codex
```

Codex 启动时加载这份配置，因此不必在普通终端一直开启代理。已经运行的 Codex 要退出后重启。若自定义了 `CODEX_HOME`，请使用该目录中的 `.env`；启动前也应清除继承的旧代理变量，避免优先级冲突。

`.env` 只配置连接方式，不会自动启动 Mihomo。SSH 断开后 tmux 继续运行；服务器重启后先执行一次 `proxy_on`。不要在 `.bashrc` 中自动 source Codex 的 `.env`，否则又会给普通终端全局启用代理。

## 4. 验证

```bash
proxy_on
curl --max-time 20 https://api.ipify.org
curl --max-time 20 https://ipinfo.io/json
proxy_off
codex --version
codex debug models > /tmp/codex-models.json
tmux capture-pane -pt proxy-test -S -30
```

核对 IP 查询中的 `city`、`region`、`country` 是否符合节点地区；洛杉矶节点应显示 `Los Angeles`、`California`、`US`，但地理数据库可能存在偏差。模型目录命令可能使用缓存，应结合代理日志中的新连接判断 Codex 是否经过代理。

若报 `HTTP 401` / `token_revoked`，表示登录凭证被撤销，并非代理端口不通。退出 Codex 后运行 `codex logout`、`codex login --device-auth`，按终端提示完成浏览器授权后重启。
