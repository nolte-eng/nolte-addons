# Nolte Stundenbericht – Odoo 19 Community

Mobile Einsatzberichte mit mitarbeiterbezogenen Zeiten, Material, Fotos,
Kundenbestätigung und Übergabe an Verkauf und Spesenbericht.

## Version 19.0.1.0.2

- Zentral verwaltete, optional einfügbare und anschließend editierbare Arbeitsvorlagen.
- Getrennte interne und kundenbezogene Checklisten. Interne Punkte erscheinen nicht im Kunden-PDF.
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
