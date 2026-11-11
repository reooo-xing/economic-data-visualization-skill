# -*- coding: utf-8 -*-
"""1_数据看板.py — 核心图表与指标，支持动态钻取筛选（时间 / 商品 / 地区）。

筛选作用于清洗后数据，结果实时联动刷新 KPI 卡片与所有图表。
数据源来自 st.session_state（由 Home.py 首次运行时计算并缓存）；
侧边栏底部提供「导入数据源 / 导出 HTML 报告 / 下载清洗后 CSV」。
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# 让页面脚本能 import utils/ 下的模块（read_data / clean_data / calculate_metrics / generate_charts / ui_helpers）
UTILS_DIR = Path(__file__).resolve().parent.parent / "utils"
sys.path.insert(0, str(UTILS_DIR))

import pandas as pd
import streamlit as st

from read_data import DIMENSION_FIELDS, detect_fields, read_file
from clean_data import clean
from calculate_metrics import compute_metrics
from generate_charts import bar_type_options, build_bar_variant, build_chart_meta, build_figures, build_html_report
from ui_helpers import AOV_LABELS, UI_CSS, fmt_money

PROJECT_ROOT = UTILS_DIR.parent


def run_pipeline(data_path):
    """执行 read → clean → metrics → figures，返回结果 dict。"""
    raw = read_file(data_path)
    detection = detect_fields(raw)
    cleaned, report = clean(raw)
    metrics, figures = None, {}
    if "error" not in report:
        metrics = compute_metrics(cleaned)
        if metrics and "__error__" not in metrics:
            figures = build_figures(metrics)
        else:
            metrics = None
    return {
        "raw_df": raw,
        "cleaned_df": cleaned,
        "detection": detection,
        "report": report,
        "metrics": metrics,
        "figures": figures,
    }


def handle_new_upload(uploaded) -> None:
    """保存上传文件并重新执行全流程，更新 st.session_state。"""
    data_dir = PROJECT_ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    dest = data_dir / uploaded.name
    dest.write_bytes(uploaded.getvalue())

    try:
        results = run_pipeline(dest)
    except Exception as e:  # 上传文件无法读取/处理时不崩溃
        st.session_state["upload_error"] = f"读取或处理上传文件失败：{e}"
        st.session_state["cleaned_df"] = None
        st.session_state["report"] = {}
        st.session_state["metrics"] = None
        st.session_state["figures"] = {}
        return

    st.session_state.pop("upload_error", None)
    st.session_state["raw_df"] = results["raw_df"]
    st.session_state["cleaned_df"] = results["cleaned_df"]
    st.session_state["detection"] = results["detection"]
    st.session_state["report"] = results["report"]
    st.session_state["metrics"] = results["metrics"]
    st.session_state["figures"] = results["figures"]
    st.session_state["data_path"] = str(dest)
    st.session_state["pipeline_ready"] = True

    # 清空旧筛选控件状态，避免日期范围等与新数据不匹配
    for k in ("filter_date", "filter_product", "filter_region"):
        st.session_state.pop(k, None)


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    """在侧边栏渲染筛选组件，并返回筛选后的 DataFrame。"""
    st.sidebar.subheader("🔍 数据钻取筛选")

    # 1) 时间范围（仅当存在日期列）
    start = end = None
    if "date" in df.columns and not df.empty:
        dmin = df["date"].min().date()
        dmax = df["date"].max().date()
        sel = st.sidebar.date_input(
            "日期范围",
            value=(dmin, dmax),
            min_value=dmin,
            max_value=dmax,
            key="filter_date",
        )
        if isinstance(sel, tuple) and len(sel) == 2:
            start, end = sel
        else:
            start = end = sel

    # 2) 类别筛选（动态：有「商品名称」「地区」字段才显示）
    sel_product = sel_region = None
    if "product_name" in df.columns:
        opts = sorted(df["product_name"].dropna().unique().tolist())
        sel_product = st.sidebar.multiselect("商品名称", opts, key="filter_product")
    if "region" in df.columns:
        opts = sorted(df["region"].dropna().unique().tolist())
        sel_region = st.sidebar.multiselect("地区", opts, key="filter_region")

    # 3) 应用筛选（作用于清洗后数据）
    filtered = df
    if start is not None and end is not None:
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end) + pd.Timedelta(days=1)  # 含当天
        filtered = filtered[(filtered["date"] >= start_ts) & (filtered["date"] < end_ts)]
    if sel_product:
        filtered = filtered[filtered["product_name"].isin(sel_product)]
    if sel_region:
        filtered = filtered[filtered["region"].isin(sel_region)]

    st.sidebar.caption(f"筛选后：{len(filtered)} 行 / 共 {len(df)} 行")
    return filtered


def render_sidebar_bottom() -> None:
    """侧边栏底部：导入数据源 / 导出 HTML 报告 / 下载清洗后 CSV。"""
    st.sidebar.divider()
    st.sidebar.subheader("📥 数据源与下载")

    # 1) 导入数据源
    up = st.sidebar.file_uploader("导入数据源", type=["csv", "xlsx", "xls"])
    if up is not None:
        sig = f"{up.name}:{len(up.getvalue())}"
        if st.session_state.get("uploaded_sig") != sig:
            st.session_state["uploaded_sig"] = sig
            handle_new_upload(up)
            st.rerun()

    cleaned = st.session_state.get("cleaned_df")
    if cleaned is None or cleaned.empty:
        st.sidebar.info("请先上传数据源")
        return

    # 2) 下载 HTML 报告（所见即所得：优先导出当前筛选后的图表，浏览器直接下载）
    # filtered_figures / filtered_meta 由 main() 每次运行时根据当前筛选实时计算；
    # 无筛选时它们等于全量图表与文案；若因异常缺失，则回退到 Home.py 缓存的全量 figures。
    figures = st.session_state.get("filtered_figures")
    meta = st.session_state.get("filtered_meta") or {}
    if figures is None:
        figures = st.session_state.get("figures") or {}
    if not figures:
        st.sidebar.info("当前没有可导出的图表。")
    else:
        html = build_html_report(figures, title="销售数据可视化报告", meta=meta)
        # 文件名带筛选标记 + 时间戳，避免覆盖历史导出
        f_rows = st.session_state.get("filtered_rows")
        c_rows = st.session_state.get("cleaned_rows")
        tag = "筛选" if (c_rows and f_rows is not None and f_rows != c_rows) else "全量"
        fname = f"销售数据可视化报告_{tag}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        st.sidebar.download_button(
            label="下载 HTML 报告",
            data=html.encode("utf-8"),
            file_name=fname,
            mime="text/html",
        )

    # 3) 下载清洗后 CSV
    csv_data = cleaned.to_csv(index=False).encode("utf-8-sig")
    st.sidebar.download_button(
        label="下载清洗后 CSV",
        data=csv_data,
        file_name="cleaned_data.csv",
        mime="text/csv",
    )


def _render_chart_card(name: str, fig, m: dict, metrics: dict) -> None:
    """按 lieflat 卡片排版渲染：结论标题 + 副标题 + 图表 + 注释 + 来源行。

    fig 为 str 时是 lieflat「横档柱」SVG（直接内联渲染）；
    否则是 Plotly 图（时间序列 / 堆叠 / 动画），走 st.plotly_chart。
    柱状类图表上方额外渲染「图表类型」切换控件。
    """
    title = m.get("title") or name
    st.markdown(f'<h3 class="chart-title">{title}</h3>', unsafe_allow_html=True)
    if m.get("subtitle"):
        st.markdown(f'<div class="chart-sub">{m["subtitle"]}</div>', unsafe_allow_html=True)

    # 图表类型切换（仅对柱状类图表显示，默认保持「横档柱」）
    options = bar_type_options(name, metrics)
    if options:
        sel = st.segmented_control(
            "图表类型", options, default=options[0],
            key=f"ctype_{name}", label_visibility="collapsed",
        )
        if sel and sel != options[0]:
            fig = build_bar_variant(name, metrics, sel) or fig

    if isinstance(fig, str):
        st.markdown(f'<div class="rung-chart">{fig}</div>', unsafe_allow_html=True)
    else:
        st.plotly_chart(fig, width="stretch", key=f"dash_fig_{name}")
    if m.get("note"):
        st.markdown(f'<div class="chart-note">💡 {m["note"]}</div>', unsafe_allow_html=True)
    if m.get("source"):
        st.markdown(f'<div class="chart-src">{m["source"]}</div>', unsafe_allow_html=True)


def _render_figures(figures: dict, meta: dict, metrics: dict) -> None:
    """逐张渲染图表卡片，并用进度条提示进度。"""
    items = list(figures.items())
    prog = st.progress(0.0, text="正在渲染图表…")
    for i, (name, fig) in enumerate(items):
        _render_chart_card(name, fig, (meta or {}).get(name, {}), metrics)
        prog.progress((i + 1) / len(items), text=f"已渲染 {i + 1} / {len(items)} 张图表")
    prog.empty()


def main() -> None:
    st.markdown(UI_CSS, unsafe_allow_html=True)
    st.title("数据看板")
    st.caption("核心指标与图表；左侧筛选实时联动刷新。")

    report = st.session_state.get("report") or {}
    cleaned = st.session_state.get("cleaned_df")

    # 侧边栏：筛选（仅当有数据且清洗成功）
    filtered = None
    if cleaned is not None and not cleaned.empty and "error" not in report:
        filtered = apply_filters(cleaned)

    # 基于筛选后的数据实时重算指标与图表，并缓存到 session_state，
    # 使「导出 HTML 报告」能导出当前筛选结果（所见即所得）。
    # 无筛选时 filtered == cleaned，因此 filtered_figures 即全量图表。
    metrics, figures, meta = None, {}, {}
    if filtered is not None and not filtered.empty:
        with st.spinner("正在生成可视化图表…"):
            m = compute_metrics(filtered)
            if "__error__" not in m:
                metrics = m
                figures = build_figures(m)
                meta = build_chart_meta(m)
    st.session_state["filtered_figures"] = figures
    st.session_state["filtered_meta"] = meta
    st.session_state["filtered_rows"] = 0 if filtered is None else len(filtered)
    st.session_state["cleaned_rows"] = 0 if cleaned is None else len(cleaned)

    # 侧边栏底部：导入 / 导出 / 下载（导出使用上方缓存的 filtered_figures）
    render_sidebar_bottom()

    # ---- 主区域 ----
    if st.session_state.get("upload_error"):
        st.error(st.session_state["upload_error"])
        return
    if "error" in report:
        st.error(f"数据清洗失败：{report['error']}")
        return
    if cleaned is None or cleaned.empty:
        st.info("请先上传数据源，或回到「首页」加载示例数据。")
        return
    if filtered is None or filtered.empty:
        st.warning("当前筛选条件下没有数据，请调整筛选条件。")
        return
    if metrics is None:
        st.error("指标计算失败，无法展示看板。")
        return

    st.caption(f"当前筛选：{len(filtered):,} 条记录（原始 {len(cleaned):,} 条）")

    # ---- KPI 指标卡 ----
    kpis = [("总销售额", fmt_money(float(filtered["sales_amount"].sum())))]
    if "quantity" in filtered.columns:
        kpis.append(("总销量", f"{int(filtered['quantity'].sum()):,} 件"))
    aov = metrics.get("aov") or {}
    for k, v in aov.items():
        kpis.append((AOV_LABELS.get(k, k), fmt_money(v)))
    kpis.append(("记录数", f"{len(filtered):,} 行"))

    kpi_cols = st.columns(len(kpis))
    for col, (label, value) in zip(kpi_cols, kpis):
        col.metric(label, value)

    st.divider()

    # ---- 左图表 / 右指标明细 ----
    left, right = st.columns([3, 2])
    with left:
        st.subheader("可视化图表")
        if not figures:
            st.info("没有可生成的图表（字段不足）。")
        else:
            _render_figures(figures, meta, metrics)

    with right:
        st.subheader("指标明细")
        for key, label in DIMENSION_FIELDS.items():
            table = (metrics.get("rankings") or {}).get(key)
            if isinstance(table, pd.DataFrame) and not table.empty:
                with st.expander(f"{label}排行（Top 5）", expanded=True):
                    show_cols = [c for c in [key, "销售额", "销售额占比"] if c in table.columns]
                    st.dataframe(table.head(5)[show_cols])
        for key, label in [("daily", "每日"), ("weekly", "每周"), ("monthly", "每月")]:
            t = metrics.get(key)
            if isinstance(t, pd.DataFrame) and not t.empty:
                with st.expander(f"{label}汇总", expanded=True):
                    st.dataframe(t)


main()
