# Voyager 3 LCARS lokal starten

Diese Anleitung startet die Weboberflaeche der Raumsonde auf deinem eigenen Rechner.

## Voraussetzungen

- Windows PowerShell
- Python installiert
- Repository befindet sich unter `D:\download\space-probe-I`

## 1. PowerShell oeffnen

Oeffne PowerShell und wechsle in den Projektordner:

```powershell
cd D:\download\space-probe-I
```

Falls du gerade in einem anderen Ordner bist, ist der obige Befehl ausreichend.

## 2. Lokalen Webserver starten

Fuehre diesen Befehl aus:

```powershell
python -m http.server 4173
```

Wenn alles funktioniert, erscheint ungefaehr diese Meldung:

```text
Serving HTTP on :: port 4173
```

Lass dieses PowerShell-Fenster geoeffnet. Der Server laeuft solange, wie der Befehl aktiv ist.

## 3. Weboberflaeche oeffnen

Oeffne im Browser diese Adresse:

[http://localhost:4173/index.html](http://localhost:4173/index.html)

Die Voyager-3-LCARS-Konsole sollte jetzt geladen werden.

## 4. Server beenden

Klicke das PowerShell-Fenster an und druecke:

```text
Ctrl + C
```

Danach ist der lokale Server beendet.

## Wenn Python nicht gefunden wird

Probiere unter Windows diesen Befehl:

```powershell
py -m http.server 4173
```

Wenn auch das nicht funktioniert, muss Python installiert werden. Beim Installieren sollte die Option **Add Python to PATH** aktiviert sein.

## Wenn Port 4173 bereits verwendet wird

Starte den Server auf einem anderen Port, zum Beispiel `4174`:

```powershell
python -m http.server 4174
```

Oeffne danach:

[http://localhost:4174/index.html](http://localhost:4174/index.html)

## Nach Aenderungen aktualisieren

1. Speichere deine Datei in VS Code.
2. Wechsle zum Browser.
3. Druecke `Ctrl + R` fuer einen Reload.
4. Bei hartnaeckigem Cache druecke `Ctrl + F5`.

## Optional: Aenderungen auf Branch `v2` pushen

Wenn du das Tutorial oder weitere Aenderungen committen moechtest:

```powershell
cd D:\download\space-probe-I
git add START_LOCALHOST.md
git commit -m "Add localhost startup tutorial"
git push
```

Da dein Branch bereits mit `origin/v2` verbunden ist, reicht danach `git push` aus.
