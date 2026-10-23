# Datenbestätigung: RA/Dec, Zeitstempel sowie Azimut-/Elevationslabels

**Projekt:** Space Probe I – ATLAS / MeerKAT-Daten  
**Status:** vorläufige Plausibilitätsprüfung; keine vollständige wissenschaftliche Validierung  
**Stand:** 23. Oktober 2026

## 1. Zweck dieser Prüfung

Dieses Dokument hält fest, welche Prüfungen an `observations.csv` tatsächlich ausgeführt wurden, welche Ergebnisse sie ergaben und was daraus geschlossen werden kann. Wichtig ist die Unterscheidung zwischen:

1. **Format- und Rechenprüfung** – lassen sich Werte umrechnen und sind sie numerisch plausibel?
2. **Plausibilitätsvergleich** – passen die Werte grob zu einer unabhängigen astronomischen Referenz?
3. **Validierung der berechneten Azimut-/Elevationswinkel** – stimmen die Winkel für genau denselben Zeitpunkt, Koordinatenrahmen und Beobachtungsstandort mit einer unabhängigen Referenz überein?

Die ersten beiden Punkte liefern gute Hinweise darauf, dass `ra` als Dezimalstunden zu interpretieren ist. Der dritte Punkt ist noch offen und darf nicht als abgeschlossen dokumentiert werden.

## 2. Die tatsächlichen Daten aus `observations.csv`

Die vom Nutzer ausgeführten Befehle ergaben folgende Werte.

### 2.1 Verteilung der RA-Spalte

Ausgeführt in PowerShell:

```powershell
python -c "import pandas as pd; x=pd.read_csv('observations.csv',usecols=['ra'])['ra']; print('RA Minimum:',x.min()); print('RA Maximum:',x.max()); print('Werte über 24:',int((x>24).sum()),'von',int(x.notna().sum()))"
```

Tatsächliche Ausgabe:

```text
RA Minimum: 12.249055555555556
RA Maximum: 13.280169466666669
Werte über 24: 0 von 1689257
```

Damit wurde für 1.689.257 nicht fehlende Zeilen festgestellt:

- Minimum der `ra`-Spalte: `12.249055555555556`
- Maximum der `ra`-Spalte: `13.280169466666669`
- Werte größer als 24: `0`

**Interpretation:** Der Wertebereich ist mit Dezimalstunden vereinbar. Der Bereich allein beweist die Einheit allerdings nicht: Auch eine Grad-Spalte könnte Werte zwischen 12 und 13 enthalten. Die Aussage „keine Werte über 24“ ist deshalb ein Konsistenzcheck und kein alleiniger Beweis.

### 2.2 Umrechnung einer konkreten Beispielzeile

Die Beispielzeile aus der CSV enthielt:

```text
ra      = 13.255836111111112
 dec    = -5.825555555555555
 tstart = 60984.176537959574
```

Der tatsächlich ausgeführte Befehl war:

```powershell
python -c "from astropy.coordinates import Angle; from astropy import units as u; from astropy.time import Time; ra=Angle(13.255836111111112,unit=u.hourangle); dec=Angle(-5.825555555555555,unit=u.deg); print('RA:',ra.to_string(unit=u.hourangle,sep=':',precision=2)); print('RA in Grad:',ra.deg); print('Dec:',dec.to_string(unit=u.deg,sep=':',alwayssign=True,precision=0)); print('UTC:',Time(60984.176537959574,format='mjd',scale='utc').isot)"
```

Tatsächliche Ausgabe:

```text
RA: 13:15:21.01
RA in Grad: 198.83754166666665
Dec: -5:49:32
UTC: 2025-11-05T04:14:12.880
```

Die mathematischen Umrechnungen sind konsistent:

- Dezimalstunden `13.2558361111 h` entsprechen ungefähr `13h 15m 21.01s`.
- Für eine RA in Stunden gilt `RA[Grad] = RA[Stunden] × 15`; daraus folgen `198.8375416667°`.
- `dec = −5.8255555556°` entspricht ungefähr `−5° 49′ 32″`.
- Das als Modified Julian Date interpretierte `tstart` ergibt `2025-11-05T04:14:12.880` bei der angegebenen UTC-Skala.

**Was dieser Befehl bestätigt:** Astropy führt die vorgegebenen Konvertierungen konsistent aus. Er beweist für sich allein nicht, dass die Einheit und der Zeitmaßstab in der Originaldatei genau so definiert sind. Diese Annahmen müssen anhand der Datensatzdokumentation oder einer externen Referenz geprüft werden.

## 3. Unabhängiger Plausibilitätsvergleich der Himmelskoordinaten

Eine öffentlich abrufbare Positionsangabe für 3I/ATLAS vom 5. November 2025 nennt ungefähr:

- RA: `13h 15m 20s`
- Dec: `−05° 49′ 36″`

Quelle: [TheSkyLive – 3I/ATLAS, 5 November 2025](https://theskylive.com/planetarium?date=2025-11-05&h=00&m=00&obj=c2025n1). Die dargestellte Zeit ist `00:00 America/Mexico_City`, also 06:00 UTC; dies ist **nicht** exakt derselbe Zeitpunkt wie `tstart` in der Beispielzeile. Die Webseite weist außerdem auf mögliche Positionsunsicherheiten hin.

Die CSV-Beispielzeile, interpretiert als Stunden/Grad, lautet:

- RA: `13h 15m 21.01s`
- Dec: `−05° 49′ 32″`

Die Zahlen liegen sehr nahe an der zitierten Positionsangabe. Das ist ein **starker Plausibilitätshinweis** dafür, dass `ra` in Stunden vorliegt und die Koordinaten ungefähr in der Nähe der Position von 3I/ATLAS liegen. Es ist kein vollständiger zeitgleicher Abgleich, da der Referenzzeitpunkt etwa 1 Stunde 45 Minuten später liegt und sich die Position von 3I/ATLAS bewegt.

Ein weiterer qualitativ passender Verlauf ist, dass die Referenzwerte für 3I/ATLAS im November von ungefähr RA `13h 15m` Anfang November zu etwa RA `12h 15m` gegen Ende November abnehmen. Der beobachtete RA-Bereich in der CSV (`12.249` bis `13.280`) passt grundsätzlich zu diesem Verlauf. Siehe zum Beispiel [TheSkyLive – 3I/ATLAS, 27 November 2025](https://theskylive.com/planetarium?date=2025-11-27&h=00&m=00&obj=c2025n1). Auch dieser Vergleich ist nur ein Plausibilitätscheck, kein Beweis für jede einzelne Zeile.

### Zwischenfazit zur RA-Einheit

Die Kombination aus (a) dem Wertebereich der 1.689.257 Zeilen, (b) der konsistenten Stunden-zu-Grad-Umrechnung und (c) der sehr ähnlichen externen RA/Dec-Position am selben Kalendertag macht **Dezimalstunden für `ra` sehr wahrscheinlich**. Für eine endgültige Bestätigung sollen die Datensatzdefinition und ein Referenzvergleich am exakt gleichen Zeitstempel geprüft werden.

## 4. Was über Azimut und Elevation bisher bekannt ist

Das Skript `derive_azimuth_labels.py` wurde vom Nutzer erfolgreich ausgeführt:

```powershell
python derive_azimuth_labels.py observations.csv -o observations_with_azimuth.csv --ra-unit hours --time-point midpoint
```

Ausgabe:

```text
Rows processed: 1,689,257
Rows with calculated azimuth/elevation: 1,689,257
Output: observations_with_azimuth.csv
Note: labels are computed target directions, not antenna encoder telemetry.
```

Eine Beispielzeile der erzeugten CSV enthielt:

```text
target_azimuth_deg      = 84.25195040458377
target_elevation_deg    = 21.135524877725317
target_position_method  = astropy_altaz_geometric
target_position_time    = observation_midpoint
```

Das belegt, dass das Skript für alle Zeilen einen Azimut- und Elevationswert ausgegeben hat. Die Zeichenfolgen `astropy_altaz_geometric` und `observation_midpoint` sind erklärende Metadaten über Methode und Zeitwahl; die Winkelwerte stehen in den beiden vorherigen numerischen Spalten.

Astropy definiert den AltAz-Rahmen als lokales horizontales Koordinatensystem: Azimut wird von Norden in Richtung Osten gemessen (N = 0°, E = 90°), und Altitude ist der Elevationswinkel. Die Umrechnung benötigt korrekte Himmelskoordinaten, Beobachtungszeit und Beobachterstandort. Siehe [Astropy `AltAz` API-Dokumentation](https://docs.astropy.org/en/stable/api/astropy.coordinates.AltAz.html) und [Astropy Koordinatentransformations-Tutorial](https://learn.astropy.org/tutorials/2_Coordinates-Transforms.html).

**Noch nicht nachgewiesen:** Es wurde hier noch kein reproduzierter Vergleich des Wertes `84.2519504° / 21.1355249°` mit einer unabhängigen Ephemeride für exakt denselben Zeitpunkt und den MeerKAT-Standort dokumentiert. Die Tatsache, dass alle Zeilen Winkelwerte erhalten haben, beweist nur, dass das Skript die Berechnung ausgeführt hat. Sie beweist nicht allein, dass die Winkel fachlich stimmen.

## 5. Nächste notwendige Validierung

Um die Azimut- und Elevationslabels als wissenschaftlich überprüft bezeichnen zu können, sollte eine ausgewählte Zeile vollständig gegengeprüft werden:

1. **Quellsemantik bestätigen:** In der Dokumentation des ATLAS-/MeerKAT-Datensatzes prüfen, ob `ra` Dezimalstunden und `dec` Grad sind und welche Himmelsreferenz (z. B. ICRS/J2000 oder apparent coordinates) die Spalten verwenden.
2. **Zeit bestätigen:** Prüfen, ob `tstart` MJD UTC repräsentiert, und die im Label-Skript verwendete Definition des Beobachtungsmittelpunkts gegen `tsamp` und `numTimesteps` prüfen. Die Einheit von `tsamp` muss dabei ausdrücklich feststehen.
3. **Standort bestätigen:** Den verwendeten MeerKAT-Standort (Länge, Breite und ggf. Höhe) im Skript dokumentieren. Die Quelle sollte ein offizielles MeerKAT/SARAO-/SKAO-Dokument sein; MeerKAT umfasst mehrere Antennen, und `telescopeId` sollte nicht ohne Dokumentation als Standortkoordinate interpretiert werden.
4. **Unabhängigen Vergleich erzeugen:** Mit [JPL Horizons](https://ssd.jpl.nasa.gov/horizons/manual.html) für dasselbe Ziel bzw. dieselbe Sichtlinie, denselben UTC-Zeitpunkt und den topozentrischen Beobachterstandort die passenden Koordinaten und/oder AZ/EL abrufen. Zeitmaßstab, Referenzrahmen und Refraktionsmodell müssen verglichen werden. Die Horizons-Dokumentation beschreibt die Ausgabe von Apparent AZ & EL sowie die Bedeutung von topozentrischen Koordinaten.
5. **Unterschiede auswerten:** RA/Dec und Azimut/Elevation vergleichen und die Abweichungen in Winkelmaßen dokumentieren. Unterschiedliche Referenzrahmen, Beobachtungszeitpunkte oder atmosphärische Refraktion können zu kleinen Differenzen führen; größere Differenzen erfordern eine Ursachenanalyse.
6. **Gesamtdatensatz prüfen:** Für alle Zeilen fehlende/nicht endliche Werte und plausible Bereiche prüfen: Azimut `0 ≤ az < 360°`, Elevation `−90° ≤ el ≤ 90°`. Diese Checks finden offensichtliche Fehler, ersetzen aber nicht den unabhängigen Referenzvergleich.

JPL Horizons-Referenz: [Horizons System Manual](https://ssd.jpl.nasa.gov/horizons/manual.html) und [Horizons API-Dokumentation](https://ssd-api.jpl.nasa.gov/doc/horizons.html).

## 6. Wichtige wissenschaftliche Einschränkungen

- Die berechneten Zielwinkel sind **geometrische Zielrichtungen**, keine gemessenen mechanischen Antennenwinkel. Für tatsächliche Encoder-/Pointing-Werte wäre Teleskoptelemetrie erforderlich.
- Der Name `target_azimuth_deg` ist nur dann als Label für eine Vorhersage sinnvoll, wenn das beabsichtigte Lernziel tatsächlich die berechnete Zielrichtung ist.
- Falls `azimuth_deg` als Eingabemerkmal identisch oder direkt aus `target_azimuth_deg` abgeleitet ist, droht Ziel-Leckage. Eingabe- und Zieldefinition müssen getrennt werden.
- Ein berechneter Azimutwert ist kein Beweis, dass ein Radioereignis von diesem Himmelsort stammt; er kann lediglich die lokale horizontale Richtung der übergebenen RA/Dec-Koordinate zur berechneten Zeit beschreiben.
- Die gute Übereinstimmung einer Beispielzeile rechtfertigt keine Aussage, dass alle 1.689.257 Zeilen unabhängig validiert sind.

## 7. Gesamtbewertung

| Prüfpunkt | Ergebnis | Status |
|---|---|---|
| CSV enthält 1.689.257 nicht fehlende RA-Werte | Vom Nutzer per Pandas gemessen | Bestätigt für den ausgeführten Befehl |
| RA-Minimum/Maximum und Anzahl `ra > 24` | `12.2490556` / `13.2801695` / `0 von 1.689.257` | Bestätigt für den ausgeführten Befehl |
| Konvertierung des Beispielwerts als Stunden | RA `13:15:21.01`, `198.8375417°` | Mathematisch bestätigt, Einheit noch per Quelle absichern |
| Konvertierung von `tstart` als MJD UTC | `2025-11-05T04:14:12.880` | Rechenoutput bestätigt; Zeitkonvention der Quelldatei prüfen |
| Plausibilität gegen öffentliche RA/Dec-Angabe für 3I/ATLAS am 5. November | Sehr nahe Koordinaten, aber nicht exakt derselbe Zeitpunkt | Starker Plausibilitätshinweis, keine abschließende Validierung |
| Azimut/Elevation für alle Zeilen ausgegeben | `1.689.257` Zeilen verarbeitet und berechnet | Erfolgreiche Ausführung bestätigt |
| Azimut/Elevation unabhängig verifiziert | Kein zeitsynchronisierter unabhängiger Vergleich dokumentiert | **Offen** |

**Gesamtfazit:** Die vorhandenen Nachweise machen es überzeugend plausibel, dass die `ra`-Spalte in Dezimalstunden vorliegt. Die errechneten Azimut-/Elevationswerte wurden erfolgreich erzeugt, sind anhand der bislang dokumentierten Schritte aber noch nicht unabhängig wissenschaftlich validiert. Erst der zeit- und standortgleiche Vergleich mit einer vertrauenswürdigen Ephemeride kann diesen letzten Schritt abschließen.
