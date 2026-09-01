from __future__ import annotations

from .client import MusinsaClient
from .constants import DEFAULT_REVIEW_PAGE_SIZE, PRODUCT_BASE_URL, REVIEW_LIST_API_URL, REVIEW_SUMMARY_API_URL
from .images import normalize_image_url


class MusinsaReviewCollector:
    def __init__(self, client: MusinsaClient):
        self.client = client

    def collect_summary(self, goods_no: int) -> dict:
        body = self.client.get_json(REVIEW_SUMMARY_API_URL.format(goods_no=goods_no), headers={"Referer": PRODUCT_BASE_URL.format(goods_no=goods_no)})
        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        return {
            "total_count": data.get("totalCount"),
            "general_count": data.get("generalCount"),
            "photo_count": data.get("photoCount"),
            "satisfaction_score": data.get("satisfactionScore"),
        }

    def collect_reviews(self, goods_no: int, *, limit: int = DEFAULT_REVIEW_PAGE_SIZE, sort: str = "up_cnt_desc") -> list[dict]:
        if limit <= 0: return []
        page_size = min(limit, 100)
        page = 0
        result = []
        while len(result) < limit:
            body = self.client.get_json(REVIEW_LIST_API_URL, params={
                "page": page, "pageSize": page_size, "goodsNo": goods_no, "sort": sort,
                "selectedSimilarNo": goods_no, "myFilter": "false", "hasPhoto": "false", "isExperience": "false",
            }, headers={"Referer": PRODUCT_BASE_URL.format(goods_no=goods_no)})
            data = body.get("data") if isinstance(body.get("data"), dict) else {}
            items = data.get("list") or []
            if not items: break
            for item in items:
                if not isinstance(item, dict): continue
                profile = item.get("userProfileInfo") if isinstance(item.get("userProfileInfo"), dict) else {}
                survey = item.get("reviewSurveySatisfaction") if isinstance(item.get("reviewSurveySatisfaction"), dict) else {}
                survey_values = {}
                for q in survey.get("questions") or []:
                    if not isinstance(q, dict): continue
                    answers = q.get("answers") or []
                    vals = [a.get("answerShortText") for a in answers if isinstance(a, dict) and a.get("answerShortText")]
                    if q.get("attribute") and vals: survey_values[q["attribute"]] = vals
                images = []
                for image in item.get("images") or []:
                    if isinstance(image, dict):
                        url = normalize_image_url(image.get("imageUrl"))
                        if url: images.append(url)
                result.append({
                    "review_id": item.get("no"), "review_type": item.get("type"), "content": item.get("content"),
                    "grade": item.get("grade"), "goods_option": item.get("goodsOption"), "like_count": item.get("likeCount"),
                    "created_at": item.get("createDate"), "images": images,
                    "reviewer": {"sex": profile.get("reviewSex"), "height": profile.get("userHeight"), "weight": profile.get("userWeight")},
                    "survey": survey_values,
                })
                if len(result) >= limit: break
            total_pages = ((data.get("page") or {}).get("totalPages") if isinstance(data.get("page"), dict) else None)
            page += 1
            if total_pages is not None and page >= total_pages: break
        return result[:limit]
