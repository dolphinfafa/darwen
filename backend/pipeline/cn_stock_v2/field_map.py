# -*- coding: utf-8 -*-
"""Tushare Pro 字段 → canonical 字段名映射

canonical 字段与 SEC us-gaap 的 ROCE 计算保持一致命名，便于 metrics/* 复用。
"""

# Tushare income (利润表) → canonical
INCOME_FIELD_MAP = {
    "revenue": "revenue",                  # 营业收入
    "total_revenue": "total_revenue",      # 营业总收入
    "oper_cost": "operating_cost",         # 营业成本
    "n_income": "net_income",              # 净利润
    "n_income_attr_p": "net_income_to_parent",  # 归母净利
    "operate_profit": "operating_income",  # 营业利润（EBIT 近似）
    "ebit": "ebit",                        # 部分公司直接给
    "total_profit": "total_profit",        # 利润总额
    "income_tax": "income_tax",
    "int_exp": "interest_expense",         # 利息费用
    "rd_exp": "rd_expense",                # 研发费用
    "sell_exp": "selling_expense",
    "admin_exp": "admin_expense",
    "fin_exp": "finance_expense",
    "basic_eps": "eps_basic",
    "diluted_eps": "eps_diluted",
}

# Tushare balancesheet → canonical
BALANCESHEET_FIELD_MAP = {
    "total_assets": "total_assets",
    "total_liab": "total_liabilities",
    "total_hldr_eqy_inc_min_int": "stockholders_equity",
    "total_hldr_eqy_exc_min_int": "equity_to_parent",
    "total_cur_assets": "current_assets",
    "total_cur_liab": "current_liabilities",
    "money_cap": "cash_and_equivalents",       # 货币资金
    "trad_asset": "short_term_investments",    # 交易性金融资产（部分情况）
    "st_borr": "short_term_debt",              # 短期借款
    "non_cur_liab_due_1y": "current_portion_ltd",  # 一年内到期非流动负债
    "lt_borr": "long_term_debt",
    "fix_assets": "ppe_net",                   # 固定资产合计（净值）
    "goodwill": "goodwill",
    "intan_assets": "intangible_assets",
    "inventories": "inventory",
    "accounts_receiv": "accounts_receivable",
    "accounts_pay": "accounts_payable",
    "total_share": "shares_outstanding",       # 总股本（万股）
    "lease_liab": "current_lease_liability",   # 部分公司
}

# Tushare cashflow → canonical
CASHFLOW_FIELD_MAP = {
    "n_cashflow_act": "ocf",                   # 经营活动净现金流
    "c_paid_for_assets": "capex_cash",         # 购建固定/无形资产支付现金
    "free_cashflow": "fcf",                    # 自由现金流（部分给）
    "c_pay_dist_dpcp_int_exp": "dividends_and_interest_paid",
    "c_recp_borrow": "borrowings_received",
}

# Tushare daily_basic → canonical
DAILY_BASIC_FIELD_MAP = {
    "close": "close_price",
    "turnover_rate": "turnover_rate",
    "pe_ttm": "pe_ttm",
    "pb": "pb",
    "ps_ttm": "ps_ttm",
    "dv_ttm": "dividend_yield_ttm",
    "total_share": "total_share_wan",          # 万股
    "float_share": "float_share_wan",
    "total_mv": "market_cap_wan",              # 万元
    "circ_mv": "float_market_cap_wan",
}


def market_to_exchange(symbol: str) -> str:
    """根据 6 位代码判断交易所"""
    if symbol.startswith("6"):
        return "SSE"
    elif symbol.startswith(("0", "3")):
        return "SZSE"
    elif symbol.startswith(("8", "4")):
        return "BSE"
    return "UNKNOWN"


def to_ts_code(stock_code: str) -> str:
    """6 位代码 → Tushare ts_code 格式（如 '600519' → '600519.SH'）"""
    exch = market_to_exchange(stock_code)
    suffix = {"SSE": "SH", "SZSE": "SZ", "BSE": "BJ"}.get(exch, "")
    return f"{stock_code}.{suffix}" if suffix else stock_code


def from_ts_code(ts_code: str) -> str:
    """ts_code → 6 位代码"""
    return ts_code.split(".")[0]
