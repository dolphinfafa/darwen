# -*- coding: utf-8 -*-
"""阶段3 商业深度抽取单测：iXBRL/文本 → 客户集中度 / segment HHI / 供应商旗标。

合成最小 iXBRL 片段（不依赖网络），锁定实测发现的关键边界：
- 客户集中度仅认「营收口径 + 客户类型 + 具体大客户成员 + 主报告期」（排除应收/地理/产品/合计/比较期）
- 营收基准兼容多成员（RevenueFromContractWithCustomer / SalesRevenueNet）
- segment HHI 仅取 OperatingSegments × BusinessSegments 两轴，排除公司/抵消项
"""
import warnings

import pytest
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

from backend.pipeline.commercial.sec_commercial import (
    _parse_contexts, _plain_text,
    extract_customer_concentration, extract_segment_hhi, extract_supplier_flag,
)


def _ctx(cid, dims_xml, *, start="2024-01-01", end="2024-12-31", instant=None):
    if instant:
        period = f"<instant>{instant}</instant>"
    else:
        period = f"<startDate>{start}</startDate><endDate>{end}</endDate>"
    return f'<context id="{cid}"><period>{period}</period><segment>{dims_xml}</segment></context>'


def _member(axis, member):
    return f'<explicitMember dimension="{axis}">{member}</explicitMember>'


def _conc(cid, val):
    return (f'<ix:nonFraction name="us-gaap:ConcentrationRiskPercentage1" '
            f'contextRef="{cid}" scale="-2" unitRef="n">{val}</ix:nonFraction>')


def _seg_rev(cid, val):
    return (f'<ix:nonFraction name="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax" '
            f'contextRef="{cid}" scale="0" unitRef="usd">{val}</ix:nonFraction>')


def _soup(body):
    return BeautifulSoup(f"<xbrl>{body}</xbrl>", "lxml")


# ---------------- 客户集中度 ----------------

def test_customer_revenue_concentration_hit():
    """营收口径 + 客户类型 + 具体大客户 + 主报告期 → 命中。"""
    body = (
        _ctx("c1", _member("srt:MajorCustomersAxis", "co:CustomerAMember")
             + _member("us-gaap:ConcentrationRiskByTypeAxis", "us-gaap:CustomerConcentrationRiskMember")
             + _member("us-gaap:ConcentrationRiskByBenchmarkAxis", "us-gaap:RevenueFromContractWithCustomerMember"))
        + _conc("c1", "28")
    )
    pct, pe = extract_customer_concentration(_soup(body), _parse_contexts(_soup(body)), "")
    assert pct == pytest.approx(0.28)
    assert pe is not None and pe.year == 2024


def test_customer_ar_benchmark_excluded():
    """应收账款口径不应计入客户集中度。"""
    body = (
        _ctx("c1", _member("srt:MajorCustomersAxis", "co:CustomerAMember")
             + _member("us-gaap:ConcentrationRiskByTypeAxis", "us-gaap:CustomerConcentrationRiskMember")
             + _member("us-gaap:ConcentrationRiskByBenchmarkAxis", "us-gaap:AccountsReceivableMember"))
        + _conc("c1", "55")
    )
    soup = _soup(body)
    pct, _ = extract_customer_concentration(soup, _parse_contexts(soup), "")
    assert pct is None


def test_geographic_concentration_excluded():
    """地理集中度（type=GeographicConcentrationRisk）不是客户集中度，应排除（实测误报根因）。"""
    body = (
        _ctx("c1", _member("us-gaap:ConcentrationRiskByTypeAxis", "us-gaap:GeographicConcentrationRiskMember")
             + _member("us-gaap:ConcentrationRiskByBenchmarkAxis", "us-gaap:RevenueFromContractWithCustomerMember"))
        + _conc("c1", "100")
    )
    soup = _soup(body)
    pct, _ = extract_customer_concentration(soup, _parse_contexts(soup), "")
    assert pct is None


def test_customer_sales_revenue_net_benchmark():
    """旧概念 SalesRevenueNet 营收基准也应接受（如 Fabrinet）。"""
    body = (
        _ctx("c1", _member("srt:MajorCustomersAxis", "co:NvidiaMember")
             + _member("us-gaap:ConcentrationRiskByTypeAxis", "us-gaap:CustomerConcentrationRiskMember")
             + _member("us-gaap:ConcentrationRiskByBenchmarkAxis", "us-gaap:SalesRevenueNetMember"))
        + _conc("c1", "27")
    )
    soup = _soup(body)
    pct, _ = extract_customer_concentration(soup, _parse_contexts(soup), "")
    assert pct == pytest.approx(0.27)


def test_customer_comparative_period_excluded():
    """仅认主报告期：旧比较期(2023)的客户事实在更新主报告期(2025)存在时应被排除。"""
    body = (
        # 主报告期标记（一条 2025 的 duration context，无关事实即可抬高 primary）
        _ctx("base", "", start="2025-01-01", end="2025-12-31") + _seg_rev_noop("base")
        + _ctx("c_old", _member("srt:MajorCustomersAxis", "co:CustomerAMember")
               + _member("us-gaap:ConcentrationRiskByTypeAxis", "us-gaap:CustomerConcentrationRiskMember")
               + _member("us-gaap:ConcentrationRiskByBenchmarkAxis", "us-gaap:RevenueFromContractWithCustomerMember"),
               start="2023-01-01", end="2023-12-31")
        + _conc("c_old", "30")
    )
    soup = _soup(body)
    pct, _ = extract_customer_concentration(soup, _parse_contexts(soup), "")
    assert pct is None  # 2023 比较期 ≠ 主报告期 2025


@pytest.mark.parametrize("member", [
    "gis:FiveLargestCustomersMember",          # 合并：前五大客户
    "cci:TMoAttAndVerizonCombinedMember",      # 合并：三家合计
    "zs:ChannelPartnersMember",                # 销售渠道（非客户）
    "zs:DirectCustomersMember",                # 销售渠道（直销）
    "co:TwoUtilityCustomersMember",            # 合并：两家
])
def test_customer_aggregate_and_channel_members_excluded(member):
    """合并客户群 / 销售渠道成员不是单一客户，应排除（实测误报根因）。"""
    body = (
        _ctx("c1", _member("srt:MajorCustomersAxis", member)
             + _member("us-gaap:ConcentrationRiskByTypeAxis", "us-gaap:CustomerConcentrationRiskMember")
             + _member("us-gaap:ConcentrationRiskByBenchmarkAxis", "us-gaap:RevenueFromContractWithCustomerMember"))
        + _conc("c1", "91")
    )
    soup = _soup(body)
    pct, _ = extract_customer_concentration(soup, _parse_contexts(soup), "")
    assert pct is None


def test_customer_picks_max_single_over_aggregate():
    """同期既有单一客户(Walmart 31%)又有合并群(五大 66%)→ 取单一客户值。"""
    single = _ctx("c1", _member("srt:MajorCustomersAxis", "gis:WalmartMember")
                  + _member("us-gaap:ConcentrationRiskByTypeAxis", "us-gaap:CustomerConcentrationRiskMember")
                  + _member("us-gaap:ConcentrationRiskByBenchmarkAxis", "us-gaap:RevenueFromContractWithCustomerMember")) + _conc("c1", "31")
    agg = _ctx("c2", _member("srt:MajorCustomersAxis", "gis:FiveLargestCustomersMember")
               + _member("us-gaap:ConcentrationRiskByTypeAxis", "us-gaap:CustomerConcentrationRiskMember")
               + _member("us-gaap:ConcentrationRiskByBenchmarkAxis", "us-gaap:RevenueFromContractWithCustomerMember")) + _conc("c2", "66")
    soup = _soup(single + agg)
    pct, _ = extract_customer_concentration(soup, _parse_contexts(soup), "")
    assert pct == pytest.approx(0.31)


def test_customer_text_fallback_no_customer():
    """iXBRL 无客户事实 + 文本明示无单一客户 >10% → 视为分散不记。"""
    soup = _soup("")
    pct, _ = extract_customer_concentration(
        soup, _parse_contexts(soup),
        "No customer accounted for at least 10% of the Company's consolidated net revenue.")
    assert pct is None


def test_customer_text_fallback_pct():
    soup = _soup("")
    pct, _ = extract_customer_concentration(
        soup, _parse_contexts(soup),
        "One customer accounted for approximately 22% of our net revenue in fiscal 2025.")
    assert pct == pytest.approx(0.22)


# ---------------- segment HHI ----------------

def test_segment_hhi():
    body = (
        _seg_member("s1", "co:DataCenterMember", "60")
        + _seg_member("s2", "co:GamingMember", "40")
    )
    soup = _soup(body)
    hhi, n, pe = extract_segment_hhi(soup, _parse_contexts(soup))
    assert n == 2
    assert hhi == pytest.approx(0.6 ** 2 + 0.4 ** 2)  # 0.52


def test_segment_single_returns_none():
    """单一分部不计 HHI（避免 HHI=1 噪声）。"""
    soup = _soup(_seg_member("s1", "co:OnlySegmentMember", "100"))
    hhi, n, pe = extract_segment_hhi(soup, _parse_contexts(soup))
    assert hhi is None


# ---------------- 供应商旗标 ----------------

@pytest.mark.parametrize("text,expect", [
    ("We depend on a limited number of suppliers for key components.", True),
    ("Certain components are available only from a sole supplier.", True),
    ("We have a diversified supplier base across many vendors.", False),
])
def test_supplier_flag(text, expect):
    assert bool(extract_supplier_flag(text)) is expect


# ---- 测试辅助：构造 segment 营收事实 / 占位 ----

def _seg_member(cid, member, val):
    dims = (_member("srt:ConsolidationItemsAxis", "us-gaap:OperatingSegmentsMember")
            + _member("us-gaap:StatementBusinessSegmentsAxis", member))
    return _ctx(cid, dims, start="2024-01-01", end="2024-12-31") + _seg_rev(cid, val)


def _seg_rev_noop(cid):
    """一条普通营收事实，仅用于抬高主报告期，不带 segment 轴。"""
    return (f'<ix:nonFraction name="us-gaap:Revenues" contextRef="{cid}" '
            f'scale="0" unitRef="usd">1000</ix:nonFraction>')
