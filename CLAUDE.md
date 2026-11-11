# 项目说明（Claude 每次在本项目工作时自动加载）

## 项目定位

`economic-data-visualization-skill` —— GitHub Skill / 参赛项目：读取品牌商品流水（Excel / CSV）→ 字段识别 → 数据清洗 → 指标计算 → 图表生成 → 多页面 Streamlit BI 系统。

## 运行

- 入口：`streamlit run Home.py`（根目录 `Home.py`，用 `st.navigation` 管理多页面，**不是** `scripts/Home.py`）
- 结构：核心模块在 `utils/`，页面在 `pages/`，旧版单页在 `legacy/app.py`，字段规则在 `references/FIELD_RULES.md`

## 硬约束（必须遵守）

- 示例数据必须是**模拟数据**，绝不编造真实业务数据；真实业务数据绝不提交（`.gitignore` 已排除 `data/*`、`assets/`，仅保留 `data/sample_data.csv`）
- `.streamlit/secrets.toml` 存 DeepSeek API 密钥，绝不提交（已 gitignore）；密钥绝不写进前端或任何 `.py` 源码

## 设计方向（已定稿）

- 图表：lieflat-charts「横档柱」(Rung Bars) 的 Mono 灰阶（INK `#1C1C1A` / PAPER `#F0EFEB`，7 级灰阶阶梯）；柱状图默认用横档柱 SVG（`utils/rung_charts.py`），时间序列/堆叠/动画仍用 Plotly
- 配色：**纯墨色、无强调色**（用户确认）；60/30/10 灰阶分布
- 动效：**标准型**（KPI/图表卡片淡入上移 + 横档柱逐档淡入，quarticOut 900ms，不弹跳）；支持 `prefers-reduced-motion`
- 排版：Inter 字体（中文回退苹方/微软雅黑），1.25 字阶，负字距大标题，四级文字层级
