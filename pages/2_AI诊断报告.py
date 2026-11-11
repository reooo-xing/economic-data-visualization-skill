# -*- coding: utf-8 -*-
"""2_AI诊断报告.py — AI 诊断报告页（接入 DeepSeek 大模型，多轮聊天界面）。

数据来自 st.session_state（由 Home.py 缓存），本页不重新读取文件。
DeepSeek 配置从 .streamlit/secrets.toml 读取（st.secrets["deepseek"]）：
密钥绝不硬编码、绝不出现在前端。用户直接在聊天框提问，支持多轮对话。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 让页面脚本能 import utils/ 下的模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "utils"))

import pandas as pd
import streamlit as st
from openai import OpenAI

from ui_helpers import fmt_money, fmt_pct

# ---------------------------------------------------------------------------
# 大模型配置（仅模型名在此；api_key / base_url 从 st.secrets 读取，禁止写死）
# ---------------------------------------------------------------------------
DEEPSEEK_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com"

# 系统提示词：固定人设 + 报告结构要求
SYSTEM_PROMPT = (
    "你是一位拥有15年经验的资深零售业商业分析师。你的风格是数据敏锐、结论直接。"
    "请根据提供的数据摘要，生成《店铺销售诊断报告》。"
    "请严格使用 Markdown 格式，并包含【滞销预警】、【异常洞察】、【行动处方】三个模块。"
    "如果用户提供的维度不全，请基于现有数据尽力分析，并在报告开头给予说明。"
    "若用户提出后续问题，请结合数据摘要与对话上下文继续回答。"
)


def get_deepseek_config() -> dict[str, str]:
    """从 st.secrets 安全读取 DeepSeek 配置（密钥不硬编码、不外泄）。

    任何缺失 / 格式错误都返回空配置，绝不抛异常、不暴露错误堆栈；
    由调用方根据 api_key 是否为空给出友好提示。

    注意：st.secrets["deepseek"] 返回的是 Streamlit 的 AttrDict（Mapping 子类，
    不是 dict），因此这里直接用 .get() 取值，不要用 isinstance(dict) 判断。
    """

    def _safe_get(key: str, default: str) -> str:
        try:
            value = st.secrets["deepseek"].get(key, default)
            return str(value or default).strip()
        except Exception:
            return default

    return {
        "api_key": _safe_get("api_key", ""),
        "base_url": _safe_get("base_url", DEFAULT_BASE_URL),
    }


def generate_data_summary(df: pd.DataFrame) -> str:
    """把任意 DataFrame 提炼成给大模型的文字摘要（强容错）。

    使用模糊匹配识别「日期 / 产品 / 销售额 / 销量」四类列（中文或英文列名均可）。
    某类列匹配不到时【不报错】，在摘要里标记「未提供相关数据」并跳过该维度分析。
    """
    # 空数据兜底，避免后续统计报错
    if df is None or df.empty:
        return "（数据为空，无法生成摘要。）"

    cols = [str(c) for c in df.columns]
    low = [c.lower() for c in cols]  # 英文列名统一小写，便于忽略大小写匹配

    def _pick(kw_cn: tuple[str, ...], kw_en: tuple[str, ...]) -> str | None:
        """模糊匹配列名：任一中文关键字命中 或 任一英文关键字命中即返回该列名。"""
        for i, c in enumerate(cols):
            if any(k in c for k in kw_cn) or any(k in low[i] for k in kw_en):
                return c
        return None

    def _num(col: str) -> pd.Series:
        """把列安全转为数值：去掉千分位逗号与货币符号，无法解析的按 NaN。"""
        s = df[col].astype(str).str.replace(",", "", regex=False)
        s = s.str.replace("￥", "", regex=False).str.replace("¥", "", regex=False).str.strip()
        return pd.to_numeric(s, errors="coerce")

    # 识别四类列（找不到则为 None，后续跳过对应维度）
    date_col = _pick(("日期", "时间", "下单", "结算", "交易"), ("date", "time", "day"))
    product_col = _pick(("商品", "产品", "品名"), ("product", "goods", "item"))
    sales_col = _pick(("销售额", "销售金额", "成交金额", "实付金额", "营收", "收入"),
                      ("sales", "amount", "revenue", "gmv"))
    qty_col = _pick(("销量", "数量", "件数"), ("quantity", "qty", "volume"))

    lines: list[str] = [f"【数据概览】共 {len(df):,} 行 × {len(cols)} 列。"]
    lines.append("全部列名：" + "、".join(cols) + "。")

    # ---- 日期维度 ----
    if date_col:
        try:
            d = pd.to_datetime(df[date_col], errors="coerce")
            valid = d.dropna()
            if valid.empty:
                lines.append(f"日期列「{date_col}」：未能解析出有效日期。")
            else:
                span = f"{valid.min():%Y-%m-%d} 至 {valid.max():%Y-%m-%d}"
                months = valid.dt.to_period("M").nunique()
                lines.append(f"日期列「{date_col}」：范围 {span}，跨度约 {months} 个月。")
        except Exception:
            lines.append(f"日期列「{date_col}」：日期解析失败，跳过时间维度分析。")
    else:
        lines.append("日期：未提供相关数据，跳过时间趋势分析。")

    # ---- 销售额维度 ----
    if sales_col:
        sales = _num(sales_col).dropna()
        if sales.empty:
            lines.append(f"销售额列「{sales_col}」：无有效数值。")
        else:
            lines.append(f"销售额列「{sales_col}」：总计 {fmt_money(sales.sum())}，"
                         f"均值 {fmt_money(sales.mean())}，最高单笔 {fmt_money(sales.max())}。")
    else:
        lines.append("销售额：未提供相关数据，跳过销售额分析。")

    # ---- 销量维度 ----
    if qty_col:
        qty = _num(qty_col).dropna()
        if qty.empty:
            lines.append(f"销量列「{qty_col}」：无有效数值。")
        else:
            lines.append(f"销量列「{qty_col}」：总计 {int(qty.sum()):,} 件，均值 {qty.mean():,.1f} 件。")
    else:
        lines.append("销量：未提供相关数据，跳过销量分析。")

    # ---- 产品维度（含销售额 Top 5，需要销售额列配合） ----
    if product_col:
        n_products = df[product_col].nunique(dropna=True)
        lines.append(f"产品列「{product_col}」：共 {n_products} 个不同商品。")
        if sales_col:
            try:
                sales = _num(sales_col)
                total = float(sales.sum())
                top = (df.assign(__sales=sales)
                         .groupby(product_col)["__sales"]
                         .sum().sort_values(ascending=False).head(5))
                if not top.empty:
                    if total > 0:
                        items = "、".join(f"{k}（{fmt_money(v)}，占比 {fmt_pct(v / total)}）"
                                          for k, v in top.items())
                    else:
                        items = "、".join(f"{k}（{fmt_money(v)}）" for k, v in top.items())
                    lines.append(f"销售额 Top 5 商品：{items}。")
            except Exception:
                pass  # Top 排名失败不影响整体摘要
    else:
        lines.append("产品：未提供相关数据，跳过商品维度分析。")

    return "\n".join(lines)


def build_chat_reply(client: OpenAI, data_summary: str, history: list[dict]) -> str:
    """组装「系统人设 + 数据摘要 + 多轮对话历史」并调用 DeepSeek 生成回复。

    抛出的异常（网络错误 / Key 无效 / 模型不可用等）由调用方 try-except 统一捕获。
    """
    system_content = f"{SYSTEM_PROMPT}\n\n【本次分析的数据摘要】\n{data_summary}"

    messages: list[dict] = [{"role": "system", "content": system_content}]
    messages.extend(history)  # 多轮对话历史（user / assistant 交替）

    resp = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=messages,
        temperature=0.3,  # 降低随机性，让诊断结论更稳定、可直接执行
    )
    return resp.choices[0].message.content or ""


def main() -> None:
    st.title("AI 诊断报告")
    st.caption("接入 DeepSeek 大模型，基于数据摘要进行多轮智能诊断（密钥已隐藏，无需手动配置）。")

    # 1) 数据来自 Home.py 缓存的 session_state，不重新读取文件
    cleaned = st.session_state.get("cleaned_df")
    raw = st.session_state.get("raw_df")
    report = st.session_state.get("report")

    if cleaned is None:
        st.error("尚未加载数据。请回到「首页」检查数据文件。")
        st.stop()
    if "error" in (report or {}):
        st.error(report["error"])
        st.stop()

    # 2) 从 st.secrets 读取 DeepSeek 配置（密钥不显示、不硬编码）
    cfg = get_deepseek_config()
    api_key = cfg["api_key"]
    base_url = cfg["base_url"]

    if not api_key:
        st.info(
            "尚未配置 DeepSeek API Key。\n\n"
            "请在项目根目录创建 `.streamlit/secrets.toml`，内容如下：\n\n"
            "```toml\n"
            "[deepseek]\n"
            'api_key = "sk-你的密钥"\n'
            'base_url = "https://api.deepseek.com"\n'
            "```\n\n"
            "保存后重启应用（`streamlit run Home.py`）即可使用。"
        )
        st.stop()

    # 3) 初始化 OpenAI 客户端（openai.OpenAI）
    client = OpenAI(api_key=api_key, base_url=base_url)

    # 4) 数据摘要（优先用原始数据，保留原始列名便于模糊匹配）
    summary_df = raw if raw is not None else cleaned
    data_summary = generate_data_summary(summary_df)

    with st.expander("查看数据摘要（将作为 AI 分析的上下文）"):
        st.write(data_summary)

    # 5) 初始化多轮对话历史
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": (
                    "你好，我是你的 AI 零售分析师。我已读取当前数据，你可以直接提问，例如：\n\n"
                    "- 帮我生成《店铺销售诊断报告》\n"
                    "- 哪些商品滞销？\n"
                    "- 近几个月销售趋势如何？"
                ),
            }
        ]

    # 6) 渲染历史消息
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 7) 聊天输入框（多轮对话）
    if prompt := st.chat_input("输入你的问题，例如「帮我生成诊断报告」"):
        # 先记录并显示用户消息
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # 再生成并显示助手回复
        with st.chat_message("assistant"):
            with st.spinner("AI 分析师正在深度诊断中..."):
                try:
                    reply = build_chat_reply(client, data_summary, st.session_state.messages)
                    st.markdown(reply)
                    # 仅在成功时保存，保证上下文一致（失败可重试，不留错误记录）
                    st.session_state.messages.append({"role": "assistant", "content": reply})
                except Exception:
                    st.error("网络异常或服务暂时不可用，请稍后重试。")


main()
