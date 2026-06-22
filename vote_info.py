import requests          # OpenAPI 호출용
import pandas as pd       # 표(DataFrame) 처리용

KEY = "0e4486c320bf4cf6987c4602e7ad4e9f"   # 열린국회정보 인증키
BASE = "https://open.assembly.go.kr/portal/openapi"
AGE = 22                                    # 대수 (제22대 국회)

def fetch(service, **extra):
    """열린국회정보 공통 호출 함수: 서비스명 + 추가 파라미터를 받아 row 리스트를 DataFrame으로 반환"""
    params = {"KEY": KEY, "Type": "json", "pIndex": 1, "pSize": 1000, "AGE": AGE}
    params.update(extra)                                  # BILL_ID 등 서비스별 필수값 추가
    j = requests.get(f"{BASE}/{service}", params=params).json()
    key = list(j.keys())[0]                               # 최상위 키 = 서비스명 (오류 시 'RESULT')
    if key == "RESULT":                                   # 오류 응답 처리
        raise RuntimeError(j["RESULT"]["MESSAGE"])
    return pd.DataFrame(j[key][1]["row"])                 # 두 번째 요소의 row가 실제 데이터

# ── 1. 본회의 처리안건 목록 (안건 단위, BILL_ID 확보) ─────────
bills = fetch("ncocpgfiaoituanbr")                        # AGE만으로 조회 가능
print("처리안건 수:", len(bills))

# ── 2. 특정 안건의 의원별 표결 (AGE + BILL_ID 필수) ──────────
bid = bills.iloc[0]["BILL_ID"]                            # 예시로 첫 번째 안건 선택
votes = fetch("nojepdqqaweusdfbi", BILL_ID=bid)          # 그 안건에 대한 300명 찬반
print(f"\n[{bills.iloc[0]['BILL_NAME']}] 표결 분포:")
print(votes["RESULT_VOTE_MOD"].value_counts())          # 찬성/반대/기권 집계

# ── 3. 의원 인적사항과 결합 (키: MONA_CD) ───────────────────
members = fetch("nwvrqwxyaytdsfvhu")                      # 의원 명단
merged = votes.merge(                                     # 표결 + 인적사항 합치기
    members[["MONA_CD", "BTH_DATE", "REELE_GBN_NM"]],     # 필요한 컬럼만 (생년월일·재선구분)
    on="MONA_CD", how="left")                             # MONA_CD 기준 left join

# ── 4. 안건 집계 정보와 결합 (키: BILL_ID) ──────────────────
merged = merged.merge(                                    # 위 결과 + 안건 집계 합치기
    bills[["BILL_ID", "PROC_RESULT_CD", "YES_TCNT", "NO_TCNT"]],
    on="BILL_ID", how="left")                             # BILL_ID 기준 left join

# ── 5. 결과 확인 ────────────────────────────────────────────
print("\n=== 결합 결과 (이름·정당·표결·재선구분·처리결과) ===")
print(merged[["HG_NM", "POLY_NM", "RESULT_VOTE_MOD",
              "REELE_GBN_NM", "PROC_RESULT_CD"]].head(10).to_string(index=False))
