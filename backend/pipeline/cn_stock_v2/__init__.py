# -*- coding: utf-8 -*-
"""A股数据管道 V2：通过 Tushare Pro 拉取财报、行情、披露日期与公告

替代旧的 cn_stock/ 目录（基于 AKShare）。Tushare Pro 提供：
- pro.income / balancesheet / cashflow — 财务三表
- pro.daily / daily_basic — 日线行情 + PE/PB/市值
- pro.disclosure_date — 财报披露日期（点时回测核心字段）
- pro.anns_d — 全量公告原文
- pro.stock_basic — 股票池白名单
"""
