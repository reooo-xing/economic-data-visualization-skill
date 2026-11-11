# -*- coding: utf-8 -*-
"""generate_charts.py — 生成图表（lieflat-charts Mono 灰阶风格）。

风格遵循 lieflat-charts：
- 纸灰底 #F0EFEB + 炭黑墨 #1C1C1A，7 级灰阶阶梯；明度即数据（最重要 = 最黑）。
- 平面无阴影、无边框，靠留白分卡；图表本体不内嵌标题。
- 卡片式排版（结论标题 / 副标题 / 注释 / 来源行）由 build_chart_meta 输出，
  交由页面用 HTML 渲染（这样字体字重、负字距都可控）。

图表按数据中**实际存在**的字段动态生成，缺失字段自动跳过：
- 时间序列：每日销售额 / 销量趋势、月度销售额；
- 维度排行：商品 / 渠道 / 门店 / 地区——有什么维度就画什么；
- 地区月度构成堆叠图与地区占比（仅当存在「地区」维度）。

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
from read_data import DIMENSION_FIELDS, find_default_data_file, read_file
from rung_charts import build_hairline_line, build_rung_bars, build_tick_donut, nice_unit

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = find_default_data_file(PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Mono 灰阶（取自 lieflat-charts 的 mono-tokens.js）。明度即数据。
# ---------------------------------------------------------------------------
INK = "#1C1C1A"      # 墨：主数据、标题、强调（最重要 = 最黑）
PAPER = "#F0EFEB"    # 纸：页面底色 / 图表底色
MUTED = "#8F8E88"    # 次级文字、副标题
FAINT = "#C6C5BF"    # 来源行、辅助刻度
GRID = "#DEDDD6"     # 网格线、发丝线
BASELINE = "#C6C5BF" # 轴线
# 7 级灰阶阶梯：多系列按重要性从黑到浅分配
LADDER = ["#1C1C1A", "#4A4944", "#6A6963", "#8F8E88", "#B0AFA9", "#C6C5BF", "#D8D7D1"]

FONT = "Inter, system-ui, -apple-system, 'Segoe UI', sans-serif"


def _style(fig: go.Figure, legend: bool = False, height: int = 340) -> go.Figure:
    """统一 Mono 外观：纸底、炭黑墨、Inter、细网格、淡化坐标轴、无阴影。"""
    fig.update_layout(
        font=dict(family=FONT, color=INK),
        paper_bgcolor=PAPER,
        plot_bgcolor=PAPER,
        height=height,
        margin=dict(l=56, r=24, t=24, b=40),
        showlegend=legend,
        hoverlabel=dict(
            bgcolor=INK, bordercolor=INK,
            font=dict(family=FONT, size=12, color=PAPER),
        ),
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False, linecolor=BASELINE, tickfont=dict(color=MUTED, size=11))
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=BASELINE, tickfont=dict(color=MUTED, size=11))
    return fig


def _fold_to_other(frame: pd.DataFrame, cap: int = 6) -> pd.DataFrame:
    """分类超过 cap 时，把其余合并为「其他」（灰阶阶梯只有 7 级，留出「其他」的浅灰位）。"""
    if len(frame.columns) <= cap:
        return frame
    keep = list(frame.columns[:cap])
    frame = frame.copy()
    frame["其他"] = frame.drop(columns=keep).sum(axis=1)
    return frame[keep + ["其他"]]


def _fold_items(items: list, cap: int = 6) -> list:
    """饼图段数超过 cap 时，把其余合并为「其他」（灰阶阶梯最多 7 级，留出浅灰位）。"""
    items = [(str(l), float(v)) for l, v in items]
    if len(items) <= cap:
        return items
    keep = items[: cap - 1]
    rest = sum(v for _, v in items[cap - 1:])
    return keep + [("其他", rest)]


# 可切换「图表类型」的柱状类图表：时间柱支持 横档柱/柱状图/折线图；分类柱支持 横档柱/柱状图/饼图
TIME_BAR_TYPES = ["横档柱", "柱状图", "折线图"]
CAT_BAR_TYPES = ["横档柱", "柱状图", "饼图"]


def _bar_specs(metrics: dict) -> dict[str, dict]:
    """收集所有柱状类图表的数据与配置，供默认渲染与「图表类型」切换共用。"""
    specs: dict[str, dict] = {}
    monthly = metrics.get("monthly")
    rankings = metrics.get("rankings") or {}

    # 月度销售额（时间柱）
    if isinstance(monthly, pd.DataFrame) and not monthly.empty:
        unit = nice_unit(float(monthly["销售额"].max()))
        items = list(zip(monthly["月份"].astype(str), monthly["销售额"].astype(float)))
        specs["月度销售额"] = {
            "items": items,
            "horizontal": False,
            "unit": unit,
            "value_fmt": lambda v: f"{v:,.0f}",
            "hover_fmt": lambda v: f"{v:,.0f} 元",
            "footer": f"ONE RUNG = ¥{unit:,.0f} · DOT MARKS EVERY FIFTH",
            "types": TIME_BAR_TYPES,
        }

    # 各维度排行（分类柱）
    for key, label in DIMENSION_FIELDS.items():
        table = rankings.get(key)
        if not isinstance(table, pd.DataFrame) or table.empty or key not in table.columns:
            continue
        top = table.head(10).sort_values("销售额", ascending=False)
        unit = nice_unit(float(top["销售额"].max()))
        items = list(zip(top[key].astype(str), top["销售额"].astype(float)))
        specs[f"{label}销售额排行"] = {
            "items": items,
            "horizontal": True,
            "unit": unit,
            "value_fmt": lambda v: f"{v:,.0f}",
            "hover_fmt": lambda v: f"{v:,.0f} 元",
            "footer": f"ONE RUNG = ¥{unit:,.0f} · DOT MARKS EVERY FIFTH",
            "types": CAT_BAR_TYPES,
            "donut_sub": "销售额构成",
        }

    # 地区销售额占比（分类柱，1 档 = 1 个百分点）
    if "region" in rankings:
        region = rankings["region"]
        if isinstance(region, pd.DataFrame) and not region.empty:
            r = region.sort_values("销售额占比", ascending=False)
            items = list(zip(r["region"].astype(str), (r["销售额占比"].astype(float) * 100)))
            specs["地区销售额占比"] = {
                "items": items,
                "horizontal": True,
                "unit": 1.0,
                "value_fmt": lambda v: f"{v:.1f}%",
                "hover_fmt": lambda v: f"{v:.1f}%",
                "footer": "ONE RUNG = 1 P.P. · DOT MARKS EVERY FIFTH",
                "types": CAT_BAR_TYPES,
                "donut_sub": "销售额占比",
            }

    return specs


def render_bar_chart(spec: dict, chart_type: str = "横档柱"):
    """按 chart_type 渲染一组 (label, value)。

    横档柱 / 折线图 / 饼图返回 lieflat 手写 SVG 字符串（可离线、带入场动效）；
    柱状图返回 Plotly 图（可缩放悬停）。
    """
    items = spec["items"]
    if chart_type == "横档柱":
        return build_rung_bars(
            items,
            horizontal=spec["horizontal"],
            unit=spec["unit"],
            value_fmt=spec["value_fmt"],
            hover_fmt=spec["hover_fmt"],
            footer=spec["footer"],
        )

    labels = [str(l) for _, l in items]
    vals = [float(v) for _, v in items]
    hover = [spec["hover_fmt"](v) for v in vals]

    if chart_type == "柱状图":
        if spec["horizontal"]:
            fig = go.Figure(go.Bar(
                x=vals, y=labels, orientation="h",
                marker=dict(color=INK),
                customdata=hover,
                hovertemplate="%{y}<br>%{customdata}<extra></extra>",
            ))
        else:
            fig = go.Figure(go.Bar(
                x=labels, y=vals,
                marker=dict(color=INK),
                customdata=hover,
                hovertemplate="%{x}<br>%{customdata}<extra></extra>",
            ))
        _style(fig, legend=False, height=360)

    elif chart_type == "折线图":
        return build_hairline_line(
            items,
            value_fmt=spec["value_fmt"],
            hover_fmt=spec["hover_fmt"],
            footer="发丝折线 · 每点 = 一月",
        )

    elif chart_type == "饼图":
        return build_tick_donut(
            _fold_items(items),
            footer="每格 = 1%",
            center_sub=spec.get("donut_sub", "构成"),
        )
    else:
        return None

    return fig


def bar_type_options(name: str, metrics: dict) -> list[str] | None:
    """返回某张图可切换的图表类型列表；非柱状类图表返回 None。"""
    spec = _bar_specs(metrics).get(name)
    return spec["types"] if spec else None


def build_bar_variant(name: str, metrics: dict, chart_type: str):
    """按指定类型重建某张柱状类图表（供数据看板「图表类型」切换）。"""
    spec = _bar_specs(metrics).get(name)
    if not spec or chart_type not in spec["types"]:
        return None
    return render_bar_chart(spec, chart_type)


def build_figures(metrics: dict) -> dict[str, "go.Figure | str"]:
    """由指标结果构建一组 Mono 风格图表（按数据中存在的字段动态生成）。

    返回 dict[str, go.Figure | str]：时间序列 / 堆叠 / 动画用 Plotly（可缩放悬停），
    实心柱状图（月度销售额、各维度排行、地区占比）改用 lieflat「横档柱」SVG 字符串
    （柱身 = 一格格明度不同的横档），由页面 / 报告按类型分别渲染。
    """
    figs: dict[str, "go.Figure | str"] = {}
    daily = metrics.get("daily")
    specs = _bar_specs(metrics)

    # 1) 每日销售额趋势（发丝折线 + 区间滑块）
    if isinstance(daily, pd.DataFrame) and not daily.empty:
        fig = go.Figure(go.Scatter(
            x=daily["日期"], y=daily["销售额"], mode="lines",
            line=dict(color=INK, width=1.5),
            hovertemplate="%{x|%Y-%m-%d}<br>销售额 %{y:,.0f} 元<extra></extra>",
        ))
        _style(fig, height=340)
        fig.update_layout(hovermode="x unified")
        fig.update_xaxes(rangeslider=dict(visible=True, thickness=0.05, bgcolor=PAPER, bordercolor=GRID))
        figs["销售额趋势_日"] = fig

    # 2) 每日销量趋势（仅当有销量字段）
    if isinstance(daily, pd.DataFrame) and not daily.empty and "销量" in daily.columns:
        fig = go.Figure(go.Scatter(
            x=daily["日期"], y=daily["销量"], mode="lines",
            line=dict(color=LADDER[1], width=1.5),
            hovertemplate="%{x|%Y-%m-%d}<br>销量 %{y:,.0f} 件<extra></extra>",
        ))
        _style(fig, height=340)
        fig.update_layout(hovermode="x unified")
        fig.update_xaxes(rangeslider=dict(visible=True, thickness=0.05, bgcolor=PAPER, bordercolor=GRID))
        figs["销量趋势_日"] = fig

    # 3) 月度销售额（默认横档柱；数据看板可切换 横档柱/柱状图/折线图）
    if "月度销售额" in specs:
        figs["月度销售额"] = render_bar_chart(specs["月度销售额"], "横档柱")

    # 4) 各维度排行（默认横向横档柱；可切换 横档柱/柱状图/饼图）
    for key, label in DIMENSION_FIELDS.items():
        name = f"{label}销售额排行"
        if name in specs:
            figs[name] = render_bar_chart(specs[name], "横档柱")

    # 5) 地区月度构成（堆叠，仅当有地区维度）
    rm = metrics.get("region_monthly")
    if isinstance(rm, pd.DataFrame) and not rm.empty:
        rm = _fold_to_other(rm)
        fig = go.Figure()
        for i, r in enumerate(rm.columns):
            fig.add_trace(go.Bar(
                x=rm.index.astype(str), y=rm[r], name=r,
                marker=dict(color=LADDER[i % len(LADDER)]),
                hovertemplate="%{x}<br>" + r + " %{y:,.0f} 元<extra></extra>",
            ))
        fig.update_layout(
            barmode="stack",
            legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(family=FONT, size=11, color=INK), orientation="h"),
        )
        _style(fig, legend=True, height=400)
        figs["地区月度堆叠"] = fig

        # 时间轴动画：按月份逐帧播放各地区销售额构成（≥ 2 个月才生成）。
        if rm.shape[0] >= 2:
            rm_long = rm.copy()
            rm_long.index.name = "月份"
            rm_long = rm_long.reset_index().melt(id_vars="月份", var_name="地区", value_name="销售额")
            ymax = max(float(rm.sum(axis=1).max()), 1.0) * 1.12
            region_colors = {r: LADDER[i % len(LADDER)] for i, r in enumerate(rm.columns)}
            anim = px.bar(
                rm_long,
                x="地区", y="销售额", color="地区",
                animation_frame="月份", animation_group="地区",
                color_discrete_map=region_colors,
                range_y=[0, ymax],
            )
            _style(anim, legend=False, height=400)
            figs["地区月度动画"] = anim

    # 6) 地区销售额占比（默认横向横档柱；可切换 横档柱/柱状图/饼图）
    if "地区销售额占比" in specs:
        figs["地区销售额占比"] = render_bar_chart(specs["地区销售额占比"], "横档柱")

    return figs


def build_chart_meta(metrics: dict) -> dict[str, dict]:
    """为每张图表输出卡片文案：结论标题 / 副标题 / 注释 / 来源行。

    返回 {图名: {"title","subtitle","note","source"}}，键与 build_figures 一一对应。
    注释是从数据实时算出的洞察（峰值、占比、头部集中度等），不是套话。
    """
    meta: dict[str, dict] = {}
    daily = metrics.get("daily")
    monthly = metrics.get("monthly")
    rankings = metrics.get("rankings") or {}
    region_monthly = metrics.get("region_monthly")

    # 1) 每日销售额
    if isinstance(daily, pd.DataFrame) and not daily.empty and "销售额" in daily.columns:
        s = daily["销售额"]
        span = f"{daily['日期'].min():%Y-%m-%d} 至 {daily['日期'].max():%Y-%m-%d}"
        peak = daily.loc[s.idxmax()]; low = daily.loc[s.idxmin()]
        meta["销售额趋势_日"] = {
            "title": "每日销售额",
            "subtitle": span + " · 单位 元",
            "note": (f"峰值 {peak['销售额']:,.0f} 元（{peak['日期']:%m-%d}），"
                     f"谷值 {low['销售额']:,.0f} 元（{low['日期']:%m-%d}）。"),
            "source": "sales · daily · 模拟数据",
        }

    # 2) 每日销量
    if isinstance(daily, pd.DataFrame) and not daily.empty and "销量" in daily.columns:
        q = daily["销量"]
        span = f"{daily['日期'].min():%Y-%m-%d} 至 {daily['日期'].max():%Y-%m-%d}"
        peak = daily.loc[q.idxmax()]; low = daily.loc[q.idxmin()]
        meta["销量趋势_日"] = {
            "title": "每日销量",
            "subtitle": span + " · 单位 件",
            "note": (f"峰值 {int(peak['销量']):,} 件（{peak['日期']:%m-%d}），"
                     f"谷值 {int(low['销量']):,} 件（{low['日期']:%m-%d}）。"),
            "source": "volume · daily · 模拟数据",
        }

    # 3) 月度销售额
    if isinstance(monthly, pd.DataFrame) and not monthly.empty:
        s = monthly["销售额"]
        total = float(s.sum()) or 0.0
        peak = monthly.loc[s.idxmax()]; low = monthly.loc[s.idxmin()]
        share = (float(s.max()) / total) if total else 0.0
        meta["月度销售额"] = {
            "title": "月度销售额",
            "subtitle": f"{monthly['月份'].iloc[0]} 至 {monthly['月份'].iloc[-1]} · 单位 元",
            "note": (f"{peak['月份']} 最高 {peak['销售额']:,.0f} 元（占全期 {share:.0%}），"
                     f"{low['月份']} 最低 {low['销售额']:,.0f} 元。"),
            "source": "sales · monthly · 模拟数据",
        }

    # 4) 各维度排行
    for key, label in DIMENSION_FIELDS.items():
        table = rankings.get(key)
        if not isinstance(table, pd.DataFrame) or table.empty or key not in table.columns:
            continue
        total = float(table["销售额"].sum()) or 0.0
        top1 = table.iloc[0]
        top3_share = (float(table["销售额"].head(3).sum()) / total) if total else 0.0
        meta[f"{label}销售额排行"] = {
            "title": f"{label}销售额排行",
            "subtitle": f"Top 10 · 共 {len(table)} 个{label} · 按销售额降序",
            "note": (f"「{top1[key]}」居首，占 {float(top1['销售额占比']):.0%}；"
                     f"头部 3 名合计占 {top3_share:.0%}。"),
            "source": f"{label} · ranking · 模拟数据",
        }

    # 5) 地区月度堆叠 + 动画 + 占比
    if isinstance(region_monthly, pd.DataFrame) and not region_monthly.empty:
        totals = region_monthly.sum(axis=0).sort_values(ascending=False)
        total = float(totals.sum()) or 0.0
        top_region = str(totals.index[0])
        top_share = (float(totals.iloc[0]) / total) if total else 0.0
        meta["地区月度堆叠"] = {
            "title": "月度销售额构成",
            "subtitle": f"按地区堆叠 · {region_monthly.index[0]} 至 {region_monthly.index[-1]} · 单位 元",
            "note": f"「{top_region}」累计贡献最高，占 {top_share:.0%}。",
            "source": "region · stacked · 模拟数据",
        }
        if region_monthly.shape[0] >= 2:
            meta["地区月度动画"] = {
                "title": "地区构成逐月变化",
                "subtitle": "按月份逐帧播放 · 各地区销售额",
                "note": "点击播放，观察各地区份额随月份的迁移。",
                "source": "region · animated · 模拟数据",
            }
        if "region" in rankings:
            r = rankings["region"].sort_values("销售额", ascending=False)
            top = r.iloc[0]
            note = f"「{top['region']}」占 {float(top['销售额占比']):.0%}"
            if len(r) >= 2:
                gap = float(top['销售额占比']) - float(r.iloc[1]['销售额占比'])
                note += f"，领先次位 {gap:.0%}。"
            else:
                note += "。"
            meta["地区销售额占比"] = {
                "title": "各地区销售额占比",
                "subtitle": f"共 {len(r)} 个地区 · 占比合计 100%",
                "note": note,
                "source": "region · share · 模拟数据",
            }

    return meta


def build_html_report(figures: dict, title: str = "销售数据可视化报告",
                      meta: dict | None = None) -> str:
    """把多张图表合并为一段离线可打开的 HTML（Mono 风格），返回 HTML 字符串。"""
    meta = meta or {}

    divs = []
    for name, fig in figures.items():
        m = meta.get(name, {})
        mtitle = m.get("title") or name
        msub = m.get("subtitle") or ""
        mnote = m.get("note") or ""
        msrc = m.get("source") or ""
        header = f'<h2 class="chart-title">{mtitle}</h2>'
        if msub:
            header += f'<p class="chart-sub">{msub}</p>'
        if isinstance(fig, str):
            div = f'<div class="rung-chart">{fig}</div>'
        else:
            div = fig.to_html(full_html=False, include_plotlyjs=False)
        note_html = f'<p class="chart-note">💡 {mnote}</p>' if mnote else ""
        src_html = f'<p class="chart-src">{msrc}</p>' if msrc else ""
        divs.append(f'<section>{header}{div}{note_html}{src_html}</section>')

    css = (
        "@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');\n"
        "body {{ margin: 0; background: {paper}; color: {ink}; "
        "font-family: {font}; -webkit-font-smoothing: antialiased; }}\n"
        ".container {{ max-width: 1080px; margin: 0 auto; padding: 40px 24px 72px; }}\n"
        "h1 {{ font-size: 28px; font-weight: 700; letter-spacing: -0.02em; }}\n"
        "section {{ margin: 32px 0; }}\n"
        "h2.chart-title {{ font-size: 16.5px; font-weight: 700; letter-spacing: -0.02em; margin: 0 0 2px; }}\n"
        ".chart-sub {{ font-size: 11.5px; color: {muted}; margin: 0 0 8px; }}\n"
        ".chart-note {{ font-size: 13px; color: {gray}; border-left: 3px solid {ink}; "
        "padding: 4px 0 4px 10px; margin: 4px 0 8px; line-height: 1.6; }}\n"
        ".chart-src {{ font-size: 9.5px; font-weight: 500; letter-spacing: 0.08em; "
        "text-transform: uppercase; color: {faint}; margin: 0; }}\n"
        ".rung-chart {{ margin: 8px 0 4px; max-width: 760px; }}\n"
        ".rung-chart svg {{ display: block; width: 100%; height: auto; }}\n"
        ".note {{ color: {muted}; font-size: 13px; margin-bottom: 24px; }}\n"
    ).format(paper=PAPER, ink=INK, muted=MUTED, faint=FAINT, gray=LADDER[2], font=FONT)

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
    return html


def save_html_report(figures: dict, out_path: Path, title: str = "销售数据可视化报告",
                     meta: dict | None = None) -> Path:
    """把多张图表合并为离线 HTML 报告并写到 out_path（供 CLI / legacy 使用）。"""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build_html_report(figures, title=title, meta=meta), encoding="utf-8")
    return out_path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成 Mono 风格交互式图表与 HTML 报告")
    ap.add_argument("path", nargs="?", default=None, help="数据文件路径（缺省自动选择示例数据）")
    ap.add_argument("-o", "--out", default=None, help="HTML 报告输出路径（默认 output/report.html）")
    args = ap.parse_args(argv)

    path = args.path or str(DEFAULT_DATA)
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
    meta = build_chart_meta(metrics)

    out_dir = PROJECT_ROOT / "output"
    out_dir.mkdir(exist_ok=True)
    out_path = Path(args.out) if args.out else out_dir / "report.html"
    save_html_report(figs, out_path, meta=meta)

    charts_dir = out_dir / "charts"
    charts_dir.mkdir(exist_ok=True)
    for name, fig in figs.items():
        if isinstance(fig, str):
            wrapped = (
                "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
                "<style>body{margin:0;background:#F0EFEB;font-family:Inter,system-ui,sans-serif;"
                "padding:24px;display:flex;justify-content:center}"
                ".rung-chart{max-width:760px;width:100%}"
                ".rung-chart svg{display:block;width:100%;height:auto}</style></head>"
                f"<body><div class=\"rung-chart\">{fig}</div></body></html>"
            )
            (charts_dir / f"{name}.html").write_text(wrapped, encoding="utf-8")
        else:
            fig.write_html(charts_dir / f"{name}.html", include_plotlyjs="cdn")

    print(f"生成 {len(figs)} 张图表。")
    print(f"完整 HTML 报告：{out_path}")
    print(f"单张图表目录：{charts_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
