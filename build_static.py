"""법안별 정적 HTML 페이지 + 사이트맵 생성 (페이지 단위 SEO·공유 미리보기).
out/bill/<의안번호>.html — 제목·개요·표결이 HTML에 박힌 + OG/메타 태그
out/index.html — 메인 피드 앱 복사
out/sitemap.xml, out/robots.txt
호스팅 시 BASE_URL 을 실제 도메인으로 바꾸면 절대 URL/사이트맵이 완성됩니다.
"""
import os, re, json, html, shutil
from collections import defaultdict
import pandas as pd

BASE_URL = "https://brbrlim.github.io/assembly-vote"   # GitHub Pages 프로젝트 페이지
OUT = "out"

b = pd.read_csv("bills_22.csv", dtype=str)
b["dt"] = pd.to_datetime(b["PROC_DT"], errors="coerce")
votes = pd.read_parquet("votes_raw_22.parquet")
summ = json.load(open("summaries.json", encoding="utf-8"))
won = json.load(open("wonmun.json", encoding="utf-8"))
headlines = json.load(open("headlines.json", encoding="utf-8")) if os.path.exists("headlines.json") else {}
overviews = json.load(open("overviews_gemini.json", encoding="utf-8")) if os.path.exists("overviews_gemini.json") else {}
if os.path.exists("overviews.json"):
    overviews.update(json.load(open("overviews.json", encoding="utf-8")))   # 수작업 다듬은 데모 우선

PC = {"더불어민주당": "#152484", "국민의힘": "#e61e2b", "조국혁신당": "#06d6a0", "개혁신당": "#ff7920",
      "진보당": "#d6001c", "기본소득당": "#00b5b8", "사회민주당": "#f58220", "무소속": "#888"}
PORDER = list(PC)
VL = {"찬성": ("찬성", "#34a853"), "반대": ("반대", "#ea4335"), "기권": ("기권", "#fbbc04"), "불참": ("불참", "#9aa0a6")}
CMTEMOJI = {"기획재정": "💰", "정무": "🏦", "국방": "🛡️", "법제사법": "⚖️", "행정안전": "🏛️", "교육": "🎓",
            "보건복지": "🏥", "환경노동": "🌿", "국토교통": "🚦", "농림축산식품해양수산": "🌾", "산업통상자원": "🏭",
            "과학기술정보방송통신": "📡", "문화체육관광": "🎭", "외교통일": "🌏", "여성가족": "👨‍👩‍👧", "국회운영": "🏛️"}

# 의원명 → 정당, 안건별 표결 집계(정당/명단)
NAME2PARTY = (votes.groupby("HG_NM")["POLY_NM"].agg(lambda s: s.value_counts().index[0])).to_dict()
PB = defaultdict(lambda: defaultdict(list))                # PB[bid][party] = [(name,res),...]
for bid, party, nm, res in zip(votes.BILL_ID, votes.POLY_NM, votes.HG_NM, votes.RESULT_VOTE_MOD):
    PB[bid][party].append((nm, res))

def esc(s): return html.escape(str(s or ""))
def cmt_emoji(c):
    for k, e in CMTEMOJI.items():
        if c and k in c: return e
    return "📋"
def friendly(n):
    s = re.sub(r"\([^)]*위원장\)", "", n); s = re.sub(r"\([^)]*의원[^)]*\)", "", s)
    for x in ["(정부)", "(대안)", "(의장)"]: s = s.replace(x, "")
    s = s.replace("일부개정법률안", "개정안").replace("전부개정법률안", "전부개정안")
    return re.sub(r"\s{2,}", " ", s).strip()
def proposer(n):
    if "(정부)" in n: return ("정부 발의", "")
    if "(의장)" in n: return ("국회의장 발의", "")
    m = re.search(r"\(([^)]*?위원장)\)", n)
    if m: return (m.group(1)[:18] + " 제안", "")
    m = re.search(r"\(([가-힣]{2,4})의원", n)
    if m: return ("최초제안 " + m.group(1), NAME2PARTY.get(m.group(1), ""))
    return ("", "")

def inline(s):
    s = esc(s)
    s = re.sub(r"\[(.+?)\]\((https?://[^)]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
def md_html(md):
    out, tbl = [], []
    def flush():
        if not tbl: return
        rows = [r for r in tbl if not re.match(r"^\s*\|?[\s|:\-]+\|?\s*$", r)]
        h = "<table>"
        for ri, r in enumerate(rows):
            cells = [c.strip() for c in r.strip().strip("|").split("|")]
            tag = "th" if ri == 0 else "td"
            h += "<tr>" + "".join(f"<{tag}>{inline(c)}</{tag}>" for c in cells) + "</tr>"
        out.append(h + "</table>"); tbl.clear()
    for ln in md.split("\n"):
        if "|" in ln and ln.strip().startswith("|"): tbl.append(ln); continue
        flush(); t = ln.strip()
        if not t or re.match(r"^-{3,}$", t): continue
        if re.match(r"^#{1,6}\s*\S", t):
            out.append("<h3>" + inline(re.sub(r"^#+\s*", "", t)) + "</h3>")
        elif re.match(r"^[-•]\s", t):
            out.append("<div class='li'>• " + inline(re.sub(r"^[-•]\s", "", t)) + "</div>")
        else:
            out.append("<p>" + inline(t) + "</p>")
    flush(); return "".join(out)

def description(bid, body):
    ov = (overviews.get(bid) or {}).get("text", "")
    if ov:
        m = re.search(r"##\s*한 줄 요약\s*\n+([^#]+)", ov)
        if m: return re.sub(r"\s+", " ", re.sub(r"[*#\[\]]", "", m.group(1))).strip()[:155]
    return re.sub(r"\s+", " ", body).strip()[:155]

PAGE = """<!DOCTYPE html><html lang="ko"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta property="og:title" content="{ogt}"><meta property="og:description" content="{desc}">
<meta property="og:type" content="article"><meta property="og:url" content="{url}">
<meta name="twitter:card" content="summary"><link rel="canonical" href="{url}">
<style>
 body{{font-family:-apple-system,"Apple SD Gothic Neo",sans-serif;max-width:720px;margin:0 auto;padding:18px;color:#1a1a1a;line-height:1.6}}
 .brandbar{{background:#16213e;margin:-18px -18px 0;padding:11px 18px}}
 .brandbar a{{color:#fff;text-decoration:none;font-weight:900;font-size:18px;letter-spacing:-.4px}}
 .brandbar .mk{{color:#f3c14b}} .brandbar .tg{{color:#cdd6e6;font-size:12px;margin-left:8px}}
 h1{{font-size:23px;line-height:1.35;margin:14px 0 4px}}
 .sub{{color:#9aa0a6;font-size:13px;margin-bottom:8px}}
 .meta{{font-size:13px;color:#555;margin:8px 0}} .meta span{{margin-right:12px}}
 .prop{{font-size:13px;margin:6px 0}} .dot{{display:inline-block;width:9px;height:9px;border-radius:50%;vertical-align:middle;margin-right:4px}}
 .ovw{{background:#eef5ff;border:1px solid #cfe0f5;border-radius:10px;padding:6px 16px;margin:16px 0}}
 .ovw h3{{font-size:15px;color:#16407a;margin:14px 0 4px}} .ovw p,.ovw .li{{font-size:14px;margin:4px 0}}
 .ovw table{{border-collapse:collapse;font-size:13px;margin:8px 0}} .ovw td,.ovw th{{border:1px solid #cfe0f5;padding:3px 9px}} .ovw th{{background:#dce8fb}}
 .bar{{display:flex;height:26px;border-radius:6px;overflow:hidden;margin:10px 0;font-size:11px}} .bar div{{display:flex;align-items:center;justify-content:center;color:#fff}}
 table.pv{{border-collapse:collapse;font-size:13px;width:100%;margin:10px 0}} table.pv td,table.pv th{{border-bottom:1px solid #eee;padding:5px 8px;text-align:left}}
 details{{margin:10px 0}} summary{{cursor:pointer;font-size:13px;color:#555}}
 .mem{{font-size:12px;color:#444;margin:2px 0}} .billlink{{display:inline-block;background:#16213e;color:#fff;padding:6px 14px;border-radius:16px;text-decoration:none;font-weight:600;margin-top:8px}}
 .sharebtn{{background:#f3c14b;color:#16213e;border:none;padding:7px 15px;border-radius:16px;font-weight:700;font-size:13px;cursor:pointer;margin:8px 0 0 6px}}
 #toast{{position:fixed;left:50%;bottom:34px;transform:translateX(-50%) translateY(20px);background:#16213e;color:#fff;padding:11px 20px;border-radius:24px;font-size:13px;font-weight:600;opacity:0;pointer-events:none;transition:.25s;box-shadow:0 6px 22px rgba(0,0,0,.3)}}
 #toast.show{{opacity:1;transform:translateX(-50%) translateY(0)}}
 footer{{margin-top:30px;font-size:11px;color:#aaa;border-top:1px solid #eee;padding-top:12px}}
</style></head><body>
<div class="brandbar"><a href="../index.html"><span class="mk">좌우</span>지간</a><span class="tg">좌든 우든, 표결은 팩트로</span></div>
<h1>{emoji} {head}</h1>
<div class="sub">{name}</div>
<div class="meta"><span>📅 {date}</span><span>🏛 {cmt}</span><span>결과 <b>{result}</b></span><span>의안번호 {no}</span></div>
{prop}
{ovw}
<h3 style="font-size:15px">📊 표결 결과</h3>
<div class="bar">{bar}</div>
<table class="pv"><tr><th>정당</th><th>찬성</th><th>반대</th><th>기권</th><th>불참</th></tr>{pvrows}</table>
{members}
<a class="billlink" href="{billurl}" target="_blank" rel="noopener">📄 의안 원문·심사경과 (국회) ↗</a>
<button class="sharebtn" onclick="shareThis()">🔗 공유</button>
<footer><b>좌우지간</b> · 좌·우 언론 시각을 함께 — 열린국회정보 OpenAPI 기반. AI 개요는 참고용이며 원문 확인을 권장합니다.</footer>
<div id="toast">🔗 링크가 복사됐어요</div>
<script>
function shareThis(){{var u=location.href;
 if(navigator.share){{navigator.share({{title:document.title,url:u}}).catch(function(){{}});}}
 else{{navigator.clipboard.writeText(u).then(function(){{var t=document.getElementById('toast');t.classList.add('show');setTimeout(function(){{t.classList.remove('show');}},1700);}});}}}}
</script>
</body></html>"""

os.makedirs(f"{OUT}/bill", exist_ok=True)
urls = []
for r in b.itertuples():
    bid = r.BILL_ID; no = r.BILL_NO
    name = r.BILL_NAME or ""
    head = headlines.get(bid) or friendly(name)
    body = summ.get(bid) or (won.get(bid, {}) or {}).get("text", "")
    desc = description(bid, body)
    url = f"{BASE_URL}/bill/{no}.html"
    # 표결 집계
    pv, bar_total = {}, {"찬성": 0, "반대": 0, "기권": 0, "불참": 0}
    for p in PB.get(bid, {}):
        c = {"찬성": 0, "반대": 0, "기권": 0, "불참": 0}
        for nm, res in PB[bid][p]:
            if res in c: c[res] += 1; bar_total[res] += 1
        pv[p] = c
    tot = sum(bar_total[k] for k in ["찬성", "반대"]) or 1
    bar = "".join(f'<div style="background:{VL[k][1]};flex:{bar_total[k]}">{VL[k][0]+" "+str(bar_total[k]) if bar_total[k]/sum(bar_total.values() or [1])>.06 else ""}</div>'
                  for k in ["찬성", "반대", "기권", "불참"] if bar_total[k])
    pvrows = "".join(f"<tr><td style='color:{PC.get(p,'#555')};font-weight:600'>{esc(p)}</td>"
                     f"<td>{pv[p]['찬성']}</td><td>{pv[p]['반대']}</td><td>{pv[p]['기권']}</td><td>{pv[p]['불참']}</td></tr>"
                     for p in PORDER if p in pv)
    # 의원 명단(접힘)
    memblocks = ""
    for p in PORDER:
        if p not in PB.get(bid, {}): continue
        arr = sorted(PB[bid][p], key=lambda x: ("찬성반대기권불참".find(x[1]), x[0]))
        memblocks += f"<div class='mem'><b style='color:{PC.get(p,'#555')}'>{esc(p)}</b> · " + \
            ", ".join(f"{esc(nm)}({res})" for nm, res in arr if res in VL) + "</div>"
    members = f"<details><summary>의원별 표결 펼쳐보기 ({sum(len(v) for v in PB.get(bid,{}).values())}명)</summary>{memblocks}</details>" if memblocks else ""
    ov = (overviews.get(bid) or {}).get("text", "")
    ovw = f'<div class="ovw"><h3>📖 한눈에 보기 <small style="font-weight:400;color:#6b86ad">AI 요약</small></h3>{md_html(ov)}</div>' if ov else ""
    pp, ppt = proposer(name)
    prop = (f'<div class="prop"><span class="dot" style="background:{PC.get(ppt,"#9aa0a6")}"></span>{esc(pp)}'
            f'{" · <b style=color:"+PC.get(ppt,"#555")+">"+esc(ppt)+"</b>" if ppt else ""}</div>') if pp else ""
    page = PAGE.format(
        title=esc(head) + " | 22대 국회 표결", ogt=esc(head), desc=esc(desc), url=esc(url),
        emoji=cmt_emoji(r.CURR_COMMITTEE), head=esc(head), name=esc(name),
        date=(r.dt.strftime("%Y-%m-%d") if pd.notna(r.dt) else "-"), cmt=esc(r.CURR_COMMITTEE or "-"),
        result=esc(r.PROC_RESULT_CD or "-"), no=esc(no), prop=prop, ovw=ovw, bar=bar, pvrows=pvrows,
        members=members, billurl=f"https://likms.assembly.go.kr/bill/billDetail.do?billId={bid}")
    open(f"{OUT}/bill/{no}.html", "w", encoding="utf-8").write(page)
    urls.append(url)

# 메인 피드 앱 복사
if os.path.exists("assembly_votes.html"):
    shutil.copy("assembly_votes.html", f"{OUT}/index.html")

# 사이트맵 + robots
sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
sm.append(f"<url><loc>{BASE_URL}/index.html</loc></url>")
for u in urls:
    sm.append(f"<url><loc>{u}</loc></url>")
sm.append("</urlset>")
open(f"{OUT}/sitemap.xml", "w", encoding="utf-8").write("\n".join(sm))
open(f"{OUT}/robots.txt", "w", encoding="utf-8").write(f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n")

print(f"생성: {len(urls)}개 법안 페이지 + index + sitemap → {OUT}/")
print(f"⚠️ 배포 전 BASE_URL을 실제 도메인으로 교체하세요 (현재: {BASE_URL})")
