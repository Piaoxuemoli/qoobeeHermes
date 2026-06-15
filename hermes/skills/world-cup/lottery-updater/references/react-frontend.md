# ⚠️ LEGACY — React Frontend (已废弃)

> **当前架构（2026-06-13 起）**：项目为纯 HTML 单文件 `~/world-cup/世界杯预测.html`（约 3000 行，JS + HTML 一体）。`world-cup-app/` 目录不存在，无 React/Vite/npm。以下为历史架构记录，仅供参考。

---

## 旧版项目结构（已废弃）

```
~/world-cup/world-cup-app/
├── package.json           # Vite + React + TypeScript
├── vite.config.ts
├── tsconfig.app.json      # TypeScript 配置（strict: false）
├── index.html             # 入口 HTML
├── src/
│   ├── main.tsx
│   ├── App.tsx            # 主组件，路由切换
│   ├── App.css            # 全局样式（响应式）
│   ├── index.css
│   ├── data/
│   │   ├── teams.ts       # 48支球队 × 26人名单
│   │   ├── models.ts      # 6个AI模型信息
│   │   ├── rounds.ts      # AI_ROUNDS 投注数据（更新目标）
│   │   └── matches.ts     # 24场小组赛赛程
│   └── components/
│       ├── Navigation.tsx  # 导航栏（移动端汉堡菜单）
│       ├── Hero.tsx
│       ├── Leaderboard.tsx # 排行榜
│       ├── Rounds.tsx      # 逐轮分析
│       ├── Contestants.tsx # 球队卡片（可展开26人名单）
│       ├── Bracket.tsx     # 赛程表格
│       ├── Format.tsx      # 赛制说明 + 玩法Tabs
│       ├── Purchase.tsx    # 购彩清单
│       ├── Sources.tsx
│       └── Footer.tsx
└── dist/                  # 构建产物
    ├── index.html
    └── assets/
        ├── index-*.css
        └── index-*.js
```

## 数据更新流程

编辑 `src/data/rounds.ts` → `npm run build` → 复制到 nginx/Caddy

## 响应式断点

- **移动端** (< 734px): 单列布局，导航折叠，表格横向滚动
- **平板** (734-1068px): 2列网格
- **桌面** (> 1068px): 3-4列网格，完整布局

## 常见 Pitfalls

### 1. TypeScript Template Literal 转义

在 Python 字符串中写 TSX 时，反引号 `` ` `` 需要特别处理：
- 使用字符串拼接 `'prefix' + variable + 'suffix'` 替代模板字符串
- 或确保 Python raw string 正确转义

### 2. verbatimModuleSyntax 类型导入

tsconfig 启用 `verbatimModuleSyntax` 时，类型必须用 `import type`：
```typescript
// ❌ 错误
import { teamsData, Team } from '../data/teams';

// ✅ 正确
import { teamsData } from '../data/teams';
import type { Team } from '../data/teams';
```

### 3. Record 类型索引签名

当使用 `Record<string, T>` 时，TypeScript 可能报错。改用索引签名：
```typescript
// ❌ 可能报错
predictions: Record<string, Prediction>;

// ✅ 更兼容
predictions: { [key: string]: Prediction };
```

### 4. 构建产物路径

Vite 构建产物在 `world-cup-app/dist/`，需要手动复制到 `~/world-cup/`：
- `dist/index.html` → `~/world-cup/index.html`
- `dist/assets/` → `~/world-cup/assets/`

nginx 从 `/root/world-cup` 提供静态文件。

## 访问地址

- **Caddy (80)**: http://43.156.230.108/ — ✅ 唯一正常运行的 Web 服务
- **nginx (8080)**: ❌ 已停止（`Active: failed`），不可用
