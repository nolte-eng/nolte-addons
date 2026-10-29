# Nolte Stundenbericht – Odoo 19 Community und Enterprise

Mobile Einsatzberichte mit mitarbeiterbezogenen Zeiten, Material, Fotos,
Kundenbestätigung und Übergabe an Verkauf und Spesenbericht.

## Version 19.0.1.3.6

- Zentral verwaltete, optional einfügbare und anschließend editierbare Arbeitsvorlagen.
- Ein zentraler **Einsatzabschluss** je Unternehmen unter Konfiguration. Neue Berichte übernehmen die Vorgabe automatisch; Monteure können eigene Prüfpunkte ergänzen. Bestehende interne Einträge bleiben gespeichert und privat.
- Ankreuzbare **Pauschalen** mit zentral hinterlegten Artikeln. Jede Auswahl wird einmal je Bericht ins Angebot übertragen und regulär abgerechnet. Im Kunden-PDF erscheinen nur Namen mit angekreuztem Kästchen.
- Automatische lokale Sicherung. Beim Öffnen von **Unterschrift** wird der aktuelle Bericht automatisch übertragen; bei Fehlern bleibt der lokale Entwurf erhalten. Keine separaten Speicher-/Synchronisationsbuttons mehr.
- Aufgeräumte Tagesaktionen in zwei Zeilen und Kopierdialog für Folgetag oder mehrere Mitarbeiter. Vorhandene Zeiten werden nicht überschrieben; Übernachtungen werden nicht kopiert.
- Serviceeinsätze ohne Termin oder Monteur anlegen; ein Termin setzt den Einsatz auf „Einsatz geplant“.
- Freie Einsätze aus dem Projekt „Aussendienst“ übernehmen und vorbereitete Berichte weiterverwenden.
- Auftragsauswahl als „Kunde · Auftragstitel“; abgeschlossene und archivierte Einsätze werden ausgeblendet.
- Einzelne Berichte und vollständige Einsätze archivieren und manuelle Archivierungen zurücknehmen.
- Pausen werden bei der Spesenübergabe auch innerhalb durchgehender Arbeitsblöcke abgezogen; überlappende Pausen und bereits freie Zeitlücken zählen nur einmal. Bestehende Spesen werden nicht automatisch neu berechnet.
- BMF-Land und Ortszuschlag aus der zentralen Spesentabelle, im Backend passend zum Einsatzjahr auswählbar.
- Firmensuche in manuellen Berichten sowie neue Einsatzorte über die Kontaktverwaltung anlegen.
- Direkte Navigation zwischen Planung und Stundenbericht; manuelle mobile Berichte erzeugen einen Einsatzauftrag.
- Korrekte PDF-Sonderzeichen; nach dem E-Mail-Versand öffnet sich der zugehörige Einsatzbericht.
- Kundenhistorie, Archiv und Konfigurationsmenü.
- PDF-Vorschau vor der Kundenbestätigung; Versand mit editierbarem Odoo-E-Mail-Dialog.
- Online-Unterschrift ohne Enterprise-Modul `sign`: befristeter Kundenlink,
  eingefrorene Berichtsfassung und PDF-Rücklauf als Alternative.
- Gegen wiederholte Übernahme geschützte Verkaufsübergabe und kompakte Auftragsnotiz.

## Abhängigkeiten

Zusätzlich zu den im Manifest aufgeführten Odoo-Modulen werden
`nolte_spesenbericht` und `nolte_overtime_billing` benötigt. Der gemeinsame
Zeitverteiler befindet sich ab Version 19.0.1.5.6 im CSV-/Überstundenmodul.

## Installation und Update

1. Datenbank, Filestore und bisherigen Quellcode konsistent sichern.
2. Alle Abhängigkeiten im tatsächlich geladenen Addons-Pfad bereitstellen.
3. Bei angehaltenem regulärem Odoo-Dienst die Module
   `nolte_overtime_billing,nolte_stundenbericht` gezielt aktualisieren.
4. Odoo starten und Anmeldung, Eingabe, Rechte und PDF prüfen.

Keine Produktivdaten, Filestores, Zugangsdaten oder Sicherungen versionieren.
Ein Code-Rollback allein macht Datenbankänderungen nicht rückgängig.

## Online-Unterschrift einrichten

Unter **Stundenbericht → Konfiguration → Online-Unterschrift** eine öffentlich
erreichbare HTTPS-Adresse dieser Odoo-Instanz eintragen. Die Einstellung
`nolte_stundenbericht.signature_base_url` darf nicht auf Staging zeigen.
Ausgehenden E-Mail-Server, Kundenadresse und Unternehmens-/Serviceadresse prüfen.

Der Monteur öffnet den Standard-E-Mail-Dialog mit Kundenlink und PDF. Text und
Empfänger bleiben bearbeitbar. Bereits beim Öffnen wird die Kundenfassung
festgeschrieben; wird der Dialog verworfen, muss die Anfrage vor Änderungen
zurückgenommen werden. Links gelten 14 Tage und können widerrufen werden.
Eine unterschriebene Fassung kann nicht erneut unterschrieben werden.

## Zentrale Vorgaben nach dem Update

Unter **Konfiguration → Einsatzabschluss** die gemeinsamen Prüfpunkte pflegen.
Eine eindeutig vorhandene Kundencheckliste desselben Unternehmens wird beim
Update als Vorgabe erhalten. Interne Vorlagen werden niemals automatisch
kundensichtbar. Bei mehreren bisherigen Kundenvorlagen wird keine Auswahl
erraten; die zentrale Vorgabe ist dann vom Administrator einzurichten.

Unter **Konfiguration → Pauschalen** Bezeichnung und verkaufbaren Artikel
zuordnen. Preise, Steuern und Rechnungsstellung folgen der normalen
Odoo-Artikelkonfiguration. Staging-Berichte, Pauschalen und Preise werden beim
Code-Update nicht in Produktionsdatenbanken kopiert.

Die lokale Sicherung ersetzt kein Serverbackup. Beim Löschen von Browserdaten
können noch nicht übertragene Entwürfe verloren gehen. Für Übertragung und
Unterschrift ist eine Verbindung zum Server nötig.

Alternativ kann ein Prüfer das zurückgesendete unterschriebene PDF nach Prüfung
der passenden Berichtsfassung übernehmen. Nach Abschluss wird eine Kopie für
Kunde und Unternehmensadresse in die Odoo-Mailwarteschlange gestellt.

Die Funktion ist eine einfache elektronische Kundenbestätigung; sie ist keine
qualifizierte elektronische Signatur und benötigt kein Odoo Sign.

## Prüfungen

Die Transaktionstests `TestOnlineSignature` prüfen eingefrorene Inhalte,
Widerruf, Ablauf, Einmaligkeit, PDF-Erzeugung und eingeschränkte Einstellungen.
Sie gehören ausschließlich auf eine Testdatenbank. Ein bestandener Test der
Mailwarteschlange bestätigt keine Zustellung durch den externen Mailanbieter.
