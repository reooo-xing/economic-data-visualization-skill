# -*- coding: utf-8 -*-
"""ui_helpers.py — 各页面共用的展示辅助函数（格式化与全站样式）。"""

AOV_LABELS = {"客单价_订单口径": "客单价（订单口径）", "客单价_销量口径": "客单价（销量口径）"}


def fmt_money(v) -> str:
    """金额格式化：千分位 + 元。"""
    try:
        return f"{float(v):,.2f} 元"
    except (TypeError, ValueError):
        return "—"


def fmt_pct(v) -> str:
    """百分比格式化（输入为小数）。"""
    try:
        return f"{float(v) * 100:.1f}%"
    except (TypeError, ValueError):
        return "—"


# 全站 UI 样式（lieflat-charts Mono 灰阶 × interface-design 排版/动效规范）。
# - 纸灰底 + 炭黑墨，纯单色（用户确认：不引入强调色）。
# - 1.25 比例字阶 + 负字距标题 + 四级文字层级（正文/说明/元信息/来源）。
# - 标准型动效：KPI 与图表卡片入场「淡入上移」、横档柱逐档淡入、按钮/卡片 hover。
# 用法：st.markdown(UI_CSS, unsafe_allow_html=True)
UI_CSS = """
<style>
/* Inter（标题/数字用），中文回退苹方/微软雅黑 */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root {
    --ink: #1C1C1A;      /* 墨：正文 / 主数据 / 强调 */
    --paper: #F0EFEB;    /* 纸：页面底色 */
    --muted: #8F8E88;    /* 次级文字 / 元信息 */
    --faint: #C6C5BF;    /* 来源行 / 最弱 */
    --grid: #DEDDD6;     /* 网格 / 发丝线 */
    --gray2: #4A4944;    /* 说明文字 */
    --gray3: #6A6963;    /* 次级说明 */
    --surface: #E7E6E0;  /* 侧边栏 / 次级容器 */
}

html, body, [data-testid="stAppViewContainer"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'PingFang SC',
                 'Microsoft YaHei', 'Segoe UI', sans-serif;
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
}

/* ---- 页首标题区：大标题 + 发丝分隔线（各页统一） ---- */
h1 {
    font-size: 28px;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: var(--ink);
    padding-bottom: 14px;
    margin-bottom: 4px;
    border-bottom: 1px solid rgba(28, 28, 26, 0.08);
}
h2 { font-size: 22px; font-weight: 700; letter-spacing: -0.015em; color: var(--ink); }
h3 { font-size: 18px; font-weight: 700; letter-spacing: -0.01em; color: var(--ink); }
[data-testid="stCaptionContainer"] { color: var(--muted); font-size: 13px; }

/* ---- 侧边栏：纸面同源，右侧一道发丝边 ---- */
[data-testid="stSidebar"] { border-right: 1px solid rgba(28, 28, 26, 0.06); }

/* ---- KPI 指标卡：扁平化，数字是焦点 ---- */
[data-testid="stMetric"] {
    background: transparent;
    border: none;
    box-shadow: none;
    padding: 10px 0;
    animation: fadeUp .5s cubic-bezier(.2, .7, .3, 1) both;
    transition: background-color .2s ease;
}
[data-testid="stMetric"]:hover { background-color: rgba(28, 28, 26, 0.04); }
[data-testid="stMetricLabel"] {
    font-size: 11px;
    font-weight: 500;
    color: var(--muted);
    letter-spacing: 0.04em;
    text-transform: uppercase;
}
[data-testid="stMetricValue"] {
    font-variant-numeric: tabular-nums;
    font-weight: 800;
    font-size: 26px;
    letter-spacing: -0.02em;
    line-height: 1.1;
    color: var(--ink);
}
[data-testid="stMetricDelta"] { font-variant-numeric: tabular-nums; }

/* ---- 按钮 / 下载按钮 hover ---- */
.stButton > button,
.stDownloadButton > button {
    transition: box-shadow .2s ease, transform .2s ease, border-color .2s ease, background-color .2s ease;
}
.stButton > button:hover,
.stDownloadButton > button:hover {
    box-shadow: 0 6px 16px rgba(0, 0, 0, 0.10);
    transform: translateY(-1px);
    border-color: var(--ink);
}

/* ---- 图表容器：扁平化，靠留白分卡，入场淡入上移 ---- */
[data-testid="stPlotlyChart"] {
    background: transparent;
    border: none;
    box-shadow: none;
    animation: fadeUp .6s cubic-bezier(.2, .7, .3, 1) both;
}

/* ---- 首页功能入口卡片：纸面之上的一层「卡」 ---- */
.feature-card {
    border: 1px solid var(--grid);
    border-radius: 16px;
    padding: 20px 22px;
    background: #FFFFFF;
    transition: transform .25s cubic-bezier(.2, .7, .3, 1), box-shadow .25s ease, border-color .25s ease;
}
.feature-card:hover {
    box-shadow: 0 10px 28px rgba(0, 0, 0, 0.08);
    transform: translateY(-3px);
    border-color: var(--ink);
}
.feature-card .fc-icon { font-size: 26px; line-height: 1; }
.feature-card .fc-title {
    font-weight: 700;
    font-size: 16px;
    margin: 10px 0 4px;
    color: var(--ink);
    letter-spacing: -0.01em;
}
.feature-card .fc-desc { font-size: 13px; color: var(--gray3); margin: 0; line-height: 1.55; }

/* ---- 首页入口链接：纸面之上的可点击卡（st.page_link） ---- */
a[data-testid="stPageLink-NavLink"] {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    padding: 18px 22px;
    background: #FFFFFF;
    border: 1px solid var(--grid);
    border-radius: 14px;
    color: var(--ink);
    font-weight: 700;
    font-size: 16px;
    letter-spacing: -0.01em;
    text-decoration: none;
    transition: transform .25s cubic-bezier(.2, .7, .3, 1), box-shadow .25s ease,
                border-color .25s ease, background-color .25s ease;
}
a[data-testid="stPageLink-NavLink"]:hover {
    box-shadow: 0 10px 28px rgba(0, 0, 0, 0.08);
    transform: translateY(-2px);
    border-color: var(--ink);
}

/* ---- 图表卡片排版：结论标题 / 副标题 / 注释 / 来源行 ---- */
.chart-title {
    font-size: 18px;
    font-weight: 700;
    letter-spacing: -0.01em;
    color: var(--ink);
    margin: 6px 0 2px;
    animation: fadeUp .5s cubic-bezier(.2, .7, .3, 1) both;
}
.chart-sub {
    font-size: 12px;
    color: var(--muted);
    margin-bottom: 10px;
    animation: fadeUp .5s cubic-bezier(.2, .7, .3, 1) both;
}
.chart-note {
    font-size: 13px;
    color: var(--gray2);
    border-left: 3px solid var(--ink);
    padding: 4px 0 4px 10px;
    margin: -4px 0 12px;
    line-height: 1.6;
    animation: fadeUp .5s cubic-bezier(.2, .7, .3, 1) both;
}
.chart-src {
    font-size: 9.5px;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--faint);
    margin: -8px 0 24px;
}

/* ---- 横档柱 SVG 容器：撑满列宽，按 viewBox 等比缩放 ---- */
.rung-chart svg { display: block; width: 100%; height: auto; }

/* ---- 分隔线柔化：浅灰细线 ---- */
hr { border-color: rgba(0, 0, 0, 0.08) !important; }

/* ---- 动效关键帧（标准型：快进快停，不弹跳） ---- */
@keyframes fadeUp {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: none; }
}
@media (prefers-reduced-motion: reduce) {
    [data-testid="stMetric"],
    [data-testid="stPlotlyChart"],
    .chart-title, .chart-sub, .chart-note, .chart-src { animation: none; }
}
</style>
"""
