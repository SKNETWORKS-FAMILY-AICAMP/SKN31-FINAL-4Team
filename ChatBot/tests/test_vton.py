import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.modules.setdefault("requests", Mock())

from app import vton


class VirtualFittingTests(unittest.TestCase):
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("app.vton.requests.post")
    def test_sends_model_and_all_items_as_image_array(self, post):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {"data": [{"b64_json": "result"}]}

        result = vton.generate(
            model_id="woman",
            items=[
                {"image": "data:image/png;base64,eA==", "category": "상의"},
                {"image": "data:image/png;base64,eQ==", "category": "하의"},
            ],
        )

        files = post.call_args.kwargs["files"]
        # 기준 사진 7장(마스터 6 + 포즈 1) + 상품 2장
        self.assertEqual([field for field, _file in files],
                         ["image[]"] * (vton.REFERENCE_COUNT + 2))
        self.assertEqual(post.call_args.kwargs["data"]["model"],
                         "gpt-image-2.5-sunburst")
        self.assertEqual(result["image"],
                         "data:" + vton.MIME[vton.OUTPUT_FORMAT] + ";base64,result")
        self.assertEqual(result["item_count"], 2)
        self.assertEqual(result["categories"], ["상의", "하의"])

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("app.vton.requests.post")
    def test_keeps_legacy_single_item_contract(self, post):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {"data": [{"b64_json": "result"}]}

        result = vton.generate(
            image_data_url="data:image/png;base64,eA==",
            model_id="man",
            category="아우터",
        )

        self.assertEqual(result["categories"], ["아우터"])

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("app.vton.requests.post")
    def test_supports_socks_and_auto_classification_prompt(self, post):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {"data": [{"b64_json": "result"}]}

        result = vton.generate(model_id="woman", items=[
            {"image": "data:image/png;base64,eA==", "category": "양말"},
            {"image": "data:image/png;base64,eQ==", "category": "자동 분류"},
        ])

        sent = post.call_args.kwargs["data"]["prompt"]
        self.assertIn("양말", sent)
        # 모자·벨트·안경이 칸에 들어오면서 "의류" 라고 못 박지 않는다 (2026-09-14)
        self.assertIn("종류를 먼저 판별", sent)
        self.assertEqual(result["categories"], ["양말", "자동 분류"])

    # ── 2026-09-14 추가 칸 · 착장 옵션 ─────────────────────────
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("app.vton.requests.post")
    def test_accessory_slots_carry_their_own_wear_guide(self, post):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {"data": [{"b64_json": "result"}]}

        result = vton.generate(model_id="woman", items=[
            {"image": "data:image/png;base64,eA==", "category": "모자"},
            {"image": "data:image/png;base64,eQ==", "category": "벨트"},
            {"image": "data:image/png;base64,eg==", "category": "안경"},
        ])

        sent = post.call_args.kwargs["data"]["prompt"]
        self.assertIn(vton.WEAR_GUIDE["모자"], sent)
        self.assertIn(vton.WEAR_GUIDE["벨트"], sent)
        self.assertIn(vton.WEAR_GUIDE["안경"], sent)
        self.assertEqual(result["categories"], ["모자", "벨트", "안경"])

    def test_options_off_keeps_the_old_prompt(self):
        """전부 꺼진 상태가 기존 동작이다 — 켜지 않은 연출이 새면 안 된다."""
        base = vton.prompt(["상의"])
        self.assertEqual(base, vton.prompt(["상의"], {}))
        self.assertEqual(base, vton.prompt(["상의"], {k: False for k in vton.OPTION_LINES}))

    def test_option_lines_are_added_and_conflicts_dropped(self):
        got = vton.prompt(["아우터"], {"outer_layered": True, "outer_open": True,
                                       "top_open": True, "top_closed": True})
        self.assertIn(vton.OPTION_LINES["outer_layered"], got)
        self.assertIn(vton.OPTION_LINES["outer_open"], got)
        # 열기·닫기를 둘 다 켜 보내면 어느 쪽도 쓰지 않는다 (모순된 지시를 막는다)
        self.assertNotIn(vton.OPTION_LINES["top_open"], got)
        self.assertNotIn(vton.OPTION_LINES["top_closed"], got)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("app.vton.requests.post")
    def test_generate_reports_the_options_it_used(self, post):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {"data": [{"b64_json": "result"}]}

        # ★ 2026-10-01 — 상의 옵션은 상의가 있을 때만 실린다(vton.SLOT_OF). 예전 시험은
        #   아우터 한 장에 top_closed 를 실었는데, 이제는 그 조합이 빠지는 것이 맞다.
        # ★ 2026-10-02 — 레이어드는 아우터가 둘일 때만 실린다(vton.apply_sight). 그래서
        #   아우터를 두 벌 넣는다. 사진 검수는 '모르겠음' 으로 고정한다(아무것도 안 뺀다).
        with patch("app.vton.inspect", side_effect=lambda imgs, hints=None: [dict(vton.UNKNOWN) for _ in imgs]):
            result = vton.generate(
                model_id="woman",
                items=[{"image": "data:image/png;base64,eA==", "category": "아우터"},
                       {"image": "data:image/png;base64,eg==", "category": "아우터"},
                       {"image": "data:image/png;base64,eQ==", "category": "상의"}],
                options={"outer_layered": True, "top_closed": True},
            )

        self.assertEqual(result["options"], ["outer_layered", "top_closed"])


class EngineAndFitOptionTests(unittest.TestCase):
    """생성 엔진 고르기 · 열기/여미기 기본값 · 핏 세 칸 (2026-10-01)."""

    def _post(self, post):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {"data": [{"b64_json": "result"}]}

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("app.vton.requests.post")
    def test_flare_is_sent_when_chosen(self, post):
        self._post(post)
        result = vton.generate(model_id="woman", engine="flare",
                               items=[{"image": "data:image/png;base64,eA==", "category": "상의"}])
        sent = post.call_args.kwargs["data"]
        self.assertEqual(sent["model"], "gpt-image-2.5-flare")
        # 해상도·품질은 엔진과 상관없이 같다 (두 모델의 한도가 같다)
        self.assertEqual((sent["size"], sent["quality"]), (vton.SIZE, vton.QUALITY))
        self.assertEqual((result["engine"], result["model"]), ("flare", "gpt-image-2.5-flare"))
        self.assertIsInstance(result["elapsed_ms"], int)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("app.vton.requests.post")
    def test_default_and_unknown_engine_is_sunburst(self, post):
        self._post(post)
        for engine in (None, "", "turbo"):
            with self.subTest(engine=engine):
                result = vton.generate(model_id="woman", engine=engine, items=[
                    {"image": "data:image/png;base64,eA==", "category": "상의"}])
                self.assertEqual(post.call_args.kwargs["data"]["model"], "gpt-image-2.5-sunburst")
                self.assertEqual(result["engine"], "sunburst")

    def test_default_open_lines_only_for_garments_in_the_outfit(self):
        # 화면 기본값(아무것도 안 만짐) — 아우터·상의 모두 '열어 입기'
        default = {"outer_open": True, "top_open": True}
        pants_only = vton.prompt(["하의"], default)
        self.assertNotIn(vton.OPTION_LINES["outer_open"], pants_only)
        self.assertNotIn(vton.OPTION_LINES["top_open"], pants_only)
        self.assertEqual(pants_only, vton.prompt(["하의"]))     # 예전 프롬프트 그대로
        both = vton.prompt(["상의", "아우터"], default)
        self.assertIn(vton.OPTION_LINES["outer_open"], both)
        self.assertIn(vton.OPTION_LINES["top_open"], both)
        # 칸을 모르는 사진이 있으면 그 사진이 상의일 수 있다 — 조건부 문장이라 붙인다
        self.assertIn(vton.OPTION_LINES["top_open"], vton.prompt(["자동 분류"], default))

    def test_open_lines_never_ask_for_a_new_opening(self):
        # 기본이 '열어 입기' 다 — 여밈 없는 옷에 트임을 만들라는 지시가 되면 안 된다
        self.assertIn("앞여밈이 없는 상의는 그대로", vton.OPTION_LINES["top_open"])
        self.assertIn("앞여밈이 없는 아우터는 그대로", vton.OPTION_LINES["outer_open"])

    def test_fit_lines_and_conflict(self):
        regular = vton.prompt(["상의"], {"top_open": True})
        self.assertIn("봉제선과 실루엣을 정확히 보존", regular)   # 정핏 = 상품 핏 그대로
        over = vton.prompt(["상의"], {"top_open": True, "fit_over": True})
        self.assertIn(vton.OPTION_LINES["fit_over"], over)
        # 핏을 골랐으면 '실루엣 보존' 과 맞서지 않게 그 말을 뺀다
        self.assertNotIn("봉제선과 실루엣을 정확히 보존", over)
        both = vton.prompt(["상의"], {"fit_over": True, "fit_slim": True})
        self.assertNotIn(vton.OPTION_LINES["fit_over"], both)
        self.assertNotIn(vton.OPTION_LINES["fit_slim"], both)


class NoInventedGarmentTests(unittest.TestCase):
    """주지 않은 옷을 지어내지 않는다 (2026-10-02).

    상의(티셔츠)만 넣고 화면 기본값(아우터 · 상의 '열어 입기')으로 만들었더니 없던
    아우터가 그려졌다. 직접 올린 사진은 'Auto' 로 오고, 칸을 모르는 사진이 있으면
    아우터 열기 문장이 붙었기 때문이다.
    """

    DEFAULT = {"outer_open": True, "top_open": True}
    TEE = {"slot": "상의", "closure": "없음", "openable": "no", "layer": "얇음"}
    SHIRT = {"slot": "상의", "closure": "버튼", "openable": "yes", "layer": "얇음"}

    def _run(self, post, items, seen_rows, options=None):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {"data": [{"b64_json": "result"}]}
        calls = []

        def look(imgs, hints=None):
            calls.append(list(imgs))
            return [dict(seen_rows[i % len(seen_rows)]) for i in range(len(imgs))]

        with patch("app.vton.inspect", side_effect=look):
            result = vton.generate(model_id="woman", items=items,
                                   options=self.DEFAULT if options is None else options)
        return result, post.call_args.kwargs["data"]["prompt"], calls

    def test_every_prompt_forbids_invented_garments(self):
        for cats in (["상의"], ["하의"], ["자동 분류"], ["상의", "아우터"]):
            with self.subTest(cats=cats):
                self.assertIn(vton.NO_INVENT, vton.prompt(cats))
                self.assertIn(vton.NO_INVENT, vton.prompt(cats, self.DEFAULT))

    def test_outer_lines_say_they_apply_only_with_an_outer(self):
        self.assertIn("아우터를 새로 만들지 마세요", vton.OPTION_LINES["outer_open"])
        self.assertIn("아우터를 새로 만들지 마세요", vton.OPTION_LINES["outer_closed"])
        self.assertIn("겉옷이나 이너를 새로 더하지 마세요", vton.OPTION_LINES["top_open"])

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("app.vton.requests.post")
    def test_auto_tee_with_default_open_gets_no_outer_line(self, post):
        result, sent, calls = self._run(
            post, [{"image": "data:image/png;base64,eA==", "category": "자동 분류"}], [self.TEE])
        self.assertEqual(len(calls), 1, "사진을 한 번 봐야 한다")
        self.assertEqual(result["categories"], ["상의"])
        self.assertNotIn(vton.OPTION_LINES["outer_open"], sent)
        # 여밈이 없는 티셔츠뿐이라 상의 열기도 뺀다
        self.assertNotIn(vton.OPTION_LINES["top_open"], sent)
        self.assertEqual(result["options"], [])
        self.assertIn(vton.NO_INVENT, sent)
        self.assertTrue(any("앞여밈이 없어" in n for n in result["sight_notes"]))

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("app.vton.requests.post")
    def test_buttoned_shirt_keeps_top_open_but_still_no_outer(self, post):
        result, sent, _calls = self._run(
            post, [{"image": "data:image/png;base64,eA==", "category": "자동 분류"}], [self.SHIRT])
        self.assertIn(vton.OPTION_LINES["top_open"], sent)
        self.assertNotIn(vton.OPTION_LINES["outer_open"], sent)
        self.assertEqual(result["options"], ["top_open"])

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("app.vton.requests.post")
    def test_unseen_photo_keeps_the_conditional_lines(self, post):
        # 사진을 못 보면 빼지도 바꾸지도 않는다 — 문장 자체의 조건이 막는다
        result, sent, _calls = self._run(
            post, [{"image": "data:image/png;base64,eA==", "category": "자동 분류"}], [vton.UNKNOWN])
        self.assertEqual(result["categories"], ["자동 분류"])
        self.assertIn(vton.OPTION_LINES["outer_open"], sent)
        self.assertEqual(result["sight_notes"], [])

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("app.vton.requests.post")
    def test_user_chosen_slot_is_not_overridden(self, post):
        result, _sent, _calls = self._run(
            post, [{"image": "data:image/png;base64,eA==", "category": "아우터"}],
            [{"slot": "상의", "closure": "지퍼", "openable": "yes", "layer": "보통"}])
        self.assertEqual(result["categories"], ["아우터"])
        self.assertEqual(result["options"], ["outer_open"])

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("app.vton.requests.post")
    def test_every_photo_is_looked_at_once(self, post):
        # 2026-10-02 오후 — 착용 컷인지 알려면 모든 상품 사진을 봐야 한다. 한 번의 호출로 같이 본다.
        _result, _sent, calls = self._run(post, [
            {"image": "data:image/png;base64,eA==", "category": "하의"},
            {"image": "data:image/png;base64,eQ==", "category": "상의"},
            {"image": "data:image/png;base64,eg==", "category": "신발"}], [self.SHIRT])
        self.assertEqual(calls, [["data:image/png;base64,eA==", "data:image/png;base64,eQ==",
                                  "data:image/png;base64,eg=="]])
        # 연출이 하나도 없어도 본다 — 착용 컷 표시는 연출과 상관이 없다
        _result, _sent, calls = self._run(post, [
            {"image": "data:image/png;base64,eA==", "category": "하의"}], [vton.UNKNOWN],
            options={})
        self.assertEqual(len(calls), 1)


class WornPhotoTests(unittest.TestCase):
    """상품 사진에 다른 사람이 찍혀 있어도 우리 모델에게 입힌다 (2026-10-02 오후).

    상의 칸에 '남자가 흰 셔츠를 입고 의자에 앉은 사진' 을 넣고 여성 모델로 만들었더니,
    그 사진의 남자 · 배경 그대로 바지와 신발만 바뀐 그림이 나왔다.
    """

    WORN_SHIRT = {"slot": "상의", "closure": "버튼", "openable": "yes", "layer": "얇음",
                  "worn": "yes"}
    FLAT = {"slot": "신발", "closure": "모르겠음", "openable": "unknown", "layer": "모르겠음",
            "worn": "no"}

    def test_every_prompt_says_item_photos_are_only_samples(self):
        for cats in (["상의"], ["하의", "신발"], ["자동 분류"]):
            with self.subTest(cats=cats):
                sent = vton.prompt(cats)
                self.assertIn(vton.ITEM_ONLY, sent)
                self.assertIn("상품 사진 속 인물이나 배경이 결과에 나오면 안 됩니다", sent)
        self.assertIn("8번째 이미지부터", vton.ITEM_ONLY)        # 번호가 references() 와 맞다
        self.assertIn("7번 사진", vton.ITEM_ONLY)

    def test_worn_photo_is_named_in_the_prompt(self):
        sent = vton.prompt(["상의", "신발"], None, [True, False])
        self.assertIn("8번째 이미지는 상의(다른 사람이 입고 찍힌 사진입니다 — 상의만 가져오고 그 사람의", sent)
        self.assertNotIn("9번째 이미지는 신발(다른 사람", sent)
        auto = vton.prompt(["자동 분류"], None, [True])
        self.assertIn("종류를 먼저 판별(다른 사람이 입고 찍힌 사진입니다 — 그 옷만 가져오고 그 사람의", auto)
        # 모르면 집어 말하지 않는다 — 일반 문장(ITEM_ONLY)만 남는다
        self.assertNotIn("다른 사람이 입고 찍힌", vton.prompt(["상의"], None, None))

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("app.vton.requests.post")
    def test_generate_marks_worn_photos_from_sight(self, post):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {"data": [{"b64_json": "result"}]}
        rows = [self.WORN_SHIRT, self.FLAT]
        with patch("app.vton.inspect", side_effect=lambda imgs, hints=None: [dict(r) for r in rows[:len(imgs)]]):
            result = vton.generate(model_id="woman", items=[
                {"image": "data:image/png;base64,eA==", "category": "상의"},
                {"image": "data:image/png;base64,eQ==", "category": "신발"}],
                options={"top_open": True})
        sent = post.call_args.kwargs["data"]["prompt"]
        self.assertIn("8번째 이미지는 상의(다른 사람이 입고 찍힌 사진", sent)
        self.assertEqual(result["worn"], [1])
        self.assertTrue(any("사람이 입고 찍힌 사진이라 옷만" in n for n in result["sight_notes"]))
        # 기준 사진 일곱 장이 상품보다 먼저 나간다 — 모델 사진이 빠지지 않았다
        files = post.call_args.kwargs["files"]
        self.assertEqual(len(files), vton.REFERENCE_COUNT + 2)
        self.assertEqual([f[1][0] for f in files[-2:]], ["item-1.png", "item-2.png"])

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("app.vton.requests.post")
    def test_failed_sight_still_sends_the_general_guard(self, post):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {"data": [{"b64_json": "result"}]}
        with patch("app.vton.inspect", side_effect=RuntimeError("vision down")):
            result = vton.generate(model_id="woman", items=[
                {"image": "data:image/png;base64,eA==", "category": "상의"}])
        sent = post.call_args.kwargs["data"]["prompt"]
        self.assertIn(vton.ITEM_ONLY, sent)
        self.assertEqual(result["worn"], [])

    def test_inspect_asks_for_worn(self):
        self.assertIn("worn", vton.UNKNOWN)
        self.assertIn("worn 은 사람이 실제로 입고", vton._INSPECT_INSTRUCTIONS)


try:
    import PIL  # noqa: F401
    HAS_PIL = True
except ImportError:          # 챗봇 이미지에는 있다(requirements.txt). 로컬에 없으면 자르기 시험만 건너뛴다.
    HAS_PIL = False


@unittest.skipUnless(HAS_PIL, "Pillow 없음")
class IsolateTests(unittest.TestCase):
    """착용 컷에서 사람을 걷어 낸다 (2026-10-02 오후 2차).

    프롬프트만 강하게 한 뒤에도 여성 모델 결과에 상품 사진(정장 착용 컷)의 남자가
    그대로 나왔다. 보내는 사진에서 머리를 덮고 그 칸 옷 영역만 남긴다.
    """

    @staticmethod
    def _photo(w=200, h=400):
        import io
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (w, h), (90, 140, 200))           # 배경(파랑)
        d = ImageDraw.Draw(img)
        d.rectangle((80, 10, 120, 60), fill=(230, 190, 160))       # 머리(살색)
        d.rectangle((50, 70, 150, 200), fill=(20, 20, 20))         # 재킷(검정)
        d.rectangle((60, 200, 140, 380), fill=(60, 60, 60))        # 바지
        out = io.BytesIO()
        img.save(out, format="JPEG")
        return out.getvalue()

    def test_worn_photo_is_cropped_to_the_garment_and_the_head_is_covered(self):
        import io
        from PIL import Image
        look = {"worn": "yes", "box": [0.25, 0.15, 0.75, 0.5], "head": [0.4, 0.02, 0.6, 0.15]}
        raw, ext, changed = vton.isolate(self._photo(), "jpg", look)
        self.assertTrue(changed)
        self.assertEqual(ext, "png")
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        w, h = img.size
        self.assertLess(h, 400 * 0.5)                               # 바지 대부분이 빠졌다
        self.assertEqual(img.getpixel((w // 2, h // 2)), (20, 20, 20))   # 재킷은 남았다
        # 머리 자리는 덮였다 — 살색 픽셀이 하나도 없다
        skin = sum(1 for x in range(w) for y in range(h)
                   if img.getpixel((x, y)) == (230, 190, 160))
        self.assertEqual(skin, 0)

    def test_not_worn_or_no_box_is_sent_as_is(self):
        photo = self._photo()
        for look in (None, {"worn": "no", "box": [0, 0, 1, 1]}, {"worn": "yes"},
                     {"worn": "unknown", "head": [0.4, 0, 0.6, 0.2]}):
            with self.subTest(look=look):
                self.assertEqual(vton.isolate(photo, "jpg", look), (photo, "jpg", False))

    def test_broken_image_falls_back_to_the_original(self):
        look = {"worn": "yes", "box": [0.1, 0.1, 0.9, 0.9], "head": []}
        self.assertEqual(vton.isolate(b"not an image", "png", look), (b"not an image", "png", False))

    def test_ratio_box_rejects_bad_values(self):
        self.assertEqual(vton._ratio_box([0.1, 0.2, 0.8, 0.9]), [0.1, 0.2, 0.8, 0.9])
        self.assertEqual(vton._ratio_box([-1, 0, 2, 1]), [0.0, 0.0, 1.0, 1.0])
        for bad in ([], [0.1, 0.2], ["a", 0, 1, 1], [0.5, 0.5, 0.52, 0.9], None):
            self.assertEqual(vton._ratio_box(bad), [])

    def test_prompt_pins_the_chosen_models_gender_at_both_ends(self):
        sent = vton.prompt(["상의"], None, None, "여성")
        self.assertTrue(sent.startswith("결과 사진의 인물은 반드시 1~6번 기준 사진의 여성 한 사람입니다."))
        self.assertIn("다른 성별 포함", sent)
        self.assertTrue(sent.endswith("상품 사진의 사람이나 장면이 나오면 실패입니다."))
        self.assertIn("결과 인물은 1~6번의 여성", sent)
        self.assertNotIn("여성", vton.prompt(["상의"]))              # who 를 안 주면 예전 그대로
        self.assertEqual(vton.MODELS["woman"]["who"], "여성")
        self.assertEqual(vton.MODELS["man"]["who"], "남성")

    def test_cut_wording_only_when_actually_cut(self):
        cut = vton.prompt(["아우터"], None, [True], "여성", [True])
        self.assertIn("아우터 부분만 잘라 낸 것입니다", cut)
        worn_only = vton.prompt(["아우터"], None, [True], "여성", [False])
        self.assertNotIn("잘라 낸", worn_only)
        self.assertIn("다른 사람이 입고 찍힌 사진입니다 — 아우터만 가져오고", worn_only)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("app.vton.requests.post")
    def test_generate_sends_the_cut_garment_and_the_slot_hints(self, post):
        import base64
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {"data": [{"b64_json": "result"}]}
        photo = "data:image/jpeg;base64," + base64.b64encode(self._photo()).decode()
        asked = []

        def look(imgs, hints=None):
            asked.append(list(hints or []))
            return [{"slot": "아우터", "closure": "버튼", "openable": "yes", "layer": "보통",
                     "worn": "yes", "box": [0.25, 0.15, 0.75, 0.5], "head": [0.4, 0.02, 0.6, 0.15]},
                    {"slot": "신발", "closure": "모르겠음", "openable": "unknown",
                     "layer": "모르겠음", "worn": "no", "box": [], "head": []}][:len(imgs)]

        with patch("app.vton.inspect", side_effect=look):
            result = vton.generate(model_id="woman", items=[
                {"image": photo, "category": "아우터"},
                {"image": "data:image/png;base64,eA==", "category": "신발"}])
        self.assertEqual(asked, [["아우터", "신발"]])               # 칸을 알려 주고 본다
        files = post.call_args.kwargs["files"]
        self.assertEqual(files[vton.REFERENCE_COUNT][1][0], "item-1.png")   # 잘라서 PNG 로
        self.assertEqual(files[vton.REFERENCE_COUNT + 1][1][1], b"x")       # 안 자른 건 그대로
        sent = post.call_args.kwargs["data"]["prompt"]
        self.assertIn("아우터 부분만 잘라 낸 것입니다", sent)
        self.assertTrue(sent.startswith("결과 사진의 인물은 반드시 1~6번 기준 사진의 여성"))
        self.assertEqual(result["isolated"], [1])


class LocateTagTests(unittest.TestCase):
    """결과 사진 위 쇼핑 태그 (2026-10-02) — 상품마다 한 점, 못 찾으면 빼고 지어내지 않는다."""

    def test_points_are_kept_in_item_order_and_bad_ones_dropped(self):
        got = {"items": [{"point": [0.5, 0.3]}, {"point": []}, {"point": [1.4, 0.2]},
                         {"point": [0.45, 0.82]}]}
        with patch("app.llm.available", return_value=True), \
             patch("app.llm.respond", return_value=got) as respond:
            tags = vton.locate("eA==", [("아우터", "블레이저"), ("상의", "셔츠"),
                                        ("하의", "슬랙스"), ("신발", "더비")])
        self.assertEqual(tags, [{"index": 0, "x": 0.5, "y": 0.3},
                                {"index": 3, "x": 0.45, "y": 0.82}])
        listing = respond.call_args.args[1][0]["content"][0]["text"]
        self.assertIn("1. 아우터 — 블레이저", listing)        # 무엇을 찾는지 이름까지 알려 준다

    def test_failure_means_no_tags(self):
        with patch("app.llm.available", return_value=True), \
             patch("app.llm.respond", side_effect=RuntimeError("down")):
            self.assertEqual(vton.locate("eA==", [("상의", "셔츠")]), [])
        with patch("app.llm.available", return_value=True), \
             patch("app.llm.respond", return_value=None):
            self.assertEqual(vton.locate("eA==", [("상의", "셔츠")]), [])
        self.assertEqual(vton.locate("", [("상의", "셔츠")]), [])

    @unittest.skipUnless(HAS_PIL, "Pillow 없음")
    def test_result_is_shrunk_before_vision(self):
        import base64
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (2480, 3312), (200, 200, 200)).save(buf, format="WEBP")
        small = vton._small_data_url(base64.b64encode(buf.getvalue()).decode())
        self.assertTrue(small.startswith("data:image/jpeg;base64,"))
        img = Image.open(io.BytesIO(base64.b64decode(small.split(",", 1)[1])))
        self.assertEqual(max(img.size), vton.LOCATE_SIDE)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("app.vton.requests.post")
    def test_generate_locates_only_when_asked(self, post):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {"data": [{"b64_json": "cmVzdWx0"}]}
        items = [{"image": "data:image/png;base64,eA==", "category": "상의", "name": "옥스퍼드 셔츠"}]
        with patch("app.vton.inspect", side_effect=lambda imgs, hints=None: [dict(vton.UNKNOWN)]), \
             patch("app.vton.locate", return_value=[{"index": 0, "x": 0.5, "y": 0.4}]) as loc:
            off = vton.generate(model_id="woman", items=items)
            self.assertEqual(off["tags"], [])
            loc.assert_not_called()
            on = vton.generate(model_id="woman", items=items, tags=True)
        self.assertEqual(on["tags"], [{"index": 0, "x": 0.5, "y": 0.4}])
        self.assertEqual(loc.call_args.args, ("cmVzdWx0", [("상의", "옥스퍼드 셔츠")]))


class PoseTests(unittest.TestCase):
    """포즈 풀 (2026-09-14).

    한 장짜리 모델일 땐 만들 때마다 같은 자세만 나왔다. 같은 모델의 포즈를
    여러 장 두고 뽑는다 — 여기서 보는 것은 '정말 여러 장에서 뽑는가' 와
    '이름을 집어 주면 그것이 나가는가' 둘이다.
    ★ 두 모델 다 본다. 여성만 보던 시절엔 남성 쪽 폴더가 비어도 초록이었다.
    """

    MODELS = ["woman", "man"]

    def test_every_model_has_a_pose_pool(self):
        for mid in self.MODELS:
            with self.subTest(model=mid):
                found = vton.poses(mid)
                self.assertGreater(len(found), 1, f"{mid} 포즈가 한 장뿐이다")
                for path in found:
                    self.assertTrue(path.is_file(), f"{path} 가 없다")

    def test_unknown_model_has_no_pose(self):
        self.assertEqual(vton.poses("robot"), [])
        with self.assertRaises(ValueError):
            vton.pick_pose("robot")

    def test_pick_pose_spreads_over_the_pool(self):
        for mid in self.MODELS:
            with self.subTest(model=mid):
                names = {vton.pick_pose(mid).name for _ in range(160)}
                self.assertGreater(len(names), 1, f"{mid} 은 늘 같은 포즈만 뽑힌다")

    def test_pick_pose_honours_a_named_pose(self):
        for mid in self.MODELS:
            with self.subTest(model=mid):
                first = vton.poses(mid)[0].name
                for _ in range(20):
                    self.assertEqual(vton.pick_pose(mid, first).name, first)

    def test_unknown_pose_name_falls_back_instead_of_failing(self):
        """없는 이름이 와도 실패시키지 않는다 — 파일이 갈린 옛 결과일 수 있다."""
        for mid in self.MODELS:
            with self.subTest(model=mid):
                self.assertIn(vton.pick_pose(mid, "nope.png"), vton.poses(mid))

    def test_pools_do_not_share_photos(self):
        """두 풀이 섞이면 여성 모델을 골랐는데 남성이 나온다."""
        woman = {p.name for p in vton.poses("woman")}
        man = {p.name for p in vton.poses("man")}
        self.assertEqual(woman & man, set(), "두 모델이 같은 파일을 쓴다")

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("app.vton.requests.post")
    def test_generate_reports_which_pose_it_used(self, post):
        for mid in self.MODELS:
            with self.subTest(model=mid):
                post.return_value = Mock(status_code=200)
                post.return_value.json.return_value = {"data": [{"b64_json": "result"}]}

                result = vton.generate(model_id=mid, items=[
                    {"image": "data:image/png;base64,eA==", "category": "상의"}])

                self.assertIn(result["pose"], [p.name for p in vton.poses(mid)])
                # 기준 사진 중 마지막이 그 포즈여야 한다 — 앞의 여섯은 마스터다
                names = [f[1][0] for f in post.call_args.kwargs["files"]]
                self.assertEqual(names[vton.REFERENCE_COUNT - 1], result["pose"])


class OutputSettingsTests(unittest.TestCase):
    """출력 해상도·품질·형식 (2026-09-14).

    셋 다 눈에 안 보이는 설정이라 조용히 어긋나도 아무도 모른다. 값 자체보다
    '그 값이 실제로 요청에 실리는가' 와 'API 가 받아 주는 범위인가' 를 본다.
    """

    def test_size_fits_the_api_limits(self):
        w, h = (int(v) for v in vton.SIZE.split("x"))
        self.assertEqual(w % 16, 0, "가로가 16의 배수가 아니다")
        self.assertEqual(h % 16, 0, "세로가 16의 배수가 아니다")
        self.assertLessEqual(max(w, h), 3840, "긴 변이 3840px 를 넘는다")
        self.assertLessEqual(w * h, 8_294_400, "총 픽셀이 상한을 넘는다")
        self.assertLessEqual(max(w, h) / min(w, h), 3, "가로세로비가 3:1 을 넘는다")

    def test_size_keeps_the_model_photo_shape(self):
        """모델 사진이 3:4 다. 출력이 다른 비율이면 전신이 잘리거나 여백만 는다."""
        w, h = (int(v) for v in vton.SIZE.split("x"))
        self.assertAlmostEqual(h / w, 4 / 3, delta=0.02)

    def test_quality_is_one_the_model_accepts(self):
        self.assertIn(vton.QUALITY, {"low", "medium", "high", "xhigh", "max", "auto"})

    def test_output_format_is_small_enough_for_the_proxy(self):
        """★ PNG 으로 되돌리면 배포된 화면에서 4K 가 한 장도 안 나온다 —
        Vercel 함수 응답 상한 4.5MB 에 base64 4K PNG(13MB 쯤)이 걸린다."""
        self.assertIn(vton.OUTPUT_FORMAT, {"jpeg", "webp"},
                      "압축 포맷이 아니면 프록시 응답 한도를 넘는다")
        self.assertIn(vton.OUTPUT_FORMAT, vton.MIME)
        self.assertTrue(0 <= int(vton.OUTPUT_COMPRESSION) <= 100)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("app.vton.requests.post")
    def test_settings_actually_ride_on_the_request(self, post):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {"data": [{"b64_json": "result"}]}

        result = vton.generate(model_id="woman", items=[
            {"image": "data:image/png;base64,eA==", "category": "상의"}])

        sent = post.call_args.kwargs["data"]
        self.assertEqual(sent["size"], vton.SIZE)
        self.assertEqual(sent["quality"], vton.QUALITY)
        self.assertEqual(sent["output_format"], vton.OUTPUT_FORMAT)
        self.assertEqual(sent["output_compression"], vton.OUTPUT_COMPRESSION)
        # 화면도 무엇으로 받았는지 알아야 한다 — 저장 파일 확장자가 여기서 나온다
        self.assertEqual(result["size"], vton.SIZE)
        self.assertEqual(result["quality"], vton.QUALITY)
        self.assertEqual(result["format"], vton.OUTPUT_FORMAT)
        self.assertTrue(result["image"].startswith(
            "data:" + vton.MIME[vton.OUTPUT_FORMAT] + ";base64,"))


class ReferenceTests(unittest.TestCase):
    """기준 사진 (2026-09-14).

    포즈 한 장만 보내던 시절엔 그 한 장에 안 보이는 것을 모델이 지어냈다 —
    얼굴이 컷마다 딴사람이 되고 체형이 흔들렸다. 얼굴 셋·전신 셋을 같이 보낸다.
    ★ 여기서 지키는 것은 '순서' 다. prompt() 가 번호로 부르기 때문에,
      한 칸만 밀려도 모델은 신발 사진을 얼굴 기준으로 읽는다.
    """

    MODELS = ["woman", "man"]

    def test_every_model_has_the_six_masters(self):
        want = ["01_face_front.png", "02_face_right.png", "03_face_left.png",
                "04_body_front.png", "05_body_side.png", "06_body_back.png"]
        for mid in self.MODELS:
            with self.subTest(model=mid):
                self.assertEqual([p.name for p in vton.masters(mid)], want)
                for path in vton.masters(mid):
                    self.assertTrue(path.is_file())

    def test_references_are_masters_then_the_pose(self):
        for mid in self.MODELS:
            with self.subTest(model=mid):
                refs = vton.references(mid)
                self.assertEqual(len(refs), vton.REFERENCE_COUNT)
                self.assertEqual(refs[:vton.MASTER_COUNT], vton.masters(mid))
                self.assertIn(refs[-1], vton.poses(mid))

    def test_missing_masters_fail_loudly(self):
        """폴더가 비면 조용히 포즈 한 장으로 떨어지지 않고 말한다."""
        with self.assertRaises(ValueError):
            vton.references("robot")

    def test_errors_say_what_is_missing_and_where(self):
        """★ 예전에는 어느 경우든 "선택한 AI 모델을 찾을 수 없습니다." 한 줄이었다.

        사진 폴더를 옮긴 뒤 옛 코드를 물고 있던 서버가 그 문구를 뱉었는데,
        화면만 봐서는 이름이 틀린 건지 파일이 없는 건지 서버가 낡은 건지
        알 수 없었다. 셋을 구분해서 말하는지 본다.
        """
        with self.assertRaises(ValueError) as bad_id:
            vton.references("robot")
        self.assertIn("robot", str(bad_id.exception))

        folder = vton.MODELS["woman"]["dir"] / vton.POSE_DIR
        moved = folder.with_name("_poses_off")
        folder.rename(moved)
        try:
            with self.assertRaises(ValueError) as no_pose:
                vton.references("woman")
        finally:
            moved.rename(folder)
        said = str(no_pose.exception)
        self.assertIn("포즈", said)
        self.assertIn(vton.POSE_DIR, said, "어느 폴더인지 안 알려 준다")
        self.assertIn("다시 시작", said, "서버 재시작을 짚어 주지 않는다")
        # 고쳐 놓고 원래대로 돌아왔는지
        self.assertGreater(len(vton.poses("woman")), 1)

    def test_prompt_pins_the_leg_proportions(self):
        """★ 다리가 짧아 보인다는 말이 나왔던 자리 (2026-09-14).

        자세를 따라 그리다 보면 허리선과 다리 길이가 같이 눌린다. 비율만은
        체형 기준(4~6번)을 보라고 따로 적어 둔다 — 이 문장이 빠지면 다시 눌린다.
        """
        got = vton.prompt(["상의"])
        self.assertIn("다리 길이와 허리선 높이는 4~6번", got)
        self.assertIn("짧아 보이게 만들지 마세요", got)

    def test_prompt_numbers_match_the_image_order(self):
        """프롬프트의 번호와 실제로 보내는 순서가 어긋나면 안 된다."""
        got = vton.prompt(["상의", "하의"])
        self.assertIn(f"1번부터 {vton.REFERENCE_COUNT}번까지", got)
        self.assertIn("1~3번은 얼굴 기준", got)
        self.assertIn("4~6번은 체형 기준", got)
        self.assertIn(f"{vton.REFERENCE_COUNT}번은 이번 컷의 기준", got)
        # 상품은 기준 사진 바로 다음 번호부터
        self.assertIn(f"{vton.REFERENCE_COUNT + 1}번째 이미지는 상의", got)
        self.assertIn(f"{vton.REFERENCE_COUNT + 2}번째 이미지는 하의", got)

    def test_items_and_references_fit_in_one_request(self):
        """★ API 는 한 번에 16장이다. 칸을 늘리다 조용히 잘리면 사용자가 넣은
        사진이 사라진다 — 합이 상한을 넘지 않는지 여기서 붙잡는다."""
        self.assertLessEqual(vton.MAX_ITEMS + vton.REFERENCE_COUNT, vton.MAX_IMAGES)
        self.assertEqual(vton.MAX_ITEMS,
                         min(len(vton.SLOT_ORDER), vton.MAX_IMAGES - vton.REFERENCE_COUNT))

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("app.vton.requests.post")
    def test_masters_ride_ahead_of_the_items(self, post):
        post.return_value = Mock(status_code=200)
        post.return_value.json.return_value = {"data": [{"b64_json": "result"}]}

        result = vton.generate(model_id="woman", items=[
            {"image": "data:image/png;base64,eA==", "category": "상의"}])

        names = [f[1][0] for f in post.call_args.kwargs["files"]]
        self.assertEqual(names[:vton.MASTER_COUNT],
                         [p.name for p in vton.masters("woman")])
        self.assertEqual(names[vton.REFERENCE_COUNT - 1], result["pose"])
        self.assertEqual(names[vton.REFERENCE_COUNT:], ["item-1.png"])
        self.assertEqual(result["references"], names[:vton.REFERENCE_COUNT])

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("app.vton.requests.post")
    def test_master_files_are_open_while_being_sent(self, post):
        """★ 보내는 그 순간에 봐야 한다.

        기준 사진은 파일 손잡이(handle)로 실린다. 한 장씩 열고 닫으면 requests 가
        읽을 때는 이미 닫혀 있어 빈 이미지가 올라간다 — 그런데 generate() 가
        끝난 뒤에 보면 정상이어도 닫혀 있다(보내고 나서 닫는 게 맞다).
        그래서 post 가 불린 그 자리에서 확인한다.
        """
        seen = {}

        def capture(*_args, **kwargs):
            for _field, (name, handle, _mime) in kwargs["files"]:
                if name.startswith("item-"):
                    continue
                seen[name] = (handle.closed, handle.read(8))
            return Mock(status_code=200,
                        json=lambda: {"data": [{"b64_json": "result"}]})

        post.side_effect = capture
        vton.generate(model_id="man", items=[
            {"image": "data:image/png;base64,eA==", "category": "상의"}])

        self.assertEqual(len(seen), vton.REFERENCE_COUNT, "기준 사진이 덜 실렸다")
        for name, (closed, head) in seen.items():
            self.assertFalse(closed, f"{name} 이 닫힌 채로 실렸다")
            self.assertTrue(head.startswith(b"\x89PNG"), f"{name} 이 비었다")


if __name__ == "__main__":
    unittest.main()
