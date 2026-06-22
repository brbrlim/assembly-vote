"""제안이유(summaries.json)가 비어있는 안건들의 '의안원문'을 받아 wonmun.json에 캐시한다.
fetch_wonmun.fetch_wonmun(bill_id) 사용. 거대 문서(예산/보고서)는 임베드용으로 CAP자에서 자른다.
"""
import json, os, time
import pandas as pd
from fetch_wonmun import fetch_wonmun

CAP = 6000                                            # 임베드 본문 최대 길이(HTML 비대화 방지)
bills = pd.read_csv("bills_22.csv", dtype=str)
summaries = json.load(open("summaries.json", encoding="utf-8"))
cache = json.load(open("wonmun.json", encoding="utf-8")) if os.path.exists("wonmun.json") else {}

# 제안이유가 빈 안건만 대상
todo = [b for b in bills["BILL_ID"] if not summaries.get(b) and b not in cache]
print(f"원문 받을 안건: {len(todo)}")

for i, bid in enumerate(todo, 1):
    try:
        txt = fetch_wonmun(bid) or ""
    except Exception:
        txt = ""
    cache[bid] = {"len": len(txt), "text": txt[:CAP], "truncated": len(txt) > CAP}
    if i % 20 == 0 or i == len(todo):
        json.dump(cache, open("wonmun.json", "w", encoding="utf-8"), ensure_ascii=False)
        got = sum(1 for v in cache.values() if v["text"])
        print(f"  {i}/{len(todo)} 처리, 원문확보 {got}")
    time.sleep(0.1)

json.dump(cache, open("wonmun.json", "w", encoding="utf-8"), ensure_ascii=False)
got = sum(1 for v in cache.values() if v["text"])
print(f"완료: 원문확보 {got}/{len(cache)}건")
