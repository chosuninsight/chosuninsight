import re
from dataclasses import dataclass
from typing import Callable, Any


SITE_LINK_QUERY_TERMS = [
    "사이트", "홈페이지", "누리집", "링크", "url", "URL", "주소",
    "접속", "들어가", "바로가기", "찾아가", "방문",
]
SITE_LINK_STOPWORDS = [
    "조선대학교", "조선대", "공식", "사이트", "홈페이지", "누리집", "링크", "url", "주소",
    "알려줘", "알려", "뭐야", "어디야", "어디", "가르쳐줘", "바로가기", "페이지",
    "확인", "해줘", "좀", "관련", "대한",
]
SITE_LINK_TARGET_TERMS = ["학과", "학부", "대학", "전공", "사업단"]
SITE_LINK_PARTICLE_SUFFIXES = ("은", "는", "이", "가", "을", "를", "도", "과", "와", "에", "의", "요")


@dataclass(frozen=True)
class SiteLinkMatch:
    item: dict[str, Any]
    score: int
    alias: str


@dataclass(frozen=True)
class SiteLinkResolution:
    matches: list[SiteLinkMatch]
    is_link_context: bool
    explicit_request: bool


@dataclass(frozen=True)
class _AliasRecord:
    item: dict[str, Any]
    alias: str
    normalized_alias: str


class DepartmentSiteResolver:
    def __init__(
        self,
        items: list[dict[str, Any]],
        focus_rules: dict[str, list[str]],
        normalizer: Callable[[str], str],
    ):
        self.items = items
        self.focus_rules = focus_rules
        self.normalizer = normalizer
        self.records = self._build_records()

    def is_link_request(self, question: str) -> bool:
        normalized = self.normalizer(str(question or "")).lower()
        return any(term.lower() in normalized for term in SITE_LINK_QUERY_TERMS)

    def is_catalog_link_request(self, question: str) -> bool:
        normalized = self._normalize(question)
        return self.is_link_request(question) and any(
            self._normalize(term) in normalized
            for term in SITE_LINK_TARGET_TERMS
        )

    def has_recent_link_context(self, history_text: str) -> bool:
        normalized = self.normalizer(str(history_text or "")).lower()
        return (
            any(term.lower() in normalized for term in SITE_LINK_QUERY_TERMS)
            or bool(re.search(r"https?://[^\s)\]]+", str(history_text or ""), re.IGNORECASE))
        )

    def resolve(self, question: str, history_text: str = "") -> SiteLinkResolution | None:
        explicit_request = self.is_link_request(question)
        is_link_context = explicit_request or self.has_recent_link_context(history_text)
        if not is_link_context:
            return None

        matches = self.match_question(question)
        if not matches:
            return SiteLinkResolution(matches=[], is_link_context=True, explicit_request=explicit_request)
        return SiteLinkResolution(
            matches=self._select_matches(matches),
            is_link_context=True,
            explicit_request=explicit_request,
        )

    def match_question(self, question: str) -> list[SiteLinkMatch]:
        query_text = self._clean_query(question)
        if not query_text:
            return []

        token_variants = self._query_token_variants(question)
        matches = []
        for record in self.records:
            score = 0
            if self._alias_matches_query(record.normalized_alias, query_text, token_variants):
                score = 1000 + len(record.normalized_alias)
            else:
                token_scores = [
                    len(token)
                    for token in token_variants
                    if token in record.normalized_alias
                ]
                score = max(token_scores, default=0)

            if score > 0:
                matches.append(SiteLinkMatch(record.item, score, record.alias))
        return sorted(matches, key=lambda match: (match.score, len(match.alias)), reverse=True)

    def select_matches(self, matches: list[SiteLinkMatch]) -> list[SiteLinkMatch]:
        return self._select_matches(matches)

    def _select_matches(self, matches: list[SiteLinkMatch]) -> list[SiteLinkMatch]:
        if not matches:
            return []

        selected = []
        seen_urls = set()
        top_score = matches[0].score

        for match in matches:
            url = str(match.item.get("url링크", "")).strip()
            if not url or url in seen_urls:
                continue
            if top_score >= 1000 and match.score != top_score:
                continue
            selected.append(match)
            seen_urls.add(url)
            if top_score < 1000:
                break

        return selected

    def _build_records(self) -> list[_AliasRecord]:
        records = []
        seen = set()

        for item in self.items:
            if not isinstance(item, dict) or not item.get("사이트명") or not item.get("url링크"):
                continue
            for alias in self._aliases_for_site(str(item["사이트명"])):
                normalized_alias = self._normalize(alias)
                if not normalized_alias:
                    continue
                key = (str(item["url링크"]), normalized_alias)
                if key in seen:
                    continue
                seen.add(key)
                records.append(_AliasRecord(item=item, alias=alias, normalized_alias=normalized_alias))

        return records

    def _aliases_for_site(self, site_name: str) -> list[str]:
        aliases = set()

        def add(value: str):
            value = str(value or "").strip()
            if not value:
                return
            aliases.add(value)
            if value.endswith("대학") and len(value) > 2:
                aliases.add(value[:-1])

        add(site_name)
        for part in re.split(r"[()ㆍ·/]", site_name):
            add(part)

        normalized_site = self._normalize(site_name)
        for canonical, focus_aliases in self.focus_rules.items():
            focus_names = [canonical, *focus_aliases]
            if any(self._normalize(name) in normalized_site for name in focus_names):
                for name in focus_names:
                    add(name)

        return sorted(aliases, key=len, reverse=True)

    def _clean_query(self, question: str) -> str:
        normalized = self._normalize(question)
        for word in [*SITE_LINK_QUERY_TERMS, *SITE_LINK_STOPWORDS]:
            normalized = normalized.replace(self._normalize(word), "")
        return normalized

    def _query_token_variants(self, question: str) -> list[str]:
        generic_tokens = {self._normalize(term) for term in [*SITE_LINK_STOPWORDS, *SITE_LINK_TARGET_TERMS]}
        variants = []
        for token in re.findall(r"[0-9A-Za-z가-힣]+", self.normalizer(str(question or "")).lower()):
            normalized = self._normalize(token)
            if not normalized or normalized in generic_tokens:
                continue
            variants.append(normalized)
            for suffix in SITE_LINK_PARTICLE_SUFFIXES:
                normalized_suffix = self._normalize(suffix)
                if normalized.endswith(normalized_suffix) and len(normalized) > len(normalized_suffix) + 1:
                    variants.append(normalized[:-len(normalized_suffix)])
        return [variant for variant in dict.fromkeys(variants) if variant and variant not in generic_tokens]

    def _alias_matches_query(self, alias: str, query_text: str, token_variants: list[str]) -> bool:
        if alias == query_text or alias in token_variants:
            return True

        for suffix in SITE_LINK_PARTICLE_SUFFIXES:
            normalized_suffix = self._normalize(suffix)
            if query_text == f"{alias}{normalized_suffix}":
                return True
            if f"{alias}{normalized_suffix}" in token_variants:
                return True

        return False

    def _normalize(self, text: str) -> str:
        normalized = self.normalizer(str(text or "")).lower()
        normalized = normalized.replace("ㆍ", "").replace("·", "").replace("-", "")
        return re.sub(r"[^0-9a-z가-힣]+", "", normalized)
