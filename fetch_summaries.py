"""각 안건의 '제안이유 및 주요내용' 텍스트를 의안정보시스템에서 받아 캐시한다.
엔드포인트: /bill/bi/popup/billSummary.do?billId=...  (제안이유 본문을 <pre>로 반환)
summaries.json 에 BILL_ID→본문 으로 저장. 재실행 시 캐시된 것은 건너뜀(재개 가능).
"""
import json, os, re, time, html as ht
import requests
import pandas as pd

CACHE = "summaries.json"
URL = "https://likms.assembly.go.kr/bill/bi/popup/billSummary.do"

def fetch_summary(bid, sess):
    try:
        r = sess.get(URL, params={"billId": bid, "currMenuNo": "2600044"}, timeout=15)
        m = re.search(r"<pre[^>]*>(.*?)</pre>", r.text, re.S)   # 본문은 <pre> 안
        if not m:
            return ""
        body = re.sub(r"<[^>]+>", "", m.group(1))               # 잔여 태그 제거
        return re.sub(r"[\xa0]", " ", ht.unescape(body)).strip()
    except Exception:
        return None                                             # 실패는 None(다음 실행때 재시도)

bills = pd.read_csv("bills_22.csv", dtype=str)
cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}

sess = requests.Session()
sess.headers.update({"User-Agent": "Mozilla/5.0"})
todo = [b for b in bills["BILL_ID"] if not cache.get(b)]        # 아직 못 받은 것만
print(f"받을 안건: {len(todo)} / 전체 {len(bills)} (캐시 {len(cache)})")

for i, bid in enumerate(todo, 1):
    body = fetch_summary(bid, sess)
    if body is not None:
        cache[bid] = body
    if i % 50 == 0 or i == len(todo):
        json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
        got = sum(1 for v in cache.values() if v)
        print(f"  {i}/{len(todo)} 처리, 본문확보 {got}")
    time.sleep(0.1)                                             # 서버 부담 완화

json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
empty = sum(1 for b in bills["BILL_ID"] if not cache.get(b))
print(f"완료: 본문 {sum(1 for v in cache.values() if v)}건, 빈 본문 {empty}건")
