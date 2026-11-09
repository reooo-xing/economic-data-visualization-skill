# -*- coding: utf-8 -*-
"""Home.py — 多页面 BI 系统入口。

使用 st.navigation 管理页面路由。在渲染任何页面之前，先执行一次全流程
（read → clean → metrics → charts），把结果缓存到 st.session_state，
后续切换页面复用缓存，避免重复计算。

运行：streamlit run Home.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# 让入口能 import utils/ 下的模块（read_data / clean_data / calculate_metrics / generate_charts / ui_helpers）
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "utils"))

from read_data import detect_fields, find_default_data_file, read_file
from clean_data import clean
from calculate_metrics import compute_metrics
from generate_charts import build_figures
from ui_helpers import UI_CSS

DEFAULT_DATA = find_default_data_file(PROJECT_ROOT)
PAGES_DIR = PROJECT_ROOT / "pages"

st.set_page_config(page_title="经济数据可视化分析系统", layout="wide", page_icon="📊")

# 注入全站 UI 动效样式（按钮 / 卡片 / 图表容器 hover 反馈）
st.markdown(UI_CSS, unsafe_allow_html=True)

# 缓存键列表，用于后续可能的「重新加载」场景下统一清理。
PIPELINE_KEYS = [
    "raw_df", "cleaned_df", "detection", "report",
    "metrics", "figures", "data_path", "pipeline_ready",
]


def load_data(data_path: Path = DEFAULT_DATA) -> None:
    """计算一次全流程并缓存到 st.session_state；已缓存则直接跳过。"""
    if st.session_state.get("pipeline_ready"):
        return

    with st.spinner("正在初始化数据看板…"):
        prog = st.progress(0.0, text="读取数据…")
        raw = read_file(data_path)
        detection = detect_fields(raw)

        prog.progress(0.3, text="清洗数据…")
        cleaned, report = clean(raw)

        prog.progress(0.55, text="计算指标…")
        metrics, figures = None, {}
        if "error" not in report:
            metrics = compute_metrics(cleaned)

        prog.progress(0.8, text="生成图表…")
        if "error" not in report and metrics and "__error__" not in metrics:
            figures = build_figures(metrics)
        else:
            metrics = None

        prog.progress(1.0, text="完成")
        prog.empty()

    st.session_state["raw_df"] = raw
    st.session_state["cleaned_df"] = cleaned
    st.session_state["detection"] = detection
    st.session_state["report"] = report
    st.session_state["metrics"] = metrics
    st.session_state["figures"] = figures
    st.session_state["data_path"] = str(data_path)
    st.session_state["pipeline_ready"] = True


def render_home() -> None:
    """首页：项目简介 + 功能入口卡片 + SKILL 使用说明。"""
    st.title("📊 经济数据可视化分析系统")
    st.caption("品牌商品流水数据整理与可视化 · 多页面专业 BI 系统")

    st.markdown("### 项目简介")
    st.markdown(
        "本系统自动完成「**数据读取 → 字段识别 → 数据清洗 → 指标计算 → 可视化输出**」"
        "全流程，适用于品牌商品销售流水数据（Excel / CSV）。"
    )

    cleaned = st.session_state.get("cleaned_df")
    rows = f"{cleaned.shape[0]:,}" if cleaned is not None else "—"
    st.info(
        f"当前数据文件：`{Path(st.session_state.get('data_path', DEFAULT_DATA)).name}`"
        f"（清洗后 {rows} 行）。"
    )

    st.markdown("### 功能入口")
    cards = [
        ("📊", "数据看板", "核心图表与指标，支持时间 / 商品 / 地区动态钻取。"),
        ("🤖", "AI 诊断报告", "字段识别、清洗结论与指标发现的规则化诊断文本。"),
        ("🧾", "原始数据", "清洗前后的数据对比与明细查看。"),
    ]
    cols = st.columns(3)
    for col, (icon, title, desc) in zip(cols, cards):
        with col:
            st.markdown(
                f'<div class="feature-card">'
                f'<div class="fc-icon">{icon}</div>'
                f'<div class="fc-title">{title}</div>'
                f'<p class="fc-desc">{desc}</p>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.divider()
    st.markdown("#### 使用左侧导航切换到各页面 👈")


# 定义页面：首页用函数，其余页面用文件路径（放在 pages/）。
home_page = st.Page(render_home, title="首页", icon="🏠", default=True)
dashboard_page = st.Page(str(PAGES_DIR / "1_数据看板.py"), title="数据看板", icon="📊")
diagnosis_page = st.Page(str(PAGES_DIR / "2_AI诊断报告.py"), title="AI 诊断报告", icon="🤖")
raw_page = st.Page(str(PAGES_DIR / "3_原始数据.py"), title="原始数据", icon="🧾")

pg = st.navigation([home_page, dashboard_page, diagnosis_page, raw_page])

# 先加载数据（只计算一次），再渲染当前选中的页面。
load_data()
pg.run()
