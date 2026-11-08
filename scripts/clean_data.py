# -*- coding: utf-8 -*-
"""clean_data.py — 数据清洗。

清洗步骤（详见 SKILL.md 第 4 节）：
1. 列名去空白；2. 删除完全重复行；3. 日期统一并删除无效日期；
4. 金额单位归一化为元；5. 删除缺失/负值销售额；6. 数量补 0、负值置 0；
7. IQR 异常值标记；8. 文本标准化、缺失补「未知」。

清洗后输出规范列名：date / product_name / sku / unit_price / quantity /
sales_amount / channel / store / region / order_id（存在时）。

可独立运行：python clean_data.py <文件路径> [-o 输出.csv] [--drop-outliers]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from read_data import detect_fields, read_file

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _to_datetime(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce")


def _to_numeric(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def standardize_text(s: pd.Series) -> pd.Series:
    """文本标准化：去首尾空白、合并连续空白（含全角空格）。"""
    def _clean(x):
        if pd.isna(x):
            return x
        t = re.sub(r"\s+", " ", str(x)).strip()
        return t

    return s.map(_clean)


def detect_amount_unit(sales_name, sales: pd.Series, qty: pd.Series | None,
                       unit_price: pd.Series | None) -> tuple[float, str, str]:
    """检测金额单位，返回 (折算到元的倍率, 单位标签, 依据说明)。"""
    name = str(sales_name)
    # 1) 列名关键字
    for kw, mult in [("亿元", 1e8), ("万元", 1e4), ("亿", 1e8), ("万", 1e4)]:
        if kw in name:
            return mult, kw, f"列名包含「{kw}」"

    # 2) 幅度启发：销售额÷数量 与 单价 的中位数比值
    if qty is not None and unit_price is not None:
        s, q, p = sales.dropna(), qty.dropna(), unit_price.dropna()
        if not s.empty and not q.empty and not p.empty:
            ref = float(p.median())
            if ref > 0:
                mask = q > 0
                if mask.any():
                    implied = float((s[mask] / q[mask]).median())
                    if implied > 0:
                        ratio = ref / implied
                        if ratio > 5e7:
                            return 1e8, "亿元", "销售额÷数量 与单价相差约 1e8 倍，推断单位为亿元"
                        if ratio > 5e3:
                            return 1e4, "万元", "销售额÷数量 与单价相差约 1e4 倍，推断单位为万元"
    return 1.0, "元", "未检测到万元/亿元，默认按「元」处理"


def clean(df: pd.DataFrame, *, drop_outliers: bool = False) -> tuple[pd.DataFrame, dict]:
    """清洗数据，返回 (清洗后 DataFrame, 报告 dict)。"""
    report: dict = {"steps": [], "notes": []}
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    report["original_shape"] = df.shape

    # 1) 字段识别
    det = detect_fields(df)
    report["field_map"] = det["field_map"]
    report["detection"] = det
    fm = det["field_map"]

    # 2) 删除完全重复行
    n_before = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    report["dropped_duplicates"] = n_before - len(df)

    # 3) 核心字段检查
    if "date" not in fm:
        report["error"] = "未识别到日期字段，无法继续清洗，请确认字段映射。"
        return df, report
    if "sales_amount" not in fm:
        report["error"] = "未识别到销售额字段，无法继续清洗，请确认字段映射。"
        return df, report

    # 4) 日期统一，删除无效日期
    df["date"] = _to_datetime(df[fm["date"]])
    n_before = len(df)
    df = df.dropna(subset=["date"]).reset_index(drop=True)
    report["dropped_invalid_date"] = n_before - len(df)

    # 5) 金额单位归一化 + 数值转换
    qty_col = fm.get("quantity")
    price_col = fm.get("unit_price")
    sales_col = fm["sales_amount"]
    qty_s = _to_numeric(df[qty_col]) if qty_col else None
    price_s = _to_numeric(df[price_col]) if price_col else None
    sales_s = _to_numeric(df[sales_col])

    mult, unit_label, basis = detect_amount_unit(sales_col, sales_s, qty_s, price_s)
    df["sales_amount"] = sales_s * mult
    if unit_label != "元":
        report["notes"].append(f"金额单位已归一化：原始「{sales_col}」按「{unit_label}」折算为元（依据：{basis}）。")
    else:
        report["notes"].append(f"金额单位：按「元」处理（{basis}）。")

    if qty_col:
        df["quantity"] = qty_s
    if price_col:
        df["unit_price"] = price_s

    # 6) 无效值处理
    n_before = len(df)
    df = df[df["sales_amount"].notna()].reset_index(drop=True)
    report["dropped_missing_sales"] = n_before - len(df)

    n_before = len(df)
    df = df[df["sales_amount"] >= 0].reset_index(drop=True)
    report["dropped_negative_sales"] = n_before - len(df)

    if "quantity" in df:
        df.loc[df["quantity"].isna(), "quantity"] = 0
        df.loc[df["quantity"] < 0, "quantity"] = 0
        report["notes"].append("缺失的数量以 0 补齐；负值数量置 0（不影响销售额口径）。")
    if "unit_price" in df:
        df.loc[df["unit_price"] <= 0, "unit_price"] = np.nan

    # 7) IQR 异常值标记（默认不删除）
    for col, label in [("sales_amount", "金额"), ("quantity", "数量"), ("unit_price", "单价")]:
        if col not in df:
            continue
        s = df[col].dropna()
        if not s.empty:
            q1, q3 = s.quantile(0.25), s.quantile(0.75)
            iqr = q3 - q1
            if iqr > 0:
                lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
                flag = (df[col] < lo) | (df[col] > hi)
            else:
                flag = pd.Series(False, index=df.index)
        else:
            flag = pd.Series(False, index=df.index)
        df[f"{col}_outlier"] = flag
        if bool(flag.any()):
            report["notes"].append(f"{label}检测到 {int(flag.sum())} 条 IQR 异常值，已标记在「{col}_outlier」列（未删除）。")

    if drop_outliers:
        n_before = len(df)
        outlier_cols = [c for c in df.columns if c.endswith("_outlier")]
        if outlier_cols:
            df = df[~df[outlier_cols].any(axis=1)].reset_index(drop=True)
        report["notes"].append(f"已按 --drop-outliers 删除 {n_before - len(df)} 条 IQR 异常值。")

    # 8) 文本标准化 + 缺失补「未知」
    for col_key, label in [
        ("product_name", "商品名称"), ("sku", "SKU"), ("channel", "渠道"),
        ("store", "门店"), ("region", "地区"),
    ]:
        src = fm.get(col_key)
        if not src:
            continue
        df[col_key] = standardize_text(df[src]).fillna("未知")
        df.loc[df[col_key].eq(""), col_key] = "未知"

    # 9) 订单号（可选）
    if "order_id" in fm:
        df["order_id"] = standardize_text(df[fm["order_id"]])

    report["cleaned_shape"] = df.shape
    report["steps"] = [
        "1. 列名去首尾空白",
        "2. 删除完全重复行",
        "3. 日期统一为 datetime，删除无效日期",
        "4. 金额单位归一化为「元」",
        "5. 删除缺失 / 负值销售额（错误金额）",
        "6. 数量缺失补 0、负值置 0",
        "7. IQR 异常值标记（默认不删除）",
        "8. 文本字段标准化，缺失补「未知」",
    ]
    return df, report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="清洗数据并输出清洗后 CSV")
    ap.add_argument("path", help="CSV / Excel 文件路径")
    ap.add_argument("-o", "--out", default=None, help="输出 CSV 路径（默认 output/cleaned_data.csv）")
    ap.add_argument("--drop-outliers", action="store_true", help="是否删除 IQR 异常值（默认仅标记）")
    args = ap.parse_args(argv)

    df = read_file(args.path)
    cleaned, report = clean(df, drop_outliers=args.drop_outliers)

    if "error" in report:
        print("⚠ 清洗中止：", report["error"])
        return 1

    out_dir = PROJECT_ROOT / "output"
    out_dir.mkdir(exist_ok=True)
    out_path = Path(args.out) if args.out else out_dir / "cleaned_data.csv"
    cleaned.to_csv(out_path, index=False, encoding="utf-8-sig")

    printable = {k: v for k, v in report.items() if k not in ("detection", "field_map")}
    print("=" * 64)
    print("清洗报告：")
    print(json.dumps(printable, ensure_ascii=False, indent=2, default=str))
    print(f"\n已输出清洗后数据：{out_path}（{cleaned.shape[0]} 行 × {cleaned.shape[1]} 列）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
