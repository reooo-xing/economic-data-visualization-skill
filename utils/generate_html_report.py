# -*- coding: utf-8 -*-
"""generate_html_report.py — 自定义多图表生成器（Streamlit）。

运行：streamlit run utils/generate_html_report.py

功能：
- 顶部下拉框选择数据文件（CSV，可上传到 data/）；
- 动态添加多个「图表配置组」（X 轴 / Y 轴 / 图表类型：折线图/柱状图/饼图/散点图）；
- 【一键生成所有图表】批量生成，直接以「标题 + 图表」展示，并保存到 output/charts/；
- 缺失 / 非法字段的图表组自动跳过并提示，绝不中断整体。

图表组状态由 st.session_state 管理。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from generate_charts import BASELINE, FONT, GRID, INK, MUTED, SALES_COLOR, SECONDARY_INK, SERIES, SURFACE, _style
from read_data import find_default_data_file, read_file

PROJECT_ROOT = Path(__file__).resolve().parent.parent

PLACEHOLDER = "（请选择）"
CHART_TYPES = ["折线图", "柱状图", "饼图", "散点图"]

st.set_page_config(page_title="自定义多图表生成器", layout="wide")


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def discover_data_files() -> list[Path]:
    """发现项目内可选的 Excel / CSV 文件（assets/、data/、项目根目录）。"""
    found: set[Path] = set()
    for d in (PROJECT_ROOT / "assets", PROJECT_ROOT / "data", PROJECT_ROOT):
        if d.is_dir():
            found.update(
                p for p in d.iterdir()
                if p.is_file() and p.suffix.lower() in {".csv", ".xlsx", ".xls", ".xlsm"}
            )
    return sorted(found, key=lambda p: str(p).lower())


def save_uploaded(uploaded) -> Path:
    """把上传的 Excel / CSV 保存到 data/，返回保存路径。"""
    data_dir = PROJECT_ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    dest = data_dir / uploaded.name
    dest.write_bytes(uploaded.getvalue())
    return dest


def reset_groups() -> None:
    """重置图表组状态（数据文件变化时调用），并清空旧结果。"""
    for k in list(st.session_state.keys()):
        if k.startswith(("x_", "y_", "type_", "del_")):
            del st.session_state[k]
    st.session_state["next_id"] = 1
    st.session_state["groups"] = [{"id": 1, "x": None, "y": None, "chart_type": "折线图"}]
    st.session_state.pop("results", None)
    st.session_state.pop("saved_files", None)


def _safe(name) -> str:
    """把字段名转成安全的文件名片段。"""
    if not name:
        return "空"
    return "".join(ch if ch not in '\\/:*?"<>|' else "_" for ch in str(name))


def _is_date_like(s: pd.Series) -> bool:
    """判断某列是否可解析为日期。"""
    try:
        parsed = pd.to_datetime(s, errors="coerce", format="mixed")
        return bool(parsed.notna().mean() > 0.8)
    except Exception:
        return False


def _aggregate(df: pd.DataFrame, x: str, y: str, chart_type: str):
    """按 X 汇总 Y（求和），返回 (agg_df 或 None, 错误信息或 None)。"""
    y_num = pd.to_numeric(df[y], errors="coerce")
    if y_num.isna().all():
        return None, f"Y 轴字段「{y}」不是数值，无法绘制{chart_type}"

    x_is_date = _is_date_like(df[x])
    x_vals = pd.to_datetime(df[x], errors="coerce", format="mixed") if x_is_date else df[x]
    tmp = pd.DataFrame({"x": x_vals, "y": y_num}).dropna(subset=["x", "y"])
    if tmp.empty:
        return None, f"字段「{x}」/「{y}」没有有效数据"

    agg = tmp.groupby("x", dropna=False)["y"].sum().reset_index()
    if chart_type == "折线图":
        agg = agg.sort_values("x")  # 时间/数值按 X 升序
    elif chart_type == "柱状图":
        if x_is_date or pd.api.types.is_numeric_dtype(df[x]):
            agg = agg.sort_values("x")
        else:
            agg = agg.sort_values("y", ascending=False)  # 分类按 Y 降序（排行）
    else:  # 饼图按值降序
        agg = agg.sort_values("y", ascending=False)
    return agg, None


def make_chart(df: pd.DataFrame, x, y, chart_type: str, title: str = ""):
    """按 (x, y, chart_type) 生成一张 Plotly 图。返回 (fig 或 None, 错误信息或 None)。"""
    if x is None or x == PLACEHOLDER or y is None or y == PLACEHOLDER:
        return None, "未选择 X 轴或 Y 轴字段"
    if x not in df.columns:
        return None, f"X 轴字段「{x}」不存在"
    if y not in df.columns:
        return None, f"Y 轴字段「{y}」不存在"
    if x == y:
        return None, "X 轴与 Y 轴选择了同一个字段"

    try:
        if chart_type == "散点图":
            xs = pd.to_numeric(df[x], errors="coerce")
            ys = pd.to_numeric(df[y], errors="coerce")
            tmp = pd.DataFrame({"x": xs, "y": ys}).dropna()
            if tmp.empty:
                return None, "散点图需要数值型 X/Y 字段，且不能全为空"
            fig = go.Figure(go.Scatter(
                x=tmp["x"], y=tmp["y"], mode="markers",
                marker=dict(color=SALES_COLOR, size=8, line=dict(color=SURFACE, width=1)),
                hovertemplate="X %{x}<br>Y %{y}<extra></extra>",
            ))
            _style(fig, title=title or f"{y} vs {x}（散点图）", legend=False, height=400)
            return fig, None

        agg, err = _aggregate(df, x, y, chart_type)
        if err:
            return None, err

        if chart_type == "折线图":
            fig = go.Figure(go.Scatter(
                x=agg["x"], y=agg["y"], mode="lines+markers",
                line=dict(color=SALES_COLOR, width=2),
                marker=dict(size=8, color=SALES_COLOR),
                hovertemplate="%{x}<br>%{y:,.4g}<extra></extra>",
            ))
            _style(fig, title=title or f"{y} vs {x}（折线图）", legend=False, height=400)
        elif chart_type == "柱状图":
            fig = go.Figure(go.Bar(
                x=agg["x"], y=agg["y"],
                marker=dict(color=SALES_COLOR),
                hovertemplate="%{x}<br>%{y:,.4g}<extra></extra>",
            ))
            _style(fig, title=title or f"{y} vs {x}（柱状图）", legend=False, height=400)
        else:  # 饼图
            fig = go.Figure(go.Pie(
                labels=agg["x"], values=agg["y"],
                marker=dict(colors=SERIES[: len(agg)]),
                hovertemplate="%{label}<br>%{value:,.4g}（%{percent}）<extra></extra>",
            ))
            _style(fig, title=title or f"{y} vs {x}（饼图）", legend=False, height=400)
        return fig, None
    except Exception as e:  # 任何异常都不中断整体，只跳过该组
        return None, f"生成失败：{e}"


def save_results(results: list[dict]) -> list[str]:
    """把生成的图表保存到 output/charts/，返回保存路径列表。"""
    charts_dir = PROJECT_ROOT / "output" / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    for r in results:
        if r["fig"] is None:
            continue
        g = r["group"]
        fname = f"{r['index']:02d}_{g['chart_type']}_{_safe(g['y'])}_{_safe(g['x'])}.html"
        path = charts_dir / fname
        r["fig"].write_html(path)
        saved.append(str(path))
    return saved


# ---------------------------------------------------------------------------
# 主界面
# ---------------------------------------------------------------------------
def main() -> None:
    st.title("自定义多图表生成器")
    st.caption("选择数据文件 → 配置多组 X/Y/图表类型 → 一键批量生成。缺失字段自动跳过，绝不报错。")

    # ---- 侧边栏：上传（保存到 data/，加入下拉框） ----
    with st.sidebar:
        st.header("上传数据")
        up = st.file_uploader("上传 CSV / Excel（保存到 data/）", type=["csv", "xlsx", "xls"])
        if up is not None:
            sig = f"{up.name}:{len(up.getvalue())}"
            if st.session_state.get("processed_upload") != sig:
                dest = save_uploaded(up)
                st.session_state["processed_upload"] = sig
                st.session_state["data_file_selector"] = str(dest)
                st.session_state["current_file"] = None  # 触发重置
                st.rerun()

    # ---- 顶部：选择数据文件（CSV / Excel）下拉框 ----
    files = discover_data_files()
    if not files:
        st.error("未找到可用数据文件。请上传，或在 assets/ 放入 CSV / Excel。")
        st.stop()

    options = [str(f) for f in files]
    default_path = str(find_default_data_file(PROJECT_ROOT))
    default_idx = options.index(default_path) if default_path in options else 0

    file_str = st.selectbox(
        "选择数据文件（CSV / Excel）",
        options=options,
        format_func=lambda s: str(Path(s).relative_to(PROJECT_ROOT)),
        index=default_idx,
        key="data_file_selector",
    )

    # 数据文件变化时重置图表组与结果
    if st.session_state.get("current_file") != file_str:
        reset_groups()
        st.session_state["current_file"] = file_str
    if "groups" not in st.session_state:
        reset_groups()

    # ---- 读取数据 ----
    df = read_file(file_str)
    st.caption(f"数据列：{', '.join(str(c) for c in df.columns)}（共 {df.shape[0]} 行 × {df.shape[1]} 列）")
    with st.expander("数据预览（前 5 行）"):
        st.dataframe(df.head(5))

    field_options = [PLACEHOLDER] + [str(c) for c in df.columns]

    # ---- 图表配置组（动态增删） ----
    st.subheader("图表配置组")
    for idx, g in enumerate(st.session_state["groups"]):
        gid = g["id"]
        with st.container(border=True):
            top = st.columns([3, 1])
            top[0].markdown(f"**第 {idx + 1} 个图表配置组**")
            if len(st.session_state["groups"]) > 1:
                if top[1].button("🗑 删除", key=f"del_{gid}"):
                    st.session_state["groups"] = [grp for grp in st.session_state["groups"] if grp["id"] != gid]
                    st.rerun()
            c1, c2, c3 = st.columns(3)
            g["x"] = c1.selectbox("X 轴字段", field_options, key=f"x_{gid}")
            g["y"] = c2.selectbox("Y 轴字段", field_options, key=f"y_{gid}")
            g["chart_type"] = c3.selectbox("图表类型", CHART_TYPES, key=f"type_{gid}")

    if st.button("➕ 添加更多图表"):
        st.session_state["next_id"] += 1
        st.session_state["groups"].append({
            "id": st.session_state["next_id"], "x": None, "y": None, "chart_type": "折线图",
        })

    # ---- 一键生成 ----
    st.divider()
    if st.button("🚀 一键生成所有图表", type="primary"):
        results: list[dict] = []
        for idx, g in enumerate(st.session_state["groups"]):
            title = f"第 {idx + 1} 组：{g['y']} vs {g['x']}（{g['chart_type']}）"
            fig, err = make_chart(df, g["x"], g["y"], g["chart_type"], title=title)
            results.append({"index": idx + 1, "group": dict(g), "fig": fig, "error": err})
        st.session_state["saved_files"] = save_results(results)
        st.session_state["results"] = results

    # ---- 展示结果 ----
    results = st.session_state.get("results")
    if results:
        st.subheader("生成的图表")
        ok = sum(1 for r in results if r["fig"] is not None)
        for r in results:
            if r["fig"] is not None:
                st.plotly_chart(r["fig"], width="stretch")
            else:
                st.error(f"第 {r['index']} 组：{r['error']}（已跳过该组）")
        st.success(f"成功生成 {ok} / {len(results)} 张图表")
        saved = st.session_state.get("saved_files") or []
        if saved:
            st.caption("已保存到 output/charts/：" + "、".join(Path(s).name for s in saved))


if __name__ == "__main__":
    main()
