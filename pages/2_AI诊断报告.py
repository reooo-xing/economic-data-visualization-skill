# -*- coding: utf-8 -*-
"""2_AI诊断报告.py — 规则化生成的诊断文本。

数据来自 st.session_state（由 Home.py 缓存）。当前为离线规则化字符串生成，
不接真实 API；接口位置见 build_diagnostic_report 的注释。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 让页面脚本能 import utils/ 下的模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "utils"))

import pandas as pd
import streamlit as st

from read_data import CANONICAL_FIELDS
from ui_helpers import AOV_LABELS, fmt_money, fmt_pct


def _top_rank(metrics: dict, key: str, label: str) -> str:
    """取某维度销售排行第一名，返回一句话描述（维度不存在时返回空串）。"""
    table = (metrics.get("rankings") or {}).get(key)
    if not isinstance(table, pd.DataFrame) or table.empty or key not in table.columns:
        return ""
    top = table.iloc[0]
    share = top.get("销售额占比")
    share_s = fmt_pct(share) if pd.notna(share) else "—"
    return f"- **{label}**：`{top[key]}`（销售额 {fmt_money(top.get('销售额'))}，占比 {share_s}）"


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
    lines.append(f"**核心指标**：总销售额 **{fmt_money(total_sales)}**；")
    has_qty = "quantity" in df.columns
    if has_qty:
        lines.append(f"总销量 **{int(df['quantity'].sum()):,} 件**；")
    aov = metrics.get("aov") or {}
    for k, v in aov.items():
        lines.append(f"{AOV_LABELS.get(k, k)} **{fmt_money(v)}**；")
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
            lines.append(f"- 最近一期销售额环比 **{fmt_pct(mom.iloc[-1])}**。")

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


def main() -> None:
    st.title("AI 诊断报告")
    st.caption("基于字段识别、清洗结果与指标规则化生成（未接真实 API）。")

    cleaned = st.session_state.get("cleaned_df")
    detection = st.session_state.get("detection")
    report = st.session_state.get("report")
    metrics = st.session_state.get("metrics")

    if cleaned is None:
        st.error("尚未加载数据。请回到「首页」检查数据文件。")
        st.stop()
    if "error" in (report or {}):
        st.error(report["error"])
        st.stop()
    if not metrics or "__error__" in metrics:
        st.error("指标计算失败，无法生成诊断报告。")
        st.stop()

    st.markdown(build_diagnostic_report(cleaned, detection, report, metrics))

    with st.expander("口径说明"):
        for k, v in (metrics.get("notes") or {}).items():
            st.write(f"- {k}：{v}")


main()
