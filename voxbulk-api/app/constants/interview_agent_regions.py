"""Regional metadata for English interview voice agents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InterviewRegionMeta:
    code: str
    label: str
    flag_emoji: str
    english_label: str
    sample_phrase_male: str
    sample_phrase_female: str
    market_zones: tuple[str, ...]


INTERVIEW_REGIONS: dict[str, InterviewRegionMeta] = {
    "GB": InterviewRegionMeta(
        code="GB",
        label="United Kingdom",
        flag_emoji="🇬🇧",
        english_label="British English",
        sample_phrase_male="Hello, this is Leo calling from the hiring team. Can you hear me clearly?",
        sample_phrase_female="Hello, this is Jode calling from the hiring team. Can you hear me clearly?",
        market_zones=("gb",),
    ),
    "SC": InterviewRegionMeta(
        code="SC",
        label="Scotland",
        flag_emoji="🏴",
        english_label="Scottish English",
        sample_phrase_male="Hello, this is Callum from the hiring team. Can you hear me alright?",
        sample_phrase_female="Hello, this is Fiona from the hiring team. Can you hear me alright?",
        market_zones=("gb",),
    ),
    "IE": InterviewRegionMeta(
        code="IE",
        label="Ireland",
        flag_emoji="🇮🇪",
        english_label="Irish English",
        sample_phrase_male="Hello, this is Sean from the hiring team. Can you hear me clearly?",
        sample_phrase_female="Hello, this is Niamh from the hiring team. Can you hear me clearly?",
        market_zones=("gb", "eu"),
    ),
    "US": InterviewRegionMeta(
        code="US",
        label="United States",
        flag_emoji="🇺🇸",
        english_label="US English",
        sample_phrase_male="Hi, this is Marcus calling from the hiring team. Can you hear me okay?",
        sample_phrase_female="Hi, this is Elena calling from the hiring team. Can you hear me okay?",
        market_zones=("us",),
    ),
    "CA": InterviewRegionMeta(
        code="CA",
        label="Canada",
        flag_emoji="🇨🇦",
        english_label="Canadian English",
        sample_phrase_male="Hello, this is Liam from the hiring team. Can you hear me clearly?",
        sample_phrase_female="Hello, this is Maya from the hiring team. Can you hear me clearly?",
        market_zones=("ca",),
    ),
    "AU": InterviewRegionMeta(
        code="AU",
        label="Australia",
        flag_emoji="🇦🇺",
        english_label="Australian English",
        sample_phrase_male="G'day, this is Jack from the hiring team. Can you hear me clearly?",
        sample_phrase_female="G'day, this is Chloe from the hiring team. Can you hear me clearly?",
        market_zones=("au",),
    ),
}


@dataclass(frozen=True)
class InterviewAgentSpec:
    slug: str
    name: str
    voice_label: str
    accent_region: str
    gender: str
    is_default_interview: bool = False
    telnyx_env_key: str = ""

    @property
    def telnyx_name(self) -> str:
        g = "M" if self.gender == "male" else "F"
        return f"VOXBULK Interview {self.accent_region} {self.voice_label} {g}"

    @property
    def voice_type_label(self) -> str:
        region = INTERVIEW_REGIONS[self.accent_region]
        gender_word = "male" if self.gender == "male" else "female"
        return f"{region.english_label} · professional {gender_word}"


INTERVIEW_ENGLISH_ROSTER: tuple[InterviewAgentSpec, ...] = (
    InterviewAgentSpec(
        slug="interview-gb-leo",
        name="interview_GB-Leo",
        voice_label="Leo",
        accent_region="GB",
        gender="male",
        is_default_interview=True,
        telnyx_env_key="INTERVIEW_TELNYX_ASSISTANT_ID_GB_LEO",
    ),
    InterviewAgentSpec(
        slug="interview-gb-jode",
        name="interview_GB-Jode",
        voice_label="Jode",
        accent_region="GB",
        gender="female",
        telnyx_env_key="INTERVIEW_TELNYX_ASSISTANT_ID_GB_JODE",
    ),
    InterviewAgentSpec(
        slug="interview-sc-callum",
        name="interview_SC-Callum",
        voice_label="Callum",
        accent_region="SC",
        gender="male",
        telnyx_env_key="INTERVIEW_TELNYX_ASSISTANT_ID_SC_MALE",
    ),
    InterviewAgentSpec(
        slug="interview-sc-fiona",
        name="interview_SC-Fiona",
        voice_label="Fiona",
        accent_region="SC",
        gender="female",
        telnyx_env_key="INTERVIEW_TELNYX_ASSISTANT_ID_SC_FEMALE",
    ),
    InterviewAgentSpec(
        slug="interview-ie-sean",
        name="interview_IE-Sean",
        voice_label="Sean",
        accent_region="IE",
        gender="male",
        telnyx_env_key="INTERVIEW_TELNYX_ASSISTANT_ID_IE_MALE",
    ),
    InterviewAgentSpec(
        slug="interview-ie-niamh",
        name="interview_IE-Niamh",
        voice_label="Niamh",
        accent_region="IE",
        gender="female",
        telnyx_env_key="INTERVIEW_TELNYX_ASSISTANT_ID_IE_FEMALE",
    ),
    InterviewAgentSpec(
        slug="interview-us-marcus",
        name="interview_US-Marcus",
        voice_label="Marcus",
        accent_region="US",
        gender="male",
        telnyx_env_key="INTERVIEW_TELNYX_ASSISTANT_ID_US_MALE",
    ),
    InterviewAgentSpec(
        slug="interview-us-elena",
        name="interview_US-Elena",
        voice_label="Elena",
        accent_region="US",
        gender="female",
        telnyx_env_key="INTERVIEW_TELNYX_ASSISTANT_ID_US_FEMALE",
    ),
    InterviewAgentSpec(
        slug="interview-ca-liam",
        name="interview_CA-Liam",
        voice_label="Liam",
        accent_region="CA",
        gender="male",
        telnyx_env_key="INTERVIEW_TELNYX_ASSISTANT_ID_CA_MALE",
    ),
    InterviewAgentSpec(
        slug="interview-ca-maya",
        name="interview_CA-Maya",
        voice_label="Maya",
        accent_region="CA",
        gender="female",
        telnyx_env_key="INTERVIEW_TELNYX_ASSISTANT_ID_CA_FEMALE",
    ),
    InterviewAgentSpec(
        slug="interview-au-jack",
        name="interview_AU-Jack",
        voice_label="Jack",
        accent_region="AU",
        gender="male",
        telnyx_env_key="INTERVIEW_TELNYX_ASSISTANT_ID_AU_MALE",
    ),
    InterviewAgentSpec(
        slug="interview-au-chloe",
        name="interview_AU-Chloe",
        voice_label="Chloe",
        accent_region="AU",
        gender="female",
        telnyx_env_key="INTERVIEW_TELNYX_ASSISTANT_ID_AU_FEMALE",
    ),
)


def region_meta_for_agent(agent: Any) -> InterviewRegionMeta | None:
    code = str(getattr(agent, "accent_region", None) or "").strip().upper()
    if code and code in INTERVIEW_REGIONS:
        return INTERVIEW_REGIONS[code]
    blob = " ".join(
        str(getattr(agent, attr, "") or "")
        for attr in ("slug", "name", "voice_label")
    ).upper()
    for code, meta in INTERVIEW_REGIONS.items():
        if f"_{code}-" in blob or f"-{code}-" in blob.lower() or blob.startswith(f"INTERVIEW_{code}"):
            return meta
    return INTERVIEW_REGIONS.get("GB")


def accent_region_from_org_country(country: str | None) -> str:
    key = str(country or "").strip().lower()
    if key in {"scotland"}:
        return "SC"
    if key in {"ireland", "republic of ireland", "eire", "éire"}:
        return "IE"
    if key in {"united states", "usa", "us", "u.s.", "u.s.a."}:
        return "US"
    if key in {"canada", "ca"}:
        return "CA"
    if key in {"australia", "au"}:
        return "AU"
    return "GB"


def voice_env_key_for_region_gender(region: str, gender: str) -> str:
    r = str(region or "GB").strip().upper()
    g = "MALE" if str(gender or "").lower() == "male" else "FEMALE"
    return f"INTERVIEW_VOICE_{r}_{g}"
