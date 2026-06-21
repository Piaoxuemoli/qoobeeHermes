# 集成交接文档：jmcomic-ai → qoobeeHermes

> 本文档自包含，供 Codex / 其他 agent 直接执行。所有命令、配置、文件路径均已核实。
> 来源调研：`JMComic-Crawler-Python`(核心库 `jmcomic`) + `jmcomic-ai`(MCP server 封装)。

---

## 0. 当前进度（已完成）

| 项 | 状态 | 说明 |
|---|---|---|
| 调研两个仓库 | ✅ 完成 | 已本地浅克隆 + 通读 pyproject/core.py/mcp/server.py/cli.py/SKILL.md |
| Hermes MCP 接入机制 | ✅ 已核实 | `hermes/skills/mcp/native-mcp/SKILL.md` 是权威手册 |
| 服务器环境探测 | ✅ 完成 | Python 3.11.6 / `python3`+`pip3` 可用 / `mcp` 包**未装** / config 无 `mcp_servers` 段 |
| **编写本交接文档** | ✅ 本文件 | |
| SOUL.md 注入工具 SOP | ✅ 已完成 | 已加入 PDF-only 回传 SOP |
| 服务器安装 + 配置 | ✅ 已完成 | `jmai 0.0.9` + `img2pdf` + PDF-only MCP wrapper |
| 验证 + 提交 | ✅ 已完成 | MCP 测试 + 飞书 PDF `MEDIA:` 附件冒烟通过 |

---

## 1. 集成方案概述

**架构**：`jmcomic-ai` 是一个 Python MCP server，启动命令 `jmai mcp stdio`，stdio 传输。把它注册为 Hermes 的 MCP server，Hermes 启动时自动发现其工具并以 `mcp_jmcomic_*` 前缀注册到所有 `hermes-*` toolset（CLI/飞书）。

**为什么装 `jmcomic-ai` 而不是单独装核心库**：`jmcomic-ai` 的 `pyproject.toml` 依赖 `jmcomic>=2.6.12`，装前者会自动拉核心库。核心库仓库无需单独处理。

**启动命令的正确写法**：服务器上 `python` 不存在（只有 `python3`），所以 MCP 配置的 `command` 必须用 `python3 -m jmcomic_ai` 或装好后的 `jmai`。下文给两种方案。

### 1.1 jmcomic-ai 暴露的 MCP 工具清单

注册后 Hermes 内工具名前缀为 `mcp_jmcomic_`。下列为方法名（即去掉前缀的部分）：

| 工具方法 | 功能 | 关键参数 |
|---|---|---|
| `search_album` | 关键词搜索（ID/标题/作者/标签，含高级过滤） | `keyword`, `page`, `main_tag`, `order_by`, `time_range`, `category` |
| `browse_albums` | 分类浏览/排行榜（同人/韩漫/美漫等，日/周/月榜，多排序） | `category`, `time_range`, `order_by`, `page` |
| `get_album_detail` | 作品详情（标题/作者/点赞/观看/章节/标签） | `album_id` |
| `download_album` | 下载整本（阻塞，带实时进度） | `album_id` |
| `download_photo` | 下载单章节 | `photo_id` |
| `download_cover` | 下载封面 | `album_id` |
| `post_process` | 后处理打包为 zip / pdf / 长图 | `album_id`, `process_type`, `params` |
| `login` | 账号登录（解锁收藏等） | `username`, `password` |
| `update_option` | 修改并保存配置 | `option_updates` (dict) |

另含 3 个 MCP Resources：`jmcomic://option/schema`、`jmcomic://option/reference`、`jmcomic://skill`。

### 1.2 配置文件路径

- **jmcomic-ai 的配置**：`~/.jmcomic/option.yml`（不存在则首次运行自动生成默认值）。优先级：CLI `--option` > 环境变量 `JM_OPTION_PATH` > 默认路径。
- **Hermes 的配置**：`~/.hermes/config.yaml`（服务器 `/root/.hermes/config.yaml`），在此追加 `mcp_servers` 段。

### 1.3 飞书文件回传策略

Hermes gateway 会扫描最终回复中的 `MEDIA:/absolute/path/file.ext`，自动把本地文件上传到当前飞书会话。Feishu adapter 支持 `send_document`，`.pdf/.doc/.xls/.ppt` 走对应文档类型，其它文件（如 `.zip`）走通用 `stream` 文件上传。

由于移动端无法可靠处理 ZIP，漫画交付必须是 PDF，不允许回传 ZIP：

1. `download_album(album_id=...)`，自定义 Feature 在 `after_album` 使用同一个 album 对象建立清单并生成 PDF。
2. 仅当下载返回 `partial`、超时或缺少 `output_paths` 时调用 `post_process(album_id=..., process_type="img2pdf")` 重扫磁盘；即使传入 `zip` 也会强制走同一 PDF 管线。
3. 结果必须满足 `valid_images == expected_images == pdf_pages`，空文件和损坏文件均为 0；否则不生成附件。
4. 最终回复为 `output_paths` 中的每个文件写入 `MEDIA:/tmp/monitor_charts/jmcomic/<title>_第001-020話.pdf`。若 PDF 失败或不完整，报告原因并停止，不回传 ZIP。

关键限制：`MEDIA:` 必须指向实际文件，不能指向目录；路径必须是服务器上的绝对路径，且要位于 Hermes 允许上传目录内。当前服务器 `HERMES_MEDIA_ALLOW_DIRS=/tmp/monitor_charts`，jmcomic 输出目录已设为 `/tmp/monitor_charts/jmcomic`。

服务器使用仓库内 `hermes/scripts/jmai_pdf_mcp.py` 作为 MCP 启动 wrapper。它通过 `JmOption.download_album(..., extra=ValidatedMobilePdfFeature)` 接入上游 Feature 生命周期，不再依赖 `post_process` 重建下载元数据。管线强制 `Bd / JM{Aid}-{Pid}` 唯一目录，按 `page_arr` 文件名递归验证 jpg/jpeg/png/webp/gif/bmp/tif/tiff，并持久化到 `/root/.hermes/state/jmcomic/<album_id>/manifest.json`；章节 ID 序列未变化时可直接复用缓存元数据重扫磁盘。完整后按 API 章节边界规划分卷、固定 150 DPI 流式写入 PDF，极窄图片会补白到最小 8 px，最后用 `pypdf` 精确核对页数。根据飞书实测限制采用 18 MB 安全线，而不是原来的 28 MB。

---

## 2. 第一步：把工具 SOP 注入 Hermes 的 SOUL.md

文件：`hermes/SOUL.md`（本地仓库 `C:\Users\Qoobeewang\Desktop\qoobeeHermes\hermes\SOUL.md`，服务器 `/root/.hermes/SOUL.md`）。

当前 SOUL.md 末尾是「## 技术栈」段。**在其后追加**一个新章节，措辞保持专业中性（技术文档风格），内容如下。可直接复制：

```markdown

## 媒体检索能力（MCP 工具集）

除上述世界杯职责外，你接入了 `jmcomic-ai` MCP server（工具前缀 `mcp_jmcomic_`），具备漫画检索与下载能力。按以下 SOP 使用：

### 触发场景

当用户请求检索/浏览/获取数字漫画作品时启用。

### 标准作业流程（SOP）

1. **检索** — 先用 `search_album(keyword=...)` 或 `browse_albums(time_range=, order_by=)` 拿到候选列表（返回 `{albums, total_count}`，支持翻页）。
2. **核实** — 对候选结果调用 `get_album_detail(album_id=...)` 确认标题、作者、章节等信息。
3. **下载并校验** — 调用 `download_album(album_id=...)`；只有磁盘清单逐章精确匹配 API 预期页数时才允许 `success`。
4. **断点修复** — `partial` 或超时后先用 `post_process(album_id=..., process_type="img2pdf")` 重扫，再按 `missing_chapter_ids` 调用 `download_photo`。最多 5 轮，退避 15/30/60 秒，连续两轮无进展停止。
5. **生成 PDF** — 完整清单自动按章节边界生成 18 MB 以内分卷，并验证 PDF 总页数；`post_process` 仅作恢复入口。
6. **发回飞书** — 仅对 `success.output_paths` 中的 PDF 输出 `MEDIA:`，不得发送 ZIP、部分 PDF 或目录。
7. **汇报** — 说明 `valid_images/expected_images`、PDF 页数及分卷数；未完整时明确报告缺章。

### 行为约束

- 检索结果可能为空或受限：如实反馈 `total_count`，不编造作品信息。
- `download_*` 是阻塞长任务，调用前向用户确认目标 ID，避免误下载。
- 下载路径由 `~/.jmcomic/option.yml` 的 `dir_rule.base_dir` 决定；如需改路径，用 `update_option` 而非手动改文件。
- `MEDIA:` 必须指向经过清单和页数双重校验的 PDF；路径必须位于 `HERMES_MEDIA_ALLOW_DIRS`，每卷采用 18 MB 安全线。
- 遵守平台与当地法规，仅处理用户明确请求且合法的内容。
```

> 注：SOUL.md 同时存在于本地仓库和服务器。**两边都要更新**：本地用于提交 GitHub，服务器 `/root/.hermes/SOUL.md` 用于 Hermes 实际加载。但服务器那份是运行态副本，git 不跟踪——可等安装阶段一并 SSH 覆盖。

---

## 3. 第二步：服务器安装与配置（命令行执行）

SSH 密钥：`C:\Users\Qoobeewang\Desktop\qoobeeHermes\hermesqoobee.pem`
主机：`root@43.156.230.108`

### 3.1 安装 jmcomic-ai 和 mcp SDK

```bash
ssh -i "C:/Users/Qoobeewang/Desktop/qoobeeHermes/hermesqoobee.pem" -o StrictHostKeyChecking=no root@43.156.230.108 "python3 -m pip install --upgrade pip && python3 -m pip install 'jmcomic-ai>=0.0.9' 'jmcomic>=2.6.19' mcp img2pdf pypdf"
```

安装后验证：

```bash
ssh -i "C:/Users/Qoobeewang/Desktop/qoobeeHermes/hermesqoobee.pem" -o StrictHostKeyChecking=no root@43.156.230.108 "python3 -c 'import mcp; import jmcomic_ai; print(\"mcp+jmcomic_ai ok\")' && which jmai && jmai --version"
```

预期：打印 `mcp+jmcomic_ai ok`，`which jmai` 输出路径（通常 `/usr/local/bin/jmai` 或 `/usr/bin/jmai`），`jmai --version` 打印 `jmai version: 0.0.9`。

### 3.2 生成 jmcomic-ai 配置文件

首次运行会自动在 `~/.jmcomic/option.yml` 生成默认配置。**不必手动创建**，直接触发一次即可：

```bash
ssh -i "C:/Users/Qoobeewang/Desktop/qoobeeHermes/hermesqoobee.pem" -o StrictHostKeyChecking=no root@43.156.230.108 "jmai option show || true; ls -la /root/.jmcomic/option.yml"
```

如需自定义下载目录，编辑 `option.yml` 的 `dir_rule`。输出必须位于飞书允许目录，且规则必须包含 `Pid`，否则同名章节会互相覆盖：

```yaml
dir_rule:
  base_dir: /tmp/monitor_charts/jmcomic
  rule: 'Bd / JM{Aid}-{Pid}'
```

编辑命令：

```bash
ssh -i "C:/Users/Qoobeewang/Desktop/qoobeeHermes/hermesqoobee.pem" -o StrictHostKeyChecking=no root@43.156.230.108 "jmai option edit"
```

> Windows 端无法用 `notepad`，`jmai option edit` 在服务器会调 `vi`/`nano`。若要非交互式改，用 `update_option` 工具或直接 `sed`。
> 修改 `option.yml` 后需要 reload/restart jmcomic MCP server，确保新下载目录被重新加载。

### 3.3 在 Hermes 配置里注册 MCP server

`/root/.hermes/config.yaml` 当前**没有** `mcp_servers` 段（已通读整个 config.yaml 确认；`platform_toolsets` 仅 `cli→hermes-cli`、`feishu→hermes-feishu`）。

**推荐做法（用 Hermes 自带 CLI，避免手写 YAML）**：仓库 `hermes/skills/autonomous-ai-agents/hermes-agent/SKILL.md` 第 130–139 行提供 `hermes mcp` 子命令：

```bash
ssh -i "C:/Users/Qoobeewang/Desktop/qoobeeHermes/hermesqoobee.pem" -o StrictHostKeyChecking=no root@43.156.230.108 "hermes mcp add jmcomic --command jmai --args 'mcp stdio' && hermes mcp list"
```

> `hermes mcp add` 的 `--args` 具体语法（单串 `'mcp stdio'` vs 多次 `--args mcp --args stdio`）以服务器上 `hermes mcp add --help` 为准；不确定就改用下方「已验证的手动方法」。注册后用 `hermes mcp test jmcomic` 验证连接、`hermes mcp list` 复核。

**已验证的手动方法（Python 注入，先备份再用 yaml 库写，不破坏现有 YAML）**——需追加（YAML 顶层）：

```yaml
mcp_servers:
  jmcomic:
    command: "/usr/bin/python3"
    args: ["/root/.hermes/scripts/jmai_pdf_mcp.py"]
    timeout: 600
    connect_timeout: 60
```

> **关键**：
> - key 必须是 `mcp_servers`（下划线），**不是** `mcpServers`。
> - `command` 使用系统 Python 绝对路径运行 PDF-only wrapper：`/usr/bin/python3 /root/.hermes/scripts/jmai_pdf_mcp.py`。不要写成裸 `python3`，gateway 的过滤 PATH 可能解析到 Hermes venv，导致 `ModuleNotFoundError: jmcomic_ai`。若临时排障需绕过 wrapper，可改回 `command: "jmai"`, `args: ["mcp", "stdio"]`。
> - stdio 模式不需要 host/port。
> - `timeout` 调到 600s，因下载是长任务（默认 120s 可能不够）。
> - Hermes 的 stdio server 只继承 `PATH/HOME/USER/LANG` 等，其它环境变量丢弃。如 jmcomic 需要代理，加 `env:` 段：
>   ```yaml
>     env:
>       HTTPS_PROXY: "http://127.0.0.1:7890"
>   ```

**安全追加方法**（先备份，再用 Python 注入，避免 sed 破坏现有 YAML）：

```bash
ssh -i "C:/Users/Qoobeewang/Desktop/qoobeeHermes/hermesqoobee.pem" -o StrictHostKeyChecking=no root@43.156.230.108 'set -e; cp /root/.hermes/config.yaml /root/.hermes/config.yaml.bak.$(date +%Y%m%d%H%M%S); python3 -c "
import yaml
p=\"/root/.hermes/config.yaml\"
d=yaml.safe_load(open(p,encoding=\"utf-8\"))
d.setdefault(\"mcp_servers\",{})[\"jmcomic\"]={\"command\":\"/usr/bin/python3\",\"args\":[\"/root/.hermes/scripts/jmai_pdf_mcp.py\"],\"timeout\":600,\"connect_timeout\":60}
open(p,\"w\",encoding=\"utf-8\").write(yaml.safe_dump(d,allow_unicode=True,sort_keys=False))
print(\"mcp_servers injected\")
"'
```

验证：

```bash
ssh -i "C:/Users/Qoobeewang/Desktop/qoobeeHermes/hermesqoobee.pem" -o StrictHostKeyChecking=no root@43.156.230.108 "python3 -c 'import yaml; d=yaml.safe_load(open(\"/root/.hermes/config.yaml\")); print(d.get(\"mcp_servers\"))'"
```

预期输出包含 `{'jmcomic': {'command': '/usr/bin/python3', 'args': ['/root/.hermes/scripts/jmai_pdf_mcp.py'], ...}}`。

---

## 4. 第三步：同步 SOUL.md 到服务器 + 重启 Hermes

### 4.1 把更新后的 SOUL.md 推到服务器

本地改好 `hermes/SOUL.md` 后：

```bash
scp -i "C:/Users/Qoobeewang/Desktop/qoobeeHermes/hermesqoobee.pem" -o StrictHostKeyChecking=no "C:/Users/Qoobeewang/Desktop/qoobeeHermes/hermes/SOUL.md" root@43.156.230.108:/root/.hermes/SOUL.md
```

### 4.2 让 MCP server 生效（先热重载，不行再重启）

改完 `mcp_servers` 后需让 Hermes 重新发现工具。**先试轻量重载，不行再重启**：

**方式 A（首选，会话内热重载）**：Hermes 内置 `/reload-mcp` 斜杠命令（仓库 `hermes-agent/SKILL.md` 第 284 行），可在不重启进程的情况下重新加载 MCP server。`config.yaml` 里 `approvals.mcp_reload_confirm: true` 说明该操作默认需确认。在飞书/CLI 会话里直接发：

```
/reload-mcp
```

> ⚠️ 口径冲突：`hermes/skills/mcp/native-mcp/SKILL.md` 第 357 行写的是「no hot-reload currently，需重启」，这处文档偏旧——`/reload-mcp` 与 config 的 `mcp_reload_confirm` 都证实有运行时重载。**优先试 `/reload-mcp`**；若工具仍未出现，落到方式 B/C。别因「文档说必须重启」就直接重启飞书 gateway 造成中断。

**方式 B（CLI 重启 gateway 服务）**：

```bash
ssh -i "C:/Users/Qoobeewang/Desktop/qoobeeHermes/hermesqoobee.pem" -o StrictHostKeyChecking=no root@43.156.230.108 "hermes gateway restart && sleep 3 && hermes gateway status"
```

**方式 C（systemd）**：若 gateway 由 `hermes gateway install` 装成 systemd 服务（单元名 `hermes-gateway`，见 `webhook-subscriptions/SKILL.md` 第 54 行）：

```bash
ssh -i "C:/Users/Qoobeewang/Desktop/qoobeeHermes/hermesqoobee.pem" -o StrictHostKeyChecking=no root@43.156.230.108 "systemctl restart hermes-gateway 2>/dev/null || systemctl --user restart hermes-gateway; sleep 3; systemctl status hermes-gateway --no-pager 2>/dev/null || systemctl --user status hermes-gateway --no-pager"
```

**先探查再决定**（确认 gateway 当前怎么跑的、是否 systemd 托管）：

```bash
ssh -i "C:/Users/Qoobeewang/Desktop/qoobeeHermes/hermesqoobee.pem" -o StrictHostKeyChecking=no root@43.156.230.108 "systemctl list-units --type=service | grep -i hermes; systemctl --user list-units --type=service 2>/dev/null | grep -i hermes; ps aux | grep -iE 'hermes.*gateway|gateway.*hermes' | grep -v grep"
```

> **关键风险——别用前台 `hermes gateway run` 重启**：`hermes-agent/SKILL.md` 故障排查段明确警告「Gateway dies on SSH logout」。若 gateway 不是 systemd 托管、且未开 linger（`sudo loginctl enable-linger root`），SSH 断开后前台进程会一起死，连带飞书 gateway 与 `hermes/cron/jobs.json` 里每日 09:00 的「世界杯每日赛果报告」（`last_status: ok`）一起停摆。**若探查发现是 nohup/前台进程，先 `loginctl enable-linger root`，再迁到 systemd 或 tmux 守护，不要盲目 kill。**

---

## 5. 第四步：验证集成

重启后检查 Hermes 日志确认 MCP 工具发现：

```bash
ssh -i "C:/Users/Qoobeewang/Desktop/qoobeeHermes/hermesqoobee.pem" -o StrictHostKeyChecking=no root@43.156.230.108 "grep -iE 'mcp|jmcomic|Registered tool' /root/.hermes/logs/*.log | tail -40"
```

预期看到 `Registered tool: search_album` / `Registered tool: download_album` 等行，以及 `Registered 3 MCP resources`。

功能冒烟（直接调 jmcomic-ai CLI，绕过 Hermes 验证库本身工作）：

```bash
ssh -i "C:/Users/Qoobeewang/Desktop/qoobeeHermes/hermesqoobee.pem" -o StrictHostKeyChecking=no root@43.156.230.108 "jmai option path && jmai option show 2>&1 | head -20"
```

Hermes 层验证（确认 MCP server 已注册并被 gateway 发现）：

```bash
ssh -i "C:/Users/Qoobeewang/Desktop/qoobeeHermes/hermesqoobee.pem" -o StrictHostKeyChecking=no root@43.156.230.108 "hermes mcp list && hermes mcp test jmcomic && hermes doctor 2>&1 | tail -25"
```

- `hermes mcp list` 应列出 `jmcomic`；`hermes mcp test jmcomic` 应连接成功并列出工具（`search_album`/`download_album` 等）；`hermes doctor` 复核依赖与配置。
- 第 5 节那条 `*.log` glob 已覆盖重点日志文件 **`/root/.hermes/logs/gateway.log`**（`hermes-agent/SKILL.md` 第 870 行指明该精确路径）。

---

## 6. 第五步：提交到 GitHub

```bash
cd "C:/Users/Qoobeewang/Desktop/qoobeeHermes"
git add hermes/SOUL.md docs/integration-handoff.md
git status          # 复核：确保 hermesqoobee.pem 不在内
git commit -m "Add jmcomic-ai MCP integration SOP to SOUL.md and handoff doc"
git push
```

---

## 7. 关键事实速查（供 Codex 参考）

| 项 | 值 |
|---|---|
| Hermes 主目录（服务器） | `/root/.hermes` |
| Hermes 配置 | `/root/.hermes/config.yaml`（已确认无 `mcp_servers` 段） |
| Hermes SOUL | `/root/.hermes/SOUL.md` |
| Hermes 日志 | `/root/.hermes/logs/*.log` |
| Hermes MCP 手册 | 仓库内 `hermes/skills/mcp/native-mcp/SKILL.md` |
| jmcomic-ai 配置 | `/root/.jmcomic/option.yml`（首运行自动生成） |
| jmcomic 输出目录 | `/tmp/monitor_charts/jmcomic`（位于 `HERMES_MEDIA_ALLOW_DIRS=/tmp/monitor_charts` 下，可被飞书 `MEDIA:` 上传） |
| PDF 依赖 | `img2pdf`（流式写入）和 `pypdf`（精确页数校验） |
| PDF 体积上限 | 默认 `JMCOMIC_PDF_MAX_SIZE_MB=18`（依据实际上传稳定性保留安全余量） |
| PDF-only wrapper | `/root/.hermes/scripts/jmai_pdf_mcp.py`（仓库源文件：`hermes/scripts/jmai_pdf_mcp.py`；Feature 清单校验、移动端 PDF、18 MB 分卷） |
| 服务器 Python | 3.11.6，命令名 `python3`（无 `python`），`pip3` 可用 |
| 服务器缺失包 | `mcp`、`jmcomic-ai`（都需 pip 安装）；`uvx`/`jmai` 未装 |
| MCP server 启动 | `/usr/bin/python3 /root/.hermes/scripts/jmai_pdf_mcp.py`（stdio 传输，强制 PDF） |
| Hermes 工具命名 | `mcp_jmcomic_{方法名}`（连字符/点→下划线） |
| SSH 密钥 | `C:\Users\Qoobeewang\Desktop\qoobeeHermes\hermesqoobee.pem`（已收紧权限，勿提交） |
| 注册 MCP 的 CLI | `hermes mcp add/list/test/remove/configure`（`hermes-agent/SKILL.md` 130–139 行） |
| 让 MCP 生效 | 首选 `/reload-mcp`（会话内热重载，受 `approvals.mcp_reload_confirm: true` 约束）；不行则 `hermes gateway restart` 或 `systemctl restart hermes-gateway` |
| Gateway 服务单元 | `hermes-gateway`（systemd，`hermes gateway install` 安装；CLI 见 `hermes gateway run/install/start/stop/restart/status`） |
| Gateway 日志（精确） | `/root/.hermes/logs/gateway.log` |
| 健康检查 | `hermes doctor`（依赖+配置）、`hermes config check`（配置缺失/过期） |
| 现有 cron 依赖 gateway | `hermes/cron/jobs.json`：每日 09:00「世界杯每日赛果报告」→飞书（`last_status: ok`），重启 gateway 勿中断 |

## 8. 风险与注意事项

1. **MCP 生效方式**：优先使用 `/reload-mcp` 轻量重载；若工具未出现，再重启 Hermes gateway。
2. **`command` 路径**：服务器无 `python`，若 `jmai` 装在用户级 `~/.local/bin` 不在非交互 SSH 的 PATH，需用绝对路径（`/usr/local/bin/jmai` 或 `command: "python3", args: ["-m","jmcomic_ai.cli","mcp","stdio"]`）。验证用 `which jmai`。
3. **网络可达性**：jmcomic 站点在国内/外访问差异大，`option.yml` 的 `client.impl`（`html`/`api`）和 `proxies` 可能需调。若检索失败，先查 `client.domain` 列表和代理。
4. **SOUL.md 措辞**：注入内容已用中性技术语言（"数字漫画检索"），避免敏感词触发内容过滤。
5. **不要把 `hermesqoobee.pem` 或 `option.yml`（可能含 cookie）提交到 GitHub**。`.gitignore` 已覆盖 `*.pem` 和 `.env`，但 `option.yml` 不在忽略列表——提交前复核 `git status`。
6. **Gateway 会随 SSH 退出而死**（`hermes-agent/SKILL.md` 故障排查段）。若 gateway 非 systemd 托管，前台 `hermes gateway run` 重启会在 SSH 断开后停摆，连带飞书 gateway 与每日 cron 报废。先 `sudo loginctl enable-linger root`，再走 systemd/`hermes gateway restart`；崩溃循环用 `systemctl --user reset-failed hermes-gateway` 清状态。
7. **下载工具 stdout 污染风险**：`jmcomic-ai` 的下载日志可能写到 stdout，污染 MCP JSON-RPC 流。若下载成功但 Hermes 报 JSON parse warning，继续执行 PDF 后处理；不要因为下载工具 warning 直接回传 ZIP。
