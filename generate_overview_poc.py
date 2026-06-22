"""PoC: 쟁점 안건 하나에 대해 '시민 친화 개요'를 생성한다.
리소스 종합: 제안이유/의안원문 + 정당별 표결(사실) + 메타 + 웹검색(배경·여론).
모델: Claude Opus 4.8. 웹검색은 내장 web_search 툴(출처 인용 포함)을 사용.
정확성 원칙: 법안 내용은 제공된 원문만 근거, 정당입장은 제공된 숫자만 사용.
"""
import os, json
import pandas as pd
import anthropic

MODEL = "claude-opus-4-8"
SEARCH_MAX_USES = 3                                   # 검색 상한(질의 밸브) — Claude가 필요한 만큼만 사용

client = anthropic.Anthropic()                         # ANTHROPIC_API_KEY 환경변수 사용
v = pd.read_parquet("votes_raw_22.parquet")
b = pd.read_csv("bills_22.csv", dtype=str)
summ = json.load(open("summaries.json", encoding="utf-8"))
won = json.load(open("wonmun.json", encoding="utf-8"))

def party_facts(bid):
    """정당별 찬/반/기권/불참 수를 '사실 문장'으로 정리(LLM은 이 숫자만 사용)."""
    sub = v[v["BILL_ID"] == bid]
    lines = []
    order = sub["POLY_NM"].value_counts().index            # 의원 많은 정당부터
    for p in order:
        g = sub[sub["POLY_NM"] == p]["RESULT_VOTE_MOD"].value_counts().to_dict()
        parts = [f"{k} {g[k]}" for k in ["찬성", "반대", "기권", "불참"] if g.get(k)]
        lines.append(f"- {p}: {', '.join(parts)}")
    return "\n".join(lines)

def overview(bid):
    row = b[b["BILL_ID"] == bid].iloc[0]
    body = summ.get(bid) or (won.get(bid, {}) or {}).get("text", "")
    facts = party_facts(bid)

    system = (
        "당신은 시민에게 국회 법안을 쉽고 중립적으로 설명하는 해설가입니다. "
        "전문용어를 풀어 쓰고, 특정 정파에 치우치지 않습니다."
    )
    user = f"""아래 자료만 근거로 '시민용 개요'를 작성하세요.

[안건명] {row['BILL_NAME']}
[처리결과] {row['PROC_RESULT_CD']}   [소관위] {row.get('CURR_COMMITTEE','')}

[공식 본문 — 이 텍스트 안에서만 법안 내용을 요약할 것]
{body[:2500]}

[정당별 표결 (확정 사실 — '정당별 입장'은 반드시 이 숫자만 사용)]
{facts}

[작성 규칙]
- 본문에 없는 법안 내용을 지어내지 말 것.
- '정당별 입장'은 위 표결 숫자에 근거해 풀어쓰되, 의도·이유를 단정하지 말 것.
- 배경/여론은 web_search로 찾고, 단정 대신 "언론 보도에 따르면…"으로 쓰고 출처를 남길 것.
  사실(법안·표결)과 외부 보도를 섞지 말 것.
- 아래 5개 섹션을 이 순서/제목으로, 각 2~4문장 이내로:

## 한 줄 요약
## 무엇이 바뀌나
## 왜 나왔나 (배경)
## 정당별 입장
## 내 삶에 미치는 영향
"""

    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": SEARCH_MAX_USES}]
    messages = [{"role": "user", "content": user}]
    searches = 0
    # 서버 툴(web_search) 루프: pause_turn이면 이어서 재요청
    while True:
        resp = client.messages.create(
            model=MODEL, max_tokens=4000, system=system,
            thinking={"type": "adaptive"}, tools=tools, messages=messages,
        )
        searches += sum(1 for blk in resp.content if getattr(blk, "type", "") == "server_tool_use")
        if resp.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": resp.content})
            continue
        break

    text = "".join(blk.text for blk in resp.content if blk.type == "text")
    return text, searches, resp.usage

if __name__ == "__main__":
    import sys
    bid = sys.argv[1]
    text, searches, usage = overview(bid)
    print(text)
    print("\n" + "─" * 50)
    print(f"실제 검색 횟수: {searches} (상한 {SEARCH_MAX_USES})")
    print(f"토큰 — 입력 {usage.input_tokens} / 출력 {usage.output_tokens}")
