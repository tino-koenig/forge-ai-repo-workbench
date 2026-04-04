"""Reusable web-search foundation primitives."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
import re
import time
from urllib import error, parse, request

from core.capability_model import EffectClass
from core.effects import ExecutionSession
from core.framework_profiles import FrameworkProfile


DUCKDUCKGO_HTML_ENDPOINT = "https://duckduckgo.com/html/"
DEFAULT_DOCS_ALLOWLIST = ["docs.typo3.org", "api.typo3.org"]


@dataclass(frozen=True)
class WebSearchPolicy:
    allowed_hosts: list[str]
    entrypoints: list[str]
    max_queries: int
    max_urls_considered: int
    max_urls_returned: int
    max_search_time_ms: int
    provider: str
    freshness_mode: str


@dataclass(frozen=True)
class WebSearchCandidate:
    url: str
    host: str
    title_hint: str | None
    source_type: str
    source_origin: str
    rank: int
    discovery_query: str


@dataclass(frozen=True)
class WebSearchOutcome:
    used: bool
    query_plan: list[str]
    candidates: list[WebSearchCandidate]
    warnings: list[str]
    fallback_reason: str | None
    provider: str
    policy: dict[str, object]
    freshness: dict[str, object]


def _host_from_url(raw: str) -> str:
    try:
        return parse.urlparse(raw).netloc.strip().lower()
    except Exception:
        return ""


def _normalize_url(raw: str) -> str | None:
    token = raw.strip()
    if not token:
        return None
    parsed = parse.urlparse(token)
    if parsed.scheme not in {"http", "https"}:
        return None
    if not parsed.netloc:
        return None
    cleaned = parse.urlunparse(
        (
            parsed.scheme,
            parsed.netloc.lower(),
            parsed.path or "/",
            "",
            parsed.query,
            "",
        )
    )
    return cleaned


def build_web_search_policy(
    *,
    framework_profile: FrameworkProfile | None,
    freshness_mode: str = "docs",
    max_queries: int = 3,
    max_urls_considered: int = 20,
    max_urls_returned: int = 8,
    max_search_time_ms: int = 3500,
) -> tuple[WebSearchPolicy, list[str]]:
    warnings: list[str] = []
    allowed_hosts: list[str] = []
    entrypoints: list[str] = []
    if framework_profile is not None:
        allowed_hosts.extend(framework_profile.docs_allowlist_hosts)
        entrypoints.extend(framework_profile.docs_entrypoints)
        if not allowed_hosts:
            derived_hosts = [_host_from_url(item) for item in framework_profile.docs_entrypoints]
            allowed_hosts.extend([item for item in derived_hosts if item])
            if not allowed_hosts:
                allowed_hosts.extend(DEFAULT_DOCS_ALLOWLIST)
                warnings.append("framework profile has no docs allowlist hosts configured; using fallback allowlist")
    else:
        allowed_hosts.extend(DEFAULT_DOCS_ALLOWLIST)
        warnings.append("no framework profile selected; using fallback docs allowlist")

    dedup_hosts: list[str] = []
    seen_hosts: set[str] = set()
    for host in allowed_hosts:
        normalized = host.strip().lower()
        if not normalized or normalized in seen_hosts:
            continue
        seen_hosts.add(normalized)
        dedup_hosts.append(normalized)

    dedup_entrypoints: list[str] = []
    seen_entrypoints: set[str] = set()
    for entry in entrypoints:
        normalized = _normalize_url(entry)
        if normalized is None or normalized in seen_entrypoints:
            continue
        seen_entrypoints.add(normalized)
        dedup_entrypoints.append(normalized)

    policy = WebSearchPolicy(
        allowed_hosts=dedup_hosts,
        entrypoints=dedup_entrypoints,
        max_queries=max(1, min(max_queries, 6)),
        max_urls_considered=max(1, min(max_urls_considered, 100)),
        max_urls_returned=max(1, min(max_urls_returned, 20)),
        max_search_time_ms=max(300, min(max_search_time_ms, 15000)),
        provider="duckduckgo_html",
        freshness_mode="latest" if freshness_mode == "latest" else "docs",
    )
    return policy, warnings


def _build_query_plan(question: str, policy: WebSearchPolicy) -> tuple[list[str], list[str]]:
    raw = " ".join(question.strip().split())
    if not raw:
        return [], []
    plan: list[str] = [raw]
    recency_queries: list[str] = []
    if policy.freshness_mode == "latest":
        year = datetime.now(timezone.utc).year
        recency_queries.extend([f"{raw} latest", f"{raw} {year}"])
        plan.extend(recency_queries)
    for entry in policy.entrypoints:
        host = _host_from_url(entry)
        if not host:
            continue
        if policy.freshness_mode == "latest":
            plan.append(f"site:{host} {raw} latest")
        else:
            plan.append(f"site:{host} {raw}")
    for host in policy.allowed_hosts[: max(0, policy.max_queries - 1)]:
        if policy.freshness_mode == "latest":
            plan.append(f"site:{host} {raw} latest")
        else:
            plan.append(f"site:{host} {raw}")
    deduped: list[str] = []
    seen: set[str] = set()
    for query in plan:
        normalized = query.strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
        if len(deduped) >= policy.max_queries:
            break
    recency_used = [item for item in deduped if any(token in item.lower() for token in (" latest", str(datetime.now(timezone.utc).year)))]
    return deduped, recency_used


def _extract_duckduckgo_result_url(href: str) -> str | None:
    direct = _normalize_url(href)
    if direct is not None:
        return direct
    parsed = parse.urlparse(href)
    params = parse.parse_qs(parsed.query)
    uddg = params.get("uddg", [])
    if not uddg:
        return None
    return _normalize_url(unescape(uddg[0]))


def _search_duckduckgo_html(
    query: str,
    *,
    timeout_s: float,
) -> list[tuple[str, str | None]]:
    url = DUCKDUCKGO_HTML_ENDPOINT + "?" + parse.urlencode({"q": query})
    req = request.Request(url, headers={"User-Agent": "Forge/1.0 (+https://forge.local)"}, method="GET")
    with request.urlopen(req, timeout=timeout_s) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    results: list[tuple[str, str | None]] = []
    for match in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, flags=re.I | re.S):
        href = unescape(match.group(1))
        title_raw = re.sub(r"<[^>]+>", "", match.group(2))
        title = " ".join(unescape(title_raw).split()) or None
        resolved = _extract_duckduckgo_result_url(href)
        if resolved is None:
            continue
        results.append((resolved, title))
        if len(results) >= 30:
            break
    return results


def run_web_search(
    *,
    question: str,
    policy: WebSearchPolicy,
    session: ExecutionSession | None = None,
    repo_root: Path | None = None,
) -> WebSearchOutcome:
    _ = repo_root
    warnings: list[str] = []
    if not policy.allowed_hosts:
        return WebSearchOutcome(
            used=False,
            query_plan=[],
            candidates=[],
            warnings=["search skipped: no allowed hosts configured", *warnings],
            fallback_reason="no allowed hosts",
            provider=policy.provider,
            policy={
                "allowed_hosts": policy.allowed_hosts,
                "entrypoints": policy.entrypoints,
                "max_queries": policy.max_queries,
                "max_urls_considered": policy.max_urls_considered,
                "max_urls_returned": policy.max_urls_returned,
                "max_search_time_ms": policy.max_search_time_ms,
                "freshness_mode": policy.freshness_mode,
            },
            freshness={"mode": policy.freshness_mode, "recency_query_variants": []},
        )

    plan, recency_variants = _build_query_plan(question, policy)
    if not plan:
        return WebSearchOutcome(
            used=False,
            query_plan=[],
            candidates=[],
            warnings=["search skipped: empty query plan"],
            fallback_reason="empty query",
            provider=policy.provider,
            policy={
                "allowed_hosts": policy.allowed_hosts,
                "entrypoints": policy.entrypoints,
                "max_queries": policy.max_queries,
                "max_urls_considered": policy.max_urls_considered,
                "max_urls_returned": policy.max_urls_returned,
                "max_search_time_ms": policy.max_search_time_ms,
                "freshness_mode": policy.freshness_mode,
            },
            freshness={"mode": policy.freshness_mode, "recency_query_variants": recency_variants},
        )

    if session is not None:
        session.record_effect(EffectClass.READ_ONLY, f"web search queries={len(plan)} provider={policy.provider}")

    started = time.perf_counter()
    ranked: list[WebSearchCandidate] = []
    seen_urls: set[str] = set()
    considered = 0
    try:
        for query in plan:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            if elapsed_ms >= policy.max_search_time_ms:
                warnings.append("search time budget exhausted")
                break
            remaining_s = max(0.2, (policy.max_search_time_ms - elapsed_ms) / 1000.0)
            raw_hits = _search_duckduckgo_html(query, timeout_s=min(3.5, remaining_s))
            for url, title in raw_hits:
                considered += 1
                if considered > policy.max_urls_considered:
                    warnings.append("max_urls_considered reached")
                    break
                host = _host_from_url(url)
                if host not in policy.allowed_hosts:
                    continue
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                ranked.append(
                    WebSearchCandidate(
                        url=url,
                        host=host,
                        title_hint=title,
                        source_type="web_docs",
                        source_origin="web_search",
                        rank=len(ranked) + 1,
                        discovery_query=query,
                    )
                )
                if len(ranked) >= policy.max_urls_returned:
                    break
            if considered > policy.max_urls_considered or len(ranked) >= policy.max_urls_returned:
                break
    except (error.HTTPError, error.URLError, TimeoutError, OSError) as exc:
        return WebSearchOutcome(
            used=False,
            query_plan=plan,
            candidates=[],
            warnings=warnings,
            fallback_reason=f"search provider failure: {exc}",
            provider=policy.provider,
            policy={
                "allowed_hosts": policy.allowed_hosts,
                "entrypoints": policy.entrypoints,
                "max_queries": policy.max_queries,
                "max_urls_considered": policy.max_urls_considered,
                "max_urls_returned": policy.max_urls_returned,
                "max_search_time_ms": policy.max_search_time_ms,
                "freshness_mode": policy.freshness_mode,
            },
            freshness={"mode": policy.freshness_mode, "recency_query_variants": recency_variants},
        )

    fallback_reason = None
    if not ranked:
        fallback_reason = "no allowed web-doc candidates found"
        warnings.append("no allowed candidates from search results")

    return WebSearchOutcome(
        used=bool(ranked),
        query_plan=plan,
        candidates=ranked,
        warnings=warnings,
        fallback_reason=fallback_reason,
        provider=policy.provider,
        policy={
            "allowed_hosts": policy.allowed_hosts,
            "entrypoints": policy.entrypoints,
            "max_queries": policy.max_queries,
            "max_urls_considered": policy.max_urls_considered,
            "max_urls_returned": policy.max_urls_returned,
            "max_search_time_ms": policy.max_search_time_ms,
            "freshness_mode": policy.freshness_mode,
            "considered_count": considered,
        },
        freshness={"mode": policy.freshness_mode, "recency_query_variants": recency_variants},
    )
