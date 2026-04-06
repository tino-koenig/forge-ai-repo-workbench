# Test Foundations

Prüfe die bereits implementierten Foundations:
- Inkompatibilitäten?
- Unschärfe in Verträgen, Parameter, Übergaben?
- Offensichtlich fehlende Elemente?
- Offensichtliche Fehler in der Umsetzung oder auch Design, Spezifikation?
- Offensichtliche Fehler, die zur Laufzeit auftreten werden?

# Run Tests

Führe alle im Repo möglichen Tests durch und prüfe so detailliert wie möglich. Lasse dir dafür Zeit, Ziel ist das bestmöglichste Ergebnis.
Führe anschließend die Themen von eben auf sowie neue Findings / Fehler / ... durch die neuen Tests.

# Fix Issues

Implementiere Issue XX.

Wichtig:
- nur die für dieses Issue nötigen Änderungen
- keine Änderung bestehender Modi oder aktiver Runtime-Pfade außerhalb des betroffenen Foundation-Scopes
- bestehende Vertragssemantik der anderen Foundations respektieren
- kleine, klare Lösung statt Umbau
- Tests ergänzen oder anpassen, so dass der beschriebene Fehler abgesichert ist
- bestehende Tests dürfen nicht regressieren

Am Ende kurz ausgeben:
- was geändert wurde
- welche Tests hinzugefügt/angepasst wurden
- wie der Fix validiert wurde

Wenn der Fix vollständig durchgeführt werden konnte, committe die Änderungen mit Hinweis auf den Issue.