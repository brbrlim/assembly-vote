"""친근한 법안 헤드라인 생성 (Claude Haiku — rate-limit 없음, 건당 ~$0.0003).
시민 눈높이의 뉴스 헤드라인 한 줄. 낚시·과장 금지, 중립. headlines.json 에 저장.
사용: python3 gen_headlines.py recent 25   |   overview   |   all
"""
import os, json, sys
import pandas as pd
import anthropic

MODEL = "claude-haiku-4-5"
client = anthropic.Anthropic()
b = pd.read_csv("bills_22.csv", dtype=str).sort_values("PROC_DT")
summ = json.load(open("summaries.json", encoding="utf-8"))
won = json.load(open("wonmun.json", encoding="utf-8"))
overviews = json.load(open("overviews.json", encoding="utf-8")) if os.path.exists("overviews.json") else {}

SYSTEM = ("당신은 시민용 뉴스 헤드라인 작성자입니다. 국회 법안을 시민이 한눈에 이해하고 클릭하고 싶게 "
          "한 줄로 표현합니다. 규칙: 28자 이내, 중립적 사실(낚시·과장·감정선동 금지), 관료적 표현 대신 일상어, "
          "결과(가결/부결)가 핵심이면 반영. 헤드라인 한 줄만 출력(따옴표·설명 없이).")

def headline(bid):
    r = b[b["BILL_ID"] == bid].iloc[0]
    ov = (overviews.get(bid, {}) or {}).get("text", "")
    body = summ.get(bid) or (won.get(bid, {}) or {}).get("text", "")
    ctx = ov[:400] if ov else body[:400]
    user = (f"법안명: {r['BILL_NAME']}\n처리결과: {r['PROC_RESULT_CD']}\n소관위: {r.get('CURR_COMMITTEE','')}\n"
            f"참고(요약/본문): {ctx}\n\n위 법안의 시민용 헤드라인 한 줄을 작성하라.")
    m = client.messages.create(model=MODEL, max_tokens=60, system=SYSTEM,
                               messages=[{"role": "user", "content": user}])
    return "".join(blk.text for blk in m.content if blk.type == "text").strip().strip('"“”')

def pick(mode, n):
    if mode == "overview":
        return list(overviews.keys())
    if mode == "all":
        return list(b["BILL_ID"])
    return list(b["BILL_ID"])[-n:]                       # recent N (처리일 최신)

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "recent"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 25
    ids = list(dict.fromkeys(list(overviews.keys()) + pick(mode, n)))  # 개요 안건은 항상 포함
    store = json.load(open("headlines.json", encoding="utf-8")) if os.path.exists("headlines.json") else {}
    for i, bid in enumerate(ids, 1):
        if bid in store:
            continue
        try:
            store[bid] = headline(bid)
        except Exception as e:
            print("  실패", bid, str(e)[:50]); continue
        if i % 10 == 0 or i == len(ids):
            json.dump(store, open("headlines.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"  {i}/{len(ids)}")
    json.dump(store, open("headlines.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # 샘플 출력
    print("\n=== 헤드라인 샘플 ===")
    for bid in ids[:12]:
        nm = b[b["BILL_ID"] == bid].iloc[0]["BILL_NAME"][:28]
        print(f"  {store.get(bid,'-'):30s} ← {nm}")
