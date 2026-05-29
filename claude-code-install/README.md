# Claude Code 安装教程

这份教程记录 Claude Code 在 macOS/Linux、Windows 上的安装方式，并补充代理、远端服务器和 Codex CLI 的常用配置。

这里更推荐使用 npm 安装 Claude Code：Node.js 环境装好之后，macOS、Linux、WSL 和 Windows 的安装命令基本一致，后续升级、卸载也容易记。

## 适用环境

- macOS 13.0+
- Ubuntu 20.04+、Debian 10+、Alpine Linux 3.19+，或其他常见 Linux 发行版
- Windows 10 1809+ / Windows 11
- 终端：Bash、Zsh、PowerShell 或 CMD
- Node.js 18+
- 网络：首次登录和日常使用都需要能访问 Claude 服务

不要使用 `sudo npm install -g @anthropic-ai/claude-code`。如果 npm 全局安装遇到权限问题，优先用 `nvm`、`fnm` 或系统包管理器重新安装 Node.js。

## macOS 从零开始安装

下面假设是一台新 Mac：没有 Node.js、没有 npm，也没有 Claude Code。

### 1. 打开终端

打开系统自带的 Terminal，或使用 iTerm2。先确认当前 shell：

```bash
echo $SHELL
```

macOS 默认一般是 `zsh`。后面的配置以 `~/.zshrc` 为例。

### 2. 可选：先配置代理

如果你的网络需要代理才能访问 npm、GitHub 或 Claude，可以先准备一个 `~/proxy.sh`。如果网络本身没问题，可以跳过这一节。

先创建文件：

```bash
nano ~/proxy.sh
```

粘贴下面内容，按 `Ctrl-O` 保存，再按 `Enter` 确认文件名，最后按 `Ctrl-X` 退出：

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

让新终端自动加载代理：

```bash
echo '[ -f "$HOME/proxy.sh" ] && source "$HOME/proxy.sh"' >> ~/.zshrc
source ~/.zshrc
```

这里默认本机代理端口是 `7891`。如果你的代理软件使用 `7890` 或其他端口，把上面所有 `7891` 改成实际端口。

### 3. 安装 nvm

推荐用 `nvm` 管理 Node.js，这样不会污染系统目录，也不需要 `sudo` 安装全局 npm 包。

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
```

安装脚本通常会自动把 nvm 配置写入 `~/.zshrc`。先让配置生效：

```bash
source ~/.zshrc
nvm --version
```

如果这里提示 `nvm: command not found`，再手动把 nvm 加入 `~/.zshrc`：

```bash
cat <<'EOF' >> ~/.zshrc

# nvm
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
[ -s "$NVM_DIR/bash_completion" ] && . "$NVM_DIR/bash_completion"
EOF
```

然后重新加载：

```bash
source ~/.zshrc
nvm --version
```

### 4. 安装 Node.js 和 npm

安装 Node.js 22，并设为默认版本：

```bash
nvm install 22
nvm use 22
nvm alias default 22
```

验证：

```bash
node --version
npm --version
```

只要 Node.js 版本大于等于 18 就可以安装 Claude Code。这里使用 22 是为了直接用当前长期维护的大版本。

### 5. 安装 Claude Code

```bash
npm install -g @anthropic-ai/claude-code
```

验证安装：

```bash
claude --version
claude doctor
```

启动 Claude Code：

```bash
claude
```

第一次运行会打开登录流程。按提示使用 Claude 账号、Console 账号，或组织配置的认证方式登录即可。

### 6. 后续升级和卸载

升级到最新版：

```bash
npm install -g @anthropic-ai/claude-code@latest
```

卸载：

```bash
npm uninstall -g @anthropic-ai/claude-code
```

## macOS / Linux / WSL 快速安装

如果你已经有 Node.js 18+ 和 npm，直接安装：

```bash
npm install -g @anthropic-ai/claude-code
claude --version
claude
```

如果还没有 Node.js，可以先用 `nvm`：

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
```

然后把下面内容加入 `~/.zshrc` 或 `~/.bashrc`：

```bash
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
[ -s "$NVM_DIR/bash_completion" ] && . "$NVM_DIR/bash_completion"
```

重新加载 shell 后安装 Node.js 和 Claude Code：

```bash
source ~/.zshrc
nvm install 22
nvm use 22
nvm alias default 22

npm install -g @anthropic-ai/claude-code
claude --version
```

如果你使用 Bash，把 `source ~/.zshrc` 换成：

```bash
source ~/.bashrc
```

## Windows 安装

Windows 可以选择原生安装，也可以选择 WSL2。简单说：

- 项目和工具链都在 Windows 里：用 Windows 原生安装。
- 项目和工具链在 Linux 环境里，或者希望使用 Linux 沙箱：用 WSL2。

### 方式一：Windows 原生 npm 安装

先在 PowerShell 中安装 Node.js LTS：

```powershell
winget install OpenJS.NodeJS.LTS
```

关闭并重新打开 PowerShell，然后验证：

```powershell
node --version
npm --version
```

安装 Claude Code：

```powershell
npm install -g @anthropic-ai/claude-code
```

验证并启动：

```powershell
claude --version
claude doctor
claude
```

建议安装 Git for Windows。安装后 Claude Code 可以使用 Git Bash 执行 Bash 类命令；如果没有 Git for Windows，Claude Code 会使用 PowerShell 工具。

```powershell
winget install Git.Git
```

升级 Claude Code：

```powershell
npm install -g @anthropic-ai/claude-code@latest
```

### 方式二：WSL2 npm 安装

如果还没有 WSL，可以在管理员 PowerShell 中安装：

```powershell
wsl --install
```

进入 WSL：

```powershell
wsl
```

在 WSL 的 Linux shell 里安装 Node.js 和 Claude Code：

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
```

把下面内容加入 WSL 里的 `~/.bashrc`：

```bash
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
[ -s "$NVM_DIR/bash_completion" ] && . "$NVM_DIR/bash_completion"
```

继续执行：

```bash
source ~/.bashrc
nvm install 22
nvm use 22
nvm alias default 22

npm install -g @anthropic-ai/claude-code
claude --version
claude
```

WSL 项目建议放在 Linux 文件系统里，例如 `~/code/my-project`，不要长期放在 `/mnt/c/...`，否则文件 IO 和权限行为更容易变慢或变复杂。

## 可选：官方原生安装器

Claude Code 也提供原生安装器。这个方式也能用，但为了让多平台命令一致，本文主线仍推荐 npm。

macOS / Linux / WSL：

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

Windows PowerShell：

```powershell
irm https://claude.ai/install.ps1 | iex
```

Homebrew：

```bash
brew install --cask claude-code
```

WinGet：

```powershell
winget install Anthropic.ClaudeCode
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

在远端设置代理：

```bash
export http_proxy=http://127.0.0.1:7891
export https_proxy=http://127.0.0.1:7891
export all_proxy=socks5://127.0.0.1:7891
```

安装 Node.js 和 Claude Code：

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
```

把下面内容加入远端的 `~/.bashrc`：

```bash
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
[ -s "$NVM_DIR/bash_completion" ] && . "$NVM_DIR/bash_completion"
```

然后执行：

```bash
source ~/.bashrc
nvm install 22
nvm use 22
nvm alias default 22

npm install -g @anthropic-ai/claude-code
claude --version
claude
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
| `npm install -g @anthropic-ai/claude-code@latest` | 升级 Claude Code |
| `npm uninstall -g @anthropic-ai/claude-code` | 卸载 Claude Code |
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
- [Codex CLI](https://developers.openai.com/codex/cli)
- [Codex on Windows](https://developers.openai.com/codex/windows)
