# 部署指南

面向 Linux（Debian / Ubuntu / CentOS 均可）。Windows 本地调试见最后一节。

## 环境要求

- Python 3.9+（建议 3.11/3.12）
- 内存 ≥ 256 MB（长连接越多占用越高）
- 磁盘 ≥ 1 GB（请求落盘取决于流量；可用 queue.history_limit 控制保留量）
- 反向代理：Nginx（推荐）或 Caddy

## 方式一：直接运行（开发 / 内网）

~~~bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

export PEOAI_HOME="$PWD"
./venv/bin/python peoai_server.py --host 127.0.0.1 --port 5007
~~~

首次启动会生成 data/bootstrap.txt：

~~~text
operator password: xxxxxxxxxxxx
admin token: adm_xxxxxxxx
api key: pk_xxxxxxxx  (name=default, rpm=120)
~~~

打开 http://127.0.0.1:5007/ 登录，修改密码，然后删除该文件。

## 方式二：systemd + Nginx（生产推荐）

### 1. 创建用户与目录

~~~bash
sudo useradd --system --create-home --home-dir /opt/peoai_server \
     --shell /usr/sbin/nologin peoai
sudo rsync -a --exclude '.git' --exclude 'data' --exclude 'config.json' \
     ./ /opt/peoai_server/
sudo chown -R peoai:peoai /opt/peoai_server
~~~

### 2. 安装依赖

~~~bash
sudo -u peoai python3 -m venv /opt/peoai_server/venv
sudo -u peoai /opt/peoai_server/venv/bin/pip install -r /opt/peoai_server/requirements.txt
~~~

### 3. 安装服务

~~~bash
sudo cp /opt/peoai_server/peoai_server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now peoai_server
sudo systemctl status peoai_server
sudo journalctl -u peoai_server -f
~~~

单元默认监听 127.0.0.1:5007，全部写入都在 /opt/peoai_server 内（ProtectSystem=full 保证系统目录只读）。

### 4. Nginx

把 [deploy/peoai.nginx.conf](../deploy/peoai.nginx.conf) 的内容加入站点 server 块：

~~~nginx
location ^~ /peoai/ {
    proxy_pass http://127.0.0.1:5007/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;          # SSE 必须
    proxy_cache off;
    proxy_read_timeout 3600s;     # 人工作答可能很慢
    client_max_body_size 16m;     # 与 security.max_body_bytes 对齐
    gzip off;
}
~~~

~~~bash
sudo nginx -t && sudo systemctl reload nginx
~~~

访问 https://your-domain/peoai/ 。控制台会自动把接口请求发往同源 /peoai 前缀。

### 前端部署在别的域名

控制台默认请求同源的 /peoai。如果页面放在其他域名（前后端不同源），用脚本把服务器地址注入页面：

~~~bash
python scripts/inject_server_host.py api.example.com -o /www/wwwroot/your-site/home/peoai.html
~~~

页面仍是单文件，只是多了一行 window.PEOAI_SERVER_HOST 配置；HTTPS 页面要求后端同样是 HTTPS。
也可以手动在页面主 <script> 之前加一行：

~~~html
<script>window.PEOAI_SERVER_HOST = "api.example.com";</script>
~~~

### 5. HTTPS

~~~bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
~~~

可选：在 config.json 打开 security.hsts = true。

## 端口与防火墙

| 端口 | 用途 |
| --- | --- |
| 5007 | PeoAI HTTP（默认只监听 127.0.0.1） |
| 443 / 80 | Nginx |

如果必须直接暴露 5007：把单元里的 PEOAI_HOST 改为 0.0.0.0，配置防火墙与 TLS 终止，并确保 security.require_api_key = true。

## 反向代理超时与缓冲（最容易踩）

- proxy_buffering off 必须开启，否则 SSE 会被攒在 Nginx 里；
- proxy_read_timeout 要大于客户端最长等待（queue.request_ttl_seconds），否则 Nginx 先 504；
- gzip off 或至少不要压缩 text/event-stream；
- Cloudflare 等 CDN 会缓冲 SSE，必要时关闭代理或改用直接子域名。

## 并发与性能

- 每个挂起请求（长轮询或 SSE）都占用一个 waitress 线程，默认 PEOAI_THREADS=32，即最多约 30 个并发等待；
- 需要更高并发时提高线程数，或把 queue.max_pending 调小以避免挤压；
- 长连接期间每 15 秒发送一次保活，Nginx 与中间设备不会判定空闲超时；
- 图片 base64 会在内存中解码，单图上限建议不超过 4 MB。

## 备份

需要备份的只有两处：

~~~bash
sudo tar czf peoai-backup-$(date +%F).tar.gz \
     -C /opt/peoai_server config.json data
~~~

- config.json：密钥哈希、模型与安全配置（恢复后旧 API Key 立即可用）；
- data/：requests/ 历史请求、audit.log、peoai.log、bootstrap.txt。

恢复：停止服务 → 解压覆盖 → 确认属主为 peoai → 启动。

## 升级

~~~bash
cd /opt/peoai_server
sudo -u peoai git pull            # 或 rsync 新版本
sudo -u peoai venv/bin/pip install -r requirements.txt
sudo systemctl restart peoai_server
sudo journalctl -u peoai_server -n 50
~~~

升级不会改动 config.json；新增配置项会自动使用默认值。跨大版本升级前先备份。

## 健康检查与监控

~~~bash
curl -sS http://127.0.0.1:5007/healthz
~~~

返回 pending / claimed 数量，可接入 Uptime Kuma、Prometheus blackbox 等。日志位于：

- journalctl -u peoai_server（运行日志）
- /opt/peoai_server/data/peoai.log（按 5 MB 滚动）
- /opt/peoai_server/data/audit.log（管理动作审计）

## 卸载

~~~bash
sudo systemctl disable --now peoai_server
sudo rm /etc/systemd/system/peoai_server.service
sudo systemctl daemon-reload
sudo rm -rf /opt/peoai_server
sudo userdel peoai    # 如需保留数据请先备份
~~~

## 故障排查

| 现象 | 排查 |
| --- | --- |
| 控制台打不开 | systemctl status peoai_server；确认 PEOAI_HOST 与 Nginx proxy_pass 端口一致 |
| 客户端一直没响应 | 队列里是否有请求；request_ttl_seconds 是否过小；Nginx proxy_read_timeout |
| 流式内容一次性到达 | proxy_buffering 未关闭，或前面还有一层 CDN 缓冲 |
| 401 | 密钥前缀是否 pk_；请求头是否被代理丢弃；require_api_key 是否已开 |
| 413 | 请求体超过 security.max_body_bytes 或 Nginx client_max_body_size |
| 502 | 后端未启动或端口不对；查看 journal |
| 图片不显示 | 模型未开启 vision；图片超过大小上限；远端图片被策略拦截（设置里可开启） |
| 登录被锁定 | 等待 login_lock_seconds，或用 scripts/peoai_admin.py set-password 重置 |

## Windows 本地调试

~~~powershell
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
$env:PEOAI_HOME = (Get-Location).Path
python peoai_server.py --port 5007 --no-waitress
~~~

Windows 下若终端中文乱码，入口已把 stdout 切换为 UTF-8；仍异常时设置 PYTHONIOENCODING=utf-8。
