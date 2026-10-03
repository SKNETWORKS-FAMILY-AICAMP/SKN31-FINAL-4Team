"""질문 유형별 리포트 템플릿 (2026-10-02).

모델은 compose_report(template=…) 로 그림의 종류만 고른다. 서버는 실제 조회 결과로
그 템플릿이 성립하는지 보고, 안 되면 결과에 맞는 템플릿으로 바꾼다. 여기서 보는 것은
질문 유형마다 —

    진단  "발레코어 요즘 어때?"        → ticker
    판정  "리본 플랫 지금 사도 될까?"   → verdict (+ 수명주기 · 시세)
    원인  "발레코어 왜 갑자기 떴어?"    → why
    비교  "고프코어 vs 블록코어"        → versus
    순위  "요즘 뜨는 스타일 TOP 10"     → leaderboard
    연관  "발레코어랑 같이 뜨는 거?"    → orbit
    관측 부족  "모브코어 어때?"         → lowsignal (모델이 ticker 를 골라도)
    섞인 결과                          → canvas (예전 생성형 캔버스)

— 맞는 그림이 서고, 같은 값을 두 모양으로 겹쳐 세우지 않는지다.
"""
import unittest
from unittest.mock import patch

from app import agent_blocks, report_skill
from app.tools import Toolbox


class Trace:
    def __init__(self, calls, missing=None):
        self.calls = calls
        self.missing = missing or []


class Store:
    def metric_facet(self, _term):
        return "style"

    def latest_day(self):
        return "2026-10-02"


class Gate:
    def facet_of(self, _term):
        return "style"


def series(days=90, base=60.0, step=0.2, spike_at=None):
    """2026-07-05 ~ 2026-10-02 일별 기록. spike_at 은 언급이 튄 날짜들."""
    from datetime import date, timedelta
    end = date(2026, 10, 2)
    rows = []
    for i in range(days):
        d = (end - timedelta(days=days - 1 - i)).isoformat()
        m = 300 if spike_at and d in spike_at else 20
        rows.append({"d": d, "t": round(base + step * i, 1), "m": m})
    return rows


def node(term, temp=78, **extra):
    out = {
        "available": True, "canonical": term, "facet": "style", "facet_name": "스타일",
        "temp": temp, "temp_band": "따뜻함", "temp_verdict": "뜨거움",
        "temp_verdict_text": "언급량이 꾸준히 오르는 중입니다.",
        "top_pct": 8, "pct_rank": 92, "raw_count": 9120, "mention_7d": 2884,
        "delta_1w": 6, "temp_1w_ago": 72, "thin": False, "observed_on": "2026-10-02",
        "direction": {"label": "오르는 중", "tone": "up", "ratio": 1.27, "ma7": 412, "ma28": 325},
        "sources": [{"name": "유튜브", "temp": 84, "raw_count": 500},
                    {"name": "무신사", "temp": 79, "raw_count": 300}],
        "associations": [
            {"canonical": "리본 플랫", "lift": 3.4, "co_count": 412, "is_new": True, "facet_name": "아이템"},
            {"canonical": "레그워머", "lift": 2.9, "co_count": 288, "is_new": False, "facet_name": "아이템"},
            {"canonical": "랩스커트", "lift": 2.6, "co_count": 251, "is_new": False, "facet_name": "아이템"},
        ],
        "evidence": [{"source": "유튜브", "kind": "영상", "body": "올가을 발레코어 하울 10벌 리본 플랫까지",
                      "at": "2026-09-05T10:00:00", "tone": "positive", "url": "https://youtu.be/x"}],
        "sentiment": {"judged": True, "positive_pct": 64, "negative_pct": 12,
                      "반응": {"합계": 900}, "window_days": 28},
        "series": series(spike_at={"2026-09-04", "2026-09-18"}),
    }
    out.update(extra)
    return out


def metric(term, axes):
    return {"tool": "get_metric", "args": {"term": term, "axes": axes},
            "result": {"term": term, "has_metric": True, "as_of": "2026-10-02"}}


def design(template, term=None, modules=None, title=""):
    spec = {"template": template, "term": term, "title": title, "accent": "coral",
            "surface": "paper", "density": "balanced", "modules": modules or []}
    return {"tool": "compose_report", "args": spec,
            "result": {"ok": True, "skill": "generative-report-v2", "spec": spec}}


def build(calls, nodes):
    with patch("app.agent_blocks.report.build_term",
               side_effect=lambda _s, _g, hit, *_a, **_k: nodes[hit["canonical"]]):
        out = agent_blocks.build(Trace(calls), Store(), Gate())
    return out[0] if out else None


def types(canvas):
    return [m["block"]["type"] for m in canvas["modules"]]


class TemplateTest(unittest.TestCase):
    def test_diagnosis_question_gets_the_ticker(self):
        """"발레코어 요즘 어때?" — 온도·모멘텀·출처별을 조회하고 ticker 를 골랐다."""
        canvas = build([metric("발레코어", ["온도", "모멘텀", "출처별"]), design("ticker", "발레코어")],
                       {"발레코어": node("발레코어")})
        self.assertEqual((canvas["template"], canvas["source"]), ("ticker", "model"))
        self.assertEqual(types(canvas)[0], "ticker")
        tk = canvas["modules"][0]["block"]
        self.assertEqual((tk["temp"], tk["delta_1w"], tk["top_pct"], tk["ratio"]), (78, 6, 8, 1.27))
        self.assertEqual(len(tk["series"]), 90)
        self.assertEqual(tk["platforms"][0], {"name": "유튜브", "temp": 84})
        # 티커가 이미 보여 주는 온도 행 · 방향 KPI · 플랫폼 막대를 따로 세우지 않는다
        self.assertNotIn("rank", types(canvas))
        self.assertNotIn("bars", types(canvas))
        self.assertEqual(canvas["title"], "발레코어 지금 온도")

    def test_thin_term_becomes_lowsignal_even_if_ticker_was_asked(self):
        """"모브코어 어때?" — 28일 언급 9건. 모델이 ticker 를 골라도 관측 부족 카드가 선다."""
        thin = node("모브코어", temp=31, raw_count=9, thin=True, series=[
            {"d": "2026-09-16", "t": 30, "m": 2}, {"d": "2026-09-25", "t": 31, "m": 4},
            {"d": "2026-10-01", "t": 31, "m": 3}])
        canvas = build([metric("모브코어", ["온도"]), design("ticker", "모브코어")], {"모브코어": thin})
        self.assertEqual((canvas["template"], canvas["source"]), ("lowsignal", "auto"))
        low = canvas["modules"][0]["block"]
        self.assertEqual((low["type"], low["n"], low["need"]), ("lowsignal", 9, 20))
        self.assertEqual(low["first_seen"], "2026-09-16")
        self.assertEqual(len(low["points"]), 3)

    def test_buy_question_gets_the_verdict_with_lifecycle_and_market(self):
        """"리본 플랫 지금 사도 될까?" — 살말 지수 + 수명주기 + 할인."""
        calls = [
            {"tool": "get_salmal_index", "args": {"term": "리본 플랫"},
             "result": {"term": "리본 플랫", "score": 72, "recommendation": "살",
                        "recommendation_allowed": True, "confidence": "보통", "coverage": 60,
                        "signals": [{"key": "trend", "label": "트렌드", "weight": 20,
                                     "score": 85, "why": "온도 상승"}],
                        "missing": ["taste", "community"],
                        "missing_why": {"taste": "로그인하지 않았습니다"}}},
            {"tool": "get_market", "args": {"axis": "lifecycle", "style": "발레코어"},
             "result": {"axis": "lifecycle", "term": "발레코어", "stage": "확산", "progress": 33,
                        "peak_date": None, "age_weeks": 9,
                        "weekly_temp_recent": [{"weeks_ago": 0, "temp": 78}]}},
            {"tool": "get_market", "args": {"axis": "discount", "kind": "플랫"},
             "result": {"axis": "discount", "label": "플랫", "days": 30,
                        "overall": {"avg_discount": 18.0, "products": 120, "min_sale_price": 39000}}},
            design("verdict"),
        ]
        canvas = build(calls, {})
        self.assertEqual(canvas["template"], "verdict")
        self.assertEqual(types(canvas), ["verdict", "lifecycle", "kpis"])
        self.assertEqual([m["span"] for m in canvas["modules"]], [12, 7, 5])
        v = canvas["modules"][0]["block"]
        self.assertEqual((v["score"], v["rec"]), (72, "살"))
        self.assertEqual([m["label"] for m in v["missing"]], ["취향", "커뮤니티"])
        self.assertEqual(v["missing_note"], "취향: 로그인하지 않았습니다")
        self.assertEqual(canvas["modules"][1]["block"]["stage"], "확산")
        self.assertEqual(canvas["modules"][2]["block"]["items"][0]["k"], "평균 할인")

    def test_why_question_gets_annotated_timeline_with_evidence(self):
        """"발레코어 왜 떴어?" — 근거를 조회한 용어만 근거 카드가 붙는다."""
        calls = [metric("발레코어", ["온도", "긍부정"]),
                 {"tool": "get_evidence", "args": {"term": "발레코어"},
                  "result": {"term": "발레코어", "count": 1, "items": []}},
                 design("why", "발레코어")]
        canvas = build(calls, {"발레코어": node("발레코어")})
        self.assertEqual(canvas["template"], "why")
        tl = canvas["modules"][0]["block"]
        self.assertEqual(tl["type"], "timeline")
        self.assertEqual([s["d"] for s in tl["spikes"]], ["2026-09-04", "2026-09-18"])
        # 9/5 근거는 9/4 급상승 옆에만 붙는다. 9/18 근처엔 근거가 없으니 비워 둔다.
        self.assertEqual(tl["spikes"][0]["src"], "유튜브")
        self.assertNotIn("src", tl["spikes"][1])
        self.assertEqual(tl["evidence"][0]["url"], "https://youtu.be/x")
        self.assertEqual(tl["sentiment"], {"pos": 64, "neg": 12, "neu": 24, "n": 900, "days": 28})
        # 타임라인이 근거·긍부정을 이미 보여 준다 — 인용 블록을 따로 세우지 않는다
        self.assertNotIn("quotes", types(canvas))

    def test_why_without_evidence_lookup_has_no_cards(self):
        canvas = build([metric("발레코어", ["온도"]), design("why", "발레코어")],
                       {"발레코어": node("발레코어")})
        self.assertEqual(canvas["modules"][0]["block"]["evidence"], [])

    def test_two_terms_get_versus(self):
        """"고프코어 vs 블록코어" — 두 용어를 같은 축으로 맞세운다."""
        calls = [metric("고프코어", ["온도"]), metric("블록코어", ["온도"]), design("versus")]
        canvas = build(calls, {"고프코어": node("고프코어", temp=64, delta_1w=-2, mention_7d=2980),
                               "블록코어": node("블록코어", temp=72, delta_1w=5)})
        self.assertEqual(canvas["template"], "versus")
        vs = canvas["modules"][0]["block"]
        self.assertEqual((vs["a"]["term"], vs["b"]["term"]), ("고프코어", "블록코어"))
        rows = {r["k"]: r for r in vs["rows"]}
        self.assertEqual(rows["트렌드 온도"]["better"], "b")
        self.assertEqual(rows["7일 언급"]["better"], "a")
        self.assertEqual(rows["1주 변화"]["av"], "-2°")
        # 비교 막대·두 용어의 온도 행은 VS 가 보여 준다
        self.assertEqual(types(canvas), ["versus"])
        self.assertEqual(canvas["title"], "고프코어 vs 블록코어")

    def test_ranking_without_design_call_still_gets_leaderboard(self):
        """"요즘 뜨는 스타일 TOP 10" — 예산이 끊겨 compose_report 를 못 불러도."""
        calls = [{"tool": "rank_terms", "args": {"facet": "style"},
                  "result": {"as_of": "2026-10-02", "window_days": 7, "asked": 10,
                             "short_of_asked": True,
                             "items": [{"rank": 1, "term": "발레코어", "facet": "style",
                                        "facet_name": "스타일", "temp": 78, "band": "따뜻함",
                                        "verdict": "뜨거움", "date": "2026-10-02"},
                                       {"rank": 2, "term": "블록코어", "facet": "style",
                                        "facet_name": "스타일", "temp": 72, "band": "따뜻함",
                                        "verdict": "뜨거움", "date": "2026-10-01"}]}}]
        canvas = build(calls, {})
        self.assertEqual((canvas["template"], canvas["source"]), ("leaderboard", "fallback"))
        lb = canvas["modules"][0]["block"]
        self.assertEqual([i["term"] for i in lb["items"]], ["발레코어", "블록코어"])
        self.assertTrue(lb["short"])
        self.assertEqual(types(canvas), ["leaderboard"])

    def test_association_question_gets_orbit(self):
        canvas = build([metric("발레코어", ["연관어"]), design("orbit", "발레코어")],
                       {"발레코어": node("발레코어")})
        self.assertEqual(canvas["template"], "orbit")
        items = canvas["modules"][0]["block"]["items"]
        self.assertEqual([i["name"] for i in items], ["리본 플랫", "레그워머", "랩스커트"])
        self.assertTrue(items[0]["is_new"])
        self.assertEqual(canvas["title"], "발레코어와 같이 뜨는 것")

    def test_template_without_its_data_falls_back_to_what_exists(self):
        """모델이 ticker 를 골랐는데 순위만 조회했다 — 없는 그림을 만들지 않고 리더보드."""
        calls = [{"tool": "rank_terms", "args": {},
                  "result": {"items": [{"rank": 1, "term": "발레코어", "temp": 78}]}},
                 design("ticker", "발레코어")]
        canvas = build(calls, {})
        self.assertEqual((canvas["template"], canvas["source"]), ("leaderboard", "auto"))

    def test_canvas_keeps_the_model_layout_and_drops_visual_duplicates(self):
        calls = [metric("발레코어", ["온도", "연관어"]),
                 design("canvas", modules=[
                     {"kind": "metric", "term": "발레코어", "presentation": "hero",
                      "span": 8, "emphasis": "strong"},
                     {"kind": "associations", "term": "발레코어", "presentation": "list",
                      "span": 4, "emphasis": "normal"}])]
        canvas = build(calls, {"발레코어": node("발레코어")})
        self.assertEqual(canvas["template"], "canvas")
        self.assertEqual(types(canvas), ["rank", "rank"])
        self.assertFalse(set(types(canvas)) & {"ticker", "orbit", "timeline", "lowsignal"})

    def test_ticker_hides_only_the_lead_terms_duplicates(self):
        """둘째 용어를 조회했는데 비교가 아니라면, 둘째 용어의 값은 보조 모듈로 남는다."""
        calls = [metric("발레코어", ["온도"]), metric("발레코어 플랫", ["온도"]),
                 design("ticker", "발레코어")]
        canvas = build(calls, {"발레코어": node("발레코어"), "발레코어 플랫": node("발레코어 플랫")})
        self.assertEqual(canvas["template"], "ticker")
        self.assertEqual(canvas["modules"][0]["block"]["term"], "발레코어")
        rest = [m for m in canvas["modules"][1:] if m["block"]["type"] == "rank"]
        self.assertTrue(any(m["block"].get("title") == "발레코어 플랫" for m in rest))

    def test_tool_accepts_template_and_drops_unknown(self):
        box = Toolbox(Store(), Gate())
        ok = box.t_compose_report("발레코어", "coral", "paper", "balanced", [], "ticker", "발레코어")
        self.assertEqual((ok["spec"]["template"], ok["spec"]["term"]), ("ticker", "발레코어"))
        self.assertIn("플랫폼별 온도", ok["note"])
        bad = box.t_compose_report("x", "coral", "paper", "balanced", [], "<script>", None)
        self.assertIsNone(bad["spec"]["template"])

    def test_no_numbers_are_made_up(self):
        """그림 블록의 숫자는 노드에 있던 값뿐이다 — 없는 지난주 대비를 0 으로 채우지 않는다."""
        canvas = build([metric("발레코어", ["온도"]), design("ticker", "발레코어")],
                       {"발레코어": node("발레코어", delta_1w=None, temp_1w_ago=None, direction=None)})
        tk = canvas["modules"][0]["block"]
        self.assertIsNone(tk["delta_1w"])
        self.assertIsNone(tk["ratio"])


class ChooseTemplateTest(unittest.TestCase):
    def test_auto_order_prefers_verdict_then_ranking(self):
        catalog = [
            {"id": "leaderboard:all", "kind": "leaderboard", "term": None,
             "block": {"type": "leaderboard", "items": [{"term": "a"}]}},
            {"id": "salmal:x:0", "kind": "salmal", "term": "x",
             "block": {"type": "verdict", "score": 50}},
        ]
        self.assertEqual(report_skill.choose_template(None, catalog)[0], "verdict")
        self.assertEqual(report_skill.choose_template(None, catalog[:1])[0], "leaderboard")

    def test_old_spec_without_template_keeps_canvas(self):
        catalog = [{"id": "ticker:a", "kind": "ticker", "term": "a", "block": {"type": "ticker"}}]
        spec = {"modules": [{"kind": "metric"}]}
        self.assertEqual(report_skill.choose_template(spec, catalog)[0], "canvas")


if __name__ == "__main__":
    unittest.main()
