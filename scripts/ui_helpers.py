# -*- coding: utf-8 -*-
"""ui_helpers.py — 各页面共用的展示辅助函数（格式化等）。"""

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


# 全站 UI 动效样式：按钮 / 指标卡 / 图表容器 / 首页功能卡片的 hover 反馈。
# 动效统一控制在 0.2–0.3s，只做视觉反馈，不改变布局结构、不影响侧边栏功能。
# 用法：st.markdown(UI_CSS, unsafe_allow_html=True)
UI_CSS = """
<style>
/* ---- 按钮 hover：轻微上浮 + 阴影 + 描边 ---- */
.stButton > button,
.stDownloadButton > button {
    transition: box-shadow 0.2s ease, transform 0.2s ease, border-color 0.2s ease;
}
.stButton > button:hover,
.stDownloadButton > button:hover {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
    transform: translateY(-1px);
    border-color: #2a78d6;
}
/* ---- 指标卡 hover：阴影 + 轻微放大 + 背景变化 ---- */
[data-testid="stMetric"] {
    border-radius: 10px;
    transition: box-shadow 0.25s ease, transform 0.25s ease, background-color 0.25s ease;
}
[data-testid="stMetric"]:hover {
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.10);
    transform: translateY(-2px);
    background-color: #f6f9fd;
}
/* ---- 图表容器 hover：阴影 ---- */
[data-testid="stPlotlyChart"] {
    border-radius: 10px;
    transition: box-shadow 0.25s ease;
}
[data-testid="stPlotlyChart"]:hover {
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.08);
}
/* ---- 首页功能入口卡片 hover ---- */
.feature-card {
    border: 1px solid #e6e5df;
    border-radius: 12px;
    padding: 18px 20px;
    background: #ffffff;
    transition: box-shadow 0.25s ease, transform 0.25s ease, border-color 0.25s ease;
}
.feature-card:hover {
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.10);
    transform: translateY(-3px);
    border-color: #2a78d6;
}
.feature-card .fc-icon { font-size: 26px; line-height: 1; }
.feature-card .fc-title { font-weight: 600; margin: 8px 0 4px; color: #0b0b0b; }
.feature-card .fc-desc { font-size: 13px; color: #52514e; margin: 0; }
</style>
"""
