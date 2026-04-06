# Contributing to SolarBatterYield

## Entwicklung

### Projektstruktur

```
solarbatteryield/
├── src/solarbatteryield/   # Application source code
│   ├── __init__.py
│   ├── streamlit_app.py    # Main entry point
│   ├── simulation.py       # Core simulation engine
│   ├── models.py           # Data classes
│   └── ...
├── tests/                  # Test suite
│   ├── test_simulation.py  # Unit tests
│   ├── test_snapshots.py   # Snapshot regression tests
│   ├── test_smoke.py       # Smoke tests
│   └── __snapshots__/      # Pinned snapshot data
├── pyproject.toml          # Project configuration
└── uv.lock                 # Dependency lock file
```

### Setup

```bash
git clone https://github.com/markusdlugi/solarbatteryield.git
cd solarbatteryield
uv sync --dev
uv run streamlit run src/solarbatteryield/streamlit_app.py
```

### Tests ausführen

```bash
# Run all tests
uv run pytest

# Run specific test files
uv run pytest tests/test_simulation.py -v
```

### Aktualisieren der Snapshots

Nach Änderungen an der Simulationslogik oder den Ausgabeformaten müssen die Snapshot-Tests aktualisiert werden, um die
neuen erwarteten Ergebnisse zu reflektieren. Dies geschieht mit dem `--snapshot-update` Flag:

```bash
uv run pytest tests/test_snapshots.py --snapshot-update
```

---

## Conventional Commits

Dieses Projekt verwendet [Conventional Commits](https://www.conventionalcommits.org/) für automatisches Versioning und
Release Notes.

## Commit-Format

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

## Typen und ihre Auswirkung auf die Version

| Typ               | Beschreibung                                        | Version-Bump |
|-------------------|-----------------------------------------------------|--------------|
| `feat:`           | Neues Feature für Nutzer                            | **Minor**    |
| `fix:`            | Bugfix für Nutzer                                   | **Patch**    |
| `perf:`           | Performance-Verbesserung                            | **Patch**    |
| `refactor:`       | Code-Änderung ohne Funktionsänderung                | **Patch**    |
| `docs:`           | Nur Dokumentation                                   | Kein Release |
| `style:`          | Formatierung, Whitespace, etc.                      | Kein Release |
| `test:`           | Tests hinzufügen/ändern                             | Kein Release |
| `chore:`          | Build-Prozess, Dependencies, etc.                   | Kein Release |
| `ci:`             | CI/CD-Änderungen                                    | Kein Release |
| `build:`          | Build-System oder externe Dependencies              | Kein Release |
| `BREAKING CHANGE` | Breaking Change (im Footer oder mit `!` nach Type)  | **Major**    |

## Beispiele

### Feature (Minor Version Bump: 1.0.0 → 1.1.0)
```
feat(simulation): add support for AC-coupled batteries
```

### Bugfix (Patch Version Bump: 1.0.0 → 1.0.1)
```
fix(api): handle PVGIS timeout gracefully
```

### Breaking Change (Major Version Bump: 1.0.0 → 2.0.0)
```
feat(models)!: change ModuleConfig to use dataclass

BREAKING CHANGE: ModuleConfig is now a dataclass instead of a dict.
```

oder:

```
refactor(simulation): redesign energy flow calculation

BREAKING CHANGE: Simulation results now use different field names.
```

### Kein Release
```
docs: update README with new screenshots

chore: update dependencies

test: add unit tests for H0 profile

ci: add Python 3.13 to test matrix
```

## Mit Scope (optional)

Der Scope beschreibt den betroffenen Bereich:

```
feat(sidebar): add battery coupling toggle
fix(report): correct currency formatting
perf(simulation): optimize hourly loop
refactor(models): extract common validation logic
```

## Mehrere Änderungen

Bei mehreren Änderungen in einem Commit gilt die "höchste" Änderung:
- BREAKING CHANGE > feat > fix/perf/refactor > andere

**Empfehlung:** Mache kleine, fokussierte Commits mit einem klaren Typ.

## Automatischer Release-Prozess

Bei jedem Push auf `master`:

1. **Tests** werden ausgeführt
2. **Commit-Messages** werden analysiert
3. **Version** wird automatisch erhöht (falls relevantem Commit-Typ)
4. **Release Notes** werden aus den Commits generiert
5. **GitHub Release** wird erstellt mit Tag

### Kein Release bei:
- `docs:`, `style:`, `test:`, `chore:`, `ci:`, `build:` Commits
- Commits ohne Conventional-Commit-Prefix
- `chore(release):` Commits (um Endlosschleifen zu vermeiden)
