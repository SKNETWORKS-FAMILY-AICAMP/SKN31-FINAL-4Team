# backend/analysis/attributes/prompts.py


LABEL_DESCRIPTIONS = {
    # COLOR
    "BLACK": "black colored fashion item",
    "WHITE": "white ivory or cream colored fashion item",
    "GRAY": "gray charcoal or ash colored fashion item",
    "BEIGE": "beige camel sand or neutral colored fashion item",
    "BROWN": "brown chocolate mocha colored fashion item",
    "RED": "red burgundy wine colored fashion item",
    "ORANGE": "orange apricot colored fashion item",
    "YELLOW": "yellow lemon mustard colored fashion item",
    "GREEN": "green olive khaki sage colored fashion item",
    "BLUE": "blue navy sky blue indigo colored fashion item",
    "PURPLE": "purple lavender lilac colored fashion item",
    "PINK": "pink rose coral peach colored fashion item",
    "METALLIC": "gold silver or metallic colored fashion item",

    # MATERIAL
    "COTTON": "fashion item made of cotton fabric",
    "DENIM": "fashion item made of denim fabric",
    "WOOL": "fashion item made of wool cashmere or wool blend",
    "LEATHER": "fashion item made of leather suede or faux leather",
    "FUR_SHEARLING": "fashion item made of fur fleece or shearling",
    "LINEN_NATURAL": "fashion item made of linen hemp or natural fiber",
    "SYNTHETIC": "fashion item made of polyester nylon acrylic or synthetic fabric",
    "REGENERATED": "fashion item made of rayon viscose modal tencel or regenerated fiber",
    "KNIT_JERSEY": "knitted jersey or sweatshirt fabric fashion item",
    "SHEER_LIGHT": "fashion item made of chiffon lace mesh or sheer lightweight fabric",
    "TEXTURED_SPECIAL": "fashion item with velvet tweed corduroy satin jacquard or textured fabric",

    # STYLE
    "CASUAL": "casual everyday relaxed fashion style",
    "MINIMAL": "minimal clean simple fashion style",
    "CLASSIC": "classic timeless preppy fashion style",
    "FEMININE": "feminine romantic girlish fashion style",
    "STREET": "streetwear urban fashion style",
    "SPORTY": "sporty athletic outdoor fashion style",
    "VINTAGE": "vintage retro y2k grunge fashion style",
    "WORK_FORMAL": "formal office business chic fashion style",

    # TPO
    "DAILY": "fashion suitable for casual daily everyday wear",
    "WORK": "fashion suitable for work office business or interview",
    "SCHOOL": "fashion suitable for school university or campus",
    "DATE_SOCIAL": "fashion suitable for dates parties concerts or social gatherings",
    "FORMAL_EVENT": "fashion suitable for weddings ceremonies or formal events",
    "TRAVEL_LEISURE": "fashion suitable for travel vacation airport or leisure",
    "SPORT_OUTDOOR": "fashion suitable for sports hiking camping golf or outdoor activities",
    "HOME_RELAX": "fashion suitable for home relaxing or loungewear",
}


def build_label_prompt(label: str) -> str:
    return LABEL_DESCRIPTIONS.get(
        label,
        f"a fashion item representing {label.lower()}",
    )


def build_product_text(
    product_name: str | None = None,
    description: str | None = None,
    category: str | None = None,
    brand: str | None = None,
) -> str:

    values = []

    if product_name:
        values.append(f"상품명: {product_name}")

    if category:
        values.append(f"카테고리: {category}")

    if brand:
        values.append(f"브랜드: {brand}")

    if description:
        values.append(f"상품 설명: {description}")

    return "\n".join(values)