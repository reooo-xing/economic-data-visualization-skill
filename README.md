# economic-data-visualization-skill

品牌商品流水数据整理与可视化 Agent（Skill）。读取 Excel / CSV 销售流水，自动完成
「字段识别 → 数据清洗 → 指标计算 → 可视化输出」，并提供多页面 Streamlit BI 系统
（数据看板 / AI 诊断报告 / 原始数据对比）。

## 功能特性

- 自动识别字段：日期、商品、SKU、单价、数量、销售额、渠道、门店、地区、订单号
- 数据清洗：去重、日期规范化、金额单位归一化（元 / 万元 / 亿元）、IQR 异常值标记
- 指标计算：销售额 / 销量 / 客单价 / 排行 / 占比 / 环比 / 同比
- 动态图表：趋势、排行、地区月度堆叠与动画、占比（按数据中实际存在的字段生成）
- 多页面 Streamlit BI 系统 + 自定义多图表生成器

## 快速开始

```bash
pip install -r requirements.txt
streamlit run Home.py
```

## 项目结构

```
.
├── Home.py                     # Streamlit 入口（st.navigation 多页面路由）
├── requirements.txt            # Python 依赖
├── .gitignore
├── SKILL.md                    # Skill 说明（供 AI Agent 使用）
├── README.md
├── LICENSE                     # MIT
├── data/
│   └── sample_data.csv         # 模拟销售流水（仅演示用，非真实业务数据）
├── pages/                      # Streamlit 多页面
│   ├── 1_数据看板.py
│   ├── 2_AI诊断报告.py
│   └── 3_原始数据.py
├── utils/                      # 核心模块（可独立运行）
│   ├── read_data.py            # 读取 + 字段识别
│   ├── clean_data.py           # 数据清洗
│   ├── calculate_metrics.py    # 指标计算
│   ├── generate_charts.py      # 图表生成 + HTML 报告
│   ├── generate_html_report.py # 自定义多图表生成器（Streamlit）
│   └── ui_helpers.py           # 格式化与 UI 样式
├── legacy/
│   └── app.py                  # 旧版单页面总控应用（保留备查）
├── references/
│   └── FIELD_RULES.md          # 字段识别与指标口径
└── output/                     # 生成的报告/图表（不入库）
```

## 数据说明

`data/sample_data.csv` 为**模拟数据**，仅用于演示，不代表任何真实业务。
真实业务数据已通过 `.gitignore` 排除（`data/*` 与 `assets/`），不会提交到仓库。

## 部署到 Streamlit Cloud

1. 在 [Streamlit Community Cloud](https://streamlit.io/cloud) 连接仓库 `reooo-xing/economic-data-visualization-skill`；
2. 选择分支 `main`；
3. **Main file path** 填 `Home.py`；
4. 点击 Deploy。

## License

[MIT](LICENSE)
