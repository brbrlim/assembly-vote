"""22대 본회의 '의원 × 안건 × 표결' 전체 raw 데이터셋을 만들어 파일로 저장한다.

흐름:
  1) ncocpgfiaoituanbr 로 처리안건 전체 목록(BILL_ID) 확보  (페이지네이션)
  2) 각 BILL_ID 마다 nojepdqqaweusdfbi 로 의원별 표결 조회
  3) 전부 누적 → CSV(+Parquet) 저장.  100건마다 중간 체크포인트 저장.
"""
import time
import requests
import pandas as pd

KEY = "0e4486c320bf4cf6987c4602e7ad4e9f"
BASE = "https://open.assembly.go.kr/portal/openapi"
AGE = 22
OUT = "votes_raw_22"                                   # 출력 파일 접두사

def fetch_rows(service, **extra):
    """한 페이지 호출 → (row 리스트, 전체건수). 오류/빈 결과는 ([], 0)."""
    params = {"KEY": KEY, "Type": "json", "pIndex": 1, "pSize": 1000, "AGE": AGE}
    params.update(extra)
    for attempt in range(3):                           # 일시적 오류 대비 3회 재시도
        try:
            j = requests.get(f"{BASE}/{service}", params=params, timeout=20).json()
            key = list(j.keys())[0]
            if key == "RESULT":                        # 데이터 없음/오류 응답
                return [], 0
            total = j[key][0]["head"][0]["list_total_count"]
            return j[key][1]["row"], total
        except Exception:
            time.sleep(1.0)                            # 잠시 쉬고 재시도
    return [], 0

# ── 1. 안건 전체 목록 (페이지 단위로 모두 수집) ──────────────
bills = []
_, total_bills = fetch_rows("ncocpgfiaoituanbr", pIndex=1, pSize=1)   # 총건수 먼저 확인
pages = (total_bills // 1000) + 1
for p in range(1, pages + 1):
    rows, _ = fetch_rows("ncocpgfiaoituanbr", pIndex=p, pSize=1000)
    bills.extend(rows)
bills_df = pd.DataFrame(bills)
print(f"처리안건 {len(bills_df)}건 확보")

# ── 2. 안건별 의원 표결 누적 ────────────────────────────────
all_votes = []                                         # 표결 행들을 모을 리스트
no_vote = []                                           # 표결 데이터가 없는 안건 기록
for i, bid in enumerate(bills_df["BILL_ID"], start=1):
    rows, _ = fetch_rows("nojepdqqaweusdfbi", pIndex=1, pSize=1000, BILL_ID=bid)
    if rows:
        all_votes.extend(rows)                         # 의원별 찬반 행 누적
    else:
        no_vote.append(bid)                            # 전자표결 없는 안건 등
    if i % 50 == 0 or i == len(bills_df):              # 진행상황 출력
        print(f"  {i}/{len(bills_df)} 안건 처리, 누적 표결행 {len(all_votes):,}")
    if i % 100 == 0:                                   # 100건마다 중간 저장(유실 방지)
        pd.DataFrame(all_votes).to_csv(f"{OUT}.csv", index=False, encoding="utf-8-sig")
    time.sleep(0.05)                                   # 서버 부담 완화용 짧은 대기

# ── 3. 최종 저장 ────────────────────────────────────────────
votes_df = pd.DataFrame(all_votes)
votes_df.to_csv(f"{OUT}.csv", index=False, encoding="utf-8-sig")   # 엑셀 호환 CSV
try:
    votes_df.to_parquet(f"{OUT}.parquet", index=False)             # 용량작고 빠른 포맷
except Exception:
    pass                                                            # pyarrow 없으면 건너뜀
bills_df.to_csv("bills_22.csv", index=False, encoding="utf-8-sig") # 안건 목록도 함께 저장

print(f"\n완료: {len(votes_df):,}행  ({votes_df['BILL_ID'].nunique()}개 안건)")
print(f"표결데이터 없는 안건: {len(no_vote)}건")
print("저장:", f"{OUT}.csv / {OUT}.parquet / bills_22.csv")
