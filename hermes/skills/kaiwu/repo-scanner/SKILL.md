---
name: repo-scanner
description: Use when initializing or rebuilding the wiki index. Scans the entire Kaiwu_2026 repository, extracts code structure via Python AST parsing, summarizes docs and experiment logs, and generates wiki/ index files.
version: 1.0.0
author: Qoobee
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [kaiwu, wiki, indexing, ast]
    related_skills: [wiki-sync, rl-advisor]
---

# Repo Scanner

全量扫描 Kaiwu_2026 仓库，生成结构化 wiki 索引。

## When to Use

- 首次部署 Hermes 后，建立初始索引
- wiki/ 目录损坏或过期时重建
- 仓库发生大规模重构后重新扫描

Don't use for: 日常小改动（用 wiki-sync）、代码审查（用 代码审查 skill）

## 执行流程

### Step 1: 扫描仓库结构

遍历以下目录，排除 `.git/`、`__pycache__/`、`node_modules/`、`.hermes/`：

```
初赛/工程/
区域赛/工程/
全国决赛/工程/
docs/
参考资料/
```

对每个目录记录：文件名、类型、大小、最后修改时间。

### Step 2: Python AST 解析

对所有 `.py` 文件执行 AST 解析，提取：

- **函数定义**：名称、参数列表、返回类型注解、docstring
- **类定义**：名称、父类、方法列表
- **配置常量**：模块级赋值（`UPPER_CASE` 变量）
- **import 关系**：`import` 和 `from ... import` 语句

使用 Python 内置 `ast` 模块：
```python
import ast
with open(file_path, 'r', encoding='utf-8') as f:
    tree = ast.parse(f.read())
```

### Step 3: 提取 docs/ 知识

读取 `docs/` 目录下的所有 `.md` 文件，提取：
- 文档标题和结构
- 关键约束和规则
- 路由表和依赖关系

### Step 4: 汇总实验记录

扫描 `初赛/实验记录/` 和各赛段下的实验相关文件，提取：
- 实验名称和日期
- 关键参数和结果
- 结论和改进方向

### Step 5: 生成 wiki/ 文件

按以下模板生成 5 个文件：

#### wiki/index.md
```markdown
# Kaiwu_2026 仓库索引

## 快速导航
- [代码架构](architecture.md)
- [实验记录](experiments.md)
- [赛段知识](competition.md)
- [API 速查](api-reference.md)

## 仓库概览
- 赛段数量：3（初赛、区域赛、全国决赛）
- 主要语言：Python
- 算法：PPO
- 成员：Qoobee（队长）、Snow（队员）

## 最近更新
<!-- 由 git log 自动生成 -->
```

#### wiki/architecture.md
```markdown
# 代码架构

## 通用模块结构
每个赛段的 agent 遵循统一结构：
- agent.py — 入口
- algorithm/ — PPO 算法实现
- conf/ — 配置参数
- feature/ — 特征工程
- model/ — 网络模型
- workflow/ — 训练流程

## 各赛段架构
<!-- 由 AST 扫描结果自动填充 -->
```

#### wiki/experiments.md
```markdown
# 实验记录索引

## 初赛实验
<!-- 由扫描结果自动填充 -->

## 区域赛实验
<!-- 由扫描结果自动填充 -->
```

#### wiki/competition.md
```markdown
# 赛段知识汇总

## 初赛：地图探索 + 宝箱收集
## 区域赛：王者 1v1
## 全国决赛：王者 3v3
<!-- 由 docs/ 和参考资料/ 提取填充 -->
```

#### wiki/api-reference.md
```markdown
# API 速查

## 函数索引
<!-- 由 AST 扫描结果自动生成表格 -->

| 模块 | 函数 | 参数 | 说明 |
|------|------|------|------|
```

### Step 6: 更新 Hermes Memory

将以下信息写入 Hermes persistent memory：
- 仓库结构摘要
- 关键配置参数位置
- 各赛段的 agent 变体列表
- 最近的实验结论

## 验证清单

- [ ] wiki/ 下生成了 5 个 .md 文件
- [ ] 每个文件包含实际内容（非空模板）
- [ ] AST 解析无报错
- [ ] memory 已更新
