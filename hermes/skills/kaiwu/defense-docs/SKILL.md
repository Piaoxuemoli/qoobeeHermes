---
name: defense-docs
description: Write and maintain Kaiwu_2026 答辩材料 (defense/presentation docs). Covers technical writing for innovation points, updating the main summary doc, and git workflow for doc commits.
version: 1.0.0
author: QoobeeHermes
platforms: [linux]
metadata:
  hermes:
    tags: [kaiwu, docs, defense, technical-writing]
    related_skills: [wiki-sync, repo-scanner]
---

# Defense Docs (答辩材料)

为 Kaiwu_2026 仓库编写和维护答辩材料。

## When to Use

- 团队要求补充/更新答辩材料
- 新增创新点需要记录
- 基础设施、工具链、工程实践有新内容需要写入答辩文档
- 整理某个维度（特征/奖励/网络/训练/工程）的答辩内容

Don't use for: wiki/ 索引更新（用 wiki-sync）、代码变更记录（用实验记录）

## 文档结构

```
docs/答辩材料总结/
├── 答辩总文档.md          # 主文档，按维度分类全部创新点
├── 特征/                  # 特征工程相关
├── 奖励/                  # 奖励设计相关（如需）
├── 网络/                  # 网络架构相关
├── 训练/                  # 训练策略相关
├── 经典问题/              # 深度技术分析
└── 工程/                  # 工程实践、基础设施、工具链
```

## 写作规范

### 1. 内容格式

每个创新点遵循「三段式」：

```markdown
### X.Y 标题

**官方做法**：简述官方基线怎么做的，有什么问题

**我们的做法**：详述我们的方案，含代码片段/公式/架构图

**核心价值**：一句话总结为什么这样做更好
```

### 2. 技术细节要求

- **代码片段**：展示关键实现，不超过 15 行，加 Python/伪代码注释
- **维度/权重表**：用 Markdown 表格列出具体数值
- **对比分析**：与官方基线、马可波罗队、2025 老版本对比
- **理论依据**：引用论文或经典结论时给出出处

### 3. 答辩总文档更新

新增内容时：

1. 在 `答辩总文档.md` 对应章节末尾添加摘要段落
2. 用 `> 详见 [子目录/文件名.md](子目录/文件名.md)` 链接详细文档
3. 摘要不超过 10 行，核心信息用表格呈现
4. 如有新维度，在「九、附录：创新点统计」表中更新计数

### 4. 答辩话术

重要创新点应附带 30 秒话术模板：

```markdown
### 答辩话术（XX 秒）

> "一句话点明问题 → 我们的方案 → 核心数据/对比"
```

## Git 提交规范

答辩材料提交严格遵守 AGENTS.md 规范：

### 身份

```bash
git -c user.name="QoobeeHermes" -c user.email="qoobeehermes@kaiwu2026" commit -m "..."
```

### Commit Message

```
docs(wiki): <描述>
```

- 用 `docs` 类型
- scope 用 `wiki`（答辩材料属于文档类）
- 描述简洁，中文即可

### 操作步骤

```bash
# 1. 查看变更
git status

# 2. 只 add 答辩材料相关文件（禁止 git add .）
git add "docs/答辩材料总结/工程/新文件.md"
git add "docs/答辩材料总结/答辩总文档.md"

# 3. 提交（QoobeeHermes 身份）
git -c user.name="QoobeeHermes" -c user.email="qoobeehermes@kaiwu2026" \
  commit -m "docs(wiki): <描述>"

# 4. 推送到 dev（禁止推 master）
git push origin dev
```

### Pitfalls

- **不要混合提交**：答辩材料的 commit 不要夹带代码改动
- **不要 `git add .`**：必须指定文件路径
- **中文路径转义**：git status 显示的中文路径是八进制转义，add 时用引号包裹原始中文路径
- **主文档链接**：新增的详细文档必须在答辩总文档中有对应的摘要+链接，否则答辩时找不到

## 信息收集

写答辩材料前，先从以下来源收集信息：

1. **代码文件**：读取相关 .py 文件的实际实现
2. **参考资料/**：官方文档、赛制说明
3. **wiki/**：已有的架构/API 索引
4. **git log**：相关 commit 的改动和 message
5. **AGENTS.md**：仓库结构和成员信息
6. **服务器环境**：`uname -a`、`python3 --version` 等实际配置

## 验证清单

- [ ] 内容遵循三段式格式
- [ ] 代码片段有注释，不超过 15 行
- [ ] 数值/维度有表格支撑
- [ ] 答辩总文档有摘要 + 链接
- [ ] 创新点统计表已更新（如需）
- [ ] git commit 用 QoobeeHermes 身份
- [ ] 只 add 了答辩材料文件，未混入其他改动
- [ ] 推送到 dev 分支
