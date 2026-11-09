---
name: economic-data-visualization-skill
description: >
  品牌商品流水数据整理与可视化 Agent。当用户提到经济数据分析、数据清洗、销售数据
  可视化、生成图表或可交互网页时触发：读取 data/ 下的数据，自动完成字段识别、
  数据清洗、指标计算与图表生成，并启动 Streamlit 页面展示结果。
version: "1.1"
---

# economic-data-visualization-skill

定位：**品牌商品流水数据整理与可视化 Agent**。

用户上传一份商品销售流水（Excel / CSV / 数据库查询结果），Skill 自动完成
「数据读取 → 字段识别 → 数据清洗 → 指标计算 → 可视化输出」全流程，并弹出
基于 Streamlit 的可视化网页（左图表 / 右指标 + AI 诊断报告）。

## 1. 触发条件（Trigger）

满足以下任一情况即触发本 Skill：

- 用户提到「经济数据分析」「可视化」「清洗数据」「销售数据整理」等关键词；
- 用户上传 / 提供了 Excel、CSV 或数据库查询结果文件，内容为商品销售流水；
- 用户要求计算销售额、销量、客单价、排行、占比、同比/环比等指标；
- 用户要求生成销售趋势图、排行图、对比图或可交互可视化网页。

典型触发语句：

- 「帮我分析 data 下的数据」
- 「清洗这份销售流水并生成图表」
- 「计算销售额、客单价和地区排行」

## 2. 工作流（Workflow）

AI 按以下步骤执行：

1. **读取数据**：读取 `data/` 下的数据文件（自动选取 `data/` / `assets/` 或根目录中的首个可用 CSV / Excel 文件）；
   如用户指定了其它路径，读取用户提供的文件（`utils/read_data.py` 的 `read_file()`）。
2. **字段识别**：自动识别日期、商品名称、SKU、单价、数量、销售额、渠道、门店、
   地区、订单号等字段（`detect_fields()`），规则见 `references/FIELD_RULES.md`。
   **核心字段（日期 / 销售额）缺失或识别置信度低时，先向用户确认字段映射，不得强行计算。**
3. **清洗**：调用 `utils/clean_data.py` 的 `clean()`。
4. **指标计算**：调用 `utils/calculate_metrics.py` 的 `compute_metrics()`。
5. **图表生成**：调用 `utils/generate_charts.py` 的 `build_figures()`。
6. **启动可视化页面**：运行 `streamlit run Home.py`，浏览器自动打开，
   以「左侧图表 + 右侧指标与 AI 诊断报告」展示结果。

> 也可逐脚本在命令行执行：
> `python utils/read_data.py "data/你的数据.xlsx"` →
> `python utils/clean_data.py "data/你的数据.xlsx"` →
> `python utils/calculate_metrics.py "data/你的数据.xlsx"` →
> `python utils/generate_charts.py "data/你的数据.xlsx"`。

## 3. 资源说明（Resources）

| 资源 | 路径 | 说明 |
|------|------|------|
| 字段识别与指标口径 | `references/FIELD_RULES.md` | 字段同义词、金额单位识别、指标计算口径、边界情况 |
| 示例数据 | `data/sample_data.csv` | 模拟销售流水（3 个月，6 商品 / 5 渠道 / 6 门店 / 4 地区），仅演示用 |
| 数据读取与字段识别 | `utils/read_data.py` | `read_file()` / `detect_fields()` / `available_fields()` / `overview()` |
| 数据清洗 | `utils/clean_data.py` | `clean(df) -> (cleaned, report)`，`report["error"]` 表示核心字段缺失 |
| 指标计算 | `utils/calculate_metrics.py` | `compute_metrics(cleaned) -> dict`，`"__error__"` 表示计算中止 |
| 图表生成 | `utils/generate_charts.py` | `build_figures(metrics) -> dict[str, Figure]` |
| **总控应用** | `Home.py` | Streamlit 页面，串联全流程（左图表 / 右指标 + 诊断报告） |

## 4. 脚本接口（供 AI 调用）

各模块均已拆分为「函数」与「`main()`」两层，函数可直接 `import` 复用：

```python
from read_data import read_file, detect_fields, overview, available_fields
from clean_data import clean
from calculate_metrics import compute_metrics
from generate_charts import build_figures, save_html_report

df = read_file("data/sample_data.csv")           # -> DataFrame
det = detect_fields(df)                            # -> {field_map, detected, missing, notes, confidence}
cleaned, report = clean(df)                        # -> (DataFrame, dict)；核心字段缺失时 report 含 "error"
metrics = compute_metrics(cleaned)                 # -> {daily, weekly, monthly, rankings, region_monthly,
                                                   #     monthly_growth, aov, notes} 或 {"__error__": ...}
figures = build_figures(metrics)                   # -> dict[str, plotly.Figure]
```

- 清洗后列名为规范列名：`date` / `product_name` / `sku` / `unit_price` / `quantity` /
  `sales_amount` / `channel` / `store` / `region` / `order_id`（存在时）。
- **动态字段**：维度（商品 / 渠道 / 门店 / 地区）与度量（数量 / 订单号 / 单价 / SKU）
  按数据中实际存在的字段动态计算，注册表在 `read_data.py` 的 `DIMENSION_FIELDS` /
  `METRIC_FIELDS` 中，脚本不做字段名硬编码；缺失字段自动隐藏跳过，绝不报错。

## 5. 字段识别规则

见 `references/FIELD_RULES.md`。识别优先级：

1. **列名匹配**（高置信度）：列名归一化（去空白、去括号、统一小写）后与同义词表做「精确匹配 → 包含匹配」。
2. **内容推断**（低置信度）：某列 >80% 的值可解析为日期则识别为「日期」；数值列按幅度区分「销售额 / 数量 / 单价」。

## 6. 数据清洗步骤

按 `utils/clean_data.py` 的顺序执行：

1. 列名去首尾空白；2. 删除完全重复行；3. 日期统一为 `datetime`，删除无效日期；
4. 金额单位归一化为「元」（自动识别元 / 万元 / 亿元）；5. 删除缺失 / 负值销售额；
6. 数量缺失补 0、负值置 0；7. IQR 异常值**标记**（默认不删除，输出到 `<字段>_outlier` 列）；
8. 文本字段标准化（去空白、合并空格）、缺失补「未知」。

## 7. 指标计算口径

全部口径见 `references/FIELD_RULES.md`，核心如下：

- **销售额**：`sum(sales_amount)`，单位元；
- **销量**：`sum(quantity)`；
- **客单价（订单口径）**：`销售额 ÷ 订单数`（存在订单号时使用）；
- **客单价（销量口径）**：`销售额 ÷ 销量`（无订单号时的替代口径，**必须说明**）；
- **同比**：`本期 / 去年同期 - 1`（需 ≥ 13 个月数据，否则为空）；
- **环比**：`本期 / 上期 - 1`；
- **销售额 / 销量占比**：`该维度值 ÷ 该维度合计`。

## 8. 可视化输出规则

使用 Plotly（`utils/generate_charts.py`）生成交互式图表，遵循：

- 趋势 → 折线图（单序列，不加图例，标题即说明）；
- 排行 / 对比 → 横向条形图，按值从大到小排序，单色；
- 占比 → 排名条形图或堆叠柱状图（饼图/环形图因可读性差，默认用排名条形图替代）；
- 地区月度构成 → 堆叠柱状图（分类色最多 8 类，超出折叠为「其他」）；
- **不使用双轴图**；金额与数量分开成图；
- 图表自带悬停提示、缩放；每日趋势图带区间滑块；
- **动态字段**：图表与筛选框按数据中实际存在的字段生成，缺失的字段自动隐藏跳过，绝不报错。

## 9. 输出物清单

| 输出物 | 来源 | 说明 |
|--------|------|------|
| 清洗后数据表 | `clean_data.py` → `output/cleaned_data.csv` | CSV（utf-8-sig） |
| 一组图表 | `generate_charts.py` → `output/charts/*.html` | 单张交互 HTML |
| 独立 HTML 报告 | `generate_charts.py` → `output/report.html` | 浏览器直接打开，离线可用 |
| **可视化网页** | `Home.py`（Streamlit） | 左图表 / 右指标 + AI 诊断报告 |
| 自定义多图表生成器 | `utils/generate_html_report.py`（Streamlit） | 选文件 → 配置多组 X/Y/类型 → 一键批量生成 |

## 10. 边界情况处理

| 情况 | 处理方式 |
|------|----------|
| 缺少日期 / 销售额字段 | 中止计算，提示用户确认字段映射 |
| 字段识别不确定 | 列出识别结果与置信度，要求确认 |
| 金额单位混乱（元/万元/亿元） | 自动检测并归一化为元，记录依据 |
| 日期格式不统一 | `pd.to_datetime(errors="coerce")`，无效值删除并计数 |
| 重复记录 | 删除完全重复行并计数 |
| 缺失值 | 销售额缺失删除；数量补 0；文本维度补「未知」 |
| 异常值 | IQR 标记，默认不删除（可 `--drop-outliers`） |
| 数据量过大 | 先抽样 / 汇总，再询问是否完整分析 |
| 同比无去年同期 | 输出为空，注明需要 ≥ 13 个月数据 |

## 本地运行

```bash
pip install -r requirements.txt
streamlit run Home.py                                   # 可视化网页（推荐，一键全流程）

python utils/read_data.py data/sample_data.csv          # 读取 + 字段识别
python utils/clean_data.py data/sample_data.csv         # 清洗 → output/cleaned_data.csv
python utils/calculate_metrics.py data/sample_data.csv  # 指标 → output/metrics/*.csv
python utils/generate_charts.py data/sample_data.csv    # 图表 → output/report.html
streamlit run utils/generate_html_report.py             # 自定义多图表生成器
```

> 示例数据 `data/sample_data.csv` 为**模拟数据**，仅用于演示，不代表任何真实业务。
