"""모은 표결 데이터를 인터랙티브 단일 HTML로 생성한다.
 - 안건별 뷰: 시계열순 안건 → 정당별 의원 표결
 - 의원별 뷰: 의원 클릭 → 전체 안건 표결 히스토리
데이터는 '의원 × 안건' 1글자 코드 행렬로 압축해 HTML에 임베드한다.
"""
import json
import os
import re
import math
import bisect
import numpy as np
import pandas as pd


def compute_issues(votes):
    """안건별 쟁점 지표를 계산해 {BILL_ID: {tags, score, ...}} 반환.
    기준: 접전(찬반 팽팽)/보이콧(불참 폭증)/이견(반대+기권)/분열(정당내 이탈)."""
    c = votes.pivot_table(index="BILL_ID", columns="RESULT_VOTE_MOD",
                          values="MONA_CD", aggfunc="count", fill_value=0)
    for k in ["찬성", "반대", "기권", "불참"]:
        if k not in c: c[k] = 0
    rec = c[["찬성", "반대", "기권", "불참"]].sum(axis=1)             # 전체 기록
    dec = (c["찬성"] + c["반대"]).replace(0, np.nan)                  # 결정표(찬+반)
    voted = (c["찬성"] + c["반대"] + c["기권"]).replace(0, np.nan)    # 실제 투표
    close = c[["찬성", "반대"]].min(axis=1) / dec                     # 접전도
    boycott = c["불참"] / rec                                         # 불참률
    dissent = (c["반대"] + c["기권"]) / voted                         # 반대+기권율

    # 정당 내 이탈(반란표): 정당별 당론(최다)에서 벗어난 최대 인원
    vt = votes[votes["RESULT_VOTE_MOD"].isin(["찬성", "반대", "기권"])]
    g = vt.groupby(["BILL_ID", "POLY_NM"])["RESULT_VOTE_MOD"].value_counts().unstack(fill_value=0)
    for k in ["찬성", "반대", "기권"]:
        if k not in g: g[k] = 0
    tot = g[["찬성", "반대", "기권"]].sum(axis=1)
    defect = (tot - g[["찬성", "반대", "기권"]].max(axis=1)).where(tot >= 10, 0)
    split = defect.groupby("BILL_ID").max().reindex(c.index).fillna(0)

    out = {}
    for bid in c.index:
        tags = []
        if close.get(bid, 0) >= 0.15:   tags.append("접전")
        if boycott.get(bid, 0) >= 0.45: tags.append("보이콧")
        if dissent.get(bid, 0) >= 0.20: tags.append("이견")
        if split.get(bid, 0) >= 10:     tags.append("분열")
        # 쟁점 점수: 각 지표를 대략 [0,1]로 정규화해 합산(태그 가중치 역할)
        score = round(float(np.nan_to_num(close.get(bid, 0)) / 0.375
                            + np.nan_to_num(boycott.get(bid, 0)) / 0.50
                            + np.nan_to_num(dissent.get(bid, 0)) / 0.65
                            + min(split.get(bid, 0) / 72.0, 1.0)), 3)
        out[bid] = {"tags": tags, "score": score, "split": int(split.get(bid, 0))}
    return out


TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>좌우지간 · 국회 표결 피드</title>
<meta name="description" content="22대 국회 표결을 시민 눈높이로 — 화제 법안, AI 개요, 정당별 표결, 의원별 기록을 한눈에.">
<meta property="og:title" content="좌우지간 · 국회 표결 피드">
<meta property="og:description" content="좌든 우든, 표결은 팩트로 — 22대 국회 표결 시민 데이터 피드">
<meta property="og:type" content="website">
<meta property="og:url" content="https://brbrlim.github.io/assembly-vote/">
<meta property="og:image" content="https://brbrlim.github.io/assembly-vote/og.png">
<meta property="og:site_name" content="좌우지간">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="https://brbrlim.github.io/assembly-vote/og.png">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  * { box-sizing: border-box; }
  body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;
         color:#1a1a1a; background:#f4f5f7; font-size:14px; }
  header { background:#16213e; color:#fff; padding:15px 20px 13px; }
  .brand { font-size:25px; font-weight:900; letter-spacing:-.6px; line-height:1; }
  .brand .mark { color:#f3c14b; }                          /* '좌우' 강조 — 중립 골드 */
  .brand .sep { color:#5b6b8c; font-weight:400; margin:0 7px; }
  .tagline { font-size:13.5px; opacity:.9; font-weight:500; vertical-align:middle; }
  header .sub { opacity:.55; font-size:11px; margin-top:6px; }
  .tabs { display:flex; gap:4px; background:#16213e; padding:0 20px; }
  .tab { padding:9px 18px; cursor:pointer; color:#aab; border-radius:6px 6px 0 0; font-weight:600; }
  .tab.active { background:#f4f5f7; color:#16213e; }
  .view { display:none; height:calc(100vh - 104px); }
  .view.active { display:flex; }
  #view-bill.active, #view-dash.active { display:block; overflow-y:auto; }   /* 단일 컬럼 스크롤 */
  .dash { max-width:720px; margin:0 auto; padding:14px 14px 80px; }
  .dsec { background:#fff; border:1px solid #e4e7eb; border-radius:14px; padding:14px 16px; margin-bottom:13px; }
  .dsec h3 { margin:0 0 11px; font-size:15px; color:#16213e; }
  .cards { display:flex; gap:10px; flex-wrap:wrap; }
  .scard { flex:1; min-width:78px; background:#f7f9fc; border-radius:10px; padding:11px 10px; text-align:center; }
  .scard b { font-size:22px; display:block; line-height:1.1; } .scard small { color:#888; font-size:11px; }
  .brow { display:flex; align-items:center; gap:8px; margin:5px 0; font-size:13px; }
  .blab { width:128px; flex:none; color:#445; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .btrack { flex:1; background:#eef0f3; border-radius:5px; height:15px; overflow:hidden; }
  .bfill { height:100%; border-radius:5px; }
  .bval { width:40px; flex:none; text-align:right; color:#667; font-variant-numeric:tabular-nums; }
  .dlist a { display:block; padding:6px 0; border-bottom:1px solid #f0f0f0; font-size:13px; color:#16213e; text-decoration:none; cursor:pointer; }
  .dlist a:hover { background:#f7f9fc; }
  .dchip { display:inline-block; background:#fff0e6; color:#d2630a; border-radius:12px; padding:3px 10px; margin:3px 3px 0 0; font-size:12.5px; cursor:pointer; }
  .dchip:hover { background:#ffe1cc; }
  .chartbox { position:relative; height:280px; }
  .cbox { border:1px solid #e8eaed; border-radius:10px; padding:10px 12px; margin-bottom:10px; }
  .cbox-h { display:flex; justify-content:space-between; align-items:center; font-weight:700; font-size:14px; margin-bottom:8px; color:#16213e; }
  .cbox-h small { color:#8a929c; font-weight:500; font-size:12px; }
  .carousel { display:flex; gap:8px; overflow-x:auto; padding-bottom:5px; scrollbar-width:thin; }
  .mcard { flex:0 0 196px; background:#f7f9fc; border:1px solid #eef0f3; border-radius:9px; padding:9px 11px; cursor:pointer; }
  .mcard:hover { background:#eef3fb; }
  .mcard .mh { font-weight:600; font-size:12.5px; color:#16213e; line-height:1.4; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
  .mcard .mm { color:#9aa0a6; font-size:11px; margin-top:5px; }
  .prow { display:flex; align-items:center; gap:8px; padding:8px 4px; border-bottom:1px solid #f0f0f0; cursor:pointer; font-size:13px; }
  .prow:hover { background:#f7f9fc; } .prow .pdot { width:9px; height:9px; border-radius:50%; flex:none; }
  .prow .pn { margin-left:auto; color:#888; font-variant-numeric:tabular-nums; }
  .pane-l { width:38%; min-width:300px; border-right:1px solid #ddd; overflow-y:auto; background:#fff; }
  .pane-r { flex:1; overflow-y:auto; padding:18px 22px; }
  .search { position:sticky; top:0; background:#fff; padding:10px; border-bottom:1px solid #eee; z-index:5; }
  .search input { width:100%; padding:8px 10px; border:1px solid #ccc; border-radius:6px; font-size:13px; }
  .row { padding:8px 12px; border-bottom:1px solid #f0f0f0; cursor:pointer; display:flex; gap:8px; align-items:baseline; }
  .row:hover { background:#eef3fb; }
  .row.sel { background:#dce8fb; }
  .row .date { color:#999; font-size:11px; white-space:nowrap; font-variant-numeric:tabular-nums; }
  .row .name { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .badge { font-size:10px; padding:1px 6px; border-radius:10px; white-space:nowrap; }
  .b-pass { background:#e6f4ea; color:#137333; } .b-fail { background:#fce8e6; color:#c5221f; }
  .b-etc { background:#eee; color:#666; }
  .tag { font-size:10px; padding:1px 6px; border-radius:4px; white-space:nowrap; font-weight:600; }
  .t-접전 { background:#ede7f6; color:#5e35b1; } .t-보이콧 { background:#fff3e0; color:#e65100; }
  .t-이견 { background:#fce4ec; color:#c2185b; } .t-분열 { background:#e0f2f1; color:#00695c; }
  .ctrl { padding:8px 10px; border-bottom:1px solid #eee; display:flex; gap:5px; flex-wrap:wrap; align-items:center; background:#fafbfc; }
  .ctrl button { border:1px solid #ccc; background:#fff; border-radius:14px; padding:3px 11px; cursor:pointer; font-size:12px; }
  .ctrl button.on { background:#16213e; color:#fff; border-color:#16213e; }
  .ctrl .lbl { font-size:11px; color:#888; margin-left:4px; }
  .pdot { width:9px; height:9px; border-radius:50%; display:inline-block; flex:none; }
  .ptag { font-size:11px; color:#fff; padding:1px 7px; border-radius:10px; }
  h2.det { margin:0 0 4px; font-size:17px; line-height:1.35; }
  .meta { color:#666; font-size:12px; margin-bottom:14px; }
  .meta span { margin-right:14px; }
  .billlink { display:inline-block; background:#16213e; color:#fff; padding:3px 12px; border-radius:14px;
              text-decoration:none; font-weight:600; }
  .billlink:hover { background:#2a3a5e; }
  .sharebtn { background:#f3c14b; color:#16213e; border:none; padding:4px 13px; border-radius:14px; font-weight:700; font-size:12px; cursor:pointer; }
  .sharebtn:hover { background:#e8b32f; }
  #toast { position:fixed; left:50%; bottom:34px; transform:translateX(-50%) translateY(20px); background:#16213e; color:#fff;
           padding:11px 20px; border-radius:24px; font-size:13.5px; font-weight:600; opacity:0; pointer-events:none; transition:.25s; z-index:99; box-shadow:0 6px 22px rgba(0,0,0,.3); }
  #toast.show { opacity:1; transform:translateX(-50%) translateY(0); }
  .sumbar { display:flex; height:26px; border-radius:5px; overflow:hidden; margin:10px 0 4px; font-size:11px; }
  .sumbar div { display:flex; align-items:center; justify-content:center; color:#fff; min-width:0; }
  .sumlegend { font-size:12px; color:#555; margin-bottom:16px; }
  .ovw { background:#eef5ff; border:1px solid #cfe0f5; border-radius:8px; margin-bottom:14px; }
  .ovw-h { padding:9px 13px; font-weight:700; font-size:14px; color:#16407a; border-bottom:1px solid #cfe0f5; }
  .ovw-ai { font-weight:500; font-size:10px; color:#6b86ad; background:#dce8fb; padding:1px 7px; border-radius:10px; margin-left:6px; }
  .ovw-b { padding:6px 14px 12px; }
  .ovw-b h4 { margin:12px 0 3px; font-size:13px; color:#16407a; }
  .ovw-b p { margin:3px 0; font-size:13px; line-height:1.65; color:#243; }
  .ovw-b .ovwli { font-size:13px; line-height:1.6; color:#243; margin:2px 0 2px 6px; }
  .ovw-b table.ovwt { border-collapse:collapse; margin:8px 0; font-size:12px; }
  .ovw-b table.ovwt th, .ovw-b table.ovwt td { border:1px solid #cfe0f5; padding:3px 9px; text-align:left; }
  .ovw-b table.ovwt th { background:#dce8fb; color:#16407a; }
  .billsum { background:#fbfaf5; border:1px solid #ece8d8; border-radius:8px; margin-bottom:16px; }
  .billsum-h { padding:8px 12px; font-weight:700; font-size:13px; color:#5b4a1f; border-bottom:1px solid #ece8d8; }
  .billsum-b { padding:12px; font-size:13px; line-height:1.7; white-space:pre-wrap; max-height:260px; overflow-y:auto; color:#333; }
  .pgroup { margin-bottom:14px; border:1px solid #eee; border-radius:8px; overflow:hidden; }
  .pgroup h3 { margin:0; padding:7px 12px; font-size:13px; color:#fff; display:flex; justify-content:space-between; }
  .chips { padding:10px; display:flex; flex-wrap:wrap; gap:5px; }
  .chip { padding:3px 9px; border-radius:14px; font-size:12px; cursor:pointer; border:1px solid transparent; }
  .chip:hover { border-color:#333; }
  .vY { background:#e6f4ea; color:#137333; } .vN { background:#fce8e6; color:#c5221f; }
  .vA { background:#fef7e0; color:#b06000; } .vX { background:#f1f3f4; color:#5f6368; text-decoration:line-through; }
  .vD { background:#fafafa; color:#bbb; }
  table.hist { width:100%; border-collapse:collapse; }
  table.hist td { padding:6px 8px; border-bottom:1px solid #f0f0f0; }
  table.hist .date { color:#999; font-size:11px; white-space:nowrap; }
  table.hist .vt { white-space:nowrap; text-align:right; }
  .stat { display:inline-block; padding:8px 14px; background:#fff; border:1px solid #eee; border-radius:8px; margin:0 8px 8px 0; }
  .stat b { font-size:18px; } .stat small { color:#888; display:block; font-size:11px; }
  .filterbar { margin:10px 0; }
  .filterbar button { border:1px solid #ccc; background:#fff; border-radius:14px; padding:3px 11px; cursor:pointer; font-size:12px; margin-right:5px; }
  .filterbar button.on { background:#16213e; color:#fff; border-color:#16213e; }
  .empty { color:#999; padding:40px; text-align:center; }
  /* ---- 뉴스피드 ---- */
  .feed { max-width:680px; margin:0 auto; padding:0 12px 80px; }
  .fctrl { position:sticky; top:0; background:#f4f5f7; padding:12px 0 10px; z-index:8; display:flex; gap:7px; flex-wrap:wrap; align-items:center; }
  .fctrl input { flex:1; min-width:150px; padding:9px 14px; border:1px solid #d0d4da; border-radius:20px; font-size:14px; outline:none; }
  .fbtn { border:1px solid #d0d4da; background:#fff; border-radius:18px; padding:6px 14px; cursor:pointer; font-size:13px; font-weight:600; color:#445; }
  .fbtn.on { background:#16213e; color:#fff; border-color:#16213e; }
  a.card { display:block; text-decoration:none; color:inherit; }
  .card { background:#fff; border:1px solid #e4e7eb; border-radius:16px; padding:15px 17px; margin-bottom:13px; cursor:pointer; transition:box-shadow .12s,transform .12s; }
  .card:hover { box-shadow:0 4px 18px rgba(20,30,60,.10); transform:translateY(-1px); }
  .cmeta { display:flex; gap:7px; align-items:center; font-size:11px; color:#8a929c; margin-bottom:8px; flex-wrap:wrap; }
  .cmeta .cmt { background:#eef0f3; padding:2px 9px; border-radius:11px; color:#556; font-weight:600; }
  .headline { font-size:18px; font-weight:800; line-height:1.38; color:#15213e; margin:0 0 4px; letter-spacing:-.2px; }
  .subname { font-size:12px; color:#a2a8b0; margin-bottom:10px; }
  .csnip { font-size:14px; line-height:1.62; color:#3a4452; margin:9px 0; }
  .cbar { display:flex; height:8px; border-radius:5px; overflow:hidden; margin:11px 0 6px; background:#eee; }
  .cfoot { display:flex; gap:14px; align-items:center; font-size:12.5px; color:#667; margin-top:9px; flex-wrap:wrap; }
  .cfoot .more { margin-left:auto; color:#1a73e8; font-weight:700; }
  .aibadge { background:#e8f0fe; color:#1a56c4; padding:2px 9px; border-radius:11px; font-size:11px; font-weight:700; }
  .buzz { background:#fff0e6; color:#d2630a; padding:2px 9px; border-radius:11px; font-size:11px; font-weight:800; }
  .prop { display:flex; align-items:center; gap:6px; font-size:12.5px; color:#556; margin:2px 0 9px; }
  .prop .pdot { width:9px; height:9px; border-radius:50%; flex:none; }
  .info { position:relative; cursor:help; color:#9aa0a6; font-size:14px; }
  .info .tip { display:none; position:absolute; top:22px; left:50%; transform:translateX(-50%); width:280px;
    background:#16213e; color:#eaeef6; font-size:12px; line-height:1.6; font-weight:400; padding:10px 12px; border-radius:8px; z-index:20; box-shadow:0 6px 20px rgba(0,0,0,.25); }
  .info:hover .tip, .info:focus .tip { display:block; }
  /* ---- 모달 ---- */
  .modal { display:none; position:fixed; inset:0; background:rgba(15,22,40,.5); z-index:50; backdrop-filter:blur(2px); }
  .modal.open { display:block; }
  .sheet { background:#f4f5f7; max-width:740px; margin:22px auto; border-radius:16px; max-height:calc(100vh - 44px); overflow-y:auto; }
  .sheet-h { position:sticky; top:0; background:#16213e; color:#fff; padding:14px 20px; display:flex; justify-content:space-between; align-items:flex-start; gap:12px; border-radius:16px 16px 0 0; }
  .sheet-h .htxt b { font-size:18px; font-weight:800; line-height:1.35; } .sheet-h .htxt small { display:block; font-size:12px; opacity:.7; margin-top:4px; }
  .sheet-h .x { cursor:pointer; font-size:20px; line-height:1; opacity:.85; flex:none; }
  .sheet-b { padding:16px 20px 30px; }
</style>
</head>
<body>
<header>
  <span class="brand"><span class="mark">좌우</span>지간</span><span class="brand sep">·</span><span class="tagline">좌든 우든, 표결은 팩트로</span>
  <div class="sub" id="hsub"></div>
</header>
<div class="tabs">
  <div class="tab active" data-v="dash" onclick="switchTab('dash')">📊 한눈에</div>
  <div class="tab" data-v="bill" onclick="switchTab('bill')">📰 안건 피드</div>
  <div class="tab" data-v="member" onclick="switchTab('member')">의원별</div>
</div>

<div class="view active" id="view-dash"><div class="dash" id="dash"></div></div>

<div class="view" id="view-bill">
  <div class="feed">
    <div class="fctrl">
      <input id="billSearch" placeholder="🔍 법안 검색…" oninput="renderFeed()">
      <button class="fbtn on" id="s-buzz" onclick="setSort('buzz')">🔥 화제순</button>
      <button class="fbtn" id="s-recent" onclick="setSort('recent')">🕒 최신순</button>
      <span class="info" tabindex="0">ⓘ<span class="tip"><b>화제도(0~100)</b>는 ① 표결이 얼마나 갈렸는지(접전·이견·분열·보이콧) ② 사회적 키워드(계엄·방송·특검 등) ③ 발의 규모 ④ 최신성을 합산한 <b>상대 점수</b>입니다. 외부 여론 지표가 아니라 표결·법안 데이터 기반 추정이며, 추후 언론 보도량으로 보강할 예정입니다.</span></span>
      <button class="fbtn" id="f-ovw" onclick="toggleOvw()">📖 개요</button>
    </div>
    <div id="feed"></div>
  </div>
</div>
<div class="modal" id="modal" onclick="if(event.target===this)closeModal()">
  <div class="sheet"><div class="sheet-h" id="sheetH"></div><div class="sheet-b" id="sheetB"></div></div>
</div>
<div id="toast"></div>

<div class="view" id="view-member">
  <div class="pane-l">
    <div class="search"><input id="memSearch" placeholder="의원명 검색…" oninput="renderMemList()"></div>
    <div id="memList"></div>
  </div>
  <div class="pane-r" id="memDetail"><div class="empty">왼쪽에서 의원을 선택하세요</div></div>
</div>

<script>
const DATA = /*__DATA__*/;
const PC = {'더불어민주당':'#152484','국민의힘':'#e61e2b','조국혁신당':'#06d6a0',
  '개혁신당':'#ff7920','진보당':'#d6001c','기본소득당':'#00b5b8','사회민주당':'#f58220','무소속':'#888'};
const PORDER = ['더불어민주당','국민의힘','조국혁신당','개혁신당','진보당','기본소득당','사회민주당','무소속'];
const VL = {Y:'찬성',N:'반대',A:'기권',X:'불참','.':'—'};
const VCLR = {Y:'#34a853',N:'#ea4335',A:'#fbbc04',X:'#9aa0a6'};
const pcolor = p => PC[p] || '#888';

DATA.members.forEach((m,i)=> m.idx=i);
document.getElementById('hsub').textContent =
  `안건 ${DATA.bills.length.toLocaleString()}건 · 의원 ${DATA.members.length}명 · 쉽게 보는 국회 표결`;

function switchTab(v){
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active',t.dataset.v===v));
  document.querySelectorAll('.view').forEach(x=>x.classList.remove('active'));
  document.getElementById('view-'+v).classList.add('active');
}

/* ---------- 대시보드 ---------- */
function bar(label,val,max,color,onclick){
  const w=Math.max(2,val/max*100);
  return `<div class="brow"><span class="blab"${onclick?` style="cursor:pointer" onclick="${onclick}"`:''}>${label}</span>`+
    `<span class="btrack"><span class="bfill" style="width:${w}%;background:${color}"></span></span><span class="bval">${val}</span></div>`;
}
function miniCard(i){
  const b=DATA.bills[i];
  return `<div class="mcard" onclick="goBill(${i})"><div class="mh">${cmtEmoji(b.cmt)} ${esc(bigTitle(b))}</div>`+
    `<div class="mm">${b.date||''} · ${esc(b.result||'')}</div></div>`;
}
function carousel(idxs){ return `<div class="carousel">${(idxs||[]).map(miniCard).join('')}</div>`; }
function togProp(k){ const e=document.getElementById('pcar'+k); e.style.display = e.style.display==='none'?'flex':'none'; }
let monthChart=null;
function drawChart(){
  const s=DATA.stats, ctx=document.getElementById('monthChart');
  if(!ctx||!window.Chart) return;
  const col=['#e8743b','#19a979','#945ecf','#cc3c43','#13a4b4','#f5b301','#6b7280','#4b6cb7'];
  const ds=[{label:'전체',data:s.monthSeries.total,borderColor:'#16213e',backgroundColor:'#16213e',borderWidth:2.5,tension:.35,pointRadius:0}];
  s.monthSeries.cmts.forEach((c,i)=>ds.push({label:c.name.replace('위원회',''),data:c.data,borderColor:col[i%col.length],backgroundColor:col[i%col.length],borderWidth:1.5,tension:.35,pointRadius:0,hidden:true}));
  if(monthChart) monthChart.destroy();
  monthChart=new Chart(ctx,{type:'line',data:{labels:s.monthSeries.labels,datasets:ds},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
      plugins:{legend:{position:'bottom',labels:{boxWidth:11,padding:7,font:{size:11}}},
        tooltip:{callbacks:{title:i=>i[0].label}}},
      scales:{y:{beginAtZero:true,ticks:{font:{size:10}}},x:{ticks:{font:{size:9},maxRotation:60,autoSkip:true,maxTicksLimit:12}}}}});
}
function renderStats(){
  const s=DATA.stats; if(!s) return;
  const pass=s.result['가결']||0, fail=s.result['부결']||0;
  let h=`<div class="dsec"><div class="cards">
    <div class="scard"><b>${s.total.toLocaleString()}</b><small>처리 안건</small></div>
    <div class="scard"><b style="color:#137333">${pass.toLocaleString()}</b><small>가결</small></div>
    <div class="scard"><b style="color:#c5221f">${fail}</b><small>부결</small></div>
    <div class="scard"><b style="color:#1a56c4">${s.ovwCount}</b><small>AI 개요</small></div></div></div>`;
  h+=`<div class="dsec"><h3>🔥 가장 화제가 된 안건</h3>`+
     s.topbuzz.map(b=>`<span class="dchip" onclick="goBill(${b.idx})">🔥${b.buzz} ${esc(b.head.slice(0,22))}</span>`).join('')+`</div>`;
  h+=`<div class="dsec"><h3>📈 월별 처리 추이 <small style="font-weight:400;color:#999;font-size:11px">(범례 클릭해 위원회별 선 켜고 끄기)</small></h3><div class="chartbox"><canvas id="monthChart"></canvas></div></div>`;
  h+=`<div class="dsec"><h3>🏛 위원회별 안건 (좌우로 넘겨보기)</h3>`+
     s.bycmt.map(c=>`<div class="cbox"><div class="cbox-h"><span>${esc(c.c)}</span><small>${c.n}건</small></div>${carousel(s.cmtBills[c.c])}</div>`).join('')+`</div>`;
  h+=`<div class="dsec"><h3>✏️ 최다 대표발의 의원 <small style="font-weight:400;color:#999;font-size:11px">(클릭해 발의 안건 보기)</small></h3>`+
     s.topprop.map((p,k)=>`<div class="prow" onclick="togProp(${k})"><span class="pdot" style="background:${PC[p.party]||'#888'}"></span>`+
       `<b>${esc(p.name)}</b> <span style="color:${PC[p.party]||'#888'};font-size:11px">${esc(p.party)}</span>`+
       `<span class="pn">${p.n}건 ▾</span></div><div class="carousel" id="pcar${k}" style="display:none">${(s.propBills[p.name]||[]).map(miniCard).join('')}</div>`).join('')+`</div>`;
  const ppmax=Math.max(...s.bypartyprop.map(p=>p.n));
  h+=`<div class="dsec"><h3>🏳 정당별 대표발의 (의원 발의)</h3>`+
     s.bypartyprop.map(p=>bar(`${esc(p.party)} <span style="font-size:11px;color:#999">가결 ${p.pass}</span>`, p.n, ppmax, PC[p.party]||'#888')).join('')+`</div>`;
  h+=`<div class="dsec"><h3>❌ 부결된 안건 (${s.rejected.length}건)</h3><div class="dlist">`+
     s.rejected.map(r=>`<a onclick="goBill(${r.idx})"><span style="color:#aaa">${r.date}</span> ${esc(r.head)}</a>`).join('')+`</div></div>`;
  document.getElementById('dash').innerHTML=h;
  drawChart();
}

/* ---------- 안건 피드 ---------- */
let sortMode='buzz', ovwOnly=false;
DATA.bills.forEach((b,i)=> b.idx=i);                       // 원래 시계열 인덱스 보존
function setSort(m){
  sortMode=m;
  document.getElementById('s-buzz').classList.toggle('on',m==='buzz');
  document.getElementById('s-recent').classList.toggle('on',m==='recent');
  renderFeed();
}
function toggleOvw(){ ovwOnly=!ovwOnly; document.getElementById('f-ovw').classList.toggle('on',ovwOnly); renderFeed(); }
function tagHTML(tags){ return tags.map(t=>`<span class="tag t-${t}">${t}</span>`).join(' '); }
// 최초제안자(당색) 표시
function propHTML(b){
  if(!b.prop) return '';
  const pname = b.prop.length>20 ? b.prop.slice(0,18)+'…' : b.prop;   // 긴 특위명 줄임
  const sys={'정부':'정부 발의','국회의장':'국회의장 발의','위원회':esc(pname)+' 제안'};
  if(sys[b.propParty]) return `<div class="prop"><span class="pdot" style="background:#9aa0a6"></span>${sys[b.propParty]}</div>`;
  const col=PC[b.propParty]||'#888';
  return `<div class="prop"><span class="pdot" style="background:${col}"></span>최초제안 <b>${esc(b.prop)}</b>${b.propParty?` · <span style="color:${col};font-weight:700">${b.propParty}</span>`:''}</div>`;
}

// 법안명 → 친근한 헤드라인(관료적 접미사 제거) — LLM 헤드라인 없을 때 폴백
function friendly(name){
  let s=name.replace(/\([^)]*위원장\)/g,'').replace(/\([^)]*의원[^)]*\)/g,'')
    .replace(/\(정부\)/g,'').replace(/\(대안\)/g,'').replace(/\(의장\)/g,'');
  s=s.replace(/일부개정법률안/g,'개정안').replace(/전부개정법률안/g,'전부개정안')
     .replace(/폐지법률안/g,'폐지안').replace(/제정법률안/g,'제정안');
  return s.replace(/\s{2,}/g,' ').trim();
}
function bigTitle(b){ return b.headline || friendly(b.name); }   // LLM 헤드라인 우선
// 위원회 → 카테고리 이모지(무료)
const CMTEMOJI={'기획재정':'💰','정무':'🏦','국방':'🛡️','법제사법':'⚖️','행정안전':'🏛️','교육':'🎓',
 '보건복지':'🏥','환경노동':'🌿','국토교통':'🚦','농림축산식품해양수산':'🌾','산업통상자원':'🏭',
 '과학기술정보방송통신':'📡','문화체육관광':'🎭','외교통일':'🌏','여성가족':'👨‍👩‍👧','정보위':'🕵️','국회운영':'🏛️','예산':'💵'};
function cmtEmoji(c){ for(const k in CMTEMOJI) if(c&&c.includes(k)) return CMTEMOJI[k]; return '📋'; }
function ovSummary(ov){ const m=ov && ov.match(/##\s*한 줄 요약\s*\n+([^#]+)/); return m? m[1].trim().replace(/\n+/g,' '):''; }
function snippet(b){
  if(b.overview){ const s=ovSummary(b.overview); if(s) return s; }
  if(b.summary){ const s=b.summary.replace(/\s+/g,' ').trim(); return s.slice(0,100)+(s.length>100?'…':''); }
  return '';
}
function votesOf(i){
  const cnt={Y:0,N:0,A:0,X:0,'.':0}, byParty={};
  DATA.members.forEach(m=>{ const v=m.v[i]; cnt[v]++; if(v!=='.')(byParty[m.party]=byParty[m.party]||[]).push({m,v}); });
  return {cnt, byParty, tot:cnt.Y+cnt.N+cnt.A+cnt.X};
}
function renderFeed(){
  const q=document.getElementById('billSearch').value.trim();
  let list=DATA.bills.filter(b=>{
    if(q && !(b.name.includes(q)||bigTitle(b).includes(q))) return false;
    if(ovwOnly && !b.overview) return false;
    return true;
  });
  list = sortMode==='recent'
    ? list.slice().sort((a,b)=>b.idx-a.idx)                          // 최신순
    : list.slice().sort((a,b)=>b.buzz-a.buzz || b.idx-a.idx);        // 화제순(동점=최신)
  let h='';
  list.forEach(b=>{
    const i=b.idx, {cnt,tot}=votesOf(i);
    const cls=b.result.includes('가결')?'b-pass':(b.result.includes('부결')?'b-fail':'b-etc');
    const bar=['Y','N','A','X'].map(k=>cnt[k]?`<div style="background:${VCLR[k]};flex:${cnt[k]}"></div>`:'').join('');
    const sn=snippet(b);
    h+=`<a class="card" href="bill/${b.no}.html" onclick="return openBill(event,${i})">
      <div class="cmeta"><span class="buzz" title="화제도 ${b.buzz}/100">🔥 ${b.buzz}</span>
        <span class="cmt">${esc(b.cmt||'안건')}</span><span>${b.date||''}</span>
        <span class="badge ${cls}">${esc(b.result||'-')}</span>${tagHTML(b.tags)}
        ${b.overview?'<span class="aibadge">📖 AI 개요</span>':''}</div>
      <div class="headline">${cmtEmoji(b.cmt)} ${esc(bigTitle(b))}</div>
      <div class="subname">${esc(b.name)}</div>
      ${propHTML(b)}
      ${sn?`<div class="csnip">${esc(sn)}</div>`:''}
      <div class="cbar">${bar}</div>
      <div class="cfoot"><span>👍 ${cnt.Y}</span><span>👎 ${cnt.N}</span><span>🚫 불참 ${cnt.X}</span>
        <span class="more">자세히 보기 →</span></div></a>`;
  });
  const cap = `${list.length}건 · ${sortMode==='buzz'?'🔥 화제순':'🕒 최신순'}${ovwOnly?' · 📖개요만':''}`;
  document.getElementById('feed').innerHTML=`<div style="font-size:12px;color:#99a;padding:2px 2px 10px">${cap}</div>`+(h||'<div class="empty">결과 없음</div>');
}
let curBill=null;
// 피드에서 카드 클릭 → 새로고침 없이 모달 + 주소를 실제 페이지(bill/<no>.html)로 변경
function goBill(i){                                   // 모든 안건 열기의 표준 진입(주소 변경+모달)
  const no=DATA.bills[i].no;
  history.pushState({bill:no}, '', 'bill/'+no+'.html');
  openModal(i);
}
function openBill(e,i){
  if(e.metaKey||e.ctrlKey||e.shiftKey||e.button===1) return true;   // 새 탭 열기는 허용
  e.preventDefault(); goBill(i); return false;
}
function openModal(i){
  const b=DATA.bills[i], {cnt,byParty,tot}=votesOf(i);
  curBill=b.no;
  let bar='', leg=[];
  ['Y','N','A','X'].forEach(k=>{ if(cnt[k]){ const pct=cnt[k]/tot*100;
    bar+=`<div style="background:${VCLR[k]};flex:${cnt[k]}">${pct>6?VL[k]+' '+cnt[k]:''}</div>`; leg.push(`${VL[k]} ${cnt[k]}`); }});
  let groups='';
  PORDER.filter(p=>byParty[p]).forEach(p=>{
    const arr=byParty[p].sort((a,b)=>'YNAX.'.indexOf(a.v)-'YNAX.'.indexOf(b.v)||a.m.name.localeCompare(b.m.name));
    const chips=arr.map(o=>`<span class="chip v${o.v}" onclick="showMember(${o.m.idx})">${esc(o.m.name)} · ${VL[o.v]}</span>`).join('');
    groups+=`<div class="pgroup"><h3 style="background:${pcolor(p)}"><span>${p}</span><span>${arr.length}명</span></h3><div class="chips">${chips}</div></div>`;
  });
  document.getElementById('sheetH').innerHTML=
    `<div class="htxt"><b>${cmtEmoji(b.cmt)} ${esc(bigTitle(b))}</b><small>${esc(b.name)}</small></div><span class="x" onclick="closeModal()">✕</span>`;
  document.getElementById('sheetB').innerHTML=`
    <div style="margin-bottom:8px"><span class="buzz" title="화제도">🔥 화제도 ${b.buzz}/100</span> ${b.tags.length?tagHTML(b.tags):''}</div>
    ${propHTML(b)}
    <div class="meta"><span>📅 ${b.date||'-'}</span><span>🏛 ${esc(b.cmt||'-')}</span><span>의안번호 ${b.no}</span>
      <span>결과 <b>${esc(b.result||'-')}</b></span><a href="${b.url}" target="_blank" class="billlink">📄 의안 원문 ↗</a>
      <button class="sharebtn" onclick="shareBill()">🔗 공유</button></div>
    ${b.overview ? `<div class="ovw"><div class="ovw-h">📖 한눈에 보기 <span class="ovw-ai">AI 요약 · 원문 확인 권장</span></div><div class="ovw-b">${mdRender(b.overview)}</div></div>` : ''}
    <div class="sumbar">${bar}</div><div class="sumlegend">${leg.join(' · ')} · 기록없음 ${cnt['.']}</div>
    ${b.summary ? `<div class="billsum"><div class="billsum-h">📄 ${esc(b.summarySrc)}</div><div class="billsum-b">${esc(b.summary)}</div></div>` : ''}
    ${groups}`;
  document.getElementById('modal').classList.add('open'); document.body.style.overflow='hidden';
}
function hideModal(){                                       // 화면만 닫음(주소 조작 없음)
  curBill=null;
  document.getElementById('modal').classList.remove('open'); document.body.style.overflow='';
}
function toast(msg){ const t=document.getElementById('toast'); t.textContent=msg; t.classList.add('show'); clearTimeout(t._t); t._t=setTimeout(()=>t.classList.remove('show'),1700); }
function shareBill(){                                       // 고유 URL 외부 공유
  const url=location.href;                                 // 모달 열림 시 주소는 bill/<no>.html
  const b=DATA.bills.find(x=>String(x.no)===String(curBill));
  const title='좌우지간 · '+(b?bigTitle(b):'국회 표결');
  if(navigator.share){ navigator.share({title, url}).catch(()=>{}); }
  else { navigator.clipboard.writeText(url).then(()=>toast('🔗 링크가 복사됐어요')).catch(()=>toast(url)); }
}
function closeModal(){ if(curBill!==null) history.back(); else hideModal(); }   // 사용자가 닫으면 뒤로가기
// 뒤로/앞으로 → 모달 동기화
window.addEventListener('popstate', e=>{
  if(e.state && e.state.bill){ const b=DATA.bills.find(z=>String(z.no)===String(e.state.bill)); if(b) openModal(b.idx); }
  else hideModal();
});
document.addEventListener('keydown',e=>{ if(e.key==='Escape')closeModal(); });

/* ---------- 의원별 ---------- */
let selMem=-1;
function memStats(m){
  const c={Y:0,N:0,A:0,X:0,'.':0};
  for(const ch of m.v) c[ch]++;
  const voted=c.Y+c.N+c.A; const present=voted+c.X;
  return {...c, voted, present, absRate: present? c.X/present*100:0};
}
function renderMemList(){
  const q=document.getElementById('memSearch').value.trim();
  let h='';
  PORDER.forEach(p=>{
    const arr=DATA.members.filter(m=>m.party===p && (!q||m.name.includes(q)));
    if(!arr.length) return;
    arr.sort((a,b)=>a.name.localeCompare(b.name));
    arr.forEach(m=>{ const s=memStats(m);
      h+=`<div class="row ${m.idx===selMem?'sel':''}" onclick="showMember(${m.idx})">
        <span class="pdot" style="background:${pcolor(p)}"></span>
        <span class="name">${esc(m.name)}</span>
        <span class="date">불참 ${s.absRate.toFixed(0)}%</span></div>`;
    });
  });
  document.getElementById('memList').innerHTML=h||'<div class="empty">결과 없음</div>';
}
let memFilter='all';
function showMember(idx){
  hideModal(); switchTab('member'); selMem=idx; renderMemList();
  const m=DATA.members[idx], s=memStats(m);
  let rows='';
  DATA.bills.forEach((b,i)=>{
    const v=m.v[i]; if(v==='.') return;
    if(memFilter!=='all' && v!==memFilter) return;
    rows+=`<tr><td class="date">${b.date||'·'}</td>
      <td>${esc(b.name)}</td>
      <td class="vt"><span class="chip v${v}">${VL[v]}</span></td></tr>`;
  });
  const st=(n,l,c)=>`<div class="stat"><b style="color:${c||'#222'}">${n}</b><small>${l}</small></div>`;
  const fb=k=>`<button class="${memFilter===k?'on':''}" onclick="memFilter='${k}';showMember(${idx})">${k==='all'?'전체':VL[k]}</button>`;
  document.getElementById('memDetail').innerHTML=`
    <h2 class="det">${esc(m.name)} <span class="ptag" style="background:${pcolor(m.party)}">${m.party}</span></h2>
    <div style="margin:12px 0">
      ${st(s.Y,'찬성','#137333')}${st(s.N,'반대','#c5221f')}${st(s.A,'기권','#b06000')}
      ${st(s.X,'불참','#5f6368')}${st(s.absRate.toFixed(1)+'%','불참률','#16213e')}</div>
    <div class="filterbar">${['all','Y','N','A','X'].map(fb).join('')}</div>
    <table class="hist"><tbody>${rows||'<tr><td class="empty">해당 표결 없음</td></tr>'}</tbody></table>`;
}

function esc(s){ return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }
function mdInline(s){     // [글](url) 링크, **굵게**, *기울임*
  return esc(s)
    .replace(/\[(.+?)\]\((https?:\/\/[^)]+)\)/g,'<a href="$2" target="_blank">$1</a>')
    .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
    .replace(/\*(.+?)\*/g,'<em>$1</em>');
}
function mdRender(md){    // 경량 마크다운: ## 제목, 표, 목록, **굵게**, 문단
  const lines=md.split('\n'); let html='', tbl=[];
  const flush=()=>{ if(!tbl.length) return;
    const rows=tbl.filter(r=>!/^\s*\|?[\s|:\-]+\|?\s*$/.test(r));  // 구분선(---) 제거
    html+='<table class="ovwt">'+rows.map((r,ri)=>{
      const cells=r.split('|').map(c=>c.trim()).filter((c,i,a)=>!(i===0&&c==='')&&!(i===a.length-1&&c===''));
      const tag=ri===0?'th':'td';
      return '<tr>'+cells.map(c=>`<${tag}>${mdInline(c)}</${tag}>`).join('')+'</tr>';
    }).join('')+'</table>'; tbl=[]; };
  for(let ln of lines){
    if(ln.includes('|')&&ln.trim().startsWith('|')){ tbl.push(ln); continue; }
    flush();
    const t=ln.trim();
    if(!t) continue;
    if(/^-{3,}$/.test(t)) continue;                          // 수평선 스킵
    else if(/^#{1,6}\s*\S/.test(t)) html+=`<h4>${mdInline(t.replace(/^#{1,6}\s*/,''))}</h4>`;  // #~###### 모두 제목
    else if(/^[-•]\s/.test(t)) html+=`<div class="ovwli">• ${mdInline(t.replace(/^[-•]\s/,''))}</div>`;
    else html+=`<p>${mdInline(t)}</p>`;
  }
  flush();
  return html;
}
renderStats(); renderFeed(); renderMemList();
</script>
</body>
</html>"""

votes = pd.read_parquet("votes_raw_22.parquet")
bills = pd.read_csv("bills_22.csv", dtype=str)

# ── 1. 안건을 시계열순(처리일)으로 정렬 → 인덱스 부여 ───────
bills["dt"] = pd.to_datetime(bills["PROC_DT"], errors="coerce")
bills = bills.sort_values("dt").reset_index(drop=True)
bill_index = {bid: i for i, bid in enumerate(bills["BILL_ID"])}   # BILL_ID → 순번
NB = len(bills)

issues = compute_issues(votes)                                    # 안건별 쟁점 태그·점수
n_issue = sum(1 for x in issues.values() if x["tags"])
print(f"쟁점법안 {n_issue}건 (전체 {NB})")

# 제안이유·주요내용 본문 캐시 (fetch_summaries.py 산출물)
summaries = json.load(open("summaries.json", encoding="utf-8")) if os.path.exists("summaries.json") else {}
# 의안원문 캐시 (제안이유 없는 결의안·동의안 등; fetch_wonmun_batch.py 산출물)
wonmun = json.load(open("wonmun.json", encoding="utf-8")) if os.path.exists("wonmun.json") else {}
# 시민 친화 개요: gemini 배치(다수) 먼저 → overviews.json(수작업 다듬은 데모)이 우선 덮어씀
overviews = json.load(open("overviews_gemini.json", encoding="utf-8")) if os.path.exists("overviews_gemini.json") else {}
if os.path.exists("overviews.json"):
    overviews.update(json.load(open("overviews.json", encoding="utf-8")))   # 수작업판 우선
# 친근한 헤드라인 (gen_headlines.py 산출물)
headlines = json.load(open("headlines.json", encoding="utf-8")) if os.path.exists("headlines.json") else {}
print(f"본문 캐시: 제안이유 {sum(1 for v in summaries.values() if v)}건, "
      f"의안원문 {sum(1 for v in wonmun.values() if v.get('text'))}건")


def bill_body(bid):
    """안건 본문 반환: 제안이유 우선, 없으면 의안원문(출처·절단여부 표시)."""
    s = summaries.get(bid, "")
    if s:
        return {"text": s, "src": "제안이유 및 주요내용"}
    w = wonmun.get(bid)
    if w and w.get("text"):
        suffix = "\n\n…(이하 생략 — 전문은 ‘의안 본문 보기’ 참고)" if w.get("truncated") else ""
        return {"text": w["text"] + suffix, "src": "의안원문"}
    return {"text": "", "src": ""}

# ── 2. 의원 목록(이름·정당) — 정당은 최빈값 ────────────────
mem = (votes.groupby("MONA_CD")
       .agg(name=("HG_NM", "first"),
            party=("POLY_NM", lambda s: s.value_counts().index[0]))
       .reset_index())
mem_index = {m: i for i, m in enumerate(mem["MONA_CD"])}           # MONA_CD → 순번
NM = len(mem)

# ── 화제 점수 + 최초제안자 ──────────────────────────────────
NAME2PARTY = dict(zip(mem["name"], mem["party"]))                 # 의원명 → 정당
HOT = ["계엄", "내란", "특검", "탄핵", "방송", "거부권", "윤석열", "김건희", "위헌", "헌재",
       "비상", "재판관", "국정조사", "증인", "감액", "명태균", "김여사", "양곡", "노란봉투"]

def proposer_of(name):
    """안건명에서 최초제안자와 그 정당 추정. (표시명, 정당) — 정부/위원회/국회의장 포함."""
    if "(정부)" in name: return ("정부", "정부")
    if "(의장)" in name: return ("국회의장", "국회의장")
    m = re.search(r"\(([^)]*?위원장)\)", name)
    if m: return (m.group(1), "위원회")
    m = re.search(r"\(([가-힣]{2,4})의원", name)                  # 대표발의자(첫 의원)
    if m: return (m.group(1), NAME2PARTY.get(m.group(1), ""))
    return ("", "")

def raw_buzz(r):
    """화제도 원점수: 표결 갈등 + 사회적 키워드 + 발의 규모 + 최신성."""
    nm = r.BILL_NAME or ""
    s = issues[r.BILL_ID]["score"]                               # 표결 갈등(0~3.75)
    hot = sum(1.5 for t in HOT if t in nm)                       # 사회적 키워드
    m = re.search(r"등\s*(\d+)\s*인", nm)
    co = math.log1p(int(m.group(1)) if m else 0) * 0.3           # 발의 규모(노이즈 보정 약가중)
    rec = 0.0
    if pd.notna(r.dt) and pd.notna(MAXDT):
        rec = max(0.0, 0.6 * (1 - (MAXDT - r.dt).days / 600))    # 최신성(작게)
    return s + hot + co + rec

MAXDT = bills["dt"].max()
RAW = {r.BILL_ID: raw_buzz(r) for r in bills.itertuples()}
_sorted = sorted(RAW.values())
BUZZ = {bid: round(bisect.bisect_left(_sorted, v) / len(_sorted) * 100)   # 백분위(0~100)
        for bid, v in RAW.items()}
PROP = {r.BILL_ID: proposer_of(r.BILL_NAME or "") for r in bills.itertuples()}

# ── 대시보드 통계 집계 ─────────────────────────────────────
from collections import Counter, defaultdict
def rcat(r):
    r = r or ""
    return "가결" if "가결" in r else ("부결" if "부결" in r else "기타")
NAME2MEMIDX = {n: i for i, n in enumerate(mem["name"])}

result = Counter(rcat(r.PROC_RESULT_CD) for r in bills.itertuples())
bymonth = defaultdict(lambda: {"n": 0, "pass": 0, "fail": 0})
for r in bills.itertuples():
    if pd.isna(r.dt): continue
    k = r.dt.strftime("%Y-%m"); bymonth[k]["n"] += 1
    c = rcat(r.PROC_RESULT_CD)
    if c == "가결": bymonth[k]["pass"] += 1
    elif c == "부결": bymonth[k]["fail"] += 1
months = [{"m": k, **v} for k, v in sorted(bymonth.items())]
bycmt = [{"c": c, "n": n} for c, n in Counter((r.CURR_COMMITTEE or "기타") for r in bills.itertuples()).most_common(12)]
rejected = [{"idx": bill_index[r.BILL_ID], "head": headlines.get(r.BILL_ID) or r.BILL_NAME,
             "date": (r.dt.strftime("%Y-%m-%d") if pd.notna(r.dt) else "")}
            for r in bills.itertuples() if rcat(r.PROC_RESULT_CD) == "부결"]
pc = Counter(); pparty = {}; ppass = defaultdict(lambda: [0, 0])
for r in bills.itertuples():
    nm, party = PROP[r.BILL_ID]
    if party in ("정부", "위원회", "국회의장") or not nm: continue
    pc[nm] += 1; pparty[nm] = party
    ppass[party][0] += 1
    if rcat(r.PROC_RESULT_CD) == "가결": ppass[party][1] += 1
topprop = [{"name": n, "party": pparty.get(n, ""), "n": c, "midx": NAME2MEMIDX.get(n, -1)} for n, c in pc.most_common(12)]
bypartyprop = sorted([{"party": p, "n": v[0], "pass": v[1]} for p, v in ppass.items()], key=lambda x: -x["n"])
topbuzz = sorted(((BUZZ[r.BILL_ID], bill_index[r.BILL_ID], headlines.get(r.BILL_ID) or r.BILL_NAME)
                  for r in bills.itertuples()), reverse=True)[:8]
topbuzz = [{"idx": i, "head": h, "buzz": z} for z, i, h in topbuzz]

# 월별 다선 그래프: 전체 + 상위 8 위원회의 월별 건수
mlabels = [m["m"] for m in months]
midx = {m: i for i, m in enumerate(mlabels)}
top_cmts = [c["c"] for c in bycmt[:8]]
series = {c: [0] * len(mlabels) for c in top_cmts}
for r in bills.itertuples():
    if pd.isna(r.dt): continue
    c = r.CURR_COMMITTEE or "기타"
    if c in series:
        series[c][midx[r.dt.strftime("%Y-%m")]] += 1
month_series = {"labels": mlabels, "total": [m["n"] for m in months],
                "cmts": [{"name": c, "data": series[c]} for c in top_cmts]}

# 위원회별 안건 목록(캐러셀용, 화제순 상위 24) / 의원별 발의 안건
cmt_bucket = defaultdict(list); prop_bucket = defaultdict(list)
for r in bills.itertuples():
    cmt_bucket[r.CURR_COMMITTEE or "기타"].append((BUZZ[r.BILL_ID], bill_index[r.BILL_ID]))
    nm, party = PROP[r.BILL_ID]
    if party not in ("정부", "위원회", "국회의장") and nm:
        prop_bucket[nm].append((BUZZ[r.BILL_ID], bill_index[r.BILL_ID]))
cmt_bills = {c["c"]: [i for _, i in sorted(cmt_bucket[c["c"]], reverse=True)[:24]] for c in bycmt}
prop_bills = {p["name"]: [i for _, i in sorted(prop_bucket[p["name"]], reverse=True)[:24]] for p in topprop}

STATS = {"total": NB, "result": dict(result), "months": months, "bycmt": bycmt,
         "rejected": rejected, "topprop": topprop, "bypartyprop": bypartyprop, "topbuzz": topbuzz,
         "monthSeries": month_series, "cmtBills": cmt_bills, "propBills": prop_bills,
         "ovwCount": sum(1 for x in overviews.values() if (x or {}).get("text"))}

# ── 3. 표결 행렬 만들기: 각 의원당 길이 NB 문자열 ──────────
CODE = {"찬성": "Y", "반대": "N", "기권": "A", "불참": "X"}        # 1글자 코드
matrix = [["."] * NB for _ in range(NM)]                          # 기본 '.'(기록없음)
for mc, bid, res in zip(votes["MONA_CD"], votes["BILL_ID"], votes["RESULT_VOTE_MOD"]):
    matrix[mem_index[mc]][bill_index[bid]] = CODE.get(res, ".")   # 해당 칸 채움
mem_votes = ["".join(row) for row in matrix]                      # 행 → 문자열

# ── 4. JSON 페이로드 구성 ──────────────────────────────────
data = {
    "bills": [                                                    # 안건(시계열순)
        {"no": r.BILL_NO, "name": r.BILL_NAME,
         "date": (r.dt.strftime("%Y-%m-%d") if pd.notna(r.dt) else ""),
         "cmt": (r.CURR_COMMITTEE if pd.notna(r.CURR_COMMITTEE) else ""),
         "result": (r.PROC_RESULT_CD if pd.notna(r.PROC_RESULT_CD) else ""),
         "url": f"https://likms.assembly.go.kr/bill/billDetail.do?billId={r.BILL_ID}",  # 공식 상세페이지
         "summary": bill_body(r.BILL_ID)["text"],                 # 본문(제안이유 또는 의안원문)
         "summarySrc": bill_body(r.BILL_ID)["src"],               # 본문 출처 라벨
         "overview": (overviews.get(r.BILL_ID, {}) or {}).get("text", ""),  # AI 시민 개요
         "headline": headlines.get(r.BILL_ID, ""),                # 친근 헤드라인
         "tags": issues[r.BILL_ID]["tags"],                       # 쟁점 태그
         "score": issues[r.BILL_ID]["score"],                     # 쟁점 점수
         "buzz": BUZZ[r.BILL_ID],                                 # 화제도(0~100)
         "prop": PROP[r.BILL_ID][0],                              # 최초제안자
         "propParty": PROP[r.BILL_ID][1]}                         # 제안자 정당
        for r in bills.itertuples()
    ],
    "members": [                                                  # 의원 + 표결 문자열
        {"name": n, "party": p, "v": v}
        for n, p, v in zip(mem["name"], mem["party"], mem_votes)
    ],
    "stats": STATS,                                              # 대시보드 통계
}
payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

# ── 5. HTML 작성 (템플릿에 JSON 주입) ──────────────────────
html = TEMPLATE.replace("/*__DATA__*/", payload)
with open("assembly_votes.html", "w", encoding="utf-8") as f:
    f.write(html)
print(f"생성 완료: assembly_votes.html  (안건 {NB}, 의원 {NM}, 용량 약 {len(html)//1024}KB)")
