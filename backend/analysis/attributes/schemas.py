MODEL_LABELS_V1 = {

    "COLOR": [
        "BLACK",
        "WHITE",
        "GRAY",
        "BEIGE",
        "BROWN",
        "RED",
        "ORANGE",
        "YELLOW",
        "GREEN",
        "BLUE",
        "PURPLE",
        "PINK",
        "METALLIC",
    ],

    "MATERIAL": [
        "COTTON",
        "DENIM",
        "WOOL",
        "LEATHER",
        "FUR_SHEARLING",
        "LINEN_NATURAL",
        "SYNTHETIC",
        "REGENERATED",
        "KNIT_JERSEY",
        "SHEER_LIGHT",
        "TEXTURED_SPECIAL",
    ],

    "STYLE": [
        "CASUAL",
        "MINIMAL",
        "CLASSIC",
        "FEMININE",
        "STREET",
        "SPORTY",
        "VINTAGE",
        "WORK_FORMAL",
    ],

    "TPO": [
        "DAILY",
        "WORK",
        "SCHOOL",
        "DATE_SOCIAL",
        "FORMAL_EVENT",
        "TRAVEL_LEISURE",
        "SPORT_OUTDOOR",
        "HOME_RELAX",
    ],

}

ATTRIBUTE_WEIGHTS = {
    "COLOR": {
        "image": 0.90,
        "text": 0.10,
    },

    "MATERIAL": {
        "image": 0.60,
        "text": 0.40,
    },

    "STYLE": {
        "image": 0.55,
        "text": 0.45,
    },

    "TPO": {
        "image": 0.30,
        "text": 0.70,
    },
}