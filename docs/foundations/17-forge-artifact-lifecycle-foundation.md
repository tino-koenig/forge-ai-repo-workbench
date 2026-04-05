# Foundation 17: .forge Artifact Lifecycle Foundation

## Zweck
Einheitliches Lebenszyklusmodell für alle `.forge`-Artefakte.

## Kernidee
Artefakte werden nicht nur gespeichert, sondern klassifiziert, versioniert, migriert, rotiert und reproduzierbar eingeordnet.

## Was sie umfasst
- Artefaktklassen (`cache`, `diagnostic`, `audit`, `session`, `run`, `index`, `graph`, `proposal`, ...)
- Ownership
- Pfad-/Namenskonventionen
- Schema-/Formatversionen
- Migration
- Retention/Cleanup/Rotation
- reproduzierbar vs. flüchtig
- Bezug zum Repo-Stand

## Erwarteter Umfang
Mittel bis groß

## Aufwand für Realisierung
Mittel bis hoch

## Priorität
P2

## Risiken
- unklare Ownership erzeugt Artefaktchaos
- Schema-Drift ohne Migration bricht Kompatibilität
- Retention löscht audit-relevante Artefakte zu früh

## Erfolgskriterium
Alle `.forge`-Artefakte sind klassifiziert, versioniert, owner-gebunden und über Lifecycle-Regeln konsistent verwaltet.

## Konzept

### Problem
Ohne Lifecycle-Foundation wachsen `.forge`-Artefakte unkontrolliert, verlieren Herkunft und werden schwer reproduzierbar.

### Ziel
- Einheitliches Metadaten- und Lebenszyklusmodell für alle Artefakte.
- Klare Trennung von flüchtigen, reproduzierbaren und audit-relevanten Artefakten.
- Verlässliche Migration bei Schemaänderungen.

### Nicht-Ziele
- Kein spezifischer Storage-Backend-Zwang.
- Keine fachliche Auswertung der Artefakte selbst.

### Leitprinzipien
- artifact metadata first
- owner accountability
- migration over silent breakage
- retention with audit guarantees

## Spezifikation

### 1. Artefaktvertrag
Pflichtfelder:
- `artifact_type`, `artifact_id`, `artifact_contract_version`, `schema_version`, `owner_foundation`, `repo_state_ref`, `retention_class`

Statusraum (verbindlich):
- `registered|active|rotated|retained|expired|deleted`

### 2. Artefaktklassen und Kritikalität
Mindestens:
- `cache`
- `diagnostic`
- `audit`
- `session`
- `run`
- `index`
- `graph`
- `proposal`

Jede Klasse definiert:
- `reproducibility_class` (`reproducible|semi_reproducible|volatile`)
- `retention_class`
- `min_required_metadata`

### 3. Lebenszyklusregeln
- Erzeugung, Update, Rotation, Löschung sind normiert.
- Migrationspfad bei Schemawechsel ist verpflichtend.

### 4. Ownership-Regeln
- Jedes Artefakt hat genau eine primäre `owner_foundation`.
- Cross-foundation Nutzung muss über Referenzen, nicht über Ownership-Übernahme erfolgen.

### 5. Repo-/Snapshot-Bezug
- Artefakte mit inhaltlichem Repo-Bezug müssen `repo_state_ref` oder `snapshot_ref` tragen.
- Fehlt dieser Bezug, ist das Artefakt als eingeschränkt reproduzierbar zu markieren.

### 6. Retention-/Cleanup-Regeln
- Retention ist klassenbasiert und policy-konfigurierbar.
- Audit-/Policy-relevante Artefakte dürfen nicht durch aggressive Cleanup-Regeln unauffindbar werden.

### 7. Migrationsvertrag
- Schemaänderung ohne Migrationspfad ist unzulässig.
- Migrationen müssen idempotent und versioniert sein.

## Design

### Zielstruktur (Vorschlag)
- `core/artifact_lifecycle_foundation.py`
- `core/artifact_registry.py`
- `core/artifact_migrations.py`
- `core/artifact_retention.py`

### API-Skizze
- `register_artifact(meta, payload) -> ArtifactRef`
- `load_artifact(ref) -> ArtifactPayload`
- `migrate_artifact(ref, target_version) -> ArtifactRef`
- `enforce_retention(policy) -> RetentionReport`
- `validate_artifact_metadata(meta) -> ValidationResult`
- `resolve_artifact_owner(ref) -> OwnerInfo`

### Integrationspunkte
- Foundation 10: Output-Provenienz über Artefaktreferenzen
- Foundation 11: Lifecycle-/Migration-/Retention-Events
- Foundation 18: Snapshot-/Indexartefakte
- Foundation 22: Kontextobjekte als Artefaktklasse mit Staleness-Bezug

## Verbindlicher Vertragskern (jetzt)

Diese Punkte sind in Foundation 17 verpflichtend:
- standardisierte Artefaktmetadaten inkl. Ownership und Repo/Snapshot-Bezug
- Schema-Versionierung mit idempotentem Migrationspfad
- klassenbasierte Retention-/Rotation-Regeln
- Schutz audit-relevanter Artefakte vor stillem Verlust

## Bewusst verschoben (spätere Detailphasen)

- differenzierte Storage-Backends
- langfristige Archivierungsstrategien
- artefaktübergreifende Konsistenzprüfungen

## Detaillierungsregel

Foundation 17 definiert Lebenszyklus und Governance von `.forge`-Artefakten.
