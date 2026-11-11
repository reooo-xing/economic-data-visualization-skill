# -*- coding: utf-8 -*-
"""rung_charts.py — lieflat-charts「横档柱」(Rung Bars) 的 SVG 渲染器。

把一根实心柱拆成「一格格横档」：远看是柱状图剪影，近看每一档都数得出来。
- 竖柱：柱身 = 一叠横向短横线（月度销售额等时间柱）；
- 横柱：柱身 = 一排纵向短竖线（排行 / 占比等排名条）。

每档的明度与宽度按**确定性伪随机**抖动（同 lieflat-charts 的 rnd，刷新结果恒定），
每 5 档旁打一个小点；并带 lieflat 的逐档淡入动画（quarticOut，900ms，逐档错峰）。
配色与字体取自 mono-tokens.js；SVG 自包含、可离线、原生 <title> 提供 hover。
金额单位写进底部 footer（"ONE RUNG = ¥…"）。
"""
from __future__ import annotations

import math
from html import escape

INK = "#1C1C1A"      # 墨：主数据 / 强调（最重要 = 最黑）
PAPER = "#F0EFEB"    # 纸：底色
MUTED = "#8F8E88"    # 次级文字
FAINT = "#C6C5BF"    # 来源行 / 辅助刻度
GRID = "#DEDDD6"     # 网格 / 基线
DOT = "#C6C5BF"      # 每 5 档的小点
# 7 级灰阶阶梯：多系列 / 分段按重要性从黑到浅分配
LADDER = ["#1C1C1A", "#4A4944", "#6A6963", "#8F8E88", "#B0AFA9", "#C6C5BF", "#D8D7D1"]

FONT = "Inter, system-ui, -apple-system, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif"


def _rnd(i: int, k: int) -> float:
    """确定性伪随机（同 lieflat-charts 的 rnd）：刷新结果必须恒定。"""
    return abs(((i * 73856093) ^ (k * 19349663)) % 1000) / 1000


def nice_unit(max_val: float, target: int = 26) -> float:
    """选一个 1 / 2 / 2.5 / 5 × 10^n 的「诚实单位」，使最高柱约 target 档。"""
    if max_val <= 0:
        return 1.0
    raw = max_val / target
    p = 10 ** math.floor(math.log10(raw))
    m = raw / p
    for nice in (1.0, 2.0, 2.5, 5.0, 10.0):
        if m <= nice:
            return nice * p
    return 10.0 * p


def _fmt_unit(u: float) -> str:
    return f"{u:,.0f}" if u >= 1 else f"{u:g}"


def _clip(s: str, n: int) -> str:
    s = str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def _svg(inner: str, w: int, h: int) -> str:
    # 动效与 mono-tokens.js 对齐：淡入(fade) / 弹入(pop) / 描线(draw)，quarticOut 快进快停。
    anim = (
        "<defs><style>"
        ".r{animation:rf .9s cubic-bezier(.2,.7,.3,1) both}"
        "@keyframes rf{from{opacity:0}}"
        ".fade{animation:fd .9s cubic-bezier(.2,.7,.3,1) both}"
        "@keyframes fd{from{opacity:0}}"
        ".pop{transform-box:fill-box;transform-origin:center;"
        "animation:pp .5s cubic-bezier(.2,.7,.3,1.3) both}"
        "@keyframes pp{from{transform:scale(0)}to{transform:none}}"
        ".draw{stroke-dasharray:1;stroke-dashoffset:1;animation:dr 1s cubic-bezier(.4,0,.2,1) both}"
        "@keyframes dr{to{stroke-dashoffset:0}}"
        "@media (prefers-reduced-motion:reduce){"
        ".r,.fade,.pop{animation:none}"
        ".draw{animation:none;stroke-dasharray:none;stroke-dashoffset:0}}"
        "</style></defs>"
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        f'preserveAspectRatio="xMidYMid meet" '
        f'style="display:block;width:100%;height:auto;background:{PAPER};font-family:{FONT};">'
        f"{anim}{inner}</svg>"
    )


def _vertical(items, unit: float, value_fmt, hover_fmt, footer: str) -> str:
    W, H = 640, 360
    top, bottom = 46, 42
    left = right = 40
    n = len(items)
    values = [v for _, v in items]
    max_rungs = max(1, round(max(values) / unit))
    baseline = H - bottom
    plot_h = baseline - top
    rung_step = plot_h / max_rungs
    slot = (W - left - right) / n
    bar_hw = min(slot * 0.22, 20.0)

    p: list[str] = []
    for i, (label, v) in enumerate(items):
        x = left + slot * i + slot / 2
        nr = max(1, round(v / unit)) if v > 0 else 0
        for k in range(nr):
            y = baseline - (k + 0.5) * rung_step
            w = bar_hw - 1.5 + _rnd(k + 1, i + 2) * 3
            op = 0.5 + _rnd(k + 2, i + 4) * 0.5
            d = f"{i * 0.08 + k * 0.012:.3f}s"
            p.append(
                f'<line x1="{x - w:.2f}" y1="{y:.2f}" x2="{x + w:.2f}" y2="{y:.2f}" '
                f'stroke="{INK}" stroke-width="1.3" stroke-linecap="round" opacity="{op:.2f}" '
                f'class="r" style="animation-delay:{d}"/>'
            )
            if k % 5 == 4:
                p.append(
                    f'<circle cx="{x + bar_hw + 4.5:.2f}" cy="{y:.2f}" r="0.9" fill="{DOT}" '
                    f'class="r" style="animation-delay:{d}"/>'
                )
        top_y = (baseline - (nr - 0.5) * rung_step) if nr else baseline - 2
        td = f"{0.4 + i * 0.08:.3f}s"
        p.append(
            f'<text x="{x:.2f}" y="{top_y - 10:.2f}" font-size="11.5" font-weight="800" '
            f'fill="{INK}" text-anchor="middle" class="r" style="animation-delay:{td}">{value_fmt(v)}</text>'
        )
        hw = bar_hw + 6
        p.append(
            f'<rect x="{x - hw:.2f}" y="{top_y - 14:.2f}" width="{hw * 2:.2f}" '
            f'height="{baseline - top_y + 14:.2f}" fill="transparent">'
            f"<title>{escape(label)} · {escape(hover_fmt(v))}</title></rect>"
        )
        p.append(
            f'<text x="{x:.2f}" y="{baseline + 15:.2f}" font-size="9" font-weight="700" '
            f'fill="{MUTED}" text-anchor="middle" letter-spacing="0.04em" '
            f'class="r" style="animation-delay:{td}">{escape(_clip(label, 12))}</text>'
        )

    p.append(
        f'<line x1="{left - 6}" y1="{baseline:.2f}" x2="{W - right + 6}" y2="{baseline:.2f}" '
        f'stroke="{GRID}" stroke-width="0.8" class="r" style="animation-delay:.15s"/>'
    )
    p.append(
        f'<text x="{W / 2:.2f}" y="{H - 8:.2f}" font-size="7.5" font-weight="600" '
        f'fill="{FAINT}" text-anchor="middle" letter-spacing="0.12em" '
        f'class="r" style="animation-delay:.6s">{escape(footer)}</text>'
    )
    return _svg("".join(p), W, H)


def _horizontal(items, unit: float, value_fmt, hover_fmt, footer: str) -> str:
    n = len(items)
    W = 640
    row_h = 34
    top, bottom = 16, 40
    H = top + n * row_h + bottom
    label_w, value_w = 150, 70
    x0 = label_w + 12
    x1 = W - value_w
    rung_w = x1 - x0
    values = [v for _, v in items]
    max_rungs = max(1, round(max(values) / unit))
    rung_step = rung_w / max_rungs
    half_h = 8.0

    p: list[str] = []
    for i, (label, v) in enumerate(items):
        y = top + i * row_h + row_h / 2
        nr = max(1, round(v / unit)) if v > 0 else 0
        for k in range(nr):
            x = x0 + (k + 0.5) * rung_step
            h = half_h - 0.5 + _rnd(k + 1, i + 2) * 1.2
            op = 0.5 + _rnd(k + 2, i + 4) * 0.5
            d = f"{i * 0.08 + k * 0.012:.3f}s"
            p.append(
                f'<line x1="{x:.2f}" y1="{y - h:.2f}" x2="{x:.2f}" y2="{y + h:.2f}" '
                f'stroke="{INK}" stroke-width="2.6" stroke-linecap="round" opacity="{op:.2f}" '
                f'class="r" style="animation-delay:{d}"/>'
            )
            if k % 5 == 4:
                p.append(
                    f'<circle cx="{x:.2f}" cy="{y + half_h + 4:.2f}" r="0.9" fill="{DOT}" '
                    f'class="r" style="animation-delay:{d}"/>'
                )
        td = f"{0.4 + i * 0.08:.3f}s"
        p.append(
            f'<text x="{x0 - 8:.2f}" y="{y + 3:.2f}" font-size="10" font-weight="600" '
            f'fill="{INK}" text-anchor="end" class="r" style="animation-delay:{td}">'
            f'{escape(_clip(label, 12))}</text>'
        )
        endx = x0 + (nr + 0.5) * rung_step if nr else x0
        vx = min(endx + 8, x1 + 8)
        p.append(
            f'<text x="{vx:.2f}" y="{y + 3:.2f}" font-size="11.5" font-weight="800" '
            f'fill="{INK}" class="r" style="animation-delay:{td}">{value_fmt(v)}</text>'
        )
        p.append(
            f'<rect x="{x0 - 4:.2f}" y="{y - row_h / 2 + 2:.2f}" '
            f'width="{max(endx - x0 + 8, 4):.2f}" height="{row_h - 4:.2f}" fill="transparent">'
            f"<title>{escape(label)} · {escape(hover_fmt(v))}</title></rect>"
        )

    p.append(
        f'<text x="{x0:.2f}" y="{H - 10:.2f}" font-size="7.5" font-weight="600" '
        f'fill="{FAINT}" letter-spacing="0.12em" class="r" style="animation-delay:.6s">{escape(footer)}</text>'
    )
    return _svg("".join(p), W, H)


def build_rung_bars(
    items,
    *,
    horizontal: bool = False,
    unit: float | None = None,
    value_fmt=None,
    hover_fmt=None,
    footer: str | None = None,
) -> str:
    """把 [(标签, 数值), ...] 渲染成 lieflat 横档柱 SVG。

    items      标签-数值对（顺序即绘图顺序；横柱从上到下、竖柱从左到右）
    horizontal 横柱（排行/占比）还是竖柱（时间柱）
    unit       每档代表的「诚实单位」；缺省按最高值自动取 1/2/2.5/5×10^n
    value_fmt  柱上数值显示函数（默认千分位整数）
    hover_fmt  hover 提示显示函数（默认同 value_fmt）
    footer     底部说明行（默认 "ONE RUNG = <unit> · DOT MARKS EVERY FIFTH"）
    """
    items = [(str(l), float(v)) for l, v in items]
    values = [v for _, v in items]
    max_val = max(values) if values else 0.0
    if unit is None:
        unit = nice_unit(max_val)
    value_fmt = value_fmt or (lambda v: f"{v:,.0f}")
    hover_fmt = hover_fmt or value_fmt
    footer = footer or f"ONE RUNG = {_fmt_unit(unit)} · DOT MARKS EVERY FIFTH"
    if horizontal:
        return _horizontal(items, unit, value_fmt, hover_fmt, footer)
    return _vertical(items, unit, value_fmt, hover_fmt, footer)


def build_hairline_line(items, *, value_fmt=None, hover_fmt=None, footer=None) -> str:
    """折线图的 lieflat「发丝折线」SVG（对标 B2 Hairline Line）。

    动态效果：发丝路径「描线入场」(draw) + 逐点「弹入」(pop) + 峰值放大标数；
    每月一根发丝立在基线当「日历地板」。纯 SVG、可离线、<title> 提供 hover。
    """
    items = [(str(l), float(v)) for l, v in items]
    value_fmt = value_fmt or (lambda v: f"{v:,.0f}")
    hover_fmt = hover_fmt or value_fmt
    n = len(items)
    W, H = 640, 360
    left, right, top, bottom = 46, 36, 40, 46
    baseline = H - bottom
    plot_h = baseline - top
    vals = [v for _, v in items]
    vmax = max(vals) if vals else 0.0
    vmin = min(vals) if vals else 0.0
    span = vmax - vmin
    if span <= 0:
        span = max(vmax, 1.0)
    lo, hi = vmin - span * 0.14, vmax + span * 0.14

    def x(i: int) -> float:
        return left + (W - left - right) * (i / (n - 1) if n > 1 else 0.5)

    def y(v: float) -> float:
        return baseline - (v - lo) / (hi - lo) * plot_h

    # top-2 峰值（彼此拉开，避免标签重叠）
    order = sorted(range(n), key=lambda i: vals[i], reverse=True)
    peaks: list[int] = []
    for i in order:
        if all(abs(i - p) >= 3 for p in peaks):
            peaks.append(i)
        if len(peaks) == 2:
            break

    p: list[str] = []
    # 日历地板：每月一根发丝立在基线
    for i in range(n):
        p.append(
            f'<line x1="{x(i):.2f}" y1="{baseline:.2f}" x2="{x(i):.2f}" y2="{baseline - 6:.2f}" '
            f'stroke="#CFCEC7" stroke-width="0.6" class="fade" style="animation-delay:{i * 0.008:.3f}s"/>'
        )
    p.append(
        f'<line x1="{left - 6:.2f}" y1="{baseline:.2f}" x2="{W - right + 6:.2f}" y2="{baseline:.2f}" '
        f'stroke="{GRID}" stroke-width="0.8" class="fade"/>'
    )
    # 发丝路径：描线入场
    pts = " L ".join(f"{x(i):.2f} {y(vals[i]):.2f}" for i in range(n))
    p.append(
        f'<path d="M{pts}" fill="none" stroke="{INK}" stroke-width="1" pathLength="1" '
        f'class="draw" style="animation-duration:1.2s"/>'
    )
    # 逐点弹入 + 峰值标数
    for i, (label, v) in enumerate(items):
        big = i in peaks
        p.append(
            f'<circle cx="{x(i):.2f}" cy="{y(v):.2f}" r="{4.2 if big else 2.1:.1f}" fill="{INK}" '
            f'class="pop" style="animation-delay:{0.2 + i * 0.03:.3f}s">'
            f"<title>{escape(label)} · {escape(hover_fmt(v))}</title></circle>"
        )
        if big:
            p.append(
                f'<text x="{x(i):.2f}" y="{y(v) - 11:.2f}" font-size="9.5" font-weight="800" '
                f'fill="{INK}" text-anchor="middle" paint-order="stroke" stroke="{PAPER}" stroke-width="3" '
                f'class="fade" style="animation-delay:{1.0 + i * 0.01:.3f}s">{value_fmt(v)}</text>'
            )
    # 月份标签：≤15 全标，否则首/中/尾
    idxs = list(range(n)) if n <= 15 else sorted({0, n // 2, n - 1})
    for i in idxs:
        p.append(
            f'<text x="{x(i):.2f}" y="{baseline + 16:.2f}" font-size="7.5" font-weight="600" '
            f'fill="{MUTED}" text-anchor="middle" letter-spacing="0.04em" '
            f'class="fade" style="animation-delay:{0.3 + i * 0.01:.3f}s">{escape(_clip(items[i][0], 10))}</text>'
        )
    footer = footer or "发丝折线 · 每点 = 一月"
    p.append(
        f'<text x="{W / 2:.2f}" y="{H - 8:.2f}" font-size="7.5" font-weight="600" '
        f'fill="{FAINT}" text-anchor="middle" letter-spacing="0.12em" '
        f'class="fade" style="animation-delay:1.1s">{escape(footer)}</text>'
    )
    return _svg("".join(p), W, H)


def build_tick_donut(items, *, hover_fmt=None, footer=None, center_sub="构成") -> str:
    """饼图的 lieflat「刻度环形」SVG（对标 B4 Tick Donut）。

    1 格 = 1%，100 格绕整圈；灰阶阶梯分段、段间留白；中心放总数与数据说明，
    段外侧用点线引线标注「名称 · 占比」。中文标签、纯 SVG、可离线。
    """
    items = [(str(l), float(v)) for l, v in items]
    hover_fmt = hover_fmt or (lambda v: f"{v:,.1f}")
    vals = [v for _, v in items]
    total = sum(vals)
    if total <= 0:
        total = 1.0
    raw = [v / total * 100 for v in vals]
    pct = list(raw)
    # 最大余数法把各段取整到共 100 格，保证整圈闭合
    ticks = [int(math.floor(r)) for r in raw]
    while sum(ticks) < 100:
        k = max(range(len(raw)), key=lambda i: raw[i] - ticks[i])
        ticks[k] += 1
    shades = LADDER[: len(items)]

    W, H = 640, 430
    cx, cy = 320, 200
    R0 = 96.0

    p: list[str] = []
    k0 = 0
    for si, (name, v) in enumerate(items):
        shade = shades[si]
        for k in range(ticks[si]):
            idx = k0 + k
            a = idx * 3.6 - 90
            rad = a * math.pi / 180
            length = 12 + _rnd(idx + 1, si + 2) * 7
            x1, y1 = cx + R0 * math.cos(rad), cy + R0 * math.sin(rad)
            x2, y2 = cx + (R0 + length) * math.cos(rad), cy + (R0 + length) * math.sin(rad)
            p.append(
                f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
                f'stroke="{shade}" stroke-width="1" class="fade" style="animation-delay:{idx * 0.012:.3f}s"/>'
            )
            if idx % 10 == 0:
                dx, dy = cx + (R0 - 5) * math.cos(rad), cy + (R0 - 5) * math.sin(rad)
                p.append(
                    f'<circle cx="{dx:.2f}" cy="{dy:.2f}" r="0.8" fill="{FAINT}" '
                    f'class="fade" style="animation-delay:{idx * 0.012:.3f}s"/>'
                )
        # 段标签：中位角外侧，点线引线
        mid = (k0 + ticks[si] / 2) * 3.6 - 90
        mrad = mid * math.pi / 180
        gx, gy = cx + (R0 + 24) * math.cos(mrad), cy + (R0 + 24) * math.sin(mrad)
        lx, ly = cx + (R0 + 52) * math.cos(mrad), cy + (R0 + 52) * math.sin(mrad)
        p.append(
            f'<line x1="{gx:.2f}" y1="{gy:.2f}" x2="{lx:.2f}" y2="{ly:.2f}" '
            f'stroke="{FAINT}" stroke-width="0.7" stroke-dasharray="1 3" '
            f'class="fade" style="animation-delay:{0.6 + si * 0.1:.3f}s"/>'
        )
        anchor = "start" if math.cos(mrad) > 0.3 else ("end" if math.cos(mrad) < -0.3 else "middle")
        p.append(
            f'<text x="{lx:.2f}" y="{ly + 3:.2f}" font-size="8.5" font-weight="800" fill="{shade}" '
            f'text-anchor="{anchor}" letter-spacing="0.04em" paint-order="stroke" '
            f'stroke="{PAPER}" stroke-width="3" class="fade" style="animation-delay:{0.65 + si * 0.1:.3f}s">'
            f'{escape(_clip(name, 8))} · {pct[si]:.0f}%'
            f"<title>{escape(name)} · 占 {pct[si]:.1f}%</title></text>"
        )
        k0 += ticks[si]
    # 中心：总数 + 数据说明（说明这张图是哪个数据）
    p.append(
        f'<text x="{cx:.2f}" y="{cy - 4:.2f}" font-size="26" font-weight="800" fill="{INK}" '
        f'text-anchor="middle" class="fade" style="animation-delay:0.9s">100</text>'
    )
    p.append(
        f'<text x="{cx:.2f}" y="{cy + 16:.2f}" font-size="8.5" font-weight="600" fill="{MUTED}" '
        f'text-anchor="middle" letter-spacing="0.08em" class="fade" style="animation-delay:0.9s">'
        f'{escape(center_sub)}</text>'
    )
    footer = footer or "每格 = 1%"
    p.append(
        f'<text x="{W / 2:.2f}" y="{H - 10:.2f}" font-size="7.5" font-weight="600" '
        f'fill="{FAINT}" text-anchor="middle" letter-spacing="0.12em" '
        f'class="fade" style="animation-delay:1.1s">{escape(footer)}</text>'
    )
    return _svg("".join(p), W, H)
