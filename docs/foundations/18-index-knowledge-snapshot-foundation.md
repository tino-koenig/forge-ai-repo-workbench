# Foundation 18: Index / Knowledge Snapshot Foundation

## Zweck
Vertrag für Indexe, Snapshots, Staleness, Rebuild und Reproduzierbarkeit der Wissensbasis.

## Kernidee
Retrieval-Qualität hängt nicht nur von Suchlogik ab, sondern auch von der Qualität und Frische der zugrunde liegenden Snapshot-Basis.

## Was sie umfasst
- Index-Arten
- Snapshot-/Versionsbezug zum Repo-Stand
- Rebuild-/Invalidate-Regeln
- inkrementelle Updates
- Staleness-Modelle
- zulässige Indexinhalte
- Diagnose der Retrieval-Basis

## Erwarteter Umfang
Mittel bis groß

## Aufwand für Realisierung
Mittel bis hoch

## Priorität
P2 (optional später, aber strategisch wichtig)

## Risiken
- stale snapshots führen zu falscher Retrieval-Basis
- inkrementelle Updates erzeugen inkonsistente Zustände
- fehlende Snapshot-Provenienz schwächt Reproduzierbarkeit

## Erfolgskriterium
Retrieval-/Ranking-nahe Entscheidungen referenzieren einen klaren, staleness-bewerteten Snapshot-Stand.

## Konzept

### Problem
Retrievalqualität hängt direkt von der Qualität und Frische des Wissensstands ab. Ohne formalen Snapshot-Vertrag werden „aktuell wirkende“, aber veraltete Daten genutzt.

### Ziel
- Versionierter Snapshot-Vertrag für alle Indexarten.
- Deterministische Staleness-Bewertung und Rebuild-Regeln.
- Transparente Kopplung zwischen Repo-Stand und Wissensbasis.

### Nicht-Ziele
- Kein Ersatz für Retrieval-/Rankinglogik.
- Keine verpflichtende verteilte Index-Infrastruktur.

### Leitprinzipien
- snapshot provenance is mandatory
- staleness is explicit
- rebuild rules are deterministic
- incremental update needs integrity checks

## Spezifikation

### 1. Snapshot-Vertrag
Pflichtfelder:
- `snapshot_id`, `snapshot_contract_version`, `repo_state_ref`, `index_kind`, `schema_version`, `created_at`, `staleness_state`

### 2. Snapshot-Klassen
Mindestens:
- `symbol_index`
- `content_index`
- `summary_index`
- `graph_index` (optional, falls aktiv)

### 3. Konsistenzregeln
- Retrieval muss Snapshot-Staleness sichtbar machen.
- Rebuild-Trigger sind deterministisch definiert.

### 4. Staleness-Modell
Mindestens:
- `fresh`
- `stale`
- `expired`
- `unknown`

Zusätzlich:
- `staleness_reason_codes[]`
- `staleness_lag_hint` (z. B. commits/zeitbasiert)

### 5. Rebuild-/Invalidate-Regeln
- Trigger müssen explizit und testbar sein.
- `expired` Snapshot darf nicht als primäre Basis für code-kritische Retrieval-Pfade genutzt werden.

### 6. Inkrementelle Update-Regeln
- Inkrementelles Update muss Integritätsmarker liefern.
- Bei Integritätszweifel ist full rebuild erzwingbar.

### 7. Provenienzvertrag
- Jede Nutzung eines Snapshots muss `snapshot_id` + `schema_version` + `repo_state_ref` referenzieren.
- Mehrere Snapshotquellen im gleichen Run müssen als solche sichtbar sein.

## Design

### Zielstruktur (Vorschlag)
- `core/index_snapshot_foundation.py`
- `core/index_staleness.py`
- `core/index_rebuild_policies.py`
- `core/index_integrity_checks.py`

### API-Skizze
- `load_snapshot(ref) -> Snapshot`
- `evaluate_staleness(snapshot, repo_state) -> StalenessReport`
- `rebuild_snapshot(policy, context) -> SnapshotRef`
- `update_snapshot_incrementally(snapshot, delta) -> SnapshotRef`
- `validate_snapshot_integrity(snapshot) -> IntegrityReport`

### Integrationspunkte
- Foundation 07: Retrieval verwendet Snapshot-Status als Basisdiagnose
- Foundation 10: Snapshot-/Staleness-Provenienz in Output-Sections
- Foundation 11: Rebuild/Invalidate/Staleness-Events
- Foundation 22: Kontextstaleness nutzt Snapshot-Bezüge

## Verbindlicher Vertragskern (jetzt)

Diese Punkte sind in Foundation 18 verpflichtend:
- snapshot-versionierter Wissensstand mit Repo-Bezug
- explizite Staleness-Bewertung inkl. Reasons
- deterministische Rebuild-/Invalidate-Regeln
- Integritätsprüfung für inkrementelle Updates
- sichtbare Snapshot-Provenienz in retrievalnahen Entscheidungen

## Bewusst verschoben (spätere Detailphasen)

- verteilter Snapshot-Betrieb
- fortgeschrittene inkrementelle Aktualisierung
- automatische Snapshot-Strategie je Repo-Typ

## Detaillierungsregel

Foundation 18 definiert den Wissensbasisvertrag, nicht das Ranking selbst.
