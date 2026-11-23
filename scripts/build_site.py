# -*- coding: utf-8 -*-
"""우아메뉴 정적 사이트 생성기.
입력: data/list.json.gz(음식점 목록: 이름·주소·좌표) · data/details/*.json.gz(대표메뉴·취급메뉴·영업시간·휴무·주차 등)
출력: _site/  (식당 상세, 지역·메뉴 허브, 안내, 검색 인덱스, sitemap)
상세가 아직 없는 식당은 만들지 않는다(상세는 매일 예산만큼 쌓임). 이미지는 쓰지 않는다(KTO 이미지 라이선스).
"""
import collections, gzip, html as ihtml, json, re, shutil, sys
from datetime import datetime, timedelta, timezone

from common import *  # noqa

sys.stdout.reconfigure(encoding="utf-8")
DATA = ROOT / "data"
TODAY = (datetime.now(timezone.utc) + timedelta(hours=9)).date()

SHORT = {"서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천", "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종",
         "경기도": "경기", "강원특별자치도": "강원", "강원도": "강원", "충청북도": "충북", "충청남도": "충남", "전북특별자치도": "전북", "전라북도": "전북", "전라남도": "전남",
         "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주", "전남광주통합특별시": "전남광주"}

# 대표메뉴(없으면 상호·취급메뉴) 키워드로 묶는 메뉴 그룹 — 앞에서부터 먼저 맞는 그룹. (이름, 정규식)
GROUPS = [
    ("치킨", r"치킨|닭강정|통닭|후라이드|파닭"),
    ("피자", r"피자"),
    ("햄버거", r"햄버거|버거"),
    ("분식", r"떡볶이|김밥|순대$|튀김|분식|어묵|오뎅|라볶이"),
    ("중식", r"짜장|짬뽕|탕수육|마라|중화|중국|딤섬|깐풍|양장피|유린기|팔보채|짜짱"),
    ("일식", r"초밥|스시|우동|라멘|라면집|돈까스|돈가스|카츠|사시미|일식|가츠|소바|오마카세|규동|텐동"),
    ("양식", r"파스타|스테이크|스파게티|리조또|리조토|브런치|양식|오므라이스|샐러드|함박|그라탕|코스요리"),
    ("냉면·막국수", r"냉면|막국수|밀면|메밀|콩국수"),
    ("칼국수·수제비", r"칼국수|수제비|국수|칼제비|면요리|우동"),
    ("족발·보쌈", r"족발|보쌈|수육"),
    ("닭요리", r"닭|삼계|백숙"),
    ("회·해산물", r"회|횟|해물|생선|매운탕|조개|꽃게|게장|대게|아귀|낙지|오징어|새우|전복|장어|굴|복어|갈치|고등어|조림|해산|문어|쭈꾸미|주꾸미|낚지|꼼장어|참치|대구탕|추어|물회|랍스터|킹크랩|대하"),
    ("고기구이", r"삼겹|갈비|목살|불고기|소고기|한우|등심|오리|훈제|곱창|막창|대창|돼지|흑돼지|양고기|구이|숯불|항정|돼지갈비|차돌|육회|생고기|양꼬치|꼬치"),
    ("국밥·탕", r"국밥|설렁탕|곰탕|갈비탕|해장국|순대국|감자탕|육개장|탕$|탕밥|순대|뼈해장|국$"),
    ("샤브·전골", r"샤브|전골|훠궈|스키야키|나베"),
    ("찌개·백반·한정식", r"찌개|백반|한정식|정식|비빔밥|순두부|된장|청국장|쌈밥|가정식|밥상|보리밥|죽$|죽집|솥밥|덮밥|두부|밥$|한식"),
    ("전·주점", r"전$|파전|막걸리|주점|호프|술집|포차|이자카야|맥주|전집"),
    ("뷔페", r"뷔페"),
    ("아시안·세계요리", r"쌀국수|베트남|태국|인도|카레|커리|멕시칸|타코|케밥|팟타이|네팔|터키|브라질|할랄|케이준|아시안"),
    ("빵·베이커리", r"빵|베이커리|제과|케이크|도넛|도너츠|와플|크로플|쿠키|마카롱|바게트|샌드위치|토스트"),
    ("카페·커피", r"커피|아메리카노|라떼|카페|에스프레소|티$|차$|음료|디저트|빙수|주스|스무디|에이드|아이스크림|전통찻집|콜드브루"),
]
GRE = [(n, re.compile(r)) for n, r in GROUPS]


def un(s):
    return ihtml.unescape(ihtml.unescape(s or ""))


def plain(s):
    s = un(s)
    s = re.sub(r"<br\s*/?>|</p>|\\n", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"[ \t ]+", " ", s.replace("\r", ""))
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def one(s):
    return re.sub(r"\s+", " ", plain(s)).strip()


def hours_text(s):
    t = plain(s)
    t = re.sub(r"^\s*-\s*", "", t)
    t = re.sub(r"\s*-\s+", " / ", t)
    t = re.sub(r"\s*\n\s*", " / ", t)
    return re.sub(r"\s+", " ", t).strip(" /")


def cut(s, n):
    return s if len(s) <= n else s[:n].rstrip(" ,/·") + "…"


def mgroup(fm, name, tm):
    for src in (fm, name, tm):
        for g, r in GRE:
            if src and r.search(src):
                return g
    return ""


def region_of(addr):
    t = (addr or "").split()
    if not t:
        return "", ""
    sido = SHORT.get(t[0], "")
    if not sido:
        return "", ""
    if sido == "세종":
        return sido, "세종시"
    sgg = t[1] if len(t) > 1 and re.search(r"(시|군|구)$", t[1]) else ""
    return sido, sgg


def load():
    rows = json.loads(gzip.open(DATA / "list.json.gz", "rt", encoding="utf-8").read())
    det = {}
    for p in (DATA / "details").glob("*.json.gz"):
        det.update(json.loads(gzip.open(p, "rt", encoding="utf-8").read()))
    ps = []
    for r in rows:
        d = det.get(r["id"])
        if not d:
            continue
        fm = one(d.get("fm"))
        tm = one(d.get("tm"))
        ot = hours_text(d.get("ot"))
        name = un(r["t"]).strip()
        if not name or not (fm or tm) or not ot:
            continue
        sido, sgg = region_of(r["a"])
        if not sido:
            continue
        menus = [m.strip(" .") for m in re.split(r"\s*/\s*|,|·", re.sub(r"\s*등$", "", tm)) if m.strip(" .")][:10]
        ps.append(dict(id=r["id"], name=name, addr=(r["a"] + (" " + r["a2"] if r["a2"] else "")).strip(), sido=sido, sgg=sgg, x=r["x"], y=r["y"], mod=r["mod"],
                       fm=fm, menus=menus, tm=tm, ot=ot, rd=one(d.get("rd")), pk=one(d.get("pk")), pa=one(d.get("pa")), cc=one(d.get("cc")), od=one(d.get("od")),
                       grp=mgroup(fm, name, tm)))
    return ps, len(rows)


def plink(p):
    return '<a href="/place/%s/">%s</a>' % (p["id"], esc(p["name"]))


def ptable(L, cap=150, region=True):
    L = L[:cap]
    head = "<tr><th>식당</th>%s<th>대표메뉴</th><th>영업시간</th></tr>" % ("<th>지역</th>" if region else "")
    rows = []
    for p in L:
        rows.append("<tr><td>%s</td>%s<td>%s</td><td>%s</td></tr>" % (plink(p), ("<td>%s</td>" % esc((p["sido"] + " " + p["sgg"]).strip())) if region else "",
                                                                       esc(cut(p["fm"] or (p["menus"][0] if p["menus"] else "-"), 24)), esc(cut(p["ot"], 46))))
    return '<div class="tbl-wrap"><table class="tbl">%s%s</table></div>' % (head, "".join(rows))


def stat(L, what="식당"):
    gc = collections.Counter(p["grp"] for p in L if p["grp"])
    s = "대표메뉴·영업시간이 등록된 %s <b>%d곳</b>입니다." % (what, len(L))
    if gc:
        s += " " + ", ".join("%s %d곳" % (k, v) for k, v in gc.most_common(4)) + " 순으로 많습니다."
    return '<p class="lead">%s</p>' % s


def hub(path, h1, sub, L, extra="", cap=150, title=None, desc=None, crumbs=None, prio="0.7", region=True, faq=None):
    body = ['<div class="page-head"><h1>%s</h1><p>%s</p></div>' % (esc(h1), esc(sub)), stat(L), ad(), extra, '<h2 class="group-title">식당 목록</h2>', ptable(L, cap, region)]
    if len(L) > cap:
        body.append('<p class="note">식당이 많아 %d곳만 표시했습니다. 지역·메뉴별 페이지에서 좁혀 보세요.</p>' % cap)
    write(path, layout(path, title or h1, desc or sub, "\n".join(b for b in body if b), faq, crumbs or [("홈", "/")], coupang=True), prio)


def page_place(p, by_sgg, by_sg, hubs_ok):
    region = (p["sido"] + " " + p["sgg"]).strip()
    lead = ["<b>%s</b>은(는) %s에 있는 음식점으로, 대표메뉴는 <b>%s</b>입니다." % (esc(p["name"]), esc(region), esc(p["fm"] or (p["menus"][0] if p["menus"] else "")))]
    lead.append("영업시간은 %s입니다." % esc(cut(p["ot"], 120)))
    if p["rd"]:
        lead.append("휴무일은 %s입니다." % esc(cut(p["rd"], 80)))
    if p["pk"]:
        lead.append("주차 항목에는 '%s'라고 등록돼 있습니다." % esc(cut(p["pk"], 40)))
    rows = [("대표메뉴", p["fm"]), ("취급메뉴", " / ".join(p["menus"])), ("영업시간", p["ot"]), ("휴무일", p["rd"]), ("주차", p["pk"]), ("포장", p["pa"]), ("신용카드", p["cc"]),
            ("개업일", p["od"]), ("주소", p["addr"])]
    tbl = '<div class="tbl-wrap"><table class="tbl">%s</table></div>' % "".join("<tr><th>%s</th><td>%s</td></tr>" % (a, esc(b)) for a, b in rows if b)
    body = ['<div class="page-head"><h1>%s</h1><p>%s</p></div>' % (esc(p["name"]), esc(" · ".join(x for x in (region, p["grp"]) if x))), '<p class="lead">%s</p>' % " ".join(lead), ad(), tbl]
    if len(p["menus"]) > 1:
        body.append('<h2 class="group-title">등록된 취급메뉴</h2><div class="chips">%s</div>' % "".join('<span class="chip">%s</span>' % esc(m) for m in p["menus"]))
    if p["x"] and p["y"]:
        body.append('<p><a class="btn" href="https://map.kakao.com/link/map/%s,%s,%s">🗺️ 지도에서 위치 보기</a></p>' % (urllib.parse.quote(p["name"][:40]), p["y"], p["x"]))
    body.append('<div class="note-box">식당 정보는 한국관광공사 TourAPI(공공데이터포털) 기준이며, 영업시간·휴무·메뉴·가격은 바뀔 수 있습니다. 방문 전에 매장에 확인하세요.</div>')
    # 같은 지역 같은 메뉴 → 같은 지역 다른 식당
    sib = []
    if p["grp"]:
        sib = [o for o in by_sg.get((p["sido"], p["sgg"], p["grp"]), []) if o is not p][:8]
    if len(sib) < 8:
        sib += [o for o in by_sgg.get((p["sido"], p["sgg"]), []) if o is not p and o not in sib][:8 - len(sib)]
    if sib:
        body.append('<h2 class="group-title">%s 다른 식당 <small>%s</small></h2>' % ("같은 지역·메뉴" if p["grp"] else "같은 지역", esc(region)))
        body.append(ptable(sib, 8, False))
    chips = []
    if ("region", p["sido"]) in hubs_ok:
        chips.append('<a class="chip" href="/region/%s/">%s 식당</a>' % (q(p["sido"]), esc(p["sido"])))
    if p["sgg"] and ("sgg", p["sido"], p["sgg"]) in hubs_ok:
        chips.append('<a class="chip" href="/region/%s/%s/">%s %s 식당</a>' % (q(p["sido"]), q(p["sgg"]), esc(p["sido"]), esc(p["sgg"])))
    if p["grp"] and ("menu", p["grp"]) in hubs_ok:
        chips.append('<a class="chip" href="/menu/%s/">%s 맛집</a>' % (q(p["grp"]), esc(p["grp"])))
    if p["grp"] and ("ms", p["grp"], p["sido"]) in hubs_ok:
        chips.append('<a class="chip" href="/menu/%s/%s/">%s %s 맛집</a>' % (q(p["grp"]), q(p["sido"]), esc(p["sido"]), esc(p["grp"])))
    if chips:
        body.append('<div class="chips">%s</div>' % "".join(chips))
    faq = [("%s의 대표메뉴는 무엇인가요?" % p["name"], "공공데이터에는 대표메뉴가 %s로 등록돼 있습니다.%s" % (p["fm"] or p["menus"][0], (" 그 밖에 %s 등을 취급한다고 안내돼 있습니다." % ", ".join(p["menus"][:4])) if len(p["menus"]) > 1 else "")),
           ("%s의 영업시간과 휴무일은 언제인가요?" % p["name"], "영업시간은 %s%s입니다. 시기별로 바뀔 수 있으니 방문 전에 확인하세요." % (cut(p["ot"], 140), (", 휴무일은 %s" % cut(p["rd"], 60)) if p["rd"] else ""))]
    extra_q = []
    if p["pk"]:
        extra_q.append("주차")
    if p["pa"]:
        extra_q.append("포장")
    if extra_q:
        faq.append(("%s에서 %s이(가) 가능한가요?" % (p["name"], "·".join(extra_q)), "공공데이터에는 " + ", ".join(("주차 '%s'" % cut(p["pk"], 40)) if k == "주차" else ("포장 '%s'" % cut(p["pa"], 40)) for k in extra_q) + "라고 등록돼 있습니다. 매장 사정에 따라 다를 수 있습니다."))
    crumbs = [("홈", "/"), (p["sido"], "/region/%s/" % p["sido"])] + [((p["name"][:26] + "…") if len(p["name"]) > 26 else p["name"], "/place/%s/" % p["id"])]
    ld = [{"@context": "https://schema.org", "@type": "Restaurant", "name": p["name"], "address": p["addr"],
           "servesCuisine": p["grp"] or p["fm"], "openingHours": p["ot"][:200]}]
    if p["x"] and p["y"]:
        ld[0]["geo"] = {"@type": "GeoCoordinates", "latitude": p["y"], "longitude": p["x"]}
    title = "%s 대표메뉴·영업시간 - %s" % (p["name"], region)
    desc = "%s(%s) 대표메뉴 %s, 영업시간 %s%s." % (p["name"], region, p["fm"] or p["menus"][0], cut(p["ot"], 50), (", 휴무 " + cut(p["rd"], 20)) if p["rd"] else "")
    write("/place/%s/" % p["id"], layout("/place/%s/" % p["id"], title, desc, "\n".join(body), faq, crumbs, "article", ld, coupang=True), "0.6")


def build():
    ps, total_rows = load()
    print("식당", len(ps), "/ 목록", total_rows)
    ps.sort(key=lambda p: (-int(p["mod"] or 0), p["id"]))
    by_sido, by_sgg, by_g, by_sg, by_gs = (collections.defaultdict(list) for _ in range(5))
    for p in ps:
        by_sido[p["sido"]].append(p)
        if p["sgg"]:
            by_sgg[(p["sido"], p["sgg"])].append(p)
        if p["grp"]:
            by_g[p["grp"]].append(p)
            by_gs[(p["grp"], p["sido"])].append(p)
            if p["sgg"]:
                by_sg[(p["sido"], p["sgg"], p["grp"])].append(p)
    hubs_ok = {("region", s) for s in by_sido} | {("sgg", s, g) for (s, g), L in by_sgg.items() if len(L) >= 3} \
        | {("menu", g) for g, L in by_g.items() if len(L) >= 5} | {("ms", g, s) for (g, s), L in by_gs.items() if len(L) >= 3} \
        | {("msg", s, g, m) for (s, g, m), L in by_sg.items() if len(L) >= 3}
    OUT.mkdir(parents=True, exist_ok=True)
    for ch in OUT.iterdir():
        shutil.rmtree(ch) if ch.is_dir() else ch.unlink()
    for p in ps:
        page_place(p, by_sgg, by_sg, hubs_ok)
    # 지역
    for s, L in by_sido.items():
        gc = collections.Counter(p["sgg"] for p in L if p["sgg"])
        mc = collections.Counter(p["grp"] for p in L if p["grp"])
        extra = ""
        if mc:
            extra += '<h2 class="group-title">메뉴별</h2><div class="chips">%s</div>' % "".join(
                ('<a class="chip" href="/menu/%s/%s/">%s <small>%d</small></a>' % (q(m), q(s), esc(m), n)) if ("ms", m, s) in hubs_ok else '<span class="chip">%s <small>%d</small></span>' % (esc(m), n) for m, n in mc.most_common())
        if gc:
            extra += '<h2 class="group-title">시군구별</h2><div class="chips">%s</div>' % "".join(
                ('<a class="chip" href="/region/%s/%s/">%s <small>%d</small></a>' % (q(s), q(g), esc(g), n)) if n >= 3 else '<span class="chip">%s <small>%d</small></span>' % (esc(g), n) for g, n in gc.most_common(80))
        hub("/region/%s/" % s, "%s 식당 %d곳 - 대표메뉴·영업시간" % (s, len(L)), "지역 식당의 대표메뉴와 영업시간", L, extra, 150, "%s 식당 %d곳 - 대표메뉴·영업시간·휴무일" % (s, len(L)),
            "%s 식당 %d곳의 대표메뉴, 영업시간, 휴무일, 주차 정보를 한눈에 정리했습니다." % (s, len(L)), [("홈", "/"), ("지역별", "/region/"), (s, "/region/%s/" % s)], "0.8",
            faq=[("%s 식당은 몇 곳이 등록돼 있나요?" % s, "한국관광공사 공공데이터에 대표메뉴·영업시간이 등록된 식당 기준 %d곳입니다." % len(L))])
    for (s, g), L in by_sgg.items():
        if len(L) >= 3:
            mc = collections.Counter(p["grp"] for p in L if p["grp"])
            extra = ""
            if mc:
                extra = '<h2 class="group-title">메뉴별</h2><div class="chips">%s</div>' % "".join(
                    ('<a class="chip" href="/menu/%s/%s/%s/">%s <small>%d</small></a>' % (q(m), q(s), q(g), esc(m), n)) if ("msg", s, g, m) in hubs_ok else '<span class="chip">%s <small>%d</small></span>' % (esc(m), n) for m, n in mc.most_common())
            hub("/region/%s/%s/" % (s, g), "%s %s 식당 %d곳" % (s, g, len(L)), "대표메뉴와 영업시간", L, extra, 150, "%s %s 식당 %d곳 - 대표메뉴·영업시간" % (s, g, len(L)),
                "%s %s의 식당 %d곳의 대표메뉴·영업시간·휴무일을 정리했습니다." % (s, g, len(L)), [("홈", "/"), (s, "/region/%s/" % s), (g, "/region/%s/%s/" % (s, g))], "0.6", region=False)
    for (s, g, m), L in by_sg.items():
        if len(L) >= 3:
            hub("/menu/%s/%s/%s/" % (m, s, g), "%s %s %s 맛집 %d곳" % (s, g, m, len(L)), "대표메뉴와 영업시간", L, "", 100, "%s %s %s 맛집 %d곳 - 영업시간·대표메뉴" % (s, g, m, len(L)),
                "%s %s의 %s 식당 %d곳의 대표메뉴와 영업시간을 정리했습니다." % (s, g, m, len(L)), [("홈", "/"), (m, "/menu/%s/" % m), (s, "/menu/%s/%s/" % (m, s)), (g, "/menu/%s/%s/%s/" % (m, s, g))], "0.5", region=False)
    cards = "".join('<a class="card" href="/region/%s/"><b>%s</b><span>%d곳</span></a>' % (q(s), esc(s), len(L)) for s, L in sorted(by_sido.items(), key=lambda t: -len(t[1])))
    write("/region/", layout("/region/", "지역별 식당", "시도별 식당의 대표메뉴와 영업시간을 확인하세요.", '<div class="page-head"><h1>지역별 식당</h1></div>' + ad() + '<div class="card-grid">%s</div>' % cards, None, [("홈", "/"), ("지역별", "/region/")]), "0.8")
    # 메뉴
    for g, L in by_g.items():
        if len(L) < 5:
            continue
        sc = collections.Counter(p["sido"] for p in L)
        extra = '<h2 class="group-title">지역별</h2><div class="chips">%s</div>' % "".join(
            ('<a class="chip" href="/menu/%s/%s/">%s <small>%d</small></a>' % (q(g), q(s), esc(s), n)) if n >= 3 else '<span class="chip">%s <small>%d</small></span>' % (esc(s), n) for s, n in sc.most_common())
        hub("/menu/%s/" % g, "%s 맛집 %d곳 - 지역별 영업시간" % (g, len(L)), "대표메뉴가 %s인 식당" % g, L, extra, 150, "%s 맛집 %d곳 - 지역별 대표메뉴·영업시간" % (g, len(L)),
            "%s 식당 %d곳을 지역별로 정리했습니다. 대표메뉴, 영업시간, 휴무일, 주차 정보를 확인하세요." % (g, len(L)), [("홈", "/"), ("메뉴별", "/menu/"), (g, "/menu/%s/" % g)], "0.8",
            faq=[("%s 맛집은 어떻게 골랐나요?" % g, "한국관광공사 공공데이터에 등록된 대표메뉴·취급메뉴·상호를 기준으로 분류했습니다. 순위나 평점이 아니라 등록 정보입니다.")])
        for s, n in sc.items():
            if n >= 3:
                L2 = by_gs[(g, s)]
                hub("/menu/%s/%s/" % (g, s), "%s %s 맛집 %d곳" % (s, g, len(L2)), "대표메뉴와 영업시간", L2, "", 150, "%s %s 맛집 %d곳 - 영업시간·대표메뉴" % (s, g, len(L2)),
                    "%s의 %s 식당 %d곳의 대표메뉴·영업시간·휴무일을 정리했습니다." % (s, g, len(L2)), [("홈", "/"), (g, "/menu/%s/" % g), (s, "/menu/%s/%s/" % (g, s))], "0.6", region=False)
    cards = "".join('<a class="card" href="/menu/%s/"><b>%s</b><span>%d곳</span></a>' % (q(g), esc(g), len(L)) for g, L in sorted(by_g.items(), key=lambda t: -len(t[1])) if len(L) >= 5)
    write("/menu/", layout("/menu/", "메뉴별 식당", "치킨·냉면·칼국수·고기구이 등 대표메뉴별로 식당을 찾으세요.", '<div class="page-head"><h1>메뉴별 식당</h1></div>' + ad() + '<div class="card-grid">%s</div>' % cards, None, [("홈", "/"), ("메뉴별", "/menu/")]), "0.8")
    # 홈
    body = ['<div class="hero"><h1>대표메뉴로 찾는 식당</h1><p>한국관광공사 공공데이터의 식당 %s곳을 대표메뉴·영업시간·휴무일로 찾으세요</p>'
            '<div class="today-box"><div><small>등록 식당</small><b>%s곳</b></div><div><small>메뉴 분류</small><b>%d개</b></div><div><small>시군구</small><b>%d곳</b></div></div></div>' % (
                "{:,}".format(len(ps)), "{:,}".format(len(ps)), sum(1 for L in by_g.values() if len(L) >= 5), len(by_sgg)),
            '<div class="search-box"><input id="q" type="search" placeholder="식당 검색 (예: 속초 막국수, 부산 돼지국밥)" autocomplete="off"><div id="sr" class="sr-list"></div></div>', ad(),
            '<h2 class="group-title">메뉴별</h2><div class="card-grid">%s</div>' % cards,
            '<h2 class="group-title">지역별</h2><div class="card-grid">%s</div>' % "".join('<a class="card" href="/region/%s/"><b>%s</b><span>%d곳</span></a>' % (q(s), esc(s), len(L)) for s, L in sorted(by_sido.items(), key=lambda t: -len(t[1]))),
            '<h2 class="group-title">최근 갱신된 식당</h2>', ptable(ps[:10], 10), '<script src="/assets/js/search.js"></script>']
    faq = [("식당 정보는 어디서 가져왔나요?", "한국관광공사가 공공데이터포털에 공개한 TourAPI 음식점 정보를 정리했습니다. 대표메뉴·영업시간·휴무일은 사업자가 등록한 값입니다."),
           ("맛집 순위인가요?", "아닙니다. 평점·후기·순위 없이 등록된 대표메뉴와 영업 정보만 보여줍니다. 방문 전에 영업 여부를 확인하세요."),
           ("메뉴 분류는 어떻게 했나요?", "대표메뉴·상호·취급메뉴 문구에서 키워드를 찾아 치킨·냉면·칼국수·고기구이 등으로 묶었습니다. 일부는 분류되지 않을 수 있습니다.")]
    ld = [{"@context": "https://schema.org", "@type": "WebSite", "name": "우아메뉴", "url": BASE + "/", "potentialAction": {"@type": "SearchAction", "target": BASE + "/?q={q}", "query-input": "required name=q"}}]
    write("/", layout("/", "대표메뉴로 찾는 식당 - 영업시간·휴무일 %s곳 | 우아메뉴" % "{:,}".format(len(ps)), "한국관광공사 공공데이터의 식당 %s곳을 대표메뉴·영업시간·휴무일·주차 정보로 찾으세요." % "{:,}".format(len(ps)), "\n".join(body), faq, None, "website", ld), "1.0")
    idx = [[p["name"], "/place/%s/" % p["id"], p["fm"] or (p["menus"][0] if p["menus"] else ""), (p["sido"] + " " + p["sgg"]).strip(), ""] for p in ps]
    (OUT / "search_index.json").write_text(json.dumps(idx, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    pages_static()
    finish()
    uncls = sum(1 for p in ps if not p["grp"])
    print("메뉴 미분류 %d (%.1f%%)" % (uncls, 100 * uncls / max(1, len(ps))))


def pages_static():
    body = ['<div class="page-head"><h1>식당 찾는 방법과 이용 안내</h1></div>', ad(),
            '<h2 class="group-title">1. 식당 찾기</h2><ol class="lead"><li><a href="/menu/">메뉴별</a> 또는 <a href="/region/">지역별</a>로 후보를 좁힙니다.</li><li>식당 상세에서 대표메뉴·영업시간·휴무일·주차 가능 여부를 확인합니다.</li><li>지도 버튼으로 위치를 보고, 방문 전에 매장에 영업 여부를 확인합니다.</li></ol>',
            '<h2 class="group-title">2. 정보 읽는 법</h2><ul class="lead"><li><b>대표메뉴</b>는 사업자가 공공데이터에 등록한 대표 메뉴이며, 인기 순위가 아닙니다.</li><li><b>영업시간·휴무일</b>은 등록 당시 기준입니다. 명절·계절에 따라 달라질 수 있습니다.</li><li><b>메뉴 분류</b>는 키워드로 자동 분류한 것이라 일부는 실제와 다를 수 있습니다.</li></ul>',
            '<div class="note-box">이 사이트는 한국관광공사 공개 데이터를 정리한 참고용이며 매장의 현재 영업 상태를 보장하지 않습니다. 동네 식당 전체는 <a href="https://wooasikdang.wooahouse.com">우아식당</a>에서 볼 수 있습니다.</div>']
    write("/guide/", layout("/guide/", "식당 찾는 방법과 이용 안내", "메뉴·지역별로 식당을 찾고 대표메뉴·영업시간 정보를 읽는 방법을 정리했습니다.", "\n".join(body), None, [("홈", "/"), ("이용 안내", "/guide/")]), "0.4")
    body = ['<div class="page-head"><h1>데이터 설명</h1></div>', '<p class="lead">우아메뉴는 한국관광공사 <b>TourAPI 국문 관광정보</b>(공공데이터포털)의 음식점(콘텐츠 유형 39) 정보를 정리합니다. 대표메뉴·취급메뉴·영업시간·휴무일·주차·포장·카드 결제 여부는 사업자가 등록한 값이며, 매일 일부씩 수집해 페이지를 늘려 갑니다. 대표메뉴나 영업시간이 비어 있는 식당은 싣지 않았고, 사진은 사용하지 않습니다.</p>']
    write("/about/", layout("/about/", "데이터 설명", "우아메뉴가 사용하는 한국관광공사 TourAPI 음식점 데이터와 정리 방법을 설명합니다.", "\n".join(body), None, [("홈", "/"), ("데이터 설명", "/about/")]), "0.3")
    body = ['<div class="page-head"><h1>개인정보처리방침</h1></div>', '<p class="lead">우아메뉴는 회원가입·로그인 없이 이용하며 개인정보를 수집하지 않습니다. 사이트 개선을 위해 Google Analytics를 사용하고, 광고 게재를 위해 Google AdSense와 쿠팡 파트너스를 사용하며 이 과정에서 쿠키가 사용될 수 있습니다.</p>']
    write("/privacy/", layout("/privacy/", "개인정보처리방침", "우아메뉴 개인정보처리방침", "\n".join(body), None, [("홈", "/"), ("개인정보처리방침", "/privacy/")]), sitemap=False)


def finish():
    shutil.copytree(ROOT / "assets", OUT / "assets")
    for nf in ROOT.glob("naver*.html"):
        shutil.copy(nf, OUT / nf.name)
    today = TODAY.isoformat()
    urls = "".join("<url><loc>%s%s</loc><lastmod>%s</lastmod><priority>%s</priority></url>" % (BASE, q(p), today, pr) for p, pr in WRITTEN)
    (OUT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">%s</urlset>\n' % urls, encoding="utf-8")
    (OUT / "robots.txt").write_text("User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % BASE, encoding="utf-8")
    (OUT / "CNAME").write_text("wooamenu.wooahouse.com\n", encoding="utf-8")
    nf = layout("/404.html", "페이지를 찾을 수 없습니다", "요청한 페이지를 찾을 수 없습니다.", '<div class="page-head"><h1>페이지를 찾을 수 없습니다</h1></div><div class="chips"><a class="chip" href="/">홈으로</a><a class="chip" href="/menu/">메뉴별</a><a class="chip" href="/region/">지역별</a></div>', None, None, noindex=True)
    (OUT / "404.html").write_text(nf, encoding="utf-8")
    print("페이지", len(WRITTEN), "(sitemap)")


if __name__ == "__main__":
    build()
