# 在远程 Linux 服务器上使用代理，并通过 tmux 保持后台运行

这份教程说明如何在远程 Linux 服务器上使用 `mihomo` 运行 Clash/Mihomo 订阅，让代理进程跑在远端服务器的 `tmux` 中。这样即使本地 SSH 断开，远端服务器上的代理仍然继续运行，远端的 tmux 终端、训练任务或命令行工具仍可以访问代理。

## 目标架构

```text
远端服务器上的命令 / 程序
  -> 127.0.0.1:7890
  -> mihomo
  -> 订阅里的代理节点
  -> 目标网站
```

这种方式不会默认接管整台服务器的所有网络流量。只有显式设置了 `http_proxy`、`https_proxy`、`all_proxy` 的 shell 或程序才会走代理，因此比透明代理/TUN 模式更适合远程服务器，不容易影响 SSH 连接。

## 1. 准备目录

```bash
mkdir -p ~/proxy-test/bin ~/proxy-test/mihomo
cd ~/proxy-test
```

## 2. 下载 mihomo

先确认服务器架构：

```bash
uname -m
```

如果输出是 `x86_64`，通常使用 `linux-amd64-v1` 版本：

```bash
curl -fL -o bin/mihomo.gz \
  https://github.com/MetaCubeX/mihomo/releases/download/v1.19.25/mihomo-linux-amd64-v1-v1.19.25.gz

gzip -d bin/mihomo.gz
chmod +x bin/mihomo
```

检查是否可运行：

```bash
./bin/mihomo -v
```

如果服务器是 `aarch64` 或 `arm64`，需要到 mihomo Releases 页面选择对应的 Linux ARM64 包：

```text
https://github.com/MetaCubeX/mihomo/releases
```

## 3. 下载订阅配置

把下面的 `YOUR_SUBSCRIPTION_URL` 替换成你的 Clash/Mihomo 订阅链接：

```bash
curl -fL -A clash-verge -o mihomo/subscription.yaml 'YOUR_SUBSCRIPTION_URL'
chmod 600 mihomo/subscription.yaml
cp mihomo/subscription.yaml mihomo/config.yaml
```

不要把订阅链接提交到 GitHub、发到公开聊天或写进公开文档。订阅链接通常等同于账号凭证。

## 4. 收紧监听地址

编辑 `mihomo/config.yaml`：

```bash
nano mihomo/config.yaml
```

确保前面几项类似下面这样：

```yaml
mixed-port: 7890
allow-lan: false
bind-address: 127.0.0.1
external-controller: '127.0.0.1:9090'
```

如果原配置里有下面这种设置：

```yaml
allow-lan: true
bind-address: '*'
```

建议改成：

```yaml
allow-lan: false
bind-address: 127.0.0.1
```

这样代理端口只会监听服务器本机，不会暴露给外部网络。

可选：让节点选择持久化，在配置里加入：

```yaml
profile:
    store-selected: true
```

## 5. 准备 Country.mmdb

有些配置第一次启动时会卡在下载地理数据库。可以提前下载：

```bash
curl -fL -o mihomo/Country.mmdb \
  https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/country.mmdb
```

## 6. 在 tmux 中启动代理

```bash
tmux new-session -d -s proxy-test "$HOME/proxy-test/bin/mihomo -d $HOME/proxy-test/mihomo"
```

查看日志：

```bash
tmux attach -t proxy-test
```

从 tmux 里退出但保持代理继续运行：

```text
Ctrl-b d
```

确认 tmux 会话仍在：

```bash
tmux list-sessions
```

看到 `proxy-test` 就说明代理进程还在后台运行。

## 7. 在新终端中使用代理

不需要再次启动 `mihomo`。在每个需要走代理的新 shell 中执行：

```bash
export http_proxy=http://127.0.0.1:7890
export https_proxy=http://127.0.0.1:7890
export all_proxy=socks5://127.0.0.1:7890
```

测试出口 IP：

```bash
curl https://api.ipify.org
```

也可以只让单条命令强制走代理：

```bash
curl -x http://127.0.0.1:7890 https://api.ipify.org
```

## 8. 切换节点

很多订阅配置会有一个主代理组，例如 `BoostNet`、`Proxy`、`GLOBAL` 等。需要先查看有哪些组：

```bash
curl -s http://127.0.0.1:9090/proxies
```

查看某个代理组当前选择：

```bash
curl -s http://127.0.0.1:9090/proxies/BoostNet
```

切换到某个节点，例如美国节点：

```bash
curl -s -X PUT http://127.0.0.1:9090/proxies/BoostNet \
  -H 'Content-Type: application/json' \
  --data '{"name":"🇺🇸 美国US1"}'
```

如果你的代理组名称不是 `BoostNet`，把命令里的 `BoostNet` 换成实际名称。如果节点名称不同，把 `🇺🇸 美国US1` 换成实际节点名。

验证出口国家：

```bash
curl -x http://127.0.0.1:7890 https://ipinfo.io/country
```

## 9. 停止代理

```bash
tmux kill-session -t proxy-test
```

## 10. 更新订阅

如果之后更换订阅链接或需要刷新节点：

```bash
cd ~/proxy-test
curl -fL -A clash-verge -o mihomo/subscription.yaml 'NEW_SUBSCRIPTION_URL'
chmod 600 mihomo/subscription.yaml
cp mihomo/subscription.yaml mihomo/config.yaml
```

重新检查并收紧监听地址：

```yaml
allow-lan: false
bind-address: 127.0.0.1
```

然后重启 tmux 中的代理：

```bash
tmux kill-session -t proxy-test
tmux new-session -d -s proxy-test "$HOME/proxy-test/bin/mihomo -d $HOME/proxy-test/mihomo"
```

## 11. 常见问题

### 新终端无法走代理

新终端需要重新设置环境变量：

```bash
export http_proxy=http://127.0.0.1:7890
export https_proxy=http://127.0.0.1:7890
export all_proxy=socks5://127.0.0.1:7890
```

### `curl -x http://127.0.0.1:7890 ...` 连接失败

先确认代理进程还在：

```bash
tmux list-sessions
```

查看日志：

```bash
tmux attach -t proxy-test
```

如果没有 `proxy-test`，重新启动：

```bash
tmux new-session -d -s proxy-test "$HOME/proxy-test/bin/mihomo -d $HOME/proxy-test/mihomo"
```

### SSH 断开后代理是否还会继续运行

会。只要 `mihomo` 运行在远端服务器的 tmux 会话里，SSH 断开不会杀掉这个 tmux 会话。服务器重启、tmux 会话被 kill、或进程崩溃时才需要重新启动。

### 是否应该开启 TUN 或透明代理

远程服务器上不建议一开始就开启 TUN、iptables、nftables 或透明代理。先使用 `127.0.0.1:7890` 加环境变量的方式，风险更低，也更容易排查问题。

## 12. 安全建议

- 不要公开订阅链接。
- 不要把 `config.yaml` 提交到公开仓库，因为里面可能包含节点密码。
- 服务器上优先监听 `127.0.0.1`，不要监听 `0.0.0.0` 或 `*`。
- 不要随便开启 `allow-lan: true`。
- 远程服务器优先使用显式代理环境变量，不要一开始改系统路由。

