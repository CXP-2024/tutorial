# 使用 rclone 上传大文件到 Google Drive，并用 gdown 下载验证

这份教程记录如何在远程 Linux 服务器上把大模型文件上传到 Google Drive，然后生成公开链接，最后用命令行下载并校验。适合上传 checkpoint、数据包、release artifact 这类几百 MB 到数 GB 的文件。

推荐组合：

- 上传：`rclone`
- 公开下载验证：`gdown`
- 代理：优先使用 `socks5h://127.0.0.1:7890`，如果你的代理端口不同，把命令里的端口换成实际端口。

## 目标流程

```text
远程服务器上的文件
  -> rclone
  -> Google Drive
  -> 生成分享链接 / file id
  -> gdown 下载
  -> sha256sum 校验
```

## 1. 安装 rclone

如果有 sudo：

```bash
curl https://rclone.org/install.sh | sudo bash
```

如果没有 sudo，可以安装到用户目录：

```bash
mkdir -p "$HOME/bin" "$HOME/tmp/rclone-install"
cd "$HOME/tmp/rclone-install"

curl -L -o rclone.zip https://downloads.rclone.org/rclone-current-linux-amd64.zip
unzip -q -o rclone.zip
cp rclone-*-linux-amd64/rclone "$HOME/bin/rclone"
chmod +x "$HOME/bin/rclone"

export PATH="$HOME/bin:$PATH"
rclone version
```

如果服务器需要代理，把下载命令前加上代理环境变量：

```bash
export http_proxy=http://127.0.0.1:7890
export https_proxy=http://127.0.0.1:7890
export HTTP_PROXY=$http_proxy
export HTTPS_PROXY=$https_proxy
```

## 2. 创建 Google Drive remote

创建一个名为 `gdrive` 的 remote：

```bash
export PATH="$HOME/bin:$PATH"
rclone config create gdrive drive scope drive
```

如果后续要重新授权：

```bash
rclone config reconnect gdrive:
```

## 3. 远程服务器 OAuth：推荐 SSH tunnel

如果服务器没有浏览器，可以用 SSH tunnel 在本机浏览器完成 Google 授权。

先在服务器上启动授权：

```bash
export PATH="$HOME/bin:$PATH"
rclone config reconnect gdrive:
```

当 rclone 问：

```text
Use web browser to automatically authenticate rclone with remote?
y/n>
```

选择 `y`。它通常会输出类似：

```text
If your browser doesn't open automatically go to the following link:
http://127.0.0.1:53682/auth?state=...
Waiting for code...
```

保持这个服务器终端不要关。

然后在你的本机开一个新终端，建立 SSH tunnel：

```bash
ssh -N -L 53682:127.0.0.1:53682 <你的SSH用户名>@<服务器地址>
```

保持 tunnel 终端不要关，在本机浏览器打开 rclone 输出的链接：

```text
http://127.0.0.1:53682/auth?state=...
```

完成 Google 登录授权后，服务器上的 rclone 会收到 code。如果它问是否配置 Shared Drive：

```text
Configure this as a Shared Drive (Team Drive)?
y/n>
```

个人 Google Drive 选 `n`。

## 4. 上传大文件

假设要上传的文件是：

```text
outputs/model/blockwise_latest.pt
```

先计算 SHA256，后面用于下载校验：

```bash
sha256sum outputs/model/blockwise_latest.pt
```

上传到 Google Drive：

```bash
export PATH="$HOME/bin:$PATH"

rclone copy \
  outputs/model/blockwise_latest.pt \
  gdrive:MyProject/checkpoints/ \
  --progress \
  --drive-chunk-size 256M \
  --transfers 1 \
  --checkers 1
```

说明：

- `--drive-chunk-size 256M`：适合几百 MB 到数 GB 的大文件。
- `--transfers 1`：单文件上传更稳。
- 如果网络中断，可以重新执行同一条命令，rclone 会检查目标文件并继续处理。

## 5. 生成分享链接和文件 ID

生成公开链接：

```bash
rclone link gdrive:MyProject/checkpoints/blockwise_latest.pt
```

输出通常类似：

```text
https://drive.google.com/open?id=FILE_ID
```

其中 `FILE_ID` 就是后续 `gdown` 可以使用的文件 ID。

也可以查看文件信息：

```bash
rclone lsjson gdrive:MyProject/checkpoints/blockwise_latest.pt
```

如果 `rclone link` 没有自动开放权限，需要到 Google Drive 网页里把文件设置成：

```text
Anyone with the link can view
```

否则其他人会下载失败。

## 6. 用 gdown 下载验证

安装 `gdown`：

```bash
pip install gdown
```

直接用文件 ID 下载：

```bash
mkdir -p /tmp/gdrive-download-test

gdown "FILE_ID" \
  -O /tmp/gdrive-download-test/blockwise_latest.pt
```

如果服务器需要代理，推荐使用 SOCKS 代理。假设代理在 `127.0.0.1:7890`：

```bash
gdown --proxy socks5h://127.0.0.1:7890 \
  "FILE_ID" \
  -O /tmp/gdrive-download-test/blockwise_latest.pt
```

如果你的代理端口是 `7891`，把端口换成：

```bash
gdown --proxy socks5h://127.0.0.1:7891 \
  "FILE_ID" \
  -O /tmp/gdrive-download-test/blockwise_latest.pt
```

校验 SHA256：

```bash
sha256sum /tmp/gdrive-download-test/blockwise_latest.pt
```

这个值必须和上传前计算的 SHA256 一致。

## 7. 写进项目 README 的推荐格式

项目 README 里建议写成这样：

```bash
pip install gdown

mkdir -p outputs/model
gdown "FILE_ID" \
  -O outputs/model/blockwise_latest.pt

sha256sum outputs/model/blockwise_latest.pt
```

如果用户在需要代理的服务器上运行：

```bash
gdown --proxy socks5h://127.0.0.1:7890 \
  "FILE_ID" \
  -O outputs/model/blockwise_latest.pt
```

同时在 README 里给出期望 SHA256：

```text
expected_sha256_here
```

这样别人可以确认自己下载到的是同一个文件，而不是下载到了 Google Drive 的 HTML 提示页或损坏的中间文件。

## 8. 常见问题

### gdown 报 SSL EOF

如果使用 HTTP 代理：

```bash
gdown --proxy http://127.0.0.1:7890 "FILE_ID" -O file.pt
```

遇到类似：

```text
SSL: UNEXPECTED_EOF_WHILE_READING
```

可以改用 SOCKS：

```bash
gdown --proxy socks5h://127.0.0.1:7890 "FILE_ID" -O file.pt
```

`socks5h` 会让 DNS 也走代理，通常比 HTTP CONNECT 更稳。

### 下载到的是一个很小的 HTML 文件

这通常说明你没有通过确认页，或者文件权限没有公开。检查：

```bash
file downloaded_file
wc -c downloaded_file
```

如果是 HTML，打开内容通常能看到 Google Drive 的提示页。需要确认：

- Google Drive 文件权限是 `Anyone with the link can view`
- `gdown` 使用的是文件 ID，不是普通网页 URL
- 大文件下载完成后做 SHA256 校验

### rclone 授权时本机没有 rclone

可以用 SSH tunnel 方式，不需要本机安装 rclone。服务器上运行 `rclone config reconnect gdrive:`，本机只负责：

```bash
ssh -N -L 53682:127.0.0.1:53682 <你的SSH用户名>@<服务器地址>
```

然后在本机浏览器打开服务器 rclone 输出的 `127.0.0.1:53682/auth?...` 链接。

### 上传后怎么确认文件在 Drive 上

```bash
rclone lsjson gdrive:MyProject/checkpoints/blockwise_latest.pt
rclone link gdrive:MyProject/checkpoints/blockwise_latest.pt
```

也可以用无登录方式轻量检查确认页：

```bash
curl -L "https://drive.google.com/uc?export=download&id=FILE_ID" | head
```

大文件会出现 Google Drive 的 virus scan warning，这是正常的。真正可靠的验证还是 `gdown` 下载加 SHA256。
