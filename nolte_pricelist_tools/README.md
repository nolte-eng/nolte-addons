# Nolte Pricelist Tools – Odoo 19

## Funktionen

- Button **Varianten hinzufügen** in jeder Preisliste.
- Erzeugt für alle Varianten eines ausgewählten Produkts feste Preisregeln.
- Preisquelle: Verkaufspreis, Kosten oder 0,00.
- Prozentuale Anpassung und frei wählbare Rundung.
- Vorhandene Regeln können übersprungen oder überschrieben werden.
- Button **Preislistenpositionen** öffnet eine normale Listenansicht. Dort stehen Odoos Standardfunktionen **Exportieren** und **Importieren** zur Verfügung.

## Installation

1. Ordner `nolte_pricelist_tools` in den gemounteten Custom-Addons-Ordner kopieren.
2. Odoo-Container neu starten.
3. Apps-Liste aktualisieren.
4. Nach `Nolte Pricelist Tools` suchen und installieren.

Beispiel Docker:

```bash
cd /pfad/zum/docker-compose-ordner
sudo docker compose restart odoo
```

Modul per Kommando aktualisieren:

```bash
sudo docker compose exec odoo odoo \
  -d DATENBANKNAME \
  -u nolte_pricelist_tools \
  --stop-after-init
sudo docker compose restart odoo
```

Die tatsächlichen Service- und Datenbanknamen müssen an die Installation angepasst werden.

## Bedienung

1. Verkauf → Konfiguration → Preislisten.
2. Preisliste öffnen.
3. **Varianten hinzufügen** anklicken.
4. Produkt und Preisberechnung auswählen.
5. **Varianten hinzufügen** bestätigen.
6. Über **Preislistenpositionen** die erzeugten Regeln exportieren oder importieren.

## Sicherheit

Die Funktionen sind für Benutzer der Gruppe **Verkaufsadministrator** freigegeben.
