# -*- coding: utf-8 -*-
"""app.py — Streamlit 总控应用（Skill 的网页入口）。

职责：串联 read_data → clean_data → calculate_metrics → generate_charts 四个模块，
并以「左图表 / 右指标 + AI 诊断报告」的布局呈现结果。业务逻辑全部在各脚本中，
本文件只负责调用与展示。

运行：streamlit run scripts/app.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from read_data import CANONICAL_FIELDS, DIMENSION_FIELDS, detect_fields, read_file
from clean_data import clean
from calculate_metrics import compute_metrics
from generate_charts import build_figures, save_html_report

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = PROJECT_ROOT / "assets" / "sample_data.csv"

st.set_page_config(page_title="经济数据可视化分析", layout="wide", page_icon="📊")

AOV_LABELS = {"客单价_订单口径": "客单价（订单口径）", "客单价_销量口径": "客单价（销量口径）"}


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def _fmt_money(v) -> str:
    try:
        return f"{float(v):,.2f} 元"
    except (TypeError, ValueError):
        return "—"


def _fmt_pct(v) -> str:
    try:
        return f"{float(v) * 100:.1f}%"
    except (TypeError, ValueError):
        return "—"


def _save_upload(uploaded) -> Path:
    """把上传的文件保存到 data/，返回保存路径。"""
    data_dir = PROJECT_ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    dest = data_dir / uploaded.name
    dest.write_bytes(uploaded.getvalue())
    return dest


def _top_rank(metrics: dict, key: str, label: str) -> str:
    """取某维度销售排行第一名，返回一句话描述（维度不存在时返回空串）。"""
    table = (metrics.get("rankings") or {}).get(key)
    if not isinstance(table, pd.DataFrame) or table.empty or key not in table.columns:
        return ""
    top = table.iloc[0]
    share = top.get("销售额占比")
    share_s = _fmt_pct(share) if pd.notna(share) else "—"
    return f"- **{label}**：`{top[key]}`（销售额 {_fmt_money(top.get('销售额'))}，占比 {share_s}）"


def build_diagnostic_report(df: pd.DataFrame, detection: dict, report: dict, metrics: dict) -> str:
    """根据识别 / 清洗 / 指标结果生成一段 AI 诊断报告。

    【接口位置】当前为离线规则化字符串生成，无需 API Key。若要接入真实 LLM：
        1. 将下方拼好的 `context`（结构化上下文）作为 prompt 传给模型；
        2. 用模型返回的文本替换函数最后的 return，例如：

            from anthropic import Anthropic
            client = Anthropic()  # 读取环境变量 ANTHROPIC_API_KEY
            resp = client.messages.create(
                model="claude-sonnet-5-5", max_tokens=1024,
                system="你是数据诊断助手，请基于给定的字段识别、清洗与指标结果输出诊断报告。",
                messages=[{"role": "user", "content": context}],
            )
            return resp.content[0].text

        3. 离线规则化版本保留为无 API 时的兜底（fallback）。
    """
    lines: list[str] = []

    shape = report.get("cleaned_shape") or df.shape
    conf = detection.get("confidence", "—")
    conf_cn = {"high": "高", "medium": "中", "low": "低"}.get(conf, conf)
    lines.append("## AI 诊断报告")
    lines.append(f"**数据概览**：清洗后 {shape[0]} 行 × {shape[1]} 列，字段识别置信度 **{conf_cn}**。")

    detected = detection.get("detected") or []
    if detected:
        mapped = "、".join(f"{CANONICAL_FIELDS.get(d['field'], d['field'])}→「{d['column']}」" for d in detected)
        lines.append(f"**字段识别**：{mapped}。")
    missing = detection.get("missing") or []
    if missing:
        lines.append(f"**未识别字段**：{'、'.join(missing)}（对应图表/指标已自动跳过）。")

    dropped = sum(
        report.get(k, 0) or 0
        for k in ("dropped_duplicates", "dropped_invalid_date", "dropped_missing_sales", "dropped_negative_sales")
    )
    lines.append(f"**清洗情况**：共剔除 {dropped} 条无效数据（重复 / 无效日期 / 缺失或负值销售额）。")
    for note in report.get("notes") or []:
        if "单位" in note or "归一化" in note:
            lines.append(f"- {note}")
            break

    total_sales = float(df["sales_amount"].sum()) if "sales_amount" in df else 0.0
    lines.append(f"**核心指标**：总销售额 **{_fmt_money(total_sales)}**；")
    has_qty = "quantity" in df.columns
    if has_qty:
        lines.append(f"总销量 **{int(df['quantity'].sum()):,} 件**；")
    aov = metrics.get("aov") or {}
    for k, v in aov.items():
        lines.append(f"{AOV_LABELS.get(k, k)} **{_fmt_money(v)}**；")
    notes = metrics.get("notes") or {}
    if notes.get("客单价"):
        lines.append(f"（口径：{notes['客单价']}）")

    lines.append("**关键发现**：")
    findings = [
        _top_rank(metrics, "product_name", "销售额最高商品"),
        _top_rank(metrics, "channel", "销售额最高渠道"),
        _top_rank(metrics, "store", "销售额最高门店"),
        _top_rank(metrics, "region", "销售额最高地区"),
    ]
    findings = [f for f in findings if f]
    lines.extend(findings or ["- （数据中无可用维度字段，未生成排行发现。）"])

    mg = metrics.get("monthly_growth")
    if isinstance(mg, pd.DataFrame) and not mg.empty and "销售额环比" in mg.columns:
        mom = mg["销售额环比"].dropna()
        if not mom.empty:
            lines.append(f"- 最近一期销售额环比 **{_fmt_pct(mom.iloc[-1])}**。")

    tips: list[str] = []
    if not isinstance(mg, pd.DataFrame) or mg.shape[0] < 13:
        tips.append("样本不足 13 个月，同比暂不可计算。")
    outlier_notes = [n for n in (report.get("notes") or []) if "异常值" in n]
    if outlier_notes:
        tips.append(outlier_notes[0] + "，建议人工复核后再决定是否剔除。")
    if not has_qty:
        tips.append("数据无「数量」字段，销量口径客单价不可用。")
    lines.append("**建议**：" + (" ".join(tips) if tips else "数据质量良好，可直接用于后续分析。"))

    # 【接口位置】接真实 LLM 时：把 `context` 作为 messages 的 content 传入，
    # 并用模型返回的文本替换这一行 return；离线规则化版本作为兜底。
    context = "\n".join(lines)
    return context


# ---------------------------------------------------------------------------
# 主界面
# ---------------------------------------------------------------------------
def main() -> None:
    st.title("经济数据可视化分析")
    st.caption("read_data → clean_data → calculate_metrics → generate_charts 全流程自动执行。")

    # ---- 数据源（侧边栏） ----
    with st.sidebar:
        st.header("数据源")
        up = st.file_uploader("上传数据文件（CSV / Excel）", type=["csv", "xlsx", "xls"])
        st.caption("未上传时默认使用 assets/sample_data.csv（模拟数据）。")

    if up is not None:
        data_path = _save_upload(up)
        st.sidebar.success(f"已读取上传文件：{up.name}")
    else:
        data_path = DEFAULT_DATA
        st.sidebar.caption(f"默认数据：{data_path.name}")

    if not data_path.exists():
        st.error(f"数据文件不存在：{data_path}")
        st.stop()

    # ---- 全流程（spinner 提升体验） ----
    with st.spinner("① 读取并识别字段…"):
        df = read_file(data_path)
        detection = detect_fields(df)
    with st.spinner("② 清洗数据…"):
        cleaned, report = clean(df)
        if "error" in report:
            st.error(report["error"])
            st.stop()
    with st.spinner("③ 计算指标…"):
        metrics = compute_metrics(cleaned)
        if "__error__" in metrics:
            st.error(metrics["__error__"])
            st.stop()
    with st.spinner("④ 生成图表…"):
        figures = build_figures(metrics)

    # ---- 侧边栏：导出结果 ----
    st.session_state["cleaned_df"] = cleaned
    with st.sidebar:
        st.subheader("📥 导出结果")
        if st.button("导出 HTML 报告"):
            # 按钮触发：调用 generate_charts.save_html_report 生成离线 HTML 到 output/
            out_path = PROJECT_ROOT / "output" / "report.html"
            save_html_report(figures, out_path, title="销售数据可视化报告")
            st.success(f"HTML 报告已生成：{out_path.relative_to(PROJECT_ROOT)}")
        if "cleaned_df" in st.session_state:
            # download_button：浏览器直接弹出下载，utf-8-sig 便于 Excel 打开中文
            csv_data = st.session_state["cleaned_df"].to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                label="下载清洗后 CSV",
                data=csv_data,
                file_name="cleaned_data.csv",
                mime="text/csv",
            )

    # ---- KPI 指标卡 ----
    kpis = [("总销售额", _fmt_money(float(cleaned["sales_amount"].sum())))]
    if "quantity" in cleaned.columns:
        kpis.append(("总销量", f"{int(cleaned['quantity'].sum()):,} 件"))
    aov = metrics.get("aov") or {}
    for k, v in aov.items():
        kpis.append((AOV_LABELS.get(k, k), _fmt_money(v)))
    kpis.append(("记录数", f"{cleaned.shape[0]:,} 行"))

    kpi_cols = st.columns(len(kpis))
    for col, (label, value) in zip(kpi_cols, kpis):
        col.metric(label, value)

    st.divider()

    # ---- 左右布局：左图表 / 右指标 + AI 诊断报告 ----
    left, right = st.columns([3, 2])
    with left:
        st.subheader("可视化图表")
        if not figures:
            st.info("没有可生成的图表（字段不足）。")
        for name, fig in figures.items():
            st.plotly_chart(fig, width="stretch", key=f"fig_{name}")

    with right:
        st.subheader("指标明细")
        if aov:
            st.markdown("**客单价**")
            for k, v in aov.items():
                st.write(f"- {AOV_LABELS.get(k, k)}：{_fmt_money(v)}")

        for key, label in DIMENSION_FIELDS.items():
            table = (metrics.get("rankings") or {}).get(key)
            if isinstance(table, pd.DataFrame) and not table.empty:
                with st.expander(f"{label}排行（Top 5）"):
                    show_cols = [c for c in [key, "销售额", "销售额占比"] if c in table.columns]
                    st.dataframe(table.head(5)[show_cols])

        for key, label in [("daily", "每日"), ("weekly", "每周"), ("monthly", "每月")]:
            t = metrics.get(key)
            if isinstance(t, pd.DataFrame) and not t.empty:
                with st.expander(f"{label}汇总"):
                    st.dataframe(t)

        st.divider()
        st.markdown(build_diagnostic_report(cleaned, detection, report, metrics))


if __name__ == "__main__":
    main()
