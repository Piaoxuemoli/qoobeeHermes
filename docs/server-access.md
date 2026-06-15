# 服务器访问流程

> 本文档从 Colosseum 部署 Skill / `ops/deploy/README.md` 抽取**仅与「访问服务器」相关**的部分（SSH 登录、远程命令、文件传输、密钥安全）。
> 应用层部署细节（Docker / Caddy / 备份）不在本文范围，请参考原始部署手册。

---

## 1. 服务器基本信息

| 项 | 值 |
|---|---|
| 主机（IP） | `43.156.230.108`（腾讯云） |
| 系统 | OpenCloudOS（hostname: `VM-0-14-opencloudos`） |
| 登录用户 | `root` |
| SSH 端口 | `22` |
| SSH 私钥（本机） | `hermesqoobee.pem` |
| Colosseum 应用目录 | `/opt/colosseum` |

> 服务器密钥本机位于 `C:\Users\Qoobeewang\Desktop\qoobeeHermes\hermesqoobee.pem`。
> **该私钥绝对不能提交到 Git**，已在本仓库 `.gitignore` 中排除（`*.pem`）。

---

## 2. SSH 登录

### 交互式登录

```bash
ssh -i hermesqoobee.pem -o StrictHostKeyChecking=no root@43.156.230.108
```

- `-i hermesqoobee.pem`：指定私钥文件路径。
- `-o StrictHostKeyChecking=no`：首次连接跳过 known_hosts 确认（自动化场景用；交互场景建议改为 `accept-new` 以保留指纹校验）。
- 登录后默认进入 `/root`，应用在 `/opt/colosseum`。

### 首次 known_hosts 处理

第一次连接时服务器指纹会写入 `~/.ssh/known_hosts`。如果服务器重装系统导致指纹变化，会报 `REMOTE HOST IDENTIFICATION HAS CHANGED`，处理方式：

```bash
ssh-keygen -R 43.156.230.108   # 删除旧指纹后重连
```

---

## 3. 远程命令执行（非交互式）

无需进入 shell，直接在远端跑一条命令：

```bash
ssh -i hermesqoobee.pem -o StrictHostKeyChecking=no root@43.156.230.108 '<remote command>'
```

常用示例：

```bash
# 查看主机身份
ssh -i hermesqoobee.pem root@43.156.230.108 'hostname && whoami'

# 查看 /opt 下应用目录
ssh -i hermesqoobee.pem root@43.156.230.108 'ls -la /opt'

# 查看 Colosseum 容器状态
ssh -i hermesqoobee.pem root@43.156.230.108 'cd /opt/colosseum/ops/deploy && docker compose ps'

# 查看应用日志（最后 100 行）
ssh -i hermesqoobee.pem root@43.156.230.108 'cd /opt/colosseum/ops/deploy && docker compose logs --tail 100 nextjs'
```

> **多行 / 复合命令**：用单引号包裹整体交给远端 shell 执行；如命令里含变量展开，注意本机与远端 shell 的引号转义差异（Windows cmd 下推荐用双引号外层 + 单引号内层，或写成一行 `&&` 串联）。

---

## 4. 文件传输

本机为 Windows，**没有 rsync**，统一使用 `scp` 或 `tar + ssh` 管道。

### 4.1 scp 单文件 / 单目录

```bash
# 上传：本地 → 服务器
scp -i hermesqoobee.pem -o StrictHostKeyChecking=no ./local-file root@43.156.230.108:/opt/colosseum/

# 下载：服务器 → 本地
scp -i hermesqoobee.pem -o StrictHostKeyChecking=no root@43.156.230.108:/opt/colosseum/.env.example ./

# 递归整目录
scp -r -i hermesqoobee.pem root@43.156.230.108:/opt/colosseum/ops/deploy ./deploy-copy
```

### 4.2 tar + ssh 管道（带排除，推荐用于整目录迁移）

scp 不支持 `--exclude`。需要排除 `node_modules`、`.git`、`.env`、日志等时，用 tar 管道：

```bash
# 下载：服务器某目录 → 本地（排除常见噪声与敏感文件）
ssh -i hermesqoobee.pem root@43.156.230.108 \
  "cd /opt && tar czf - --exclude=node_modules --exclude=.git --exclude=.env --exclude='*.log' colosseum" \
  | tar xzf -

# 上传：本地某目录 → 服务器（同样可加 --exclude）
tar czf - --exclude=node_modules --exclude=.git --exclude=.env ./mydir \
  | ssh -i hermesqoobee.pem root@43.156.230.108 "cd /opt && tar xzf -"
```

> Windows cmd / Git Bash 下 `|` 管道可正常工作；若用 PowerShell 注意管道对象类型差异，建议在 Git Bash 中执行上述命令。

---

## 5. 密钥安全管理（强制约束）

1. **私钥不入库**：`hermesqoobee.pem` 及任何 `*.pem` / `*.key` 必须被 `.gitignore` 排除。提交前用 `git status` 复核待提交清单，确认无密钥文件。
2. **私钥权限收紧**（Windows / OpenSSH 要求私钥仅当前用户可读，否则拒绝加载并报 `UNPROTECTED PRIVATE KEY FILE`）：

   ```cmd
   :: 移除继承，仅授予当前用户读取权限
   icacls "C:\Users\Qoobeewang\Desktop\qoobeeHermes\hermesqoobee.pem" /inheritance:r /grant:r "%USERNAME%:R"
   ```

   若仍报权限错误，进一步用 `icacls ... /remove "Everyone" "Users"` 移除组权限。

3. **防火墙最小开放**：云安全组仅放行 `:80` / `:443`；SSH（`:22`）建议限源 IP。
4. **强随机密钥**：应用层 `MATCH_TOKEN_SECRET` 等使用 `openssl rand -base64 48` 生成，至少 32 字节随机。

---

## 6. 常见访问场景速查

| 场景 | 命令 |
|---|---|
| 登录服务器 | `ssh -i hermesqoobee.pem root@43.156.230.108` |
| 看主机身份 | `ssh -i hermesqoobee.pem root@43.156.230.108 'hostname'` |
| 看应用容器 | `ssh ... 'cd /opt/colosseum/ops/deploy && docker compose ps'` |
| 看应用日志 | `ssh ... 'cd /opt/colosseum/ops/deploy && docker compose logs --tail 100 nextjs'` |
| 下单个文件 | `scp -i hermesqoobee.pem root@43.156.230.108:/path/file ./` |
| 下整目录（带排除） | `ssh ... "cd /parent && tar czf - --exclude=node_modules dir" \| tar xzf -` |
| 上整目录 | `tar czf - --exclude=node_modules ./dir \| ssh ... "cd /parent && tar xzf -"` |
| 删旧主机指纹 | `ssh-keygen -R 43.156.230.108` |

> 上表中 `ssh ...` 代表 `ssh -i hermesqoobee.pem -o StrictHostKeyChecking=no root@43.156.230.108`。

---

## 7. 相关文件（来源）

- 原始部署 Skill：`Colosseum/.kimi-code/skills/deployment/SKILL.md`
- 生产部署手册：`Colosseum/ops/deploy/README.md`
- Vercel fallback：`Colosseum/docs/deploy/vercel.md`
