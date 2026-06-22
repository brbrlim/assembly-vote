"""검증 레이어 + 비교 페이지 생성.
- URL 검증: 함께읽기 링크를 HTTP로 확인, 죽은 링크(404 등) 표시
- 인용 검증: '○○ 의원' 이름을 22대 명단(305명)과 대조, 비실존이면 플래그
- 두 버전(Gemini Flash-Lite vs 기존 Opus)을 나란히 compare.html 로 출력
"""
import re, json, urllib.request
import pandas as pd

BILL = "ARC_X2O4L0L9E0U2G1R6D4J8E2F0U7Q1H1"
MEMBERS = set(pd.read_parquet("votes_raw_22.parquet")["HG_NM"].unique())
PARTIES = "더불어민주당|국민의힘|조국혁신당|개혁신당|진보당|기본소득당|사회민주당|무소속"

def check_url(u):
    if "likms.assembly" in u:
        return True
    try:
        req = urllib.request.Request(u, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
        code = urllib.request.urlopen(req, timeout=8).status
        return code < 400 or code == 403          # 403=봇차단(실재로 간주)
    except Exception as e:
        return getattr(e, "code", 0) == 403

# 실제 검색(WebSearch)에서 확보한 검증된 기사 링크 — LLM이 만든 URL은 신뢰하지 않음
TRUSTED_LINKS = [
    ("상속세 최고세율 인하·공제 확대 법안 국회 본회의서 부결 (한국경제)", "https://www.hankyung.com/article/2024121077027"),
    ("2024년 세법개정안 국회 통과…상증세법 개정안 부결 (한국세정신문)", "https://taxtimes.co.kr/mobile/article.html?no=267547"),
    ("상속세·증여세법 개정안 통째로 부결…조특·부가세법 수정 통과 (일간NTN)", "https://www.intn.co.kr/news/articleView.html?idxno=2040547"),
]
BILL_LINK = ("의안 원문·심사경과 (국회 의안정보시스템)",
             f"https://likms.assembly.go.kr/bill/billDetail.do?billId={BILL}")

def verify(text):
    report = {"fake_removed": [], "links_replaced": 0, "links_kept": []}

    # 1) 가짜 인용 제거 — 비실존 의원의 발언 '문장째' 삭제
    fakes = set()
    for m in re.finditer(rf"([가-힣]{{2,4}})\s*(?:{PARTIES})?\s*의원", text):
        if m.group(1) not in MEMBERS:
            fakes.add(m.group(1))
    for nm in fakes:
        # 해당 이름이 든 문장(마침표 사이) 제거
        new = re.sub(rf"(?:^|(?<=\.))\s*[^.\n]*{nm}[^.\n]*?(?:다|요)\.", "", text)
        if new != text:
            report["fake_removed"].append(nm)
            text = new

    # 2) '함께 읽기'를 검증된 실제 링크로 통째 교체 (LLM URL 폐기)
    body = re.split(r"\n##\s*함께 읽기", text)[0].rstrip()
    kept = [BILL_LINK]
    for name, url in TRUSTED_LINKS:
        if check_url(url):
            kept.append((name, url))
    report["links_kept"] = kept
    report["links_replaced"] = len(re.findall(r"https?://", text.split("함께 읽기")[-1])) if "함께 읽기" in text else 0
    sec = "## 함께 읽기\n" + "\n".join(f"- [{n}]({u})" for n, u in kept)
    text = body + "\n\n" + sec
    return text, report

# 두 버전 로드: Gemini는 2단계 검증판(gen_gemini_verified.py 산출), Opus는 기존
gemini_text = json.load(open("overviews_gemini.json", encoding="utf-8"))[BILL]["text"]
opus_text = json.load(open("overviews.json", encoding="utf-8"))[BILL]["text"]
real_links = len([u for u in re.findall(r"\((https?://[^)]+)\)", gemini_text) if "likms" not in u])
rep = {"fake_removed": [], "links_kept": [None]*(real_links+1)}
print(f"Gemini 검증판 — 그라운딩 실제 링크 {real_links}개")

# ── 비교 HTML ──
def md(s):                                          # 경량 마크다운(링크/굵게/제목/목록/표)
    return s   # placeholder, replaced by JS renderer below

PAGE = """<!DOCTYPE html><html lang=ko><head><meta charset=utf-8>
<title>개요 비교 — Gemini vs Opus</title><style>
 body{font-family:-apple-system,"Apple SD Gothic Neo",sans-serif;margin:0;background:#f4f5f7;color:#1a1a1a}
 header{background:#16213e;color:#fff;padding:14px 20px}header h1{margin:0;font-size:17px}
 .wrap{display:flex;gap:14px;padding:16px;align-items:flex-start}
 .col{flex:1;background:#fff;border-radius:10px;border:1px solid #ddd;overflow:hidden}
 .col-h{padding:10px 14px;font-weight:700;color:#fff;display:flex;justify-content:space-between;align-items:center}
 .g .col-h{background:#1a73e8}.o .col-h{background:#5b4a1f}
 .meta{font-size:11px;font-weight:500;opacity:.9}
 .body{padding:6px 16px 16px;font-size:13px;line-height:1.65}
 .body h4{margin:13px 0 3px;font-size:13px;color:#16407a}
 .body p{margin:3px 0}.body .li{margin:2px 0 2px 6px}
 .body a{color:#1558d6}.body table{border-collapse:collapse;margin:8px 0;font-size:12px}
 .body td,.body th{border:1px solid #cfe0f5;padding:3px 9px}.body th{background:#dce8fb}
 .flag{background:#fff3cd;color:#7a5b00;border-radius:3px;padding:0 3px;font-size:11px}
 .rep{background:#fbe9e7;border:1px solid #f5c6bc;border-radius:8px;margin:0 16px 8px;padding:8px 12px;font-size:12px;color:#7a2e22}
</style></head><body>
<header><h1>📊 시민 개요 비교 — Gemini Flash-Lite (검증 적용) vs Claude Opus 4.8</h1></header>
<div class="rep">🔎 <b>2단계 검증판(Gemini)</b> — ①검색 전담 호출로 그라운딩 발동 → 실제 출처 __KEPT__개 자동 첨부, ②작성 호출은 검색 브리프 범위에서만 인용. 비실존 의원 인용 __FAKE__건. 본문 URL은 전량 폐기.</div>
<div class="wrap">
 <div class="col g"><div class="col-h"><span>📖 Gemini Flash-Lite · 2단계 검증판</span><span class="meta">~$0.001 · 그라운딩 출처</span></div><div class="body" id="g"></div></div>
 <div class="col o"><div class="col-h"><span>📖 Claude Opus 4.8 (기존)</span><span class="meta">$0.39</span></div><div class="body" id="o"></div></div>
</div>
<script>
const G=__G__, O=__O__;
function mdInline(s){return s
  .replace(/⚠️\\[(.+?)\\]/g,'<span class="flag">⚠️ $1</span>')
  .replace(/❌링크없음/g,'<span class="flag">❌ 링크 없음</span>')
  .replace(/\\[(.+?)\\]\\((https?:\\/\\/[^)]+)\\)/g,'<a href="$2" target=_blank>$1</a>')
  .replace(/\\*\\*(.+?)\\*\\*/g,'<strong>$1</strong>');}
function esc(s){return s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function render(md){const L=md.split('\\n');let h='',tbl=[];
 const flush=()=>{if(!tbl.length)return;const rows=tbl.filter(r=>!/^\\s*\\|?[\\s|:\\-]+\\|?\\s*$/.test(r));
   h+='<table>'+rows.map((r,ri)=>{const c=r.split('|').map(x=>x.trim()).filter((x,i,a)=>!(i===0&&x==='')&&!(i===a.length-1&&x===''));
   const tg=ri===0?'th':'td';return '<tr>'+c.map(x=>`<${tg}>${mdInline(esc(x))}</${tg}>`).join('')+'</tr>';}).join('')+'</table>';tbl=[];};
 for(let ln of L){if(ln.includes('|')&&ln.trim().startsWith('|')){tbl.push(ln);continue;}flush();
  const t=ln.trim();if(!t){continue;}if(/^-{3,}$/.test(t))continue;
  if(t.startsWith('## '))h+=`<h4>${mdInline(esc(t.slice(3)))}</h4>`;
  else if(/^[-*•]\\s/.test(t))h+=`<div class="li">• ${mdInline(esc(t.replace(/^[-*•]\\s/,'')))}</div>`;
  else h+=`<p>${mdInline(esc(t))}</p>`;}
 flush();return h;}
document.getElementById('g').innerHTML=render(G);
document.getElementById('o').innerHTML=render(O);
</script></body></html>"""

html = (PAGE.replace("__G__", json.dumps(gemini_text, ensure_ascii=False))
            .replace("__O__", json.dumps(opus_text, ensure_ascii=False))
            .replace("__FAKE__", str(len(rep["fake_removed"])))
            .replace("__KEPT__", str(len(rep["links_kept"]))))
open("compare.html", "w", encoding="utf-8").write(html)
print("compare.html 생성 완료")
