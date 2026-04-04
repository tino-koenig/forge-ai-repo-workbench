from __future__ import annotations

from pathlib import Path

from core.capability_model import Capability, CommandRequest
from core.effects import ExecutionSession
from core.framework_profiles import load_framework_registry, select_framework_profile
from core.llm_integration import maybe_refine_summary, provenance_section, resolve_settings
from core.output_contracts import build_contract, emit_contract_json
from core.output_views import is_full, resolve_view
from core.web_retrieval_foundation import build_web_retrieval_policy, run_web_retrieval
from core.web_search_foundation import build_web_search_policy, run_web_search


def _resolve_runtime_bool(args, key: str, default: bool) -> tuple[bool, str]:
    values = getattr(args, "runtime_settings_values", {})
    sources = getattr(args, "runtime_settings_sources", {})
    raw = values.get(key) if isinstance(values, dict) else None
    source = str(sources.get(key) or "default") if isinstance(sources, dict) else "default"
    if raw is None:
        return default, "default"
    if isinstance(raw, bool):
        return raw, source
    lowered = str(raw).strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True, source
    if lowered in {"0", "false", "no", "off"}:
        return False, source
    return default, "default"


def run(request: CommandRequest, args, session: ExecutionSession) -> int:
    _ = session
    is_json = args.output_format == "json"
    view = resolve_view(args)
    question = request.payload.strip()
    repo_root = Path(args.repo_root).resolve()

    ask_preset = str(getattr(args, "ask_preset", "") or "auto")
    ask_command = str(getattr(args, "ask_command", "") or "ask")
    ask_guided = bool(getattr(args, "ask_guided", False))
    requested_framework_profile = getattr(args, "framework_profile", None)

    framework_registry = load_framework_registry(repo_root, session)
    framework_profile, framework_profile_id, framework_warnings = select_framework_profile(
        framework_registry,
        requested_framework_profile,
    )
    search_outcome = None
    search_warnings: list[str] = []
    search_policy = None
    retrieval_outcome = None
    retrieval_policy = None
    retrieval_warnings: list[str] = []
    access_web_enabled, access_web_source = _resolve_runtime_bool(args, "access.web", False)
    web_policy_blocked_reason = None
    if ask_preset in {"docs", "latest"}:
        if not access_web_enabled:
            web_policy_blocked_reason = "web access denied by runtime policy (access.web=false)"
            search_warnings.append(web_policy_blocked_reason)
            retrieval_warnings.append(web_policy_blocked_reason)
        else:
            search_policy, policy_warnings = build_web_search_policy(framework_profile=framework_profile)
            search_warnings.extend(policy_warnings)
            search_outcome = run_web_search(
                question=question,
                policy=search_policy,
                session=session,
                repo_root=repo_root,
            )
            search_warnings.extend(search_outcome.warnings)
            retrieval_policy = build_web_retrieval_policy()
            retrieval_outcome = run_web_retrieval(
                question=question,
                candidates=search_outcome.candidates,
                allowed_hosts=list(search_policy.allowed_hosts),
                policy=retrieval_policy,
                session=session,
                repo_root=repo_root,
            )
            retrieval_warnings.extend(retrieval_outcome.warnings)

    deterministic_summary = "No LLM answer available for this free ask question."
    if retrieval_outcome is not None and retrieval_outcome.used and retrieval_outcome.sources:
        top_urls = ", ".join(item.url for item in retrieval_outcome.sources[:3])
        deterministic_summary = f"Retrieved documentation evidence from: {top_urls}."
    elif search_outcome is not None and search_outcome.candidates:
        top_urls = ", ".join(item.url for item in search_outcome.candidates[:3])
        deterministic_summary = f"Top documentation URLs discovered: {top_urls}."
    elif ask_preset in {"docs", "latest"}:
        deterministic_summary = "No documentation evidence could be retrieved from allowed web sources."
    task_context = [question]
    task_context.append(f"ask_preset={ask_preset}")
    if requested_framework_profile:
        task_context.append(f"framework_profile={requested_framework_profile}")
    if ask_guided:
        task_context.append("guided=true")
    if search_outcome is not None:
        task_context.append(f"web_search_used={search_outcome.used}")
        for item in search_outcome.candidates[:5]:
            task_context.append(f"web_source={item.url}")
    if retrieval_outcome is not None:
        task_context.append(f"web_retrieval_used={retrieval_outcome.used}")
        for item in retrieval_outcome.snippets[:6]:
            task_context.append(f"web_snippet={item.text}")
    llm_task = "\n".join(task_context)

    search_evidence = []
    if retrieval_outcome is not None and retrieval_outcome.snippets:
        for item in retrieval_outcome.snippets[:8]:
            search_evidence.append(
                {
                    "path": item.url,
                    "line": 0,
                    "text": item.text,
                    "source_type": "web_docs",
                    "source_origin": "web_retrieval",
                }
            )
    elif search_outcome is not None:
        for item in search_outcome.candidates[:8]:
            search_evidence.append(
                {
                    "path": item.url,
                    "line": 0,
                    "text": item.title_hint or item.url,
                    "source_type": item.source_type,
                    "source_origin": item.source_origin,
                }
            )

    llm_settings = resolve_settings(args, repo_root)
    llm_outcome = maybe_refine_summary(
        capability=Capability.ASK,
        profile=request.profile,
        task=llm_task,
        deterministic_summary=deterministic_summary,
        evidence=search_evidence,
        settings=llm_settings,
        repo_root=repo_root,
    )

    summary = llm_outcome.summary if llm_outcome.summary.strip() else deterministic_summary
    uncertainty = [
        "Ask mode is a free LLM question and does not perform repository file search.",
    ]
    if search_outcome is None or not search_outcome.used:
        uncertainty.append("No web-search evidence anchors were available for ask output.")
    uncertainty.extend(llm_outcome.uncertainty_notes)
    if ask_guided:
        uncertainty.append("--guided is reserved for a later rollout and is currently not interactive.")
    for warning in framework_warnings:
        uncertainty.append(f"Framework profile warning: {warning}")
    for warning in search_warnings:
        uncertainty.append(f"Web search warning: {warning}")
    for warning in retrieval_warnings:
        uncertainty.append(f"Web retrieval warning: {warning}")
    if search_outcome is not None and search_outcome.fallback_reason:
        uncertainty.append(f"Web search fallback: {search_outcome.fallback_reason}")
    if retrieval_outcome is not None and retrieval_outcome.fallback_reason:
        uncertainty.append(f"Web retrieval fallback: {retrieval_outcome.fallback_reason}")
    if llm_outcome.usage.get("fallback_reason"):
        uncertainty.append(f"LLM fallback: {llm_outcome.usage['fallback_reason']}")

    sections: dict[str, object] = {
        "ask": {
            "command": ask_command,
            "preset": ask_preset,
            "guided_requested": ask_guided,
            "framework_profile_requested": requested_framework_profile,
            "framework_profile_resolved": framework_profile_id,
            "mode": "docs_web_search" if ask_preset in {"docs", "latest"} else "free_llm_question",
            "access_policy": {
                "access_web_enabled": access_web_enabled,
                "access_web_source": access_web_source,
                "web_policy_blocked": bool(web_policy_blocked_reason),
                "blocked_reason": web_policy_blocked_reason,
            },
            "search": (
                {
                    "used": bool(search_outcome.used) if search_outcome is not None else False,
                    "provider": search_outcome.provider if search_outcome is not None else None,
                    "fallback_reason": search_outcome.fallback_reason if search_outcome is not None else None,
                    "policy": search_outcome.policy if search_outcome is not None else None,
                    "query_plan": search_outcome.query_plan if search_outcome is not None else [],
                    "candidates": [
                        {
                            "url": item.url,
                            "host": item.host,
                            "title_hint": item.title_hint,
                            "source_type": item.source_type,
                            "source_origin": item.source_origin,
                            "rank": item.rank,
                            "discovery_query": item.discovery_query,
                        }
                        for item in (search_outcome.candidates if search_outcome is not None else [])
                    ],
                }
                if ask_preset in {"docs", "latest"}
                else None
            ),
            "retrieval": (
                {
                    "used": bool(retrieval_outcome.used) if retrieval_outcome is not None else False,
                    "fetched_count": retrieval_outcome.fetched_count if retrieval_outcome is not None else 0,
                    "extracted_snippet_count": (
                        retrieval_outcome.extracted_snippet_count if retrieval_outcome is not None else 0
                    ),
                    "fallback_reason": retrieval_outcome.fallback_reason if retrieval_outcome is not None else None,
                    "policy": retrieval_outcome.policy if retrieval_outcome is not None else None,
                    "sources": [
                        {
                            "url": item.url,
                            "title": item.title,
                            "source_type": item.source_type,
                            "source_origin": item.source_origin,
                            "retrieved_at": item.retrieved_at,
                            "snippet_count": item.snippet_count,
                        }
                        for item in (retrieval_outcome.sources if retrieval_outcome is not None else [])
                    ],
                    "citations": [item.url for item in (retrieval_outcome.sources if retrieval_outcome is not None else [])],
                }
                if ask_preset in {"docs", "latest"}
                else None
            ),
        },
        "framework_profile": {
            "requested": requested_framework_profile,
            "resolved": framework_profile_id,
            "config_path": str(framework_registry.config_path),
            "config_present": framework_registry.exists,
            "default_profile": framework_registry.default_profile,
            "warnings": framework_warnings,
            "framework_id": framework_profile.profile_id if framework_profile is not None else None,
            "framework_version": framework_profile.version if framework_profile is not None else None,
            "docs_allowlist_hosts": framework_profile.docs_allowlist_hosts if framework_profile is not None else [],
            "docs_entrypoints": framework_profile.docs_entrypoints if framework_profile is not None else [],
        },
        "llm_usage": llm_outcome.usage,
        "provenance": provenance_section(
            llm_used=bool(llm_outcome.usage.get("used")),
            evidence_count=len(search_evidence),
        ),
    }
    next_step = (
        'Use `forge query "..."` for repository-grounded file locations.'
        if ask_preset in {"auto", "repo", "docs"}
        else 'Verify freshness with external sources if "latest" accuracy is required.'
    )
    contract = build_contract(
        capability=request.capability.value,
        profile=request.profile.value,
        summary=summary,
        evidence=search_evidence,
        uncertainty=uncertainty,
        next_step=next_step,
        sections=sections,
    )
    if is_json:
        emit_contract_json(contract)
        return 0

    print("=== FORGE ASK ===")
    print(f"Profile: {request.profile.value}")
    print(f"Question: {question}")
    print("\n--- Answer ---")
    print(summary)
    if is_full(view):
        print("\n--- Ask ---")
        print(f"Command: {ask_command}")
        print(f"Preset: {ask_preset}")
        print(f"Guided requested: {ask_guided}")
        print(f"Framework profile requested: {requested_framework_profile or '-'}")
        print(f"Framework profile resolved: {framework_profile_id or '-'}")
        if search_outcome is not None:
            print(f"Web search used: {search_outcome.used}")
            print(f"Web search provider: {search_outcome.provider}")
            if search_policy is not None:
                print(f"Allowed hosts: {', '.join(search_policy.allowed_hosts) if search_policy.allowed_hosts else '-'}")
            if search_outcome.candidates:
                print("Top web candidates:")
                for item in search_outcome.candidates[:5]:
                    print(f"- [{item.rank}] {item.url}")
            if search_outcome.fallback_reason:
                print(f"Web search fallback: {search_outcome.fallback_reason}")
        if retrieval_outcome is not None:
            print(f"Web retrieval used: {retrieval_outcome.used}")
            print(f"Web retrieval fetched: {retrieval_outcome.fetched_count}")
            print(f"Web retrieval snippets: {retrieval_outcome.extracted_snippet_count}")
            if retrieval_policy is not None:
                print(f"Web retrieval max URLs: {retrieval_policy.max_urls_fetched}")
            if retrieval_outcome.sources:
                print("Retrieved sources:")
                for item in retrieval_outcome.sources[:5]:
                    print(f"- {item.url}")
            if retrieval_outcome.fallback_reason:
                print(f"Web retrieval fallback: {retrieval_outcome.fallback_reason}")
        if ask_preset in {"docs", "latest"}:
            print(f"Web access enabled: {access_web_enabled} ({access_web_source})")
            if web_policy_blocked_reason:
                print(f"Web policy blocked: {web_policy_blocked_reason}")
        print("\n--- LLM Usage ---")
        print(f"Policy: {llm_outcome.usage.get('policy')}")
        print(f"Mode: {llm_outcome.usage.get('mode')}")
        print(f"Used: {llm_outcome.usage.get('used')}")
        print(f"Provider: {llm_outcome.usage.get('provider') or 'none'}")
        print(f"Model: {llm_outcome.usage.get('model') or 'none'}")
        if llm_outcome.usage.get("fallback_reason"):
            print(f"Fallback: {llm_outcome.usage.get('fallback_reason')}")
    print("\n--- Next Step ---")
    print(next_step)
    print("\n--- Uncertainty ---")
    notes = uncertainty if is_full(view) else uncertainty[:1]
    for note in notes:
        print(f"- {note}")
    return 0
