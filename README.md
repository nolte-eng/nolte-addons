# Nolte Odoo Addons – Odoo 19

Dieser Branch enthält die für Odoo 19 gepflegten Nolte-Zusatzmodule.

## Branch-Regel

Für Odoo 19 ausschließlich den Branch `19.0` verwenden. Änderungen werden über einen eigenen Arbeitsbranch und Pull Request eingebracht. Direkte Änderungen auf dem Server sollten vermieden werden.

## Enthaltene Module

Je nach Ausbaustand befinden sich unter anderem folgende Module im Repository:

- `nolte`
- `nolte_berichte`
- `nolte_overtime_billing`
- `portal_travel_expense`

Maßgeblich sind immer die vorhandenen Modulordner mit einer `__manifest__.py`.

## Empfohlener Installationspfad

```text
~/addons/19.0/nolte-addons
```

Der Pfad muss in der Odoo-Konfiguration beziehungsweise im Container als Addons-Pfad eingebunden sein.

## Repository aktualisieren

```bash
cd ~/addons/19.0/nolte-addons
git fetch origin
git checkout 19.0
git pull --ff-only origin 19.0
```

`--ff-only` verhindert unbeabsichtigte lokale Merge-Commits auf dem Server.

## Submodule aktualisieren

Falls Git-Submodule verwendet werden:

```bash
git submodule sync --recursive
git submodule update --init --recursive
```

## Vor einem Odoo-Modulupdate

1. Datenbank und Filestore sichern.
2. Prüfen, dass der Arbeitsbaum sauber ist:

```bash
git status --short
```

3. Den gewünschten Stand laden.
4. Betroffene Module gezielt aktualisieren.
5. Odoo-Log auf Fehler prüfen.

## Beispiel für ein Modulupdate im Container

Container-, Datenbank- und Konfigurationsnamen müssen an die jeweilige Installation angepasst werden:

```bash
docker exec -it <odoo-container> \
  odoo -c /etc/odoo/odoo.conf \
  -d <datenbank> \
  -u <modulname> \
  --stop-after-init
```

Danach den Container regulär neu starten.

## Rollback

Vor dem Deployment den bisherigen Commit notieren:

```bash
git rev-parse HEAD
```

Bei einem notwendigen Code-Rollback:

```bash
git checkout 19.0
git reset --hard <vorheriger-commit>
```

Ein Datenbank-Rollback ist nur über ein passendes Backup sicher möglich. Ein reines Zurücksetzen des Git-Stands macht bereits ausgeführte Datenbankmigrationen nicht rückgängig.

## Automatische Prüfungen

GitHub Actions prüft bei Pull Requests und Pushes:

- Python-Syntax
- XML-Syntax
- Odoo-Manifeste und Pflichtfelder
- unerwünschte Laufzeit-, Dump- und Secret-Dateien
- offensichtliche private Schlüssel

## Vertrauliche Dateien

Niemals folgende Inhalte committen:

- `.env`-Dateien
- Passwörter, Tokens oder private Schlüssel
- Datenbank-Dumps und Backups
- Odoo-Filestore und Sessions
- produktive Konfigurationsdateien mit Zugangsdaten
