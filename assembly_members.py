import requests          # HTTP 요청을 보내 OpenAPI 데이터를 받아오기 위한 라이브러리
import pandas as pd       # 받아온 데이터를 표(DataFrame) 형태로 다루기 위한 라이브러리

# ── 1. 인증키와 요청 정보 설정 ───────────────────────────────
API_KEY = "0e4486c320bf4cf6987c4602e7ad4e9f"   # 열린국회정보에서 발급받은 인증키
URL = "https://open.assembly.go.kr/portal/openapi/nwvrqwxyaytdsfvhu"  # '국회의원 인적사항' 서비스 주소

params = {                 # API에 함께 보낼 요청 파라미터들
    "KEY": API_KEY,        # 인증키
    "Type": "json",        # 응답 형식 (json 또는 xml) — 여기서는 json 사용
    "pIndex": 1,           # 가져올 페이지 번호 (1페이지부터)
    "pSize": 300,          # 한 페이지에 받을 데이터 개수 (국회의원 전체를 넉넉히 커버)
}

# ── 2. API 호출 ──────────────────────────────────────────────
response = requests.get(URL, params=params)   # GET 방식으로 API에 요청을 보내고 응답을 받음
response.raise_for_status()                    # 응답 코드가 오류(4xx/5xx)면 예외를 발생시켜 즉시 멈춤
data = response.json()                          # 받은 JSON 문자열을 파이썬 딕셔너리로 변환

# ── 3. 실제 데이터(행) 추출 ─────────────────────────────────
# 열린국회정보 응답 구조: { "서비스명": [ {head 정보}, {"row": [실제 데이터 목록]} ]
service_key = "nwvrqwxyaytdsfvhu"               # 응답에서 데이터가 담긴 최상위 키 (= 서비스명)
rows = data[service_key][1]["row"]              # 두 번째 요소의 "row" 안에 의원 목록이 들어 있음

# ── 4. DataFrame으로 변환 및 출력 ───────────────────────────
df = pd.DataFrame(rows)    # 딕셔너리 리스트를 pandas DataFrame(표)으로 변환
print(df)                  # 표 전체를 화면에 출력

# (참고) 주요 컬럼만 보고 싶다면 아래처럼 선택할 수 있음:
# HG_NM(이름), POLY_NM(정당), ORIG_NM(지역구), CMIT_NM(소속위원회)
# print(df[["HG_NM", "POLY_NM", "ORIG_NM", "CMIT_NM"]])
