"""검증판 Gemini 생성기 (flash-lite).
개선점:
 1) 검색 강제 프롬프트로 그라운딩 확실히 발동
 2) '함께 읽기' 링크는 본문 텍스트가 아니라 grounding_metadata의 실제 출처에서 추출
    (리다이렉트 추적 → 실제 기사 URL, 뉴스 도메인만, 중복 제거)
 3) 인용 의원을 22대 명단과 대조해 비실존 인용 문장 삭제
결과를 overviews_gemini.json 에 저장.
"""
import os, json, re, sys, html, urllib.request
from datetime import datetime
import pandas as pd
import trafilatura
from google import genai
from google.genai import types

MODEL = "gemini-2.5-flash-lite"
PARTIES = "더불어민주당|국민의힘|조국혁신당|개혁신당|진보당|기본소득당|사회민주당|무소속"
NON_NEWS = ("youtube.com", "youtu.be", "facebook.com", "instagram.com", "twitter.com", "x.com", "tiktok.com",
            ".go.kr", "lawmaking", "namu.wiki", "wikipedia.org", "blog.naver", "cafe.naver",
            "tistory.com", "brunch.co.kr", "dcinside")     # 정부·위키·블로그·커뮤니티 제외
LOW_VALUE_PATH = re.compile(r"/(photo|photos|gallery|video|tv|cartoon|movie)s?/", re.I)  # 사진·영상 등 비기사

# 언론사: 도메인 → (이름, 성향). 성향은 대략적 분류(논쟁 가능).
NEWS = {
    "biz.chosun.com": ("조선비즈", "우"), "chosun.com": ("조선일보", "우"),
    "joongang.co.kr": ("중앙일보", "우"), "donga.com": ("동아일보", "우"),
    "munhwa.com": ("문화일보", "우"), "segye.com": ("세계일보", "우"),
    "hankyung.com": ("한국경제", "우"), "mk.co.kr": ("매일경제", "우"),
    "hani.co.kr": ("한겨레", "좌"), "khan.co.kr": ("경향신문", "좌"),
    "ohmynews.com": ("오마이뉴스", "좌"), "pressian.com": ("프레시안", "좌"),
    "hankookilbo.com": ("한국일보", "중"), "seoul.co.kr": ("서울신문", "중"),
    "sedaily.com": ("서울경제", "중"), "mt.co.kr": ("머니투데이", "중"),
    "fnnews.com": ("파이낸셜뉴스", "중"), "edaily.co.kr": ("이데일리", "중"),
    "asiae.co.kr": ("아시아경제", "중"), "heraldcorp.com": ("헤럴드경제", "중"),
    "newsway.co.kr": ("뉴스웨이", "중"), "kmib.co.kr": ("국민일보", "중"),
    "newsis.com": ("뉴시스", "통신"), "newspim.com": ("뉴스핌", "통신"),
    "news1.kr": ("뉴스1", "통신"), "yna.co.kr": ("연합뉴스", "통신"),
    "imbc.com": ("MBC", "중"), "kbs.co.kr": ("KBS", "중"), "sbs.co.kr": ("SBS", "중"), "ytn.co.kr": ("YTN", "중"),
    "taxtimes.co.kr": ("한국세정신문", "전문"), "intn.co.kr": ("일간NTN", "전문"),
}
def outlet(url):
    for dom in sorted(NEWS, key=len, reverse=True):          # 긴 키(biz.chosun) 우선
        if dom in url:
            return NEWS[dom]
    return (url.split("/")[2].replace("www.", ""), "기타")

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
v = pd.read_parquet("votes_raw_22.parquet")
b = pd.read_csv("bills_22.csv", dtype=str)
summ = json.load(open("summaries.json", encoding="utf-8"))
won = json.load(open("wonmun.json", encoding="utf-8"))
MEMBERS = set(v["HG_NM"].unique())

def party_facts(bid):
    sub = v[v["BILL_ID"] == bid]; out = []
    for p in sub["POLY_NM"].value_counts().index:
        g = sub[sub["POLY_NM"] == p]["RESULT_VOTE_MOD"].value_counts().to_dict()
        out.append(f"- {p}: " + ", ".join(f"{k} {g[k]}" for k in ["찬성","반대","기권","불참"] if g.get(k)))
    return "\n".join(out)

def power_context(d):
    return ("대통령 윤석열(국민의힘). 여당=국민의힘, 야당 다수=더불어민주당(야대여소)."
            if d and d < "2025-06-04" else "대통령 이재명(더불어민주당). 여당=더불어민주당, 야당=국민의힘.")

def fetch_page(url):
    """기사를 받아 trafilatura로 본문·제목·날짜 추출(사이트 구조 무관). 실패면 None."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        r = urllib.request.urlopen(req, timeout=12)         # GET(HEAD는 일부 언론사가 막음)
        final, raw = r.geturl(), r.read(400000)
    except Exception:
        return None
    try:
        data = trafilatura.extract(raw, output_format="json", include_comments=False,
                                   with_metadata=True, target_language="ko")
    except Exception:
        data = None
    if not data:
        return None
    d = json.loads(data)
    body = (d.get("text") or "").strip()
    title = (d.get("title") or "").strip()
    date = d.get("date")                                    # 'YYYY-MM-DD' 또는 None
    npara = sum(1 for ln in body.split("\n") if len(ln.strip()) > 30)
    return {"title": title, "url": final, "body": body, "date": date, "npara": npara}

def get_keywords(bill_name):
    """안건명에서 관련성 판정 키워드 추출(예: 상속세 및 증여세법 → 상속세, 증여세)."""
    base = re.split(r"법|일부개정|전부개정|제정|\(", bill_name)[0]
    kws = [w for w in re.split(r"\s*(?:및|·|,|\s)\s*", base) if len(w) >= 2]
    return kws or [base[:3]]

RICH = re.compile(r"사설|칼럼|논설|오피니언|opinion|editorial|분석|심층|종합|짚어|쟁점", re.I)
EVENT = re.compile(r"부결|가결|수정가결|표결|의결|본회의|국회")          # 표결 사건 관련성

def search(query):
    cfg = types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
    return client.models.generate_content(model=MODEL, contents=query, config=cfg)

MIN_BODY = 800        # 본문 최소 글자수(미만이면 단신·포토로 보고 탈락)
MIN_PARA = 3          # 의미있는 문단 최소 수
MAX_DAYS = 100        # 표결일과 기사 날짜 최대 격차(보수적 — 엉뚱한 시점 기사 배제)

def date_ok(article_date, proc):
    if not article_date or not proc: return True            # 날짜 없으면 통과(과배제 방지)
    try:
        d1 = datetime.strptime(article_date[:10], "%Y-%m-%d")
        d2 = datetime.strptime(proc[:10], "%Y-%m-%d")
        return abs((d1 - d2).days) <= MAX_DAYS
    except Exception:
        return True

def add_pool(resp, keywords, pool, seen, proc):
    gm = resp.candidates[0].grounding_metadata
    for c in (getattr(gm, "grounding_chunks", None) or []) if gm else []:
        w = getattr(c, "web", None)
        if not w or not w.uri: continue
        page = fetch_page(w.uri)
        if not page: continue
        title, final, body, npara = page["title"], page["url"], page["body"], page["npara"]
        dom = final.split("/")[2].replace("www.", "").replace("mobile.", "").replace("m.", "")
        if any(x in final for x in NON_NEWS) or dom in seen: continue
        if LOW_VALUE_PATH.search(final): continue
        if not title or len(title) < 8: continue
        name, lean = outlet(final)
        if lean == "기타": continue                                  # ① 신뢰 소스 화이트리스트
        if len(body) < MIN_BODY or npara < MIN_PARA: continue        # ② 본문 충실도 게이트
        if not any(kw in body for kw in keywords): continue          # 관련성은 '본문'으로(오연결 차단)
        if not EVENT.search(body): continue                          # 표결 사건 관련
        if not date_ok(page["date"], proc): continue                 # ③ 날짜 근접(엉뚱한 연도 배제)
        seen.add(dom)
        score = (2 if RICH.search(title) or RICH.search(final) else 0)
        score += min(len(body), 6000) / 1500                         # 본문 충실도(최대 +4)
        pool.append({"title": title[:55], "url": final, "name": name, "lean": lean,
                     "score": score, "chars": len(body)})

def select_balanced(pool, k=3):                             # 양보다 질 — 상위 3개만
    pool.sort(key=lambda x: -x["score"])
    chosen, leans = [], set()
    for it in pool:                                          # 성향 하나씩 먼저(다양성)
        if it["lean"] not in leans and len(chosen) < k:
            chosen.append(it); leans.add(it["lean"])
    for it in pool:                                          # 나머지는 점수순
        if it not in chosen and len(chosen) < k:
            chosen.append(it)
    chosen.sort(key=lambda x: -x["score"])
    return [(f"{it['title']} ({it['name']})", it["url"]) for it in chosen]

# 사람 이름이 아닌 일반어(오탐 방지)
STOP = {"여당","야당","여야","국민의힘","더불어민주당","조국혁신당","개혁신당","진보당","기본소득당",
        "사회민주당","무소속","정부","의장","복수","일부","여러","해당","관련","소속","동료","상대",
        "현직","전직","초선","재선","제","각","전","현","신임","담당","소관"}
QUOTE = "\"“”'‘’「」『』"

def remove_fake_quotes(text):
    """비실존 의원의 '직접 인용 문장'만 삭제. 일반어·따옴표 없는 문장은 건드리지 않음."""
    fakes = set()
    for m in re.finditer(rf"([가-힣]{{2,4}})\s*(?:{PARTIES})?\s*의원", text):
        nm = m.group(1)
        if nm in MEMBERS or nm in STOP: continue
        # 그 이름이 든 문장에 따옴표(직접 인용)가 있을 때만 가짜로 판단
        sent = re.search(rf"[^.\n]*{nm}[^.\n]*[다요]\.", text)
        if sent and any(q in sent.group() for q in QUOTE):
            fakes.add(nm)
    removed = []
    for nm in fakes:
        new = re.sub(rf"(?:^|(?<=\.))\s*[^.\n]*{nm}[^.\n]*?[다요]\.", "", text)
        if new != text: removed.append(nm); text = new
    return text, removed

SYSTEM = ("시민에게 국회 법안을 쉽고 중립적으로 설명하는 해설가. 어려운 용어는 일상어로 풀고 "
          "구체적 숫자·사례로 체감되게, 찬반 양측을 균형 있게.")

def step1_search(bid, row, proc):
    """검색 전담 호출 — 일반 검색 + 진보/중도 언론 타게팅으로 다양한 시각 확보."""
    keywords = get_keywords(row["BILL_NAME"])
    nm, res = row["BILL_NAME"], row["PROC_RESULT_CD"]
    base = (f"{proc} 국회 본회의에서 '{nm}'이(가) {res}되었다. 여야 의원 발언·찬반 논거·여론을 "
            "**웹에서 검색**해 정리하라. 사설·분석 기사도. 직접인용은 발언자와 함께, 확실한 것만. 최신 기사 검색.")
    brief, usages = "", []
    pool, seen = [], set()
    for _ in range(3):                                          # ① 일반 검색(그라운딩 발동까지)
        r = search(base); usages.append(r.usage_metadata)
        add_pool(r, keywords, pool, seen, proc)
        brief = r.text
        if pool: break
    # ② 진보·중도 언론 타게팅 — 다른 시각 보강
    leans = {p["lean"] for p in pool}
    if "좌" not in leans:
        r = search(f"한겨레 경향신문 오마이뉴스 '{nm}' {res} 비판 사설"); usages.append(r.usage_metadata)
        add_pool(r, keywords, pool, seen, proc)
    if "중" not in leans:
        r = search(f"한국일보 서울신문 '{nm}' {res} 쟁점 분석"); usages.append(r.usage_metadata)
        add_pool(r, keywords, pool, seen, proc)
    sources = select_balanced(pool, 3)
    return brief, sources, usages

def step2_write(bid, row, proc, body, brief):
    """작성 호출 — 법안 사실 + 1단계 브리프로 집필(검색 없음). 인용은 브리프 범위 내에서만."""
    prompt = f"""아래 자료로 시민용 심화 개요를 작성하라.

[안건명] {row['BILL_NAME']}  [처리결과] {row['PROC_RESULT_CD']}  [표결일] {proc}
[표결 당시 정치지형(사실)] {power_context(proc)}
[공식 본문 — 법안 내용은 이 안에서만]
{body[:2200]}
[정당별 표결(확정 사실)]
{party_facts(bid)}
[참고 브리프 — 의원 발언·여론은 이 범위 안에서만 인용]
{brief[:2500]}

규칙: 전문용어 괄호풀이 + 구체 숫자예시 / 여야는 위 정치지형(표결일 기준) /
의원 발언 직접인용은 위 브리프에 있는 것만(없으면 인용 생략하고 양측 논리만) /
도구·검색·과정 메타설명 금지 / 본문에 URL 쓰지 말 것 /
섹션: ## 한 줄 요약 / ## 무엇이 바뀌나 (쉽게) / ## 왜 이런 표결이 나왔나 / ## 정당별 입장 / ## 내 삶에 미치는 영향"""
    resp = client.models.generate_content(model=MODEL, contents=prompt,
            config=types.GenerateContentConfig(system_instruction=SYSTEM))
    return resp.text, resp.usage_metadata

def generate(bid):
    row = b[b["BILL_ID"] == bid].iloc[0]
    body = summ.get(bid) or (won.get(bid, {}) or {}).get("text", "")
    proc = row.get("PROC_DT", "")
    brief, sources, usages = step1_search(bid, row, proc)       # ① 검색(다회)
    text, u2 = step2_write(bid, row, proc, body, brief)         # ② 작성
    text = re.split(r"\n##\s*함께 읽기", text)[0].rstrip()
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1", text)
    text, removed = remove_fake_quotes(text)
    links = [("의안 원문·심사경과 (국회 의안정보시스템)",
              f"https://likms.assembly.go.kr/bill/billDetail.do?billId={bid}")] + sources
    text += "\n\n## 함께 읽기\n" + "\n".join(f"- [{n}]({u})" for n, u in links)
    tot_in = sum(u.prompt_token_count for u in usages) + u2.prompt_token_count
    tot_out = sum(u.candidates_token_count for u in usages) + u2.candidates_token_count
    return text, {"fake_removed": removed, "sources": sources, "tin": tot_in, "tout": tot_out}

if __name__ == "__main__":
    bid = sys.argv[1]
    text, rep = generate(bid)
    store = json.load(open("overviews_gemini.json", encoding="utf-8")) if os.path.exists("overviews_gemini.json") else {}
    store[bid] = {"text": text}
    json.dump(store, open("overviews_gemini.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(text[-700:])
    print("\n" + "─"*50)
    print("가짜인용 삭제:", rep["fake_removed"])
    print("그라운딩 실제 출처:", len(rep["sources"]), "개")
    for n, link in rep["sources"]: print("  ·", n[:24], "→", link[:60])
    print(f"2단계 합산 입력 {rep['tin']} / 출력 {rep['tout']} 토큰 | ~${rep['tin']*0.1/1e6 + rep['tout']*0.4/1e6:.4f}")
