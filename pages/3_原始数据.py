# -*- coding: utf-8 -*-
"""3_原始数据.py — 清洗前后数据对比表格。"""
from __future__ import annotations

import sys
from pathlib import Path

# 让页面脚本能 import utils/ 下的模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "utils"))

import streamlit as st


def main() -> None:
    st.title("原始数据")
    st.caption("清洗前后的数据对比。")

    raw = st.session_state.get("raw_df")
    cleaned = st.session_state.get("cleaned_df")
    report = st.session_state.get("report")

    if raw is None:
        st.error("尚未加载数据。请回到「首页」检查数据文件。")
        st.stop()

    # 清洗摘要
    if report and "error" not in report:
        original = report.get("original_shape", (len(raw), raw.shape[1]))
        cleaned_shape = report.get("cleaned_shape", (len(cleaned) if cleaned is not None else 0, raw.shape[1]))
        dropped = sum(
            report.get(k, 0) or 0
            for k in ("dropped_duplicates", "dropped_invalid_date", "dropped_missing_sales", "dropped_negative_sales")
        )
        c1, c2, c3 = st.columns(3)
        c1.metric("原始行数", f"{original[0]:,}")
        c2.metric("清洗后行数", f"{cleaned_shape[0]:,}")
        c3.metric("剔除无效数据", f"{dropped:,}")

    tab1, tab2 = st.tabs(["原始数据", "清洗后数据"])
    with tab1:
        st.dataframe(raw)
    with tab2:
        if cleaned is not None:
            st.dataframe(cleaned)
        else:
            st.info("清洗失败，无清洗后数据。")


main()
