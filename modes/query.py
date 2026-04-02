from __future__ import annotations

from pathlib import Path

from core.capability_model import CommandRequest
from core.effects import ExecutionSession
from core.repo_io import iter_repo_files, read_text_file


def search_repo(root: Path, query: str, session: ExecutionSession) -> list[str]:
    matches: list[str] = []
    query_lower = query.lower()

    for file_path in iter_repo_files(root, session):
        content = read_text_file(file_path, session)
        if not content:
            continue

        for idx, line in enumerate(content.splitlines(), start=1):
            if query_lower in line.lower():
                rel_path = file_path.relative_to(root)
                matches.append(f"{rel_path}:{idx}:{line.strip()}")

    return matches


def run(request: CommandRequest, args, session: ExecutionSession) -> int:
    print("=== FORGE QUERY ===")
    print(f"Profile: {request.profile.value}")
    print(f"Question: {request.payload}")

    repo_root = Path(args.repo_root).resolve()
    matches = search_repo(repo_root, request.payload, session)

    if not matches:
        print("No matches found.")
        return 0

    print("\n--- Matches ---")
    for line in matches[:20]:
        print(line)

    if len(matches) > 20:
        print(f"\n... and {len(matches) - 20} more")

    print("\n--- Interpretation ---")
    print("Found occurrences of the query in the repository.")
    return 0
