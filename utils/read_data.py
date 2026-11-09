# -*- coding: utf-8 -*-
"""read_data.py — 数据读取与字段识别。

负责：
1. 读取 CSV / Excel 文件；
2. 按列名与列内容自动识别常见字段（日期、商品名称、SKU、单价、数量、
   销售额、渠道、门店、地区、订单号）；
3. 输出数据概览与字段识别结果（含不确定项，供用户确认）。

可独立运行：python read_data.py <文件路径> [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

# Windows 控制台默认使用 GBK，无法打印中文与特殊符号；统一为 UTF-8 输出。
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# 字段规则：规范字段名 -> 常见同义词（先精确匹配，再包含匹配）
# ---------------------------------------------------------------------------
CANONICAL_FIELDS: dict[str, str] = {
    "date": "日期",
    "product_name": "商品名称",
    "sku": "SKU",
    "unit_price": "单价",
    "quantity": "数量",
    "sales_amount": "销售额",
    "channel": "渠道",
    "store": "门店",
    "region": "地区",
    "order_id": "订单号",
}

FIELD_SYNONYMS: dict[str, list[str]] = {
    "date": [
        "日期", "时间", "日期时间", "下单时间", "销售日期", "交易日期", "结算日期",
        "date", "time", "datetime", "day", "dt",
    ],
    "product_name": [
        "商品名称", "商品名", "品名", "产品名称", "产品", "商品",
        "product", "productname", "product_name", "item", "itemname", "name",
    ],
    "sku": [
        "sku", "货号", "条码", "商品编码", "商品编号", "物料编码", "编码",
        "code", "itemcode", "barcode", "sku编码",
    ],
    "unit_price": [
        "单价", "价格", "售价", "商品单价", "零售价", "成交单价",
        "price", "unitprice", "单价(元)", "单价（元）",
    ],
    "quantity": [
        "数量", "销量", "件数", "销售数量", "成交件数", "购买数量",
        "qty", "quantity", "count", "数量(件)", "数量（件）",
    ],
    "sales_amount": [
        "销售额", "销售金额", "成交金额", "实付金额", "应付金额", "总金额", "金额", "营收",
        "amount", "sales", "salesamount", "revenue", "gmv", "销售额(元)", "销售额（元）",
    ],
    "channel": [
        "渠道", "销售渠道", "平台", "来源", "订单渠道",
        "channel", "source", "platform",
    ],
    "store": [
        "门店", "店铺", "门店名称", "店铺名称", "分店", "网点",
        "store", "shop", "branch", "storename",
    ],
    "region": [
        "地区", "区域", "省份", "城市", "大区", "地域",
        "region", "area", "city", "province", "zone",
    ],
    "order_id": [
        "订单号", "订单编号", "订单id", "交易编号",
        "orderid", "order_id", "orderno", "order_no",
    ],
}

# 维度字段（决定筛选框与对比/排行图是否出现）：规范键 -> 中文标签。
# 其它脚本只按这里的键遍历，不硬编码某个字段名。
DIMENSION_FIELDS: dict[str, str] = {
    "product_name": "商品名称",
    "channel": "渠道",
    "store": "门店",
    "region": "地区",
}

# 可选度量字段（决定相关指标/图表是否出现）。
METRIC_FIELDS: dict[str, str] = {
    "quantity": "数量",
    "order_id": "订单号",
    "unit_price": "单价",
    "sku": "SKU",
}


def normalize_name(name: Any) -> str:
    """归一化列名：去首尾空白、统一小写、去空格与括号，便于同义词匹配。"""
    if not isinstance(name, str):
        return ""
    n = name.strip().lower()
    for ch in " \t\r\n（）()【】[]":
        n = n.replace(ch, "")
    return n


def find_default_data_file(project_root: str | Path | None = None) -> Path:
    """返回优先级最高的默认数据文件。优先从 assets/ 选取，缺失时回退到 data/ 或项目根目录。"""
    root = Path(project_root) if project_root is not None else Path(__file__).resolve().parent.parent
    candidates: list[Path] = []
    for base in (root / "assets", root / "data", root):
        if not base.exists():
            continue
        if base.is_file() and base.suffix.lower() in {".csv", ".xlsx", ".xls", ".xlsm"}:
            candidates.append(base)
        elif base.is_dir():
            candidates.extend(
                p for p in base.iterdir()
                if p.is_file() and p.suffix.lower() in {".csv", ".xlsx", ".xls", ".xlsm"}
            )
    if not candidates:
        fallback = root / "data" / "sample_data.csv"
        return fallback
    candidates = sorted({p.resolve() for p in candidates}, key=lambda p: str(p).lower())
    return candidates[0]


def read_file(path: str | Path) -> pd.DataFrame:
    """读取 CSV / Excel 文件为 DataFrame。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"文件不存在：{p}")
    suffix = p.suffix.lower()
    if suffix == ".csv":
        for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
            try:
                return pd.read_csv(p, encoding=enc)
            except (UnicodeDecodeError, UnicodeError):
                continue
        raise ValueError("无法识别 CSV 编码，请转为 UTF-8 后重试。")
    if suffix in (".xlsx", ".xlsm"):
        return pd.read_excel(p, engine="openpyxl")
    if suffix == ".xls":
        return pd.read_excel(p, engine="xlrd")
    raise ValueError(f"不支持的文件类型：{suffix}（支持 .csv / .xlsx / .xls）")


# ---------------------------------------------------------------------------
# 字段识别
# ---------------------------------------------------------------------------
def _match_synonyms(norm_cols: list[str], raw_cols: list, syns: list[str], used: set) -> Any | None:
    """先精确匹配、再包含匹配，返回命中的原始列名（跳过已占用的列）。"""
    for norm_syn in syns:
        key = normalize_name(norm_syn)
        if not key:
            continue
        for raw, norm in zip(raw_cols, norm_cols):
            if norm == key and raw not in used:
                return raw
    for norm_syn in syns:
        key = normalize_name(norm_syn)
        if len(key) < 2:
            continue
        for raw, norm in zip(raw_cols, norm_cols):
            if key in norm and raw not in used:
                return raw
    return None


def _looks_like_date(x: str) -> bool:
    try:
        pd.to_datetime(x, errors="raise")
        return True
    except Exception:
        return False


def _infer_date_column(df: pd.DataFrame, raw_cols: list, used: set) -> tuple[Any | None, str]:
    """内容兜底：找可解析为日期的列。"""
    best_col, best_ratio = None, 0.0
    for col in raw_cols:
        if col in used:
            continue
        s = df[col]
        if pd.api.types.is_datetime64_any_dtype(s):
            return col, f"列「{col}」已是日期类型，自动识别为日期字段。"
        if pd.api.types.is_numeric_dtype(s):
            continue
        sample = s.dropna().head(200).astype(str)
        if sample.empty:
            continue
        ratio = sample.map(_looks_like_date).mean()
        if ratio > best_ratio:
            best_col, best_ratio = col, ratio
    if best_col and best_ratio >= 0.8:
        return best_col, f"列「{best_col}」约 {best_ratio:.0%} 的值可解析为日期，推断为日期字段（建议确认）。"
    return None, ""


def _infer_numeric_columns(df, raw_cols, used, field_map, detected, notes) -> None:
    """内容兜底：对未被识别的数值列做名称 + 幅度推断（低置信度，提示确认）。"""
    candidates = [
        c for c in raw_cols
        if c not in used and c not in field_map.values()
        and pd.api.types.is_numeric_dtype(df[c])
    ]
    for col in candidates:
        s = df[col].dropna()
        if s.empty:
            continue
        name = normalize_name(col)
        mean = float(s.mean())
        is_int = float((s % 1 == 0).mean()) > 0.9
        guess = None
        if any(k in name for k in ("单价", "价格", "price")):
            guess = "unit_price"
        elif any(k in name for k in ("数量", "销量", "件数", "qty", "count")):
            guess = "quantity"
        elif any(k in name for k in ("金额", "销售额", "营收", "amount", "sales", "gmv")):
            guess = "sales_amount"
        else:
            if mean > 1000:
                guess = "sales_amount"
            elif mean < 500 and is_int:
                guess = "quantity"
            else:
                guess = "unit_price"
        if guess and guess not in field_map:
            field_map[guess] = col
            detected.append({"field": guess, "column": col, "method": "内容推断（数值幅度）"})
            notes.append(f"列「{col}」按数值幅度推断为「{CANONICAL_FIELDS[guess]}」（低置信度，请确认）。")


def detect_fields(df: pd.DataFrame) -> dict:
    """自动识别字段。

    返回 dict:
      field_map : {规范字段: 原始列名}
      detected  : [{field, column, method}]
      missing   : [未识别字段的中文名]
      notes     : [提示文本]
      confidence: "high" | "medium" | "low"
    """
    raw_cols = list(df.columns)
    norm_cols = [normalize_name(c) for c in raw_cols]
    field_map: dict[str, Any] = {}
    used: set = set()
    detected: list[dict] = []
    notes: list[str] = []

    # 1) 列名匹配
    for canon, syns in FIELD_SYNONYMS.items():
        col = _match_synonyms(norm_cols, raw_cols, syns, used)
        if col is not None:
            field_map[canon] = col
            used.add(col)
            detected.append({"field": canon, "column": col, "method": "列名匹配"})

    # 2) 内容兜底：日期
    if "date" not in field_map:
        col, note = _infer_date_column(df, raw_cols, used)
        if col is not None:
            field_map["date"] = col
            used.add(col)
            detected.append({"field": "date", "column": col, "method": "内容推断"})
            notes.append(note)

    # 3) 内容兜底：数值字段
    _infer_numeric_columns(df, raw_cols, used, field_map, detected, notes)

    missing = [CANONICAL_FIELDS[k] for k in CANONICAL_FIELDS if k not in field_map]

    core = {"date", "sales_amount"}
    inferred = any(d["method"] != "列名匹配" for d in detected)
    if core <= set(field_map) and not inferred:
        confidence = "high"
    elif core <= set(field_map):
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "field_map": field_map,
        "detected": detected,
        "missing": missing,
        "notes": notes,
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# 可用字段
# ---------------------------------------------------------------------------
def available_fields(df: pd.DataFrame) -> dict:
    """返回数据中实际存在的维度/度量字段，供 UI 与图表动态使用。

    df 为清洗后数据（规范列名）。返回：
      dimensions: {规范键: 中文标签}  实际存在的维度（商品/渠道/门店/地区）
      metrics:    {规范键: 中文标签}  实际存在的可选度量（数量/订单号/单价/SKU）
    """
    cols = set(df.columns)
    return {
        "dimensions": {k: v for k, v in DIMENSION_FIELDS.items() if k in cols},
        "metrics": {k: v for k, v in METRIC_FIELDS.items() if k in cols},
    }


# ---------------------------------------------------------------------------
# 数据概览
# ---------------------------------------------------------------------------
def overview(df: pd.DataFrame) -> dict:
    """数据概览：形状、列、类型、缺失、重复、预览。"""
    nulls = df.isnull().sum()
    return {
        "shape": df.shape,
        "columns": list(df.columns),
        "dtypes": {str(c): str(df[c].dtype) for c in df.columns},
        "null_counts": {str(c): int(nulls[c]) for c in df.columns},
        "duplicate_rows": int(df.duplicated().sum()),
        "numeric_columns": df.select_dtypes(include="number").columns.tolist(),
        "head": df.head(5),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="读取数据并识别字段")
    ap.add_argument("path", help="CSV / Excel 文件路径")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = ap.parse_args(argv)

    df = read_file(args.path)
    ov = overview(df)
    det = detect_fields(df)

    if args.json:
        out = {
            "overview": {k: v for k, v in ov.items() if k != "head"},
            "detection": det,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0

    print("=" * 64)
    print(f"文件：{args.path}")
    print(f"形状：{ov['shape'][0]} 行 × {ov['shape'][1]} 列")
    print(f"重复行：{ov['duplicate_rows']}")
    print(f"缺失值统计：{ov['null_counts']}")
    print("\n字段识别结果：")
    for d in det["detected"]:
        print(f"  - {CANONICAL_FIELDS[d['field']]:<6} -> 「{d['column']}」（{d['method']}）")
    if det["missing"]:
        print(f"\n⚠ 缺少/未识别字段：{'、'.join(det['missing'])}")
    if det["notes"]:
        print("\n提示：")
        for n in det["notes"]:
            print(f"  - {n}")
    print(f"\n识别置信度：{det['confidence']}")
    print("\n数据预览（前 5 行）：")
    print(ov["head"].to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
