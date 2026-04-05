# Foundation 12: Repository / Workspace Foundation

## Zweck
Einheitliches Modell für Repo, Workspace, Pfade, Artefaktbereiche, Include-/Ignore-Regeln sowie les-/schreibbare Bereiche.

## Kernidee
Forge kann nur dann verlässlich analysieren und später kontrolliert Änderungen vorschlagen/ausführen, wenn der relevante Arbeitsraum formalisiert ist.

## Was sie umfasst
- Repo-Root / Workspace-Root / Multi-Repo- oder Subrepo-Kontext
- Pfadnormalisierung und kanonische Lokatoren
- Include-/Ignore-Regeln
- Generated/Vendor/Temp/Cache/Build-Artefakte
- lesbare vs. schreibbare Bereiche
- Dateiarten/Rollen (`source|config|test|docs|generated|artifact|external`)
- Symlink-/Case-/Plattformregeln
- Abgrenzung Produktcode vs. Doku vs. Build-Ausgabe vs. `.forge`

## Beispiel
`vendor/`, `node_modules/`, `dist/` werden für code-zentrierte Analyse standardmäßig nicht als Primärquellen gewertet, bleiben aber als Herkunft sichtbar.

## Erwarteter Umfang
Groß

## Aufwand für Realisierung
Hoch

## Priorität
P0/P1

## Risiken
- zu strenge Workspace-Regeln blockieren legitime Fälle
- zu lockere Regeln erzeugen Noise und Sicherheitsrisiken

## Erfolgskriterium
Alle Foundations nutzen dasselbe Workspace-Modell und dieselben Lokator-/Scope-Regeln.

## Konzept

### Problem
Ohne zentrale Workspace-Definition divergieren Retrieval, Ranking, Target Resolution und spätere Write-Pfade.

### Ziel
- Zentrale Workspace-Wahrheit für Scope, Pfade, Rollen und Zugriffsgrenzen.
- Deterministische Lokator-Normalisierung.
- Explizite Trennung zwischen analysierbaren und mutierbaren Bereichen.

### Nicht-Ziele
- Keine plattformspezifische Speziallogik in jeder Foundation.
- Keine implizite Auto-Erweiterung des Scopes ohne Policy-Entscheidung.

### Leitprinzipien
- Canonical locator first.
- Scope-Entscheidungen sind explizit und diagnostizierbar.
- Path-/Role-Regeln sind versioniert.

## Spezifikation

### 1. Workspace-Vertrag
 Mindestens:
 - `workspace_id`
 - `workspace_contract_version`
 - `workspace_snapshot_id`
 - `workspace_status` (`ok|partial|blocked`)
 - `workspace_root`
 - `repo_roots[]`
 - `artifact_roots[]`
 - `read_scopes[]`
 - `write_scopes[]`

Die `workspace_snapshot_id` muss deterministisch aus dem relevanten Workspace-Zustand ableitbar sein und darf kein freier Zufallswert sein.

Sie basiert mindestens auf `workspace_root`, `repo_roots`, `artifact_roots`, effektiven Include-/Ignore-Regeln sowie Read-/Write-Scopes. Diagnostics und Laufzeitmetadaten dürfen die `workspace_snapshot_id` nicht beeinflussen.

- `ok`: vollständiger Workspace nutzbar
- `partial`: Teile des Workspace sind eingeschränkt, aber der Workspace bleibt verwendbar
- `blocked`: Workspace ist für den vorgesehenen Zweck nicht nutzbar

### 2. Lokator-Vertrag
Jeder Pfadbezug wird normalisiert zu:
- `locator` (kanonisch)
- `locator_kind` (`path|url|virtual`)
- `workspace_relative_path` (falls lokal)
- `platform_case_policy`

Für lokale Pfade muss `locator` absolut, normalisiert und stabil sein.

### 3. Include/Ignore
 - Regeln sind zentral und priorisiert (default + repo + local + cli).
Priorität (höchste zuerst): cli → local → repo → default.
 - Jede Include-/Ignore-Entscheidung muss mit Regelquelle und nach Möglichkeit `rule_id` diagnostizierbar sein.
 - Prioritätskonflikte werden als `scope_rule_conflict_resolved` dokumentiert.

### 4. Rollenklassifikation
 Dateien/Artefakte erhalten mindestens:
 - `role` (`source|config|test|docs|generated|artifact|external`)
 - `role_source` (wie klassifiziert)

Eine Datei erhält genau eine primäre Rolle. Mehrfachklassifikation muss diagnostiziert werden.

### 5. Read/Write-Scope
 - `read_allowed` und `write_allowed` sind getrennt.
 - Write-Scope ist standardmäßig deny-by-default und muss explizit freigegeben werden.
 - Write-Scope muss enger oder gleich Read-Scope sein.
 - Scope-Verletzungen werden als Policy-relevante Diagnostics ausgegeben.
- `ScopeDecision` enthält mindestens `allowed`, `decision_type` (`read|write`), `matched_rule_source`, `matched_rule_id`, `diagnostics[]`.

### 6. Plattform-/Symlink-Regeln
- Symlink-Handling ist explizit konfigurierbar.
- Es wird explizit unterschieden zwischen Symlink-Auflösung und Traversal durch Symlinks.
- Case-Sensitivity wird nicht implizit angenommen.
- Plattformabhängige Pfadnormalisierung muss deterministisch und testbar sein.

## Design

### Zielstruktur (Vorschlag)
- `core/workspace_foundation.py`
- `core/workspace_locators.py`
- `core/workspace_scope_rules.py`
- `core/workspace_roles.py`

### Datenmodelle (konzeptionell)
 - `WorkspaceContext`
   - workspace_id, workspace_contract_version, workspace_snapshot_id, workspace_status, workspace_root, repo_roots, artifact_roots, read_scopes, write_scopes, diagnostics
 - `CanonicalLocator`
   - locator, locator_kind, workspace_relative_path, platform_case_policy
 - `ScopeDecision`
   - allowed, decision_type (`read|write`), matched_rule_source, matched_rule_id, diagnostics
 - `FileRoleAssignment`
   - role, role_source, diagnostics

### API-Skizze
- `resolve_workspace_context(args, repo_root) -> WorkspaceContext`
- `compute_workspace_snapshot_id(workspace) -> str`
- `normalize_locator(path_or_ref, workspace) -> CanonicalLocator`
- `is_in_read_scope(locator, workspace) -> ScopeDecision`
- `is_in_write_scope(locator, workspace) -> ScopeDecision`
- `classify_file_role(locator, workspace) -> FileRoleAssignment`

### Integrationsregeln
 - Foundation 07/08/09 nutzen `CanonicalLocator`.
 - Foundation 14 konsumiert Scope-Entscheidungen.
 - `ScopeDecision` ist direkt policy-relevant und darf in nachgelagerten Foundations nicht umgedeutet werden.
 - Foundation 16 darf nur mit positivem Write-Scope arbeiten.
 - Foundation 17 nutzt `artifact_roots[]` und Workspace-Status für `.forge`-Artefakte.
 - Foundation 19/20 dürfen nur im validierten Workspace-Kontext ausführen.

## Verbindlicher Vertragskern (jetzt)

 Diese Punkte sind verpflichtend:
 - zentraler Workspace-Kontext inklusive deterministischer `workspace_snapshot_id`
 - kanonische Lokatoren
 - explizite Read-/Write-Scope-Entscheidungen mit diagnostizierbarer Regelherkunft
 - standardisierte Rollenklassifikation
 - deny-by-default für Write-Scope

## Bewusst verschoben (spätere Detailphasen)

- tiefere Multi-Repo-Workspaces mit Cross-Root-Referenzen
- erweiterte Plattformprofile

## Detaillierungsregel

Foundation 12 definiert die Workspace- und Scope-Basis für alle nachfolgenden Foundations.
