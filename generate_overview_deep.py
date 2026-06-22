"""심화 버전 PoC: 시민이 '피부로' 이해하는 깊은 개요.
- 무엇이 바뀌나: 전문용어 풀이 + 구체 숫자 예시
- 왜 반대했나: 의원 발언·여론을 web_search로 찾아 직접 인용("…")+출처
모델: Claude Opus 4.8. 토큰 사용량을 출력해 절감 설계의 근거로 삼는다.
"""
import os, json, sys
import pandas as pd
import anthropic

MODEL = os.environ.get("OV_MODEL", "claude-opus-4-8")   # 모델 비교용 (haiku/sonnet/opus)
SEARCH_MAX_USES = 5
# 가격표 ($/1M): 입력, 출력
PRICE = {"claude-opus-4-8": (5, 25), "claude-sonnet-4-6": (3, 15), "claude-haiku-4-5": (1, 5)}

client = anthropic.Anthropic()
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
    """표결일 기준 여당/대통령을 사실로 제공(22대 중 정권교체로 여야가 뒤바뀜)."""
    # 이재명(더불어민주당) 취임 전후로 여야가 뒤집힘. 취임일 기준 분기.
    LEE_INAUG = "2025-06-04"                            # 제21대 대선 후 이재명 정부 출범
    if proc_dt and proc_dt < LEE_INAUG:
        return "대통령 윤석열(국민의힘). 여당=국민의힘, 야당 다수=더불어민주당(야대여소)."
    return "대통령 이재명(더불어민주당). 여당=더불어민주당, 야당=국민의힘."

def overview(bid):
    row = b[b["BILL_ID"] == bid].iloc[0]
    body = summ.get(bid) or (won.get(bid, {}) or {}).get("text", "")
    facts = party_facts(bid)
    proc_dt = row.get("PROC_DT", "")
    power = power_context(proc_dt)
    bill_url = f"https://likms.assembly.go.kr/bill/billDetail.do?billId={bid}"

    system = (
        "당신은 시민에게 국회 법안을 쉽고 중립적으로 설명하는 해설가입니다. "
        "어려운 세법·법률 용어를 일상어로 풀고, 구체적 사례와 숫자로 체감되게 설명합니다. "
        "특정 정파에 치우치지 않으며, 찬성·반대 양측 논리를 균형 있게 전합니다."
    )
    user = f"""아래 자료와 웹검색으로 '시민용 심화 개요'를 작성하세요.

[안건명] {row['BILL_NAME']}
[처리결과] {row['PROC_RESULT_CD']}   [소관위] {row.get('CURR_COMMITTEE','')}
[표결일] {proc_dt}
[표결 당시 정치지형(사실)] {power}

[공식 본문 — 법안 내용은 이 안에서만]
{body[:2500]}

[정당별 표결 (확정 사실)]
{facts}

[의안 원문 링크] {bill_url}

[작성 규칙]
- 전문용어(공제·과세표준·할증평가 등)는 괄호로 쉬운 풀이를 달 것.
- '무엇이 바뀌나'는 **구체 숫자 예시**로 체감되게. 예: "자녀 2명에게 10억을 물려줄 때…" 식.
  단, 본문/출처에 없는 세액은 지어내지 말고, 계산 예시는 '대략·예시'임을 밝힐 것.
- **표결 당시 여당/야당은 위 '정치지형'을 사용**할 것(임기 중 정권교체로 여야가 바뀌었으니
  현재 시점이 아닌 표결일 기준으로 설명). 정부안인데 표결 구도가 의외라면 그 맥락을 짚을 것.
- '왜 반대가 많았나'는 web_search로 **의원 발언·여론**을 찾아 **직접 인용("…")과 출처**를 달고,
  찬성측·반대측 논리를 모두 제시. 단정 대신 "○○ 의원은 …라고 말했다(매체, 날짜)"처럼 귀속.
- '함께 읽기'에는 의안 원문 링크 + web_search로 찾은 **신뢰할 만한 기사 2~3개를 [제목](URL)** 형식으로.
- **금지: 도구·검색·모델·작성과정에 대한 메타 설명을 본문에 쓰지 말 것**
  (예: "검색 한도 소진", "인용을 못 가져왔다" 같은 문구 금지 — 시민에게 보이는 화면임).
  자료가 부족하면 그 섹션을 짧게 쓰거나 생략하고, 변명·면책 문구는 넣지 말 것.
- 아래 섹션을 이 순서/제목으로:

## 한 줄 요약
(1문장)

## 무엇이 바뀌나 (쉽게)
(전문용어 풀이 + 구체 숫자 예시)

## 왜 이런 표결이 나왔나
(표결일 기준 여야 구도 맥락 + 반대측·찬성측 논리, 의원 발언·여론 직접 인용과 출처)

## 정당별 입장
(표결 숫자 근거)

## 내 삶에 미치는 영향
(누구에게 어떻게, 체감되게)

## 함께 읽기
(의안 원문 링크 + 참고 기사 2~3개를 [제목](URL)로)
"""
    # allowed_callers=["direct"]: 동적필터링(코드실행) 끔 → Haiku 호환 + 토큰/비용 급감
    tools = [{"type": "web_search_20260209", "name": "web_search",
              "max_uses": SEARCH_MAX_USES, "allowed_callers": ["direct"]}]
    messages = [{"role": "user", "content": user}]
    web_searches = 0
    kw = {}
    if "haiku" not in MODEL:                                   # haiku는 adaptive thinking 미지원
        kw["thinking"] = {"type": "adaptive"}
    while True:
        resp = client.messages.create(
            model=MODEL, max_tokens=5000, system=system,
            tools=tools, messages=messages, **kw,
        )
        # web_search 호출만 카운트(동적 필터링 코드실행 제외)
        web_searches += sum(1 for blk in resp.content
                            if getattr(blk, "type", "") == "server_tool_use"
                            and getattr(blk, "name", "") == "web_search")
        if resp.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": resp.content})
            continue
        break
    text = "".join(blk.text for blk in resp.content if blk.type == "text")
    return text, web_searches, resp.usage

if __name__ == "__main__":
    bid = sys.argv[1]
    text, ws, u = overview(bid)
    print(text)
    print("\n" + "─" * 50)
    pin, pout = PRICE.get(MODEL, (5, 25))
    cost = u.input_tokens*pin/1e6 + u.output_tokens*pout/1e6
    print(f"모델 {MODEL} | 웹검색 {ws}회 | 입력 {u.input_tokens} / 출력 {u.output_tokens} 토큰")
    print(f"개략 비용(검색비 별도): ${cost:.4f}")
