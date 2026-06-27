# -*- coding: utf-8 -*-
"""按 300896 的格式，为一批 A股公司批量采集深度研究材料到 docs/<code>/。

每家公司产出（与 docs/300896 同构）：
- financials/   Tushare 结构化财务 CSV（三表/指标/主营构成/股东/质押/管理层/分红/估值）+ 本系统已算指标
- reports/      巨潮官方 PDF：近 3 个年报 + 最新季报 + IPO 招股说明书（能找到的）
- announcements/ 全量公告索引 CSV（标题+日期+PDF链接）
- README.md     单公司清单（基础信息 + ROCE 序列 + 已采集/缺口）

逐条公告 PDF、券商研报、产品注册深挖因需逐家研究、量大，本批不下载（索引已给链接，按需再取）。
幂等：已存在文件跳过。限速避免触发巨潮/Tushare 限频。

用法：
    python -m scripts.collect_company_docs --codes 600519 000333        # 指定
    python -m scripts.collect_company_docs --from-file /tmp/codes.txt    # 文件(每行 code 或 code\\tname)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
import urllib.parse
import urllib.request

DOCS = "/srv/workspaces/zheyang/darwen/docs"
ORGMAP_PATH = "/tmp/cninfo_orgmap.json"
CNINFO_QUERY = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_STATIC = "http://static.cninfo.com.cn/"
HDR_JSON = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json", "X-Requested-With": "XMLHttpRequest"}
HDR_PDF = {"User-Agent": "Mozilla/5.0"}


def to_ts(code: str) -> str:
    return f"{code}.SH" if code[:1] == "6" else f"{code}.SZ"


def load_orgmap() -> dict:
    if os.path.exists(ORGMAP_PATH):
        return json.load(open(ORGMAP_PATH))
    m = {}
    for url in ("http://www.cninfo.com.cn/new/data/szse_stock.json",):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        d = json.loads(urllib.request.urlopen(req, timeout=40).read().decode("utf-8"))
        for x in (d.get("stockList") or []):
            if x.get("code"):
                m[x["code"]] = x.get("orgId")
    json.dump(m, open(ORGMAP_PATH, "w"))
    return m


# ---------------- Tushare 财务导出 ----------------

def dump_financials(pro, code: str, outdir: str) -> dict:
    ts = to_ts(code)
    stat = {}

    def dump(name, df, sort=None):
        if df is None or len(df) == 0:
            stat[name] = 0
            return
        if sort and sort in df.columns:
            df = df.sort_values(sort)
        df.to_csv(f"{outdir}/{name}.csv", index=False, encoding="utf-8-sig")
        stat[name] = len(df)

    dump("income_利润表", pro.income(ts_code=ts, start_date="20140101"), "end_date")
    dump("balancesheet_资产负债表", pro.balancesheet(ts_code=ts, start_date="20140101"), "end_date")
    dump("cashflow_现金流量表", pro.cashflow(ts_code=ts, start_date="20140101"), "end_date")
    dump("fina_indicator_财务指标", pro.fina_indicator(ts_code=ts, start_date="20140101"), "end_date")
    dump("fina_mainbz_主营构成_按产品", pro.fina_mainbz(ts_code=ts, type="P"), "end_date")
    dump("fina_mainbz_主营构成_按地区", pro.fina_mainbz(ts_code=ts, type="D"), "end_date")
    dump("top10_holders_前十大股东", pro.top10_holders(ts_code=ts, start_date="20140101", end_date="20261231"), "end_date")
    dump("top10_floatholders_前十大流通股东", pro.top10_floatholders(ts_code=ts, start_date="20140101", end_date="20261231"), "end_date")
    dump("pledge_stat_质押统计", pro.pledge_stat(ts_code=ts), "end_date")
    dump("stk_managers_管理层", pro.stk_managers(ts_code=ts), "ann_date")
    dump("dividend_分红", pro.dividend(ts_code=ts), "end_date")
    dump("daily_basic_估值历史", pro.daily_basic(
        ts_code=ts, start_date="20140101", end_date="20261231",
        fields="trade_date,close,pe,pe_ttm,pb,ps_ttm,dv_ttm,total_mv,circ_mv,turnover_rate"), "trade_date")
    return stat


def dump_darwen_metrics(db, code: str, outdir: str):
    from sqlalchemy import text
    rows = db.execute(text(
        "SELECT period_end, metric_name, value, formula_version, notes "
        "FROM metric_periodic WHERE company_id=:c ORDER BY metric_name, period_end"
    ), {"c": f"CN_{code}"}).all()
    with open(f"{outdir}/darwen_computed_metrics_本系统已算指标.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["period_end", "metric_name", "value", "formula_version", "notes"])
        for r in rows:
            w.writerow([r.period_end, r.metric_name, r.value, r.formula_version, r.notes])
    roce = [(r.period_end, r.value) for r in rows if r.metric_name == "roce"]
    return roce


# ---------------- 巨潮公告 ----------------

def cninfo_query(code: str, org: str, se_date: str, pages: int = 12) -> list:
    out = []
    for pn in range(1, pages + 1):
        body = {"stock": f"{code},{org}", "tabName": "fulltext", "pageSize": 30,
                "pageNum": pn, "column": "szse" if code[:1] != "6" else "sse",
                "category": "", "seDate": se_date, "isHLtitle": "true"}
        data = urllib.parse.urlencode(body).encode()
        r = None
        for attempt in range(3):
            try:
                req = urllib.request.Request(CNINFO_QUERY, data=data, headers=HDR_JSON)
                r = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))
                break
            except Exception:
                time.sleep(2)
        if not r:
            break
        out += (r.get("announcements") or [])
        if not r.get("hasMore"):
            break
        time.sleep(0.3)
    return out


def clean(t): return re.sub(r"<[^>]+>", "", t or "").strip()
def ann_date(a):
    ts = a.get("announcementTime", 0)
    return time.strftime("%Y-%m-%d", time.localtime(ts / 1000)) if ts else ""


def download_pdf(adj: str, path: str) -> bool:
    if os.path.exists(path) and os.path.getsize(path) > 1024:
        return True
    try:
        req = urllib.request.Request(CNINFO_STATIC + adj, headers=HDR_PDF)
        with urllib.request.urlopen(req, timeout=120) as r, open(path, "wb") as f:
            f.write(r.read())
        return os.path.getsize(path) > 1024
    except Exception:
        if os.path.exists(path):
            os.remove(path)
        return False


def collect_reports_and_index(code: str, org: str, base: str, list_year: int | None = None) -> dict:
    anns = {}
    for se in ["2024-01-01~2026-12-31", "2020-01-01~2023-12-31"]:
        for a in cninfo_query(code, org, se):
            aid = a.get("announcementId")
            if aid:
                anns[aid] = a
    anns = sorted(anns.values(), key=lambda x: x.get("announcementTime", 0), reverse=True)
    # 索引 CSV
    with open(f"{base}/announcements/announcement_index_公告索引.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["日期", "标题", "PDF链接"])
        for a in anns:
            url = CNINFO_STATIC + a.get("adjunctUrl", "") if a.get("adjunctUrl") else ""
            w.writerow([ann_date(a), clean(a.get("announcementTitle")), url])

    # 报告 PDF：近 3 年报 + 最新季报 + IPO 招股书
    # 标题常含公司名前缀（如「贵州茅台2025年年度报告」），故用 search；排除 摘要/英文 等非全文。
    got = {"annual": [], "quarter": None, "ipo": False}
    annual_re = re.compile(r"(\d{4})年年度报告")
    quarter_re = re.compile(r"(\d{4})年(第一季度报告|一季度报告|半年度报告|第三季度报告|三季度报告)")
    ipo_re = re.compile(r"首次公开发行股票.*招股说明书")
    skip_re = re.compile(r"摘要|英文|英文版|提示性|更正|补充|已取消|取消")
    for a in anns:
        ti = clean(a.get("announcementTitle")); adj = a.get("adjunctUrl")
        if not adj or skip_re.search(ti):
            continue
        m = annual_re.search(ti)
        if m and len(got["annual"]) < 3 and m.group(1) not in [x[0] for x in got["annual"]]:
            if download_pdf(adj, f"{base}/reports/{code}_{m.group(1)}年年度报告.pdf"):
                got["annual"].append((m.group(1), ti)); time.sleep(0.3)
            continue
        if got["quarter"] is None and quarter_re.search(ti):
            qlabel = quarter_re.search(ti).group(0)
            if download_pdf(adj, f"{base}/reports/{code}_{ann_date(a)}_{qlabel}.pdf"):
                got["quarter"] = qlabel; time.sleep(0.3)
            continue
        if not got["ipo"] and ipo_re.search(ti):
            if download_pdf(adj, f"{base}/reports/{code}_IPO招股说明书.pdf"):
                got["ipo"] = True; time.sleep(0.3)

    # IPO 招股书常因公告量大被分页截断 → 按上市年份定向补查
    if not got["ipo"] and list_year:
        ipo_anns = cninfo_query(code, org, f"{list_year-1}-01-01~{list_year}-12-31")
        for a in sorted(ipo_anns, key=lambda x: x.get("announcementTime", 0)):
            ti = clean(a.get("announcementTitle")); adj = a.get("adjunctUrl")
            if adj and ipo_re.search(ti) and not skip_re.search(ti):
                if download_pdf(adj, f"{base}/reports/{code}_IPO招股说明书.pdf"):
                    got["ipo"] = True
                    break
    return {"announcements": len(anns), **got}


# ---------------- 单公司 ----------------

def collect_one(pro, db, code: str, name: str, orgmap: dict) -> dict:
    base = f"{DOCS}/{code}"
    for sub in ("financials", "reports", "announcements"):
        os.makedirs(f"{base}/{sub}", exist_ok=True)
    fin = dump_financials(pro, code, f"{base}/financials")
    roce = dump_darwen_metrics(db, code, f"{base}/financials")
    org = orgmap.get(code)
    rep = {"announcements": 0, "annual": [], "quarter": None, "ipo": False}
    if org:
        from sqlalchemy import text
        ld = db.execute(text("SELECT list_date FROM company WHERE company_id=:c"),
                        {"c": f"CN_{code}"}).scalar()
        list_year = ld.year if ld else None
        rep = collect_reports_and_index(code, org, base, list_year)
    _write_readme(base, code, name, fin, roce, rep, bool(org))
    return {"code": code, "name": name, "fin_tables": sum(1 for v in fin.values() if v),
            "annual_pdf": len(rep["annual"]), "quarter_pdf": bool(rep["quarter"]),
            "ipo_pdf": rep["ipo"], "anns_index": rep["announcements"], "org_found": bool(org)}


def _write_readme(base, code, name, fin, roce, rep, org_found):
    ts = to_ts(code)
    roce_lines = "\n".join(f"| {pe} | {v:.3f} |" for pe, v in roce if v is not None) or "| - | 无 |"
    annuals = "、".join(f"{y}年报" for y, _ in rep["annual"]) or "无"
    lines = [
        f"# {code} {name} — 研究材料包",
        "",
        f"> 采集日期：2026-06-27 ｜ Tushare({ts}) + 巨潮 cninfo ｜ 本系统：`CN_{code}`",
        f"> 格式同 `docs/300896`。官方 PDF 为权威底稿；Tushare CSV 便于复算 ROCE/营运资本/FCF/TTM PE。",
        "",
        "## 已采集",
        "",
        "| 类别 | 内容 |",
        "|---|---|",
        f"| 财务 CSV（financials/）| 三表/指标/主营构成/股东/质押/管理层/分红/估值历史 + 本系统已算指标，共 {sum(1 for v in fin.values() if v)} 张 |",
        f"| 年报 PDF（reports/）| {annuals} |",
        f"| 最新季报 PDF | {rep['quarter'] or '无'} |",
        f"| IPO 招股说明书 | {'已下载' if rep['ipo'] else '未找到（老股或巨潮无存档）'} |",
        f"| 公告索引（announcements/）| {rep['announcements']} 条（标题+日期+PDF链接 CSV）|",
        "",
        "## ROCE 序列（本系统已算，roce = EBIT/(净营运资本+固定资产净值)）",
        "",
        "| period_end | roce |",
        "|---|---|",
        roce_lines,
        "",
        "> 注：轻资产公司个别早年 ROCE 可能畸高（净营运资本极小放大），分析剔除异常年。",
        "",
        "## 缺口（按需再取，同 300896 做法）",
        "",
        "- 逐条重大公告 PDF：见 `announcements/announcement_index_公告索引.csv` 链接，按需下载。",
        "- 券商深度报告：东方财富研报中心 / 慧博按「{name} {code}」检索。".replace("{name}", name).replace("{code}", code),
        "- 产品注册/行业研究：按公司所属行业从 NMPA / 行业库补充。",
        "- 投资者关系活动记录表：深交所互动易 / Wind / iFinD。",
    ]
    if not org_found:
        lines.append("\n> ⚠️ 未在巨潮映射中找到 orgId，报告/公告未采集，仅有 Tushare 财务 CSV。")
    open(f"{base}/README.md", "w", encoding="utf-8").write("\n".join(lines))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--codes", nargs="*", default=[])
    p.add_argument("--from-file", default=None)
    args = p.parse_args()

    from backend.pipeline.cn_stock_v2.tushare_client import get_pro
    from backend.database import SessionLocal

    pairs = []
    if args.from_file:
        for line in open(args.from_file):
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            pairs.append((parts[0], parts[1] if len(parts) > 1 else ""))
    for c in args.codes:
        pairs.append((c, ""))

    orgmap = load_orgmap()
    pro = get_pro()
    db = SessionLocal()
    results = []
    try:
        for i, (code, name) in enumerate(pairs, 1):
            try:
                r = collect_one(pro, db, code, name, orgmap)
                results.append(r)
                print(f"[{i}/{len(pairs)}] {code} {name}  财务{r['fin_tables']}张 "
                      f"年报{r['annual_pdf']} 季报{int(r['quarter_pdf'])} IPO{int(r['ipo_pdf'])} "
                      f"公告索引{r['anns_index']}", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"[{i}/{len(pairs)}] {code} {name}  失败: {str(e)[:120]}", flush=True)
            time.sleep(0.5)
    finally:
        db.close()
    print(json.dumps({"total": len(pairs), "done": len(results)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
