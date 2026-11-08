# -*- coding: utf-8 -*-
"""generate_charts.py — 使用 Plotly 生成交互式图表与独立 HTML 报告。

图表按数据中**实际存在**的字段动态生成，缺失字段自动跳过：
- 时间序列：每日销售额/销量趋势、月度销售额；
- 维度排行：商品/渠道/门店/地区——有什么维度就画什么；
- 地区月度构成堆叠图与地区占比（仅当存在「地区」维度）。

规范（遵循 dataviz）：单序列单色、不加图例、标题即说明；占比用排名条形/
堆叠（不用饼图）；不用双轴图；金额与销量分开成图；每日趋势带区间滑块。

可独立运行：python generate_charts.py [文件路径] [-o 报告.html]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

from calculate_metrics import compute_metrics
from clean_data import clean
from read_data import DIMENSION_FIELDS, read_file

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# 调色板：取自 dataviz 参考调色板（已校验的分类色固定顺序，禁止循环生成）。
# 约定：销售额 = 蓝，销量 = 橙；地区堆叠用分类色 1..8。
# ---------------------------------------------------------------------------
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SALES_COLOR = SERIES[0]
QTY_COLOR = SERIES[1]
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
SECONDARY_INK = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"


def _style(fig: go.Figure, title: str | None = None, legend: bool = False, height: int = 380) -> go.Figure:
    """统一图表外观：表面色、字体、细网格线、淡化坐标轴。"""
    fig.update_layout(
        title=dict(text=title, font=dict(family=FONT, size=16, color=INK)),
        font=dict(family=FONT, color=INK),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        height=height,
        margin=dict(l=64, r=24, t=52, b=40),
        showlegend=legend,
        hoverlabel=dict(
            bgcolor="#ffffff",
            bordercolor=GRID,
            font=dict(family=FONT, size=13, color=INK),
        ),
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False, linecolor=BASELINE, tickfont=dict(color=MUTED))
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=BASELINE, tickfont=dict(color=MUTED))
    return fig


def _fold_to_other(frame: pd.DataFrame, cap: int = 8) -> pd.DataFrame:
    """分类超过 cap 时，把其余合并为「其他」。"""
    if len(frame.columns) <= cap:
        return frame
    keep = list(frame.columns[:cap])
    frame = frame.copy()
    frame["其他"] = frame.drop(columns=keep).sum(axis=1)
    return frame[keep + ["其他"]]


def build_figures(metrics: dict) -> dict[str, go.Figure]:
    """由指标结果构建一组 Plotly 图表（按数据中存在的字段动态生成）。"""
    figs: dict[str, go.Figure] = {}
    daily = metrics.get("daily")
    monthly = metrics.get("monthly")
    rankings = metrics.get("rankings") or {}

    # 1) 每日销售额趋势（折线 + 区间滑块）
    if isinstance(daily, pd.DataFrame) and not daily.empty:
        fig = go.Figure(go.Scatter(
            x=daily["日期"], y=daily["销售额"], mode="lines+markers",
            line=dict(color=SALES_COLOR, width=2),
            marker=dict(size=5, color=SALES_COLOR),
            hovertemplate="%{x|%Y-%m-%d}<br>销售额 %{y:,.0f} 元<extra></extra>",
        ))
        _style(fig, title="每日销售额趋势", legend=False, height=360)
        fig.update_layout(hovermode="x unified")
        fig.update_xaxes(rangeslider=dict(visible=True, thickness=0.06))
        figs["销售额趋势_日"] = fig

    # 2) 每日销量趋势（仅当有销量字段）
    if isinstance(daily, pd.DataFrame) and not daily.empty and "销量" in daily.columns:
        fig = go.Figure(go.Scatter(
            x=daily["日期"], y=daily["销量"], mode="lines+markers",
            line=dict(color=QTY_COLOR, width=2),
            marker=dict(size=5, color=QTY_COLOR),
            hovertemplate="%{x|%Y-%m-%d}<br>销量 %{y:,.0f} 件<extra></extra>",
        ))
        _style(fig, title="每日销量趋势", legend=False, height=360)
        fig.update_layout(hovermode="x unified")
        fig.update_xaxes(rangeslider=dict(visible=True, thickness=0.06))
        figs["销量趋势_日"] = fig

    # 3) 月度销售额（柱状）
    if isinstance(monthly, pd.DataFrame) and not monthly.empty:
        fig = go.Figure(go.Bar(
            x=monthly["月份"], y=monthly["销售额"],
            marker=dict(color=SALES_COLOR),
            hovertemplate="%{x}<br>销售额 %{y:,.0f} 元<extra></extra>",
        ))
        _style(fig, title="月度销售额", legend=False, height=360)
        figs["月度销售额"] = fig

    # 4) 各维度排行（动态：有什么维度就画什么）
    for key, label in DIMENSION_FIELDS.items():
        table = rankings.get(key)
        if not isinstance(table, pd.DataFrame) or table.empty or key not in table.columns:
            continue
        top = table.head(10).sort_values("销售额", ascending=True)
        fig = go.Figure(go.Bar(
            x=top["销售额"], y=top[key], orientation="h",
            marker=dict(color=SALES_COLOR),
            text=(top["销售额占比"] * 100).round(1).astype(str) + "%",
            textposition="outside",
            customdata=(top["销售额占比"] * 100).round(1),
            hovertemplate="%{y}<br>销售额 %{x:,.0f} 元<br>占比 %{customdata:.1f}%<extra></extra>",
        ))
        _style(fig, title=f"{label}销售额排行（Top 10）", legend=False, height=400)
        figs[f"{label}销售额排行"] = fig

    # 5) 地区月度构成（堆叠，仅当有地区维度）
    rm = metrics.get("region_monthly")
    if isinstance(rm, pd.DataFrame) and not rm.empty:
        rm = _fold_to_other(rm)
        fig = go.Figure()
        for i, r in enumerate(rm.columns):
            fig.add_trace(go.Bar(
                x=rm.index.astype(str), y=rm[r], name=r,
                marker=dict(color=SERIES[i % len(SERIES)]),
                hovertemplate="%{x}<br>" + r + " %{y:,.0f} 元<extra></extra>",
            ))
        fig.update_layout(barmode="stack")
        _style(fig, title="月度销售额构成（按地区堆叠）", legend=True, height=420)
        figs["地区月度堆叠"] = fig

        # 时间轴动画：按月份逐帧播放各地区销售额构成（≥ 2 个月才生成）。
        # 使用 px.bar + animation_frame，颜色与堆叠图保持一致（固定顺序、不循环）。
        if rm.shape[0] >= 2:
            rm_long = rm.copy()
            rm_long.index.name = "月份"
            rm_long = rm_long.reset_index().melt(
                id_vars="月份", var_name="地区", value_name="销售额"
            )
            ymax = max(float(rm.sum(axis=1).max()), 1.0) * 1.12
            region_colors = {r: SERIES[i % len(SERIES)] for i, r in enumerate(rm.columns)}
            anim = px.bar(
                rm_long,
                x="地区",
                y="销售额",
                color="地区",
                animation_frame="月份",
                animation_group="地区",
                color_discrete_map=region_colors,
                range_y=[0, ymax],
            )
            _style(anim, title="月度销售额构成动画（按地区，可播放）", legend=False, height=420)
            figs["地区月度动画"] = anim

    # 6) 地区销售额占比（排名条形，仅当有地区维度）
    if "region" in rankings:
        region = rankings["region"]
        r = region.sort_values("销售额", ascending=True)
        fig = go.Figure(go.Bar(
            x=r["销售额占比"] * 100, y=r["region"], orientation="h",
            marker=dict(color=SALES_COLOR),
            text=(r["销售额占比"] * 100).round(1).astype(str) + "%",
            textposition="outside",
            hovertemplate="%{y}<br>占比 %{x:.1f}%<extra></extra>",
        ))
        _style(fig, title="各地区销售额占比", legend=False, height=320)
        figs["地区销售额占比"] = fig

    return figs


def save_html_report(figures: dict, out_path: Path, title: str = "销售数据可视化报告") -> Path:
    """把多张图表合并为一个离线可打开的 HTML 报告。"""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    divs = []
    for name, fig in figures.items():
        div = fig.to_html(full_html=False, include_plotlyjs=False)
        divs.append(f'<section><h2 class="chart-title">{name}</h2>{div}</section>')

    css = (
        "body {{ font-family: {font}; margin: 0; background: #f9f9f7; color: {ink}; }}\n"
        ".container {{ max-width: 1080px; margin: 0 auto; padding: 32px 20px 64px; }}\n"
        "h1 {{ font-size: 26px; font-weight: 600; }}\n"
        "h2.chart-title {{ font-size: 15px; font-weight: 600; color: {secondary}; margin: 28px 0 4px; }}\n"
        ".note {{ color: {muted}; font-size: 13px; margin-bottom: 24px; }}\n"
    ).format(font=FONT, ink=INK, secondary=SECONDARY_INK, muted=MUTED)

    html = (
        "<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<title>{title}</title>\n<style>{css}</style>\n"
        f"<script>{get_plotlyjs()}</script>\n</head>\n<body>\n"
        '<div class="container">\n'
        f"<h1>{title}</h1>\n"
        '<p class="note">数据为模拟数据。图表可缩放、悬停查看数值。金额单位：元。</p>\n'
        f"{''.join(divs)}\n</div>\n</body>\n</html>\n"
    )
    out_path.write_text(html, encoding="utf-8")
    return out_path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成交互式图表与 HTML 报告")
    ap.add_argument("path", nargs="?", default=None, help="数据文件路径（缺省使用 assets/sample_data.csv）")
    ap.add_argument("-o", "--out", default=None, help="HTML 报告输出路径（默认 output/report.html）")
    args = ap.parse_args(argv)

    path = args.path or str(PROJECT_ROOT / "assets" / "sample_data.csv")
    df = read_file(path)
    cleaned, report = clean(df)
    if "error" in report:
        print("⚠ 清洗中止：", report["error"])
        return 1

    metrics = compute_metrics(cleaned)
    if "__error__" in metrics:
        print("⚠ 指标计算中止：", metrics["__error__"])
        return 1

    figs = build_figures(metrics)

    out_dir = PROJECT_ROOT / "output"
    out_dir.mkdir(exist_ok=True)
    out_path = Path(args.out) if args.out else out_dir / "report.html"
    save_html_report(figs, out_path)

    charts_dir = out_dir / "charts"
    charts_dir.mkdir(exist_ok=True)
    for name, fig in figs.items():
        fig.write_html(charts_dir / f"{name}.html", include_plotlyjs="cdn")

    print(f"生成 {len(figs)} 张图表。")
    print(f"完整 HTML 报告：{out_path}")
    print(f"单张图表目录：{charts_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
