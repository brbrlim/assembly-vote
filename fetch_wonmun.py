# -*- coding: utf-8 -*-
"""
국회 의안정보시스템(likms.assembly.go.kr)에서 특정 안건의 '의안원문'(원안 전문)
문서를 내려받아 텍스트로 추출하는 모듈.

핵심 흐름
---------
1. billDetail.do 를 한 번 GET 하여 JSESSIONID 세션 쿠키를 확보한다.
2. /bill/bi/dwld/selectFileList.do 에 billId 만 POST 하면, 해당 안건에 등록된
   문서 목록(JSON)을 돌려준다. 각 항목에는 PDF/HWP 직접 다운로드 URL이 들어 있다.
       - pdfFileDwnldUrl: .../filegate/servlet/FileGate?bookId=...&type=1
       - hwpFileDwnldUrl: .../filegate/servlet/FileGate?bookId=...&type=0
   docKindName == "의안원문" 인 항목이 우리가 원하는 원문이다.
   (이 엔드포인트는 화면 JS docBndlDwld.js 의 fn billIdFileExistsYn 가 사용하며,
    일괄다운로드 ZIP 엔드포인트 /bi/dwld/billListDownload.do 보다 훨씬 단순하다.)
3. PDF를 우선 내려받아 PyMuPDF(fitz)로 텍스트를 추출한다.
   PDF가 없으면 HWP를 내려받아 olefile 로 PrvText/본문에서 텍스트를 추출한다.

주의
----
- 모든 /bi/... 호출은 반드시 '/bill' 컨텍스트 경로를 붙여야 한다.
- 요청에는 billDetail URL을 Referer 로 넣어야 안정적으로 동작한다.
- 네트워크 예의를 위해 요청 사이에 time.sleep(0.1) 을 둔다.
"""

import io
import time
import zlib
import struct

import requests

BASE = "https://likms.assembly.go.kr"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


# ---------------------------------------------------------------------------
# 1) 세션 + 문서목록 조회
# ---------------------------------------------------------------------------
def _new_session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    return s


def _select_file_list(session, bill_id, referer):
    """selectFileList.do 호출 → 등록된 문서 목록(JSON) 반환. 실패 시 빈 list."""
    url = f"{BASE}/bill/bi/dwld/selectFileList.do"
    hdr = {"Referer": referer, "X-Requested-With": "XMLHttpRequest"}
    try:
        r = session.post(url, data={"billId": bill_id}, headers=hdr, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []
    return data.get("billFileList") or []


# ---------------------------------------------------------------------------
# 2) 파일 다운로드
# ---------------------------------------------------------------------------
def _download(session, url, referer):
    """주어진 FileGate URL에서 바이트를 받는다. 실패 시 None."""
    try:
        r = session.get(url, headers={"Referer": referer}, timeout=60)
        r.raise_for_status()
    except Exception:
        return None
    return r.content


# ---------------------------------------------------------------------------
# 3) 텍스트 추출 - PDF
# ---------------------------------------------------------------------------
def _extract_pdf(data):
    """PDF 바이트 → 텍스트. PyMuPDF(fitz) 사용. 실패 시 빈 문자열."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return ""
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        return text
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# 3) 텍스트 추출 - HWP (5.x, OLE/CFBF)
# ---------------------------------------------------------------------------
def _extract_hwp(data):
    """
    HWP 5.x 바이트 → 텍스트. olefile 사용.
    - 본문(BodyText/Section*)은 zlib(raw, -15) 압축된 레코드 스트림이라
      디코딩이 까다롭다. 여기서는 텍스트 레코드(tag 67)만 골라 UTF-16LE 로 추출.
    - 실패하거나 본문이 비면 PrvText(미리보기, UTF-16LE 평문)로 폴백.
    """
    try:
        import olefile
    except ImportError:
        return ""

    try:
        ole = olefile.OleFileIO(io.BytesIO(data))
    except Exception:
        return ""

    try:
        # FileHeader 로 본문 압축 여부 확인 (bit 0 == 1 이면 압축)
        compressed = True
        if ole.exists("FileHeader"):
            fh = ole.openstream("FileHeader").read()
            if len(fh) > 36:
                compressed = bool(fh[36] & 0x01)

        # 본문 섹션 수집
        sections = sorted(
            "/".join(s) for s in ole.listdir()
            if len(s) == 2 and s[0] == "BodyText" and s[1].startswith("Section")
        )

        body = []
        for name in sections:
            raw = ole.openstream(name).read()
            if compressed:
                try:
                    raw = zlib.decompress(raw, -15)
                except Exception:
                    continue
            body.append(_parse_hwp_section(raw))
        text = "\n".join(t for t in body if t)

        # PrvText(미리보기, UTF-16LE 평문)도 함께 추출.
        # 본문 레코드 파싱은 인라인 컨트롤 처리 한계로 누락이 있을 수 있으므로,
        # 둘 중 더 많은 글자를 담은 쪽을 채택한다.
        prv = ""
        if ole.exists("PrvText"):
            prv = ole.openstream("PrvText").read().decode("utf-16-le", "ignore")

        return text if len(text.strip()) >= len(prv.strip()) else prv
    except Exception:
        # 최후 폴백: PrvText
        try:
            if ole.exists("PrvText"):
                return ole.openstream("PrvText").read().decode("utf-16-le", "ignore")
        except Exception:
            pass
        return ""
    finally:
        ole.close()


def _parse_hwp_section(buf):
    """
    HWP 본문 섹션(압축 해제된 바이트)을 레코드 단위로 순회하며
    텍스트 레코드(HWPTAG_PARA_TEXT = 67)의 내용을 UTF-16LE 로 모은다.
    제어문자(0~31) 중 일부는 인라인 컨트롤이므로 정리한다.
    """
    out = []
    i, n = 0, len(buf)
    while i + 4 <= n:
        header = struct.unpack_from("<I", buf, i)[0]
        tag_id = header & 0x3FF
        size = (header >> 20) & 0xFFF
        i += 4
        if size == 0xFFF:  # 확장 크기
            if i + 4 > n:
                break
            size = struct.unpack_from("<I", buf, i)[0]
            i += 4
        if i + size > n:
            break
        if tag_id == 67:  # HWPTAG_PARA_TEXT
            raw = buf[i:i + size]
            chars = []
            j = 0
            while j + 1 < len(raw):
                code = raw[j] | (raw[j + 1] << 8)
                # 인라인 컨트롤(코드 < 32)은 대부분 무시, 단 줄바꿈류는 공백 처리
                if code in (13, 10):
                    chars.append("\n")
                    j += 2
                elif code < 32:
                    # 일부 컨트롤은 8바이트(또는 16바이트) 추가 영역을 가짐
                    j += 16 if code in (1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23) else 2
                else:
                    chars.append(chr(code))
                    j += 2
            out.append("".join(chars))
    return "\n".join(out)


# ---------------------------------------------------------------------------
# 공개 함수
# ---------------------------------------------------------------------------
def fetch_wonmun(bill_id):
    """
    주어진 BILL_ID 안건의 '의안원문' 문서를 내려받아 텍스트로 반환한다.
    원문 문서가 없거나 추출에 실패하면 빈 문자열을 반환한다.

    Parameters
    ----------
    bill_id : str  예) "PRC_E2W4R1Q2I0U4B0O0Y5Q5Z4N6H5E8O7"

    Returns
    -------
    str  추출된 원문 텍스트 (실패 시 "")
    """
    session = _new_session()
    referer = f"{BASE}/bill/billDetail.do?billId={bill_id}"

    # 1) 세션 쿠키 확보
    try:
        session.get(referer, timeout=30)
    except Exception:
        return ""
    time.sleep(0.1)

    # 2) 문서 목록 조회
    files = _select_file_list(session, bill_id, referer)
    time.sleep(0.1)
    if not files:
        return ""

    # 3) '의안원문' 항목 선택 (없으면 첫 항목)
    target = None
    for f in files:
        if f.get("docKindName") == "의안원문":
            target = f
            break
    if target is None:
        target = files[0]

    # 4) PDF 우선 → 실패 시 HWP 폴백
    pdf_url = target.get("pdfFileDwnldUrl")
    if pdf_url:
        data = _download(session, pdf_url, referer)
        time.sleep(0.1)
        if data and data[:5] == b"%PDF-":
            text = _extract_pdf(data)
            if text.strip():
                return text

    hwp_url = target.get("hwpFileDwnldUrl")
    if hwp_url:
        data = _download(session, hwp_url, referer)
        time.sleep(0.1)
        # HWP는 OLE/CFBF 매직바이트(D0 CF 11 E0)로 시작
        if data and data[:4] == b"\xd0\xcf\x11\xe0":
            text = _extract_hwp(data)
            if text.strip():
                return text

    return ""


# ---------------------------------------------------------------------------
# 단독 실행 시: 테스트 안건 3건 검증
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    tests = [
        ("비상계엄해제요구 결의안", "PRC_E2W4R1Q2I0U4B0O0Y5Q5Z4N6H5E8O7"),
        ("국정조사 결과보고서 채택", "PRC_C2F5H0D2U2P7K1E6M5N4Q1Q2W1S9G1"),
        ("특검법(법률안)",          "PRC_W2L5V0D9A1S1W1T5G4F4S1Q8N7B6D8"),
    ]
    for name, bid in tests:
        txt = fetch_wonmun(bid)
        head = txt[:150].replace("\n", " ")
        print(f"[{name}] billId={bid}")
        print(f"  글자수: {len(txt)}")
        print(f"  앞150자: {head!r}")
        print("-" * 70)
        time.sleep(0.1)
