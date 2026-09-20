# Source this file from ~/.bashrc. Sourcing defines functions only.
# Requires Bash, tmux, and the layout described in README.md.
proxy_on() {
    local proxy_dir="$HOME/proxy-test" i ready=0
    if ! (exec 3<>/dev/tcp/127.0.0.1/7890) 2>/dev/null; then
        if ! tmux has-session -t proxy-test 2>/dev/null; then
            test -x "$proxy_dir/bin/mihomo" || { echo 'Install mihomo first.' >&2; return 1; }
            tmux new-session -d -s proxy-test "\"$proxy_dir/bin/mihomo\" -d \"$proxy_dir/mihomo\"" || return
        fi
        for ((i=0; i<30; i++)); do
            if (exec 3<>/dev/tcp/127.0.0.1/7890) 2>/dev/null; then ready=1; break; fi
            sleep 0.1
        done
        if (( ! ready )); then
            echo 'Proxy unavailable; inspect: tmux attach -t proxy-test' >&2
            return 1
        fi
    fi
    export http_proxy=http://127.0.0.1:7890 https_proxy=http://127.0.0.1:7890
    export all_proxy=socks5h://127.0.0.1:7890
    export HTTP_PROXY="$http_proxy" HTTPS_PROXY="$https_proxy" ALL_PROXY="$all_proxy"
    export ws_proxy="$http_proxy" wss_proxy="$http_proxy" WS_PROXY="$http_proxy" WSS_PROXY="$http_proxy"
    export no_proxy=localhost,127.0.0.1,::1 NO_PROXY=localhost,127.0.0.1,::1
    echo 'Proxy ON: 127.0.0.1:7890'
}

proxy_off() {
    unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY
    unset ws_proxy wss_proxy WS_PROXY WSS_PROXY no_proxy NO_PROXY
    echo 'Proxy OFF for this terminal; background mihomo remains running.'
}
