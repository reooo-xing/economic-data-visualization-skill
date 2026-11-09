# -*- coding: utf-8 -*-
"""calculate_metrics.py — 指标计算。

输入：清洗后的数据（含规范列，见 clean_data.py）。
输出：每日/每周/每月销售额与销量、客单价、各维度排行与占比、同比/环比。

维度（商品/渠道/门店/地区）按数据中**实际存在**的字段动态计算，
缺失的维度自动跳过，不硬编码某个字段名。口径见 references/FIELD_RULES.md。

可独立运行：python calculate_metrics.py <文件路径>
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from clean_data import clean
from read_data import DIMENSION_FIELDS, read_file

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _agg_period(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """按时间列聚合销售额 / 销量 / 订单数（存在哪个度量就用哪个）。"""
    agg = {"销售额": ("sales_amount", "sum")}
    if "quantity" in df.columns:
        agg["销量"] = ("quantity", "sum")
    if "order_id" in df.columns and df["order_id"].notna().any():
        agg["订单数"] = ("order_id", "nunique")
    return df.groupby(col).agg(**agg).reset_index()


def _ranking(df: pd.DataFrame, dim: str) -> pd.DataFrame | None:
    """按某维度聚合并计算占比，按销售额降序；维度不存在返回 None。"""
    if dim not in df.columns:
        return None
    agg = {"销售额": ("sales_amount", "sum")}
    if "quantity" in df.columns:
        agg["销量"] = ("quantity", "sum")
    r = df.groupby(dim).agg(**agg).reset_index()
    r = r.sort_values("销售额", ascending=False).reset_index(drop=True)
    r["销售额占比"] = r["销售额"] / r["销售额"].sum()
    if "销量" in r.columns:
        r["销量占比"] = r["销量"] / r["销量"].sum()
    return r


def compute_metrics(df: pd.DataFrame) -> dict:
    """基于清洗后数据计算全部指标，返回 {name: ...} 与口径说明。"""
    need = ["date", "sales_amount"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        return {"__error__": f"缺少必要列：{missing}（请先运行 clean_data.clean）"}

    df = df.copy()
    has_qty = "quantity" in df.columns
    has_order = "order_id" in df.columns and df["order_id"].notna().any()

    df["period_daily"] = df["date"]
    df["period_weekly"] = df["date"].dt.to_period("W-MON").dt.start_time
    df["period_monthly"] = df["date"].dt.to_period("M").dt.start_time

    # 每日 / 每周 / 每月
    daily = _agg_period(df, "period_daily").rename(columns={"period_daily": "日期"})
    weekly = _agg_period(df, "period_weekly").rename(columns={"period_weekly": "周起始"})
    weekly["周起始"] = pd.to_datetime(weekly["周起始"]).dt.strftime("%Y-%m-%d")
    monthly = _agg_period(df, "period_monthly").rename(columns={"period_monthly": "月份"})
    monthly["月份"] = pd.to_datetime(monthly["月份"]).dt.strftime("%Y-%m")

    # 客单价（两种口径）
    total_sales = float(df["sales_amount"].sum())
    aov: dict[str, float] = {}
    aov_note = "客单价（订单口径）= 销售额 ÷ 订单数。"
    if has_order:
        orders = int(df["order_id"].nunique())
        aov["客单价_订单口径"] = total_sales / orders if orders else np.nan
        daily["客单价_订单"] = daily["销售额"] / daily["订单数"].replace(0, np.nan)
    if has_qty:
        qty_sum = float(df["quantity"].sum())
        aov["客单价_销量口径"] = total_sales / qty_sum if qty_sum else np.nan
        daily["客单价_销量"] = daily["销售额"] / daily["销量"].replace(0, np.nan)
        aov_note += " 客单价（销量口径）= 销售额 ÷ 销量（无订单号时使用）。"

    # 各维度排行（动态：只计算数据中实际存在的维度）
    rankings: dict[str, pd.DataFrame] = {}
    for key in DIMENSION_FIELDS:
        t = _ranking(df, key)
        if t is not None:
            rankings[key] = t

    # 环比 / 同比
    monthly_growth = monthly.copy()
    monthly_growth["销售额环比"] = monthly_growth["销售额"].pct_change()
    monthly_growth["销售额同比"] = monthly_growth["销售额"].pct_change(12)
    if "销量" in monthly_growth.columns:
        monthly_growth["销量环比"] = monthly_growth["销量"].pct_change()
        monthly_growth["销量同比"] = monthly_growth["销量"].pct_change(12)
    growth_note = "环比 = 本期/上期 − 1；同比 = 本期/去年同期 − 1（需 ≥ 13 个月数据，样本不足时同比为空）。"

    # 地区月度堆叠（仅当存在地区维度）
    region_monthly = None
    if "region" in df.columns:
        pivot = (
            df.groupby(["period_monthly", "region"])["sales_amount"].sum()
            .reset_index()
            .pivot(index="period_monthly", columns="region", values="sales_amount")
            .fillna(0)
        )
        pivot.index = pd.to_datetime(pivot.index).strftime("%Y-%m")
        region_monthly = pivot

    return {
        "daily": daily,
        "weekly": weekly,
        "monthly": monthly,
        "rankings": rankings,
        "region_monthly": region_monthly,
        "monthly_growth": monthly_growth,
        "aov": aov,
        "notes": {"客单价": aov_note, "增长率": growth_note},
    }


def save_metrics(metrics: dict, out_dir: Path) -> list[Path]:
    """将各指标表保存为 CSV。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for name in ["daily", "weekly", "monthly", "monthly_growth", "region_monthly"]:
        table = metrics.get(name)
        if isinstance(table, pd.DataFrame) and not table.empty:
            p = out_dir / f"{name}.csv"
            table.to_csv(p, index=False, encoding="utf-8-sig")
            paths.append(p)
    for key, table in metrics.get("rankings", {}).items():
        if isinstance(table, pd.DataFrame) and not table.empty:
            p = out_dir / f"ranking_{key}.csv"
            table.to_csv(p, index=False, encoding="utf-8-sig")
            paths.append(p)
    return paths


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="计算销售指标并输出 CSV")
    ap.add_argument("path", help="CSV / Excel 文件路径")
    ap.add_argument("-o", "--out-dir", default=None, help="输出目录（默认 output/metrics）")
    args = ap.parse_args(argv)

    df = read_file(args.path)
    cleaned, report = clean(df)
    if "error" in report:
        print("⚠ 清洗中止：", report["error"])
        return 1

    metrics = compute_metrics(cleaned)
    if "__error__" in metrics:
        print("⚠ 指标计算中止：", metrics["__error__"])
        return 1

    out_dir = Path(args.out_dir) if args.out_dir else PROJECT_ROOT / "output" / "metrics"
    paths = save_metrics(metrics, out_dir)

    print("=" * 64)
    print("口径说明：")
    print("  -", metrics["notes"]["客单价"])
    print("  -", metrics["notes"]["增长率"])
    print("\n客单价：")
    for k, v in metrics["aov"].items():
        print(f"  - {k} = {v:,.2f} 元")
    print("\n各维度销售排行（Top 5，仅显示数据中存在的维度）：")
    for key, table in metrics["rankings"].items():
        cols = [key, "销售额"]
        if "销售额占比" in table.columns:
            cols.append("销售额占比")
        print(f"\n[{DIMENSION_FIELDS[key]}]")
        print(table.head(5)[cols].to_string(index=False))
    print(f"\n已输出 {len(paths)} 个指标表到：{out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
