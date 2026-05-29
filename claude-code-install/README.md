# Claude Code 安装教程

这份教程记录 Claude Code 在 macOS/Linux、Windows 上的安装方式，并补充代理、远端服务器和 Codex CLI 的常用配置。命令以官方推荐的原生安装器为主；如果你更习惯 npm，也可以使用 npm 方案。

## 适用环境

- macOS 13.0+
- Ubuntu 20.04+、Debian 10+、Alpine Linux 3.19+，或其他常见 Linux 发行版
- Windows 10 1809+ / Windows 11
- 终端：Bash、Zsh、PowerShell 或 CMD
- 网络：首次登录和日常使用都需要能访问 Claude 服务

如果使用 npm 安装，需要 Node.js 18+。建议用 `nvm`、`fnm` 或系统包管理器安装 Node.js，不要用 `sudo npm install -g` 安装 Claude Code。

## macOS / Linux / WSL 安装

### 方式一：官方原生安装器

这是最省事的方式，适合 macOS、Linux 和 Windows WSL。

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

安装完成后重新打开终端，或按安装脚本提示把 `~/.local/bin` 加入 `PATH`。然后验证：

```bash
claude --version
claude
```

第一次运行 `claude` 会打开登录流程。按提示使用 Claude 账号、Console 账号，或组织配置的认证方式登录即可。

### 方式二：Homebrew

macOS 用户也可以用 Homebrew：

```bash
brew install --cask claude-code
```

Homebrew 安装不会自动更新，之后可以手动升级：

```bash
brew upgrade claude-code
```

### 方式三：npm

如果已经有 Node.js 18+：

```bash
npm install -g @anthropic-ai/claude-code
claude --version
claude
```

之后升级到最新版：

```bash
npm install -g @anthropic-ai/claude-code@latest
```

不要使用 `sudo npm install -g`。如果遇到全局 npm 权限问题，优先改用 `nvm` 或 `fnm` 重新安装 Node.js。

## Windows 安装

Windows 可以选择原生安装，也可以选择 WSL。简单说：

- 项目和工具链都在 Windows 里：用原生 Windows。
- 项目和工具链在 Linux 环境里，或者希望使用 Linux 沙箱：用 WSL2。

### 方式一：Windows 原生安装

在 PowerShell 中运行：

```powershell
irm https://claude.ai/install.ps1 | iex
```

也可以用 WinGet：

```powershell
winget install Anthropic.ClaudeCode
```

安装完成后重新打开 PowerShell、CMD 或 Windows Terminal：

```powershell
claude --version
claude
```

建议安装 Git for Windows。安装后 Claude Code 可以使用 Git Bash 执行 Bash 类命令；如果没有 Git for Windows，Claude Code 会使用 PowerShell 工具。

WinGet 安装不会自动更新，可以定期执行：

```powershell
winget upgrade Anthropic.ClaudeCode
```

### 方式二：WSL2 安装

如果还没有 WSL，可以在管理员 PowerShell 中安装：

```powershell
wsl --install
```

进入 WSL 后，在 Linux shell 里安装 Claude Code：

```bash
curl -fsSL https://claude.ai/install.sh | bash
claude --version
claude
```

WSL 项目建议放在 Linux 文件系统里，例如 `~/code/my-project`，不要长期放在 `/mnt/c/...`，否则文件 IO 和权限行为更容易变慢或变复杂。

## 可选：配置本机代理

如果你的网络需要代理，可以准备一个 `~/proxy.sh`：

```bash
proxy_on() {
    export http_proxy="http://127.0.0.1:7891"
    export https_proxy="http://127.0.0.1:7891"
    export all_proxy="socks5://127.0.0.1:7891"
    export HTTP_PROXY="$http_proxy"
    export HTTPS_PROXY="$https_proxy"
    export ALL_PROXY="$all_proxy"
    export no_proxy="localhost,127.0.0.1,::1"
    export NO_PROXY="$no_proxy"
    echo "Proxy enabled on 127.0.0.1:7891"
}

proxy_off() {
    unset http_proxy https_proxy all_proxy
    unset HTTP_PROXY HTTPS_PROXY ALL_PROXY
    unset no_proxy NO_PROXY
    echo "Proxy disabled"
}

proxy_on
```

在 `~/.zshrc` 或 `~/.bashrc` 中加载：

```bash
[ -f "$HOME/proxy.sh" ] && source "$HOME/proxy.sh"
```

让配置生效：

```bash
source ~/.zshrc
```

如果使用 Bash，把最后一条换成：

```bash
source ~/.bashrc
```

## 可选：远端 Linux 服务器安装

如果在远端服务器上使用 Claude Code，而代理在本机，可以通过 SSH `RemoteForward` 把本机代理转发到远端。

编辑本机 `~/.ssh/config`：

```sshconfig
Host my-server
  HostName example.com
  User your-user
  Port 22
  RemoteForward 7891 127.0.0.1:7891
```

连接远端：

```bash
ssh my-server
```

在远端设置代理并安装：

```bash
export http_proxy=http://127.0.0.1:7891
export https_proxy=http://127.0.0.1:7891
export all_proxy=socks5://127.0.0.1:7891

curl -fsSL https://claude.ai/install.sh | bash
claude --version
claude
```

如果远端需要 Node.js，再使用 npm 安装：

```bash
curl -fsSL https://fnm.vercel.app/install | bash
source ~/.bashrc
fnm install 22
fnm use 22

npm install -g @anthropic-ai/claude-code
claude --version
```

如果 SSH 连接时报错：

```text
Warning: remote port forwarding failed for listen port 7891
```

通常说明远端 7891 端口被旧会话占用。可以在远端释放端口后重连：

```bash
fuser -k 7891/tcp
```

也可以在远端 `/etc/ssh/sshd_config` 中加入心跳配置，减少旧会话残留：

```text
ClientAliveInterval 60
ClientAliveCountMax 3
```

然后重启 SSH 服务：

```bash
sudo systemctl restart sshd
```

## 常用命令

| 命令 | 说明 |
| --- | --- |
| `claude` | 启动 Claude Code |
| `claude --version` | 查看版本 |
| `claude doctor` | 检查安装、更新和环境问题 |
| `proxy_on` | 启用代理环境变量 |
| `proxy_off` | 关闭代理环境变量 |

## 顺带：Codex CLI 安装

Codex CLI 是 OpenAI 的本地命令行编码助手，支持 macOS、Linux 和 Windows。

macOS / Linux 推荐使用官方安装器：

```bash
curl -fsSL https://chatgpt.com/codex/install.sh | sh
codex
```

Windows 可以原生运行 Codex，也可以在 WSL2 中运行。如果选择 WSL2，进入 WSL 后执行同样的 Linux 安装命令：

```bash
curl -fsSL https://chatgpt.com/codex/install.sh | sh
codex
```

第一次运行 `codex` 时会提示登录，可以使用 ChatGPT 账号或 API key 完成认证。

## 参考链接

- [Claude Code setup](https://code.claude.com/docs/en/setup)
- [Claude Code Windows setup](https://code.claude.com/docs/en/installation)
- [Codex CLI](https://developers.openai.com/codex/cli)
- [Codex on Windows](https://developers.openai.com/codex/windows)
