"""Reusable web-retrieval foundation primitives."""

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
from core.web_search_foundation import WebSearchCandidate


@dataclass(frozen=True)
class WebRetrievalPolicy:
    max_urls_fetched: int
    max_content_chars_per_url: int
    max_total_context_chars: int
    max_snippets: int
    max_retrieval_time_ms: int
    request_timeout_s: float


@dataclass(frozen=True)
class WebRetrievalSource:
    url: str
    title: str | None
    source_type: str
    source_origin: str
    retrieved_at: str
    snippet_count: int


@dataclass(frozen=True)
class WebRetrievalSnippet:
    url: str
    title: str | None
    text: str
    score: int


@dataclass(frozen=True)
class WebRetrievalOutcome:
    used: bool
    fetched_count: int
    extracted_snippet_count: int
    sources: list[WebRetrievalSource]
    snippets: list[WebRetrievalSnippet]
    warnings: list[str]
    fallback_reason: str | None
    policy: dict[str, object]


def build_web_retrieval_policy(
    *,
    max_urls_fetched: int = 4,
    max_content_chars_per_url: int = 24000,
    max_total_context_chars: int = 32000,
    max_snippets: int = 8,
    max_retrieval_time_ms: int = 7000,
    request_timeout_s: float = 3.5,
) -> WebRetrievalPolicy:
    return WebRetrievalPolicy(
        max_urls_fetched=max(1, min(max_urls_fetched, 8)),
        max_content_chars_per_url=max(500, min(max_content_chars_per_url, 120000)),
        max_total_context_chars=max(1000, min(max_total_context_chars, 180000)),
        max_snippets=max(1, min(max_snippets, 24)),
        max_retrieval_time_ms=max(500, min(max_retrieval_time_ms, 30000)),
        request_timeout_s=max(0.4, min(request_timeout_s, 10.0)),
    )


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def _extract_html_title(html: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
    if not match:
        return None
    title = _normalize_whitespace(unescape(re.sub(r"<[^>]+>", "", match.group(1))))
    return title or None


def _html_to_text(html: str) -> str:
    data = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
    data = re.sub(r"<style[^>]*>.*?</style>", " ", data, flags=re.I | re.S)
    data = re.sub(r"<noscript[^>]*>.*?</noscript>", " ", data, flags=re.I | re.S)
    data = re.sub(r"<[^>]+>", " ", data)
    data = unescape(data)
    return _normalize_whitespace(data)


def _question_terms(question: str) -> list[str]:
    terms = re.findall(r"[A-Za-z0-9_\-.]{3,}", question.lower())
    stop = {
        "the",
        "and",
        "for",
        "with",
        "der",
        "die",
        "das",
        "und",
        "ist",
        "ein",
        "eine",
        "where",
        "what",
        "wie",
        "wo",
        "welche",
        "which",
    }
    out: list[str] = []
    seen: set[str] = set()
    for item in terms:
        if item in stop or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out[:24]


def _score_line(line: str, terms: list[str]) -> int:
    if not line:
        return 0
    lowered = line.lower()
    score = 0
    for term in terms:
        if term in lowered:
            score += 2
    if any(token in lowered for token in ("typo3", "docs", "reference", "api", "manual")):
        score += 1
    return score


def _extract_snippets(text: str, *, question: str, max_snippets: int) -> list[tuple[str, int]]:
    terms = _question_terms(question)
    if not text:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for part in re.split(r"(?<=[.!?])\s+", text):
        piece = part.strip()
        if not piece:
            continue
        projected = current_len + len(piece) + (1 if current else 0)
        if projected > 360 and current:
            chunks.append(" ".join(current))
            current = [piece]
            current_len = len(piece)
            continue
        current.append(piece)
        current_len = projected
    if current:
        chunks.append(" ".join(current))

    scored: list[tuple[str, int]] = []
    for chunk in chunks:
        score = _score_line(chunk, terms)
        if score <= 0:
            continue
        scored.append((chunk[:500], score))

    if not scored and chunks:
        scored = [(item[:500], 1) for item in chunks[:2]]

    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:max_snippets]


def _host_from_url(raw: str) -> str:
    try:
        return parse.urlparse(raw).netloc.strip().lower()
    except Exception:
        return ""


def _fetch_html(url: str, *, timeout_s: float) -> str:
    req = request.Request(url, headers={"User-Agent": "Forge/1.0 (+https://forge.local)"}, method="GET")
    with request.urlopen(req, timeout=timeout_s) as resp:
        content_type = (resp.headers.get("Content-Type") or "").lower()
        if "html" not in content_type and "xml" not in content_type and content_type:
            return ""
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


def run_web_retrieval(
    *,
    question: str,
    candidates: list[WebSearchCandidate],
    allowed_hosts: list[str],
    policy: WebRetrievalPolicy,
    session: ExecutionSession | None = None,
    repo_root: Path | None = None,
) -> WebRetrievalOutcome:
    _ = repo_root
    warnings: list[str] = []
    if not candidates:
        return WebRetrievalOutcome(
            used=False,
            fetched_count=0,
            extracted_snippet_count=0,
            sources=[],
            snippets=[],
            warnings=["retrieval skipped: no search candidates"],
            fallback_reason="no candidates",
            policy={
                "max_urls_fetched": policy.max_urls_fetched,
                "max_content_chars_per_url": policy.max_content_chars_per_url,
                "max_total_context_chars": policy.max_total_context_chars,
                "max_snippets": policy.max_snippets,
                "max_retrieval_time_ms": policy.max_retrieval_time_ms,
                "request_timeout_s": policy.request_timeout_s,
            },
        )

    if session is not None:
        session.record_effect(EffectClass.READ_ONLY, f"web retrieval candidates={len(candidates)}")

    allowed = {item.strip().lower() for item in allowed_hosts if item.strip()}
    started = time.perf_counter()
    sources: list[WebRetrievalSource] = []
    snippets: list[WebRetrievalSnippet] = []
    fetched_count = 0
    total_chars = 0

    for candidate in candidates:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if elapsed_ms >= policy.max_retrieval_time_ms:
            warnings.append("retrieval time budget exhausted")
            break
        if fetched_count >= policy.max_urls_fetched:
            break
        if len(snippets) >= policy.max_snippets:
            break
        if total_chars >= policy.max_total_context_chars:
            warnings.append("max_total_context_chars reached")
            break

        host = _host_from_url(candidate.url)
        if allowed and host not in allowed:
            warnings.append(f"candidate skipped by host policy: {candidate.url}")
            continue

        try:
            remaining_s = max(0.3, (policy.max_retrieval_time_ms - elapsed_ms) / 1000.0)
            html = _fetch_html(candidate.url, timeout_s=min(policy.request_timeout_s, remaining_s))
        except (error.HTTPError, error.URLError, TimeoutError, OSError) as exc:
            warnings.append(f"retrieval fetch failed for {candidate.url}: {exc}")
            continue

        fetched_count += 1
        if not html:
            warnings.append(f"retrieval empty/non-html response for {candidate.url}")
            continue

        html_limited = html[: policy.max_content_chars_per_url]
        text = _html_to_text(html_limited)
        if not text:
            warnings.append(f"retrieval extraction produced no text for {candidate.url}")
            continue

        page_snippets = _extract_snippets(
            text,
            question=question,
            max_snippets=max(1, min(3, policy.max_snippets - len(snippets))),
        )
        if not page_snippets:
            warnings.append(f"retrieval produced no relevant snippet for {candidate.url}")
            continue

        title = _extract_html_title(html_limited) or candidate.title_hint
        retrieved_at = datetime.now(timezone.utc).isoformat()

        accepted_count = 0
        for snippet_text, score in page_snippets:
            if len(snippets) >= policy.max_snippets:
                break
            projected = total_chars + len(snippet_text)
            if projected > policy.max_total_context_chars:
                warnings.append("max_total_context_chars reached")
                break
            snippets.append(
                WebRetrievalSnippet(
                    url=candidate.url,
                    title=title,
                    text=snippet_text,
                    score=score,
                )
            )
            total_chars = projected
            accepted_count += 1

        sources.append(
            WebRetrievalSource(
                url=candidate.url,
                title=title,
                source_type=candidate.source_type,
                source_origin=candidate.source_origin,
                retrieved_at=retrieved_at,
                snippet_count=accepted_count,
            )
        )

    fallback_reason = None
    if not snippets:
        fallback_reason = "no retrieval snippets extracted"
        warnings.append("retrieval produced no snippets")

    return WebRetrievalOutcome(
        used=bool(snippets),
        fetched_count=fetched_count,
        extracted_snippet_count=len(snippets),
        sources=sources,
        snippets=snippets,
        warnings=warnings,
        fallback_reason=fallback_reason,
        policy={
            "max_urls_fetched": policy.max_urls_fetched,
            "max_content_chars_per_url": policy.max_content_chars_per_url,
            "max_total_context_chars": policy.max_total_context_chars,
            "max_snippets": policy.max_snippets,
            "max_retrieval_time_ms": policy.max_retrieval_time_ms,
            "request_timeout_s": policy.request_timeout_s,
            "total_context_chars": total_chars,
        },
    )
