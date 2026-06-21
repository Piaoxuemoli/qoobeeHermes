---
name: static-html-deploy
description: 把静态 HTML 站点部署到服务器对外访问的标准 SOP。覆盖 Caddy(Docker,:80/:443) 与 nginx(宿主,独立端口) 两条路径、端口约定、80 端口冲突坑、部署目录、reload 与 curl 验证。任何"部署/上线/开放访问一个 HTML 页面或静态站点"的请求都必须先读这里，不要自己瞎配。
version: 1.0.0
author: QoobeeHermes
platforms: [linux]
metadata:
  hermes:
    tags: [deploy, nginx, caddy, static-site, html, sop]
    related_skills: [feishu-gateway]
---

# Static HTML Deploy · 标准 SOP

服务器 `43.156.230.108` 上对外提供静态 HTML 的**唯一两条正确路径**。部署前必须读完「选型」和「Pitfalls」。

## 0. 先决条件：选对 Web 服务器

| 场景 | 用谁 | 端口 | 典型例子 |
|---|---|---|---|
| 公网访问、要 HTTP(S)、放在某个路径下 | **Caddy（Docker 容器 `colosseum-caddy-1`）** | 80 / 443 | `/xigai/`（习思想复习站）、`/xi-thought/` |
| 独立站点、要独占端口 | **宿主 nginx** | 8080+ 自选 | （旧的 8080 世界杯 / 8081 bbs 已下线） |

**铁律**：
- 根路径 `/`（端口 80）**归 Colosseum Next.js 应用**，静态内容**绝不**放根路径，必须用路径前缀（Caddy）或独立端口（nginx）。
- 宿主 nginx **绝不监听 80 端口**（被 docker-proxy 占用，见 Pitfall #1）。
- 部署 HTML **绝不**需要重启 `openclaw-gateway` 或改飞书配置（`/root/.openclaw/openclaw.json`、`/root/.hermes/.env`）——那是 Qoobee 维护的，别碰。

## 1. 内容目录约定

- 统一放 `/opt/<name>-docs/`（如 `/opt/xigai-docs/`），入口文件 `index.html`。
- 中文页面 nginx 加 `charset utf-8;`。
- 上传用 scp（本机无 rsync）：
  ```bash
  scp -i hermesqoobee.pem -o StrictHostKeyChecking=no -r ./my-site root@43.156.230.108:/opt/myname-docs/
  ```

## 2. 路径 A：Caddy（推荐，公网 :80/:443）

Caddyfile 在宿主 `/opt/colosseum/ops/deploy/Caddyfile`，容器内挂载为 `/etc/caddy/Caddyfile`。

### 步骤

1. **确认目录已挂载进容器**。当前 docker-compose 只挂了 `/opt/xigai-docs` 和 `/opt/exam-study`。**新目录要先加挂载**：
   ```bash
   # 编辑 /opt/colosseum/ops/deploy/docker-compose.yml，在 caddy.volumes 加：
   #   - /opt/myname-docs:/opt/myname-docs:ro
   cd /opt/colosseum/ops/deploy && docker compose up -d caddy   # 重建 caddy 容器生效
   ```
   > 偷懒办法：直接把新内容放进**已挂载**的 `/opt/xigai-docs/` 或 `/opt/exam-study/` 子目录，免改 compose。

2. **在 Caddyfile 的 `:80 { }` 块内加 handle**：
   ```caddyfile
   handle /myname/* {
       uri strip_prefix /myname
       root * /opt/myname-docs
       @assets path *.css *.js *.mjs *.json *.pdf *.png *.jpg *.svg *.woff2
       header @assets Cache-Control "public, max-age=86400"
       header { 
           not path *.css *.js *.mjs *.json *.pdf *.png *.jpg *.svg *.woff2
           Cache-Control "no-cache"
       }
       file_server
   }
   ```

3. **reload（在容器内）**：
   ```bash
   docker exec colosseum-caddy-1 caddy reload --config /etc/caddy/Caddyfile
   ```

4. **验证**：
   ```bash
   curl -sI http://localhost/myname/index.html   # 期望 200
   ```

> 域名/HTTPS：Caddy 当前 `:80`，域名块 `your-domain.com` 注释着（等 ICP 备案）。未备案前别开 443 自动签证书。

## 3. 路径 B：宿主 nginx（独立端口）

配置目录 `/etc/nginx/conf.d/<name>.conf`。

### 步骤

1. 内容放 `/opt/<name>-docs/`（见 §1）。
2. 新建 `/etc/nginx/conf.d/<name>.conf`：
   ```nginx
   server {
       listen 8082;                # 自选空闲端口，绝不选 80
       server_name _;
       root /opt/myname-docs;
       charset utf-8;
       index index.html;
       location / { try_files $uri $uri/ =404; }
   }
   ```
3. `nginx -t && nginx -s reload`（**每次必先 `-t`**）。
4. 验证：`curl -sI http://localhost:8082/`（期望 200）。
5. **云安全组放行该端口**（腾讯云控制台；本机改不了）。

## 4. Pitfalls（必读，每次部署过一遍）

### #1 端口 80 冲突（最高频翻车点）
`/etc/nginx/nginx.conf` 默认有一个**不带 listen 的 server 块**（约 37–51 行），默认监听 80，与 docker-proxy 冲突：
```
nginx: [emerg] bind() to 0.0.0.0:80 failed (98: Address already in use)
```
**该块必须保持注释状态**。如果你看到它被取消注释，重新注释：`sed -i '37,51s/^/#/' /etc/nginx/nginx.conf`。

### #2 Caddy 改了配置不生效
- 必须在**容器内** `caddy reload`，不是宿主的 caddy（宿主没装）。
- 新内容目录**必须先在 docker-compose 加 volume 挂载并 `docker compose up -d caddy` 重建**，否则容器内看不到文件（404）。

### #3 nginx 改完忘了 reload / 没 -t
顺序永远是 `nginx -t` → 通过 → `nginx -s reload` → `curl` 验证。跳过 `-t` 可能导致 nginx 挂掉。

### #4 中文乱码
nginx server 块加 `charset utf-8;`；HTML 头加 `<meta charset="utf-8">`。

### #5 改 HTML 牵连飞书
**不要**为了部署 HTML 去重启 `openclaw-gateway` 或动 `/root/.openclaw/openclaw.json`、`/root/.hermes/.env`。HTML 部署只碰 Caddy/nginx + `/opt/*-docs/`。

## 5. 当前线上静态站点清单（2026-06-21）

| 路径/端口 | 服务 | 源目录 |
|---|---|---|
| `http://43.156.230.108/xigai/` | 习思想复习站（Caddy） | `/opt/xigai-docs` |
| `http://43.156.230.108/xi-thought/` | 考试背书（Caddy） | `/opt/exam-study` |
| ~~8080 世界杯~~ | 已下线 | — |
| ~~8081 bbs-demo~~ | 已下线 | — |

新增站点后**回来更新这张表**。
