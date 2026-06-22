"""Gemini 버전 PoC: 가장 싼 모델(gemini-2.5-flash-lite)로 검색+작성 한 번에.
구글 검색 그라운딩(native)으로 기사·여론 수집. Claude 버전과 품질·비용 비교용.
프롬프트 구조는 Claude 심화판과 동일하게 맞춰 공정 비교.
"""
import os, json, sys
import pandas as pd
from google import genai
from google.genai import types

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")   # 제일 저렴, 안되면 gemini-2.5-flash
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

v = pd.read_parquet("votes_raw_22.parquet")
b = pd.read_csv("bills_22.csv", dtype=str)
summ = json.load(open("summaries.json", encoding="utf-8"))
won = json.load(open("wonmun.json", encoding="utf-8"))

def party_facts(bid):
    sub = v[v["BILL_ID"] == bid]
    lines = []
    for p in sub["POLY_NM"].value_counts().index:
        g = sub[sub["POLY_NM"] == p]["RESULT_VOTE_MOD"].value_counts().to_dict()
        parts = [f"{k} {g[k]}" for k in ["찬성", "반대", "기권", "불참"] if g.get(k)]
        lines.append(f"- {p}: {', '.join(parts)}")
    return "\n".join(lines)

def power_context(proc_dt):
    LEE_INAUG = "2025-06-04"
    if proc_dt and proc_dt < LEE_INAUG:
        return "대통령 윤석열(국민의힘). 여당=국민의힘, 야당 다수=더불어민주당(야대여소)."
    return "대통령 이재명(더불어민주당). 여당=더불어민주당, 야당=국민의힘."

SYSTEM = (
    "당신은 시민에게 국회 법안을 쉽고 중립적으로 설명하는 해설가입니다. "
    "어려운 용어를 일상어로 풀고 구체적 숫자·사례로 체감되게 설명하며, 찬반 양측을 균형 있게 전합니다."
)

def overview(bid):
    row = b[b["BILL_ID"] == bid].iloc[0]
    body = summ.get(bid) or (won.get(bid, {}) or {}).get("text", "")
    proc_dt = row.get("PROC_DT", "")
    bill_url = f"https://likms.assembly.go.kr/bill/billDetail.do?billId={bid}"
    user = f"""아래 자료와 구글 검색으로 '시민용 심화 개요'를 작성하세요.

[안건명] {row['BILL_NAME']}
[처리결과] {row['PROC_RESULT_CD']}   [표결일] {proc_dt}
[표결 당시 정치지형(사실)] {power_context(proc_dt)}

[공식 본문 — 법안 내용은 이 안에서만]
{body[:2500]}

[정당별 표결 (확정 사실)]
{party_facts(bid)}

[의안 원문 링크] {bill_url}

[작성 규칙]
- 전문용어는 괄호로 쉬운 풀이. '무엇이 바뀌나'는 구체 숫자 예시로 체감되게(없는 세액 지어내지 말 것).
- 여당/야당은 위 '정치지형'(표결일 기준) 사용. 현재 시점 아님.
- '왜 이런 표결이 나왔나'는 검색으로 의원 발언·여론을 찾아 직접 인용("…")+출처. 찬반 양측 균형.
- '함께 읽기'에 의안 원문 + 검색으로 찾은 기사 2~3개를 [제목](URL)로.
- 금지: 도구·검색·모델·작성과정 메타설명(예: "검색 못함") 금지. 자료 부족 섹션은 짧게.
- 섹션: ## 한 줄 요약 / ## 무엇이 바뀌나 (쉽게) / ## 왜 이런 표결이 나왔나 / ## 정당별 입장 / ## 내 삶에 미치는 영향 / ## 함께 읽기
"""
    cfg = types.GenerateContentConfig(
        system_instruction=SYSTEM,
        tools=[types.Tool(google_search=types.GoogleSearch())],   # 구글 검색 그라운딩
    )
    resp = client.models.generate_content(model=MODEL, contents=user, config=cfg)
    um = resp.usage_metadata
    return resp.text, um

if __name__ == "__main__":
    bid = sys.argv[1]
    text, um = overview(bid)
    print(text)
    print("\n" + "─" * 50)
    pi, po = um.prompt_token_count, um.candidates_token_count
    print(f"모델 {MODEL} | 입력 {pi} / 출력 {po} 토큰")
    cost = pi*0.10/1e6 + po*0.40/1e6
    print(f"개략 비용(flash-lite, 검색비 별도): ${cost:.4f}")
