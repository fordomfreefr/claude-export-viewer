# Claude Export Viewer (Version 2026.10.26.16)

[English](README.md) | [Français](README.fr.md) | [Español](README.es.md) | **Deutsch** | [Italiano](README.it.md) | [Português](README.pt.md) | [Nederlands](README.nl.md) | [Polski](README.pl.md) | [Русский](README.ru.md) | [中文](README.zh.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

Verwandeln Sie den Unterhaltungsverlauf von Claude.ai in eine lokale HTML-Website, die jeder Browser ohne Internetverbindung öffnen kann, und bewahren Sie ein fortlaufendes Archiv Ihrer Unterhaltungen auf, auch derjenigen, die inzwischen auf Claude.ai gelöscht wurden.

![Bildschirmfoto](docs/apercu.png)

Dieses Projekt basiert auf [claude-export-viewer](https://github.com/lordjabez/claude-export-viewer) von Judson Neer und wurde stark verändert und erweitert (siehe „Lizenz und Dank“).

> Dieses Projekt ist unabhängig und nicht mit Anthropic verbunden. Claude ist eine Marke von Anthropic.

> Es wurde unter Linux Ubuntu 26.04 in Python 3.14 und JavaScript entwickelt und getestet. Es sollte auch unter Windows funktionieren. Der Code wurde mit Claude geschrieben (Modell Opus 5.5, hohe Denktiefe). Diese README ist eine maschinelle Übersetzung der französischen Fassung.

## Schnellstart unter Linux Ubuntu / Debian

1. Holen Sie den Unterhaltungsverlauf auf claude.ai: **Einstellungen > Datenschutz > Daten exportieren**. Sie erhalten zuerst eine Informations-E-Mail und dann eine zweite mit einem Link zum Herunterladen einer „Manifest“-Datei.

2. Installieren Sie die 4 Bibliotheken und Pandoc in einem Terminal:  
`sudo apt install python3-jinja2 python3-mistune python3-pydantic python3-pygments pandoc`

3. Speichern Sie das Programm `claude-export-viewer.zip` in `~/Downloads`.

4. Entpacken Sie es in Ihren persönlichen Ordner und starten Sie es: Die Dateien des Exports werden anhand des Manifests heruntergeladen und importiert, dann öffnet sich die Übersicht.  
`cd ~/Downloads && unzip -o claude-export-viewer.zip`  
`rm -rf ~/claude-export-viewer && mv claude-export-viewer ~/`  
`cd ~/claude-export-viewer`  
`python3 claude-export-viewer.py ~/Downloads -o ~/claude_site`  
(Das `rm -rf` entfernt nur die vorherige Version des Programms: Ihre Unterhaltungen liegen in `~/claude_site`.)

5. Erstellen Sie einmalig das Startsymbol auf dem Desktop:  
`python3 claude-export-viewer.py -o ~/claude_site --install-icon`

## Funktionen

- **Gesamtübersicht** aller Unterhaltungen mit:
  - Suche in den Titeln, mit Trefferzähler;
  - Sortierung der Unterhaltungen: nach Erstellungsdatum, Datum des letzten Austauschs, Titel, Anzahl der Nachrichten;
  - eigenen **Rubriken**, gewählt in einem kleinen Menü rechts neben jeder Unterhaltung, zum gezielten Filtern;
  - die **Suche im Inhalt** (ab 3 Buchstaben): nur Unterhaltungen, die alle Wörter enthalten, bleiben stehen, mit der Zahl der Fundstellen; ein Wort wird im Text gesucht, ein Befehl wie `\alpha` in den Formeln, ein Symbol wie `α` oder `∞` in beidem; Groß-/Kleinschreibung und Akzente werden ignoriert.
- **In jeder Unterhaltung**:
  - lokales Datum und Uhrzeit, Link **Auf claude.ai öffnen** (falls sie dort noch existiert);
  - formatiertes Markdown (fett, Listen, Tabellen) und hervorgehobener Code (Pygments);
  - Code-Rahmen mit dem Namen der Sprache und einer Schaltfläche **Kopieren** (kopiert den exakten Code in die Zwischenablage);
  - **mathematische Formeln wie in LaTeX dargestellt** (KaTeX, mitgeliefert, offline): `$…$`, `$$…$$`, `\(…\)`, `\[…\]`; beim Kopieren einer Passage wird der LaTeX-Quelltext ihrer Formeln kopiert; eine Formel, die nicht dargestellt werden kann, bleibt als Quelltext stehen, mit dem Grund im Tooltip;
  - angezeigte Artefakte (Code, Dokumente, HTML/SVG als Code gezeigt, nie ausgeführt);
  - Denkprozesse, Werkzeugaufrufe und Ergebnisse in einklappbaren Blöcken;
  - **mehrere Versionen**: Wurde eine Nachricht bearbeitet oder eine Antwort neu erzeugt, folgt die Seite der Version, die zum letzten Austausch führt; die anderen Versionen stehen in einklappbaren Rahmen „Andere Version“, an der Stelle, an der sich die Unterhaltung verzweigt hat;
  - **Export nach Markdown, LibreOffice (.odt) und Word (.docx) auf Wunsch**: eine Schaltfläche „.md“ in jeder Unterhaltung; die Datei enthält den Hauptverlauf und, in Rahmen (Zitaten) mit kursiven Beschriftungen, jede andere Version an ihrem Verzweigungspunkt (oder, bei abgewähltem Kästchen, nur den Hauptverlauf); Formeln als `$…$`, Code, Artefakte und Namen der Anhänge inklusive (ohne Denkprozesse und Werkzeugergebnisse); lesbar mit Typora, Obsidian, Zettlr, umwandelbar mit Pandoc;
  - **PDF-Export** über das Druckfenster des Browsers, Formeln inklusive;
  - **gesuchte Wörter hervorgehoben**, wenn die Seite aus der Übersicht geöffnet wird, mit einer kleinen Leiste, um von Fundstelle zu Fundstelle zu springen;
  - **Antworten von Claude ausblenden**, um nur Ihre Nachrichten untereinander zu sehen (kleiner Pfeil nach dem Datum jeder Nachricht, Schaltfläche oben rechts für alle);
  - **eine Nachricht kopieren** als Markdown, Formeln in LaTeX, über das Symbol neben dem Datum;
  - **Tastaturnavigation**: ← und → (4 und 6 des Ziffernblocks, wenn er aus ist), um von einer Ihrer Nachrichten zur nächsten zu gehen, 7, 5 und 1 des Ziffernblocks für Anfang, Mitte und Ende der Seite, M zum Ausblenden der Antworten, ? für die Liste; dieselben Schaltflächen rechts, mit **langsamem, fortlaufendem Scrollen** in einstellbarem Tempo (+ und −);
  - **angehängte Dokumente**: vollständiger Text (keine Kürzung mehr auf 3000 Zeichen), als Datei gespeichert und über ein Symbol mit dem Programm des Computers geöffnet; die von claude.ai automatisch hinzugefügten Anweisungen werden nur einmal angezeigt.
- **Ihre Dateien wiedergefunden**: die Bilder und Dateien, die Sie gesendet haben, die Originale der angehängten Dokumente und die von Claude erstellten Dateien, die Sie gespeichert haben, werden unter ihrem genauen Namen in den in der Übersicht gewählten Ordnern gesucht (mit Unterordnern), in die Website kopiert und in der Unterhaltung angezeigt; Schaltflächen Ja / Nein, um zu bestätigen, dass es die richtige Datei ist (und Ändern, um die Antwort zu korrigieren); noch fehlende Dateien werden bei jedem Start erneut gesucht.
- **Fortlaufendes Archiv**: aufeinanderfolgende Exporte werden ohne Duplikate ergänzt, und inzwischen auf claude.ai gelöschte Unterhaltungen bleiben erhalten.
- **12 Sprachen** (Seiten, Konsole, Exporte), wählbar in der Übersicht.
- **Desktop-Symbol** (Linux, Windows), das die Übersicht öffnet und mit einem Klick einen neuen Export importiert.
- Helles oder dunkles Design, je nach Systemeinstellung.

## Installation

Entpacken Sie diesen Ordner an einen beliebigen Ort (Festplatte, USB-Stick…) und installieren Sie die vier benötigten Bibliotheken.

**Ubuntu / Debian**: siehe „Schnellstart“ oben.

**Windows** (Python 3.11 oder neuer, von [python.org](https://www.python.org/downloads/) oder aus dem Microsoft Store), in einem Terminal (PowerShell oder Eingabeaufforderung):

```
py -m pip install jinja2 mistune pydantic pygments
```

Ersetzen Sie unter Windows in den Befehlen dieses Dokuments `python3` durch `py` und die Pfade `~/…` durch Windows-Pfade (`C:\Users\[Benutzer]\claude_site`, `E:\claude_site` für einen USB-Stick…). **Die Windows-Unterstützung wurde anhand der Dokumentation von Python und Windows geschrieben, aber noch nicht auf einem Windows-Rechner ausprobiert**: Rückmeldungen sind willkommen.

## Das Symbol „Claude-Archiv“ (der einfachste Weg)

Erstellen Sie nach dem ersten Import (siehe unten) einmal das Symbol:

```
python3 claude-export-viewer.py -o ~/claude_site --install-icon
```

Es erscheint im Anwendungsmenü und auf dem Desktop (Linux; KDE fragt eventuell einmal, ob dem Starter vertraut werden soll), oder im Startmenü und auf dem Desktop (Windows: Verknüpfungen, die PowerShell anlegt und die `pythonw.exe` starten, sodass sich kein Konsolenfenster öffnet; nicht ausprobiert). Ein Klick öffnet die Übersicht im Browser, bereitgestellt von einem kleinen lokalen Server (http://127.0.0.1:8000), der sich 30 Minuten nach dem Schließen der letzten Seite von selbst beendet (`--idle`, um diese Frist zu ändern). Ein zweiter Klick verwendet den bereits laufenden Server wieder, außer wenn er von einer früheren Version des Programms gestartet wurde: Dann wird er beendet und ersetzt, damit wirklich die neue Version verwendet wird. Legen Sie das Programm in einen festen Ordner (zum Beispiel `~/claude-export-viewer`), bevor Sie das Symbol erstellen.

Über das Symbol geöffnet, fasst die Übersicht ihre Einstellungen oben in einem Rahmen zusammen: die Schaltflächen **Neues Manifest importieren** und **Rubriken verwalten**, darunter den Download-Ordner mit seiner Schaltfläche **Ändern**. Jede Schaltfläche öffnet ihren Bereich; ein zweiter Klick (oder das Kreuz) schließt ihn. Die Schaltfläche **Neues Manifest importieren**: Nachdem Sie den Export auf claude.ai angefordert und auf den Link der E-Mail geklickt haben, die meldet, dass Ihre Daten bereitstehen, nimmt sie das neueste Manifest aus Ihrem Download-Ordner, öffnet die Links nacheinander (sie werden auch anklickbar im Protokoll der Seite angezeigt), importiert den Export und lädt die Übersicht neu. Das Schließen des Protokolls während eines Imports bricht ihn nicht ab: Ein weiterer Klick zeigt es wieder an.

Im selben Rahmen zeigt die Zeile **Download-Ordner**, wo nach dem Manifest gesucht wird. Speichert Ihr Browser Dateien woanders (seine Einstellung „Dateien speichern unter“ oder „Speicherort“), klicken Sie auf **Ändern** und geben Sie diesen Ordner an: Er wird im Archiv gespeichert und zuerst durchsucht, vor dem Systemordner. Ein leeres Feld kehrt zum Systemordner zurück; verschwindet der gewählte Ordner (USB-Stick entfernt), wird der Systemordner verwendet.

Und in jeder Unterhaltung funktionieren die Exporte .md, .odt und .docx mit einem Klick.

**Sicherheit**: Der Server lauscht nur auf Ihrem Computer (127.0.0.1) und liefert das Rohdaten-Archiv nicht aus. Der Import erfordert ein „geheimes Token“, das nur die Seiten der Übersicht lesen können, und Anfragen von einer anderen Website werden abgelehnt: Eine im selben Browser geöffnete Webseite kann sie nicht auslösen.

## Befehlszeile

1. Auf claude.ai: **Einstellungen > Datenschutz > Daten exportieren**.
2. Wenn die E-Mail eintrifft, klicken Sie auf ihren Link: Der Browser lädt eine kleine „Manifest“-Datei herunter (die Liste der Dateien des Exports und ihrer Links).
3. Starten Sie:

```
python3 claude-export-viewer.py ~/Downloads -o ~/claude_site
```

Das Programm nimmt das neueste Manifest des Ordners und:

- öffnet selbst jeden Link in Ihrem Browser (in dem Sie bei claude.ai angemeldet sind), **einen nach dem anderen**, und wartet das Ende jedes Downloads ab (ein Link kann nach Gebrauch ungültig werden);
- erkennt bereits heruntergeladene Dateien, auch wenn der Browser sie umbenannt hat (`conversations-000 (1).zip`), und ignoriert die eines früheren Exports;
- verschiebt die Dateien nach `~/claude_site/archive/exports/<Datum>/`;
- importiert den Export in das Archiv und öffnet die Übersicht.

Standardmäßig werden nur die nützlichen Dateien geholt (Unterhaltungen, Projekte, Konto). Optionen:

- `--all`: alle 7 Dateien des Exports holen (vollständige Sicherung);
- `--browser brave-browser`: den Browser wählen, der die Links öffnet;
- `--manual`: nichts öffnen; die Links werden nacheinander im Terminal angezeigt (Strg + Klick zum Öffnen, oder Rechtsklick > Adresse kopieren, um sie im Browser Ihrer Wahl einzufügen), und das Programm geht zum nächsten über, sobald die Datei angekommen ist;
- `--timeout 600`: bis zu 600 s auf jeden Download warten (standardmäßig 300, im manuellen Modus 900);
- `--no-browser`: die Übersicht am Ende nicht öffnen;
- `--downloads ORDNER`: den Ordner speichern, in dem Ihr Browser Downloads ablegt (dieselbe Einstellung wie „Ändern“ in der Übersicht); `--downloads ""` kehrt zum Systemordner zurück. Allein, ohne zu importierende Datei, speichert die Option die Einstellung und beendet sich.

Jede Option hat auch einen französischen Namen (`--tout`, `--navigateur`, `--manuel`, `--delai`, `--sans-navigateur`, `--telechargements`…), angezeigt von `--help`.

**Voraussetzung**: im Browser, der die Links öffnet, bei claude.ai angemeldet sein (Export-Links funktionieren nur in einer angemeldeten Sitzung). Im automatischen Modus wird jeder Link auch im Terminal angezeigt: Hat sich der falsche Browser geöffnet, öffnen Sie ihn im richtigen, das Programm erkennt die Datei trotzdem. Strg + C bricht sauber ab; derselbe Befehl setzt dort fort, wo er aufgehört hat.

Browser: alle, die im üblichen Download-Ordner speichern (laufende Downloads `.crdownload` von Chrome, Brave, Edge, Opera, Vivaldi, `.part` von Firefox, `.download` von Safari), oder im mit `--downloads` angegebenen Ordner. Der Systemordner wird unter Linux mit `xdg-user-dir` und unter Windows in der Registry gefunden (auch wenn er verschoben wurde, zum Beispiel nach OneDrive). Unter Linux getestet; macOS und Windows sollten funktionieren, wurden aber noch nicht ausprobiert.

Die Links verfallen 24 Stunden nach Erstellung des Exports; danach meldet das Programm dies und erinnert daran, wie man einen neuen Export anfordert. Es werden nur Links zu `https://claude.ai/` geöffnet, und es werden keine Zugangsdaten verarbeitet: Der Download erfolgt in Ihrem eigenen Browser.

Man kann die ZIP-Dateien (oder den entpackten Ordner) auch direkt angeben:

```
python3 claude-export-viewer.py ~/Downloads/conversations-000.zip -o ~/claude_site
```

Unterhaltungen ganz ohne ausgetauschten Text werden von der Website ausgeschlossen: So erscheinen gelöschte Unterhaltungen im Export, manchmal mit einem Rest (Bild oder angehängte Datei, leere Antwort), der nicht als Text zählt. Fügen Sie `--keep-empty` hinzu, um sie trotzdem aufzunehmen.

## Rubriken

Jede Unterhaltung kann eine Rubrik Ihrer Wahl erhalten („Mathe“, „Medizin“, „Wissenschaft“…), eine pro Unterhaltung.

- **Wählen**: Wenn die Übersicht über das Symbol geöffnet ist, bietet ein kleines Menü rechts neben jeder Unterhaltung die vorhandenen Rubriken, „Keine Rubrik“ und **Neue Rubrik…** zum Anlegen einer neuen (höchstens 40 Zeichen; „Mathe“ und „mathe“ sind dieselbe Rubrik).
- **Filtern**: Sobald eine Rubrik existiert, erscheint neben den anderen Filtern ein Menü „Alle Rubriken“ mit „Ohne Rubrik“ und jeder einzelnen Rubrik. Es lässt sich mit der Suche, den anderen Filtern und allen Sortierungen kombinieren: Bei „Alle Rubriken“ bleiben alle Unterhaltungen sichtbar.
- **Verwalten**: Die Schaltfläche **Rubriken verwalten** neben der Import-Schaltfläche zeigt jede Rubrik mit der Anzahl ihrer Unterhaltungen, um sie umzubenennen (die Umbenennung in eine vorhandene Rubrik führt beide zusammen) oder zu löschen (ihre Unterhaltungen bleiben, ohne Rubrik).

Die Rubriken werden im Archiv gespeichert (`archive/topics.json`): Sie folgen der Website (USB-Stick, anderer Browser) und überstehen spätere Importe. Direkt über `index.html` geöffnet, ohne das Programm, zeigt die Übersicht die Rubriken und erlaubt das Filtern, aber nicht das Ändern.

## Wo Programm und Website liegen können

Der Programmordner (`claude-export-viewer`) und der Ordner der Website (`claude_site`, gewählt mit `-o`) können überall liegen, auch auf einem USB-Stick:

```
python3 /media/ich/USB/claude-export-viewer/claude-export-viewer.py ~/Downloads -o /media/ich/USB/claude_site
```

Die Website öffnet sich dann über `index.html`, auf jedem Computer, auch ohne das Programm (die Import-Schaltfläche und die Exporte .odt/.docx benötigen das Programm; die Exporte .md und .pdf funktionieren überall). Das Symbol und die in den Seiten angezeigten Befehle speichern vollständige Pfade: Wird der Stick woanders eingehängt (anderer Computer, anderer Laufwerksbuchstabe unter Windows), erstellen Sie das Symbol vom neuen Ort aus neu; die Seiten werden beim nächsten Import aktualisiert.

## Sprachen

Das Programm spricht 12 Sprachen: Englisch, Französisch, Spanisch, Deutsch, Italienisch, Portugiesisch, Niederländisch, Polnisch, Russisch, Chinesisch (vereinfacht), Japanisch und Koreanisch.

- **Die Seiten** öffnen sich in der Sprache des Browsers oder auf Englisch, wenn diese nicht verfügbar ist. Das Menü oben rechts in der Übersicht ändert die Sprache der gesamten Website mit einem Klick: Übersicht, Unterhaltungen, Datumsangaben (im Format des jeweiligen Landes), Exporte und Importprotokoll. Der Browser merkt sich die Wahl.
- **Die Konsolenmeldungen** folgen der Systemsprache oder der Option `--lang` (`--langue`): `--lang de`, `--lang fr`…
- **Der Name des Symbols** folgt der Sprache der Sitzung („Claude-Archiv“ auf Deutsch, „Claude Archives“ auf Englisch…).
- Die Unterhaltungen selbst werden nie übersetzt. Code und Formeln sind so markiert, dass die automatische Übersetzung eines Browsers sie unverändert lässt.

Übersetzungen außer Französisch und Englisch sind maschinelle Übersetzungen: Korrekturen sind willkommen. Jede Sprache ist eine einfache Textdatei, `src/claude_export_viewer/i18n/<Code>.json`; ein in einer Sprache fehlender Satz wird auf Englisch angezeigt.

## Eine Unterhaltung exportieren (.md, .odt, .docx, .pdf)

Jede Unterhaltungsseite bietet „Exportieren: .md .odt .docx .pdf“, gefolgt vom Kästchen **Andere Versionen und gelöschte Teile einschließen**:

- angehakt (Standard): Alles wird exportiert, die anderen Versionen und die gelöschten Teile in eingerückten Rahmen an ihrem Verzweigungspunkt;
- abgewählt: Nur der **Hauptverlauf** wird exportiert (der auf der Seite angezeigte), und der Dateiname endet auf „(Hauptverlauf)“.

Der Browser merkt sich die letzte Wahl. In der Befehlszeile entspricht das abgewählte Kästchen der Option `--main-thread`.

- **.md** funktioniert immer, direkt im Browser.
- **.pdf** funktioniert ebenfalls immer: Es öffnet das Druckfenster des Browsers, in dem man nur „Als PDF speichern“ wählt. Die Formeln sehen genau wie auf dem Bildschirm aus, auf weißem Hintergrund auch im dunklen Modus; der Inhalt ist derselbe wie bei den anderen Formaten (ohne Denkprozesse und Werkzeuge), und der Dateiname wird vorgeschlagen.
- **.odt** (LibreOffice) und **.docx** (Word) laufen über Pandoc, das LaTeX-Formeln in echte, bearbeitbare Formeln umwandelt. Installieren Sie es einmal (siehe „Optionale Abhängigkeiten“). Zwei Möglichkeiten:
  - **mit einem Klick**, wenn Sie die Website über den kleinen eingebauten lokalen Server ansehen:  
    `python3 claude-export-viewer.py -o ~/claude_site --serve`  
    dann öffnet sich http://127.0.0.1:8000 (Strg + C zum Beenden). Der Server ist nur von Ihrem Computer aus erreichbar;
  - **mit einem Befehl**, wenn die Seite ohne Server geöffnet ist: Die Schaltfläche zeigt den genauen Befehl zum Kopieren, zum Beispiel  
    `python3 claude-export-viewer.py -o ~/claude_site --odt "Pythagoras"`  
    (Titel, Titelanfang oder Kennung; `--export-dir`, um zu wählen, wohin die Datei geschrieben wird).

Formeln, die Pandoc nicht umwandeln kann, bleiben im Dokument als LaTeX stehen, und das Programm meldet sie.

## Fortlaufendes Archiv: die nächsten Exporte hinzufügen

Jeder Export von claude.ai ist eine Momentaufnahme Ihres Kontos. Der Ordner der Website enthält ein **Archiv** (`archive/`), das alle importierten Exporte sammelt. Für einen neuen Export starten Sie einfach denselben Befehl mit demselben Ordner `-o`: Nur neue oder geänderte Unterhaltungen werden verarbeitet.

- **Keine Duplikate**: Jede Unterhaltung wird an ihrer Kennung erkannt.
- **Nichts geht verloren**: Eine auf claude.ai gelöschte Unterhaltung bleibt im Archiv, mit einem Hinweis „Auf claude.ai gelöscht“ in der Übersicht, einem Banner auf ihrer Seite und einem Filter, um sie anzuzeigen oder auszublenden.
- **Verschwundene Nachrichten**: Der Export enthält alle Versionen einer Unterhaltung (bearbeitete Nachrichten, neu erzeugte Antworten). Sollten trotzdem Nachrichten aus einem späteren Export verschwinden, behält das Archiv sie und zeigt sie an ihrer Stelle, in einem Rahmen „Auf claude.ai gelöschter Teil“.
- **Beliebige Reihenfolge**: Ein älterer Export, der nach einem neueren importiert wird, ergänzt das Archiv, ohne etwas zu überschreiben.
- **Datum jedes Exports**: Das Programm sucht das Manifest neben der ZIP-Datei (gibt es mehrere, nimmt es das erste, das nach der neuesten Nachricht des Exports erstellt wurde); andernfalls nimmt es das Datum dieser Nachricht. Sie können es auch mit `--export-date JJJJ-MM-TT` angeben.

**Löschen Sie den Ordner der Website nicht**: `archive/` enthält die Kopie Ihrer Unterhaltungen, auch derjenigen, die auf claude.ai nicht mehr existieren. Zum Sichern kopieren Sie diesen Ordner. Um das Programm zu aktualisieren, ersetzen Sie den Programmordner und starten den Befehl ohne Export, um die Seiten neu zu erzeugen:

```
python3 claude-export-viewer.py -o ~/claude_site
```

Nützliche Optionen: `--rebuild` (alle Seiten neu erzeugen), `--structure EXPORT.zip` (zeigt nur die Feldnamen des Exports, ohne Inhalt: nützlich, um ein Problem zu melden).

Der Fortschritt wird alle 50 Unterhaltungen angezeigt. Unlesbare Elemente werden übersprungen und am Ende mit einer Warnung gemeldet, ohne die Verarbeitung abzubrechen.

## Änderungen gegenüber dem Original

- **Konstanter Speicherbedarf**: Die Unterhaltungen werden einzeln gelesen und geschrieben (Streaming), statt den ganzen Export zu laden. Gemessen an einem künstlichen Export von 595 MB: höchstens 57 MB Speicher (das Original braucht etwa das Vierfache der Dateigröße).
- **Neues Exportformat**: akzeptiert den auf mehrere ZIP-Dateien aufgeteilten Export, einen Ordner oder `.json`- / `.jsonl`-Dateien, unabhängig von ihrem genauen Namen. Das Original suchte nur `conversations.json` und meldete sonst ohne Fehler „0 Unterhaltungen“.
- **Toleranz**: Ein unbekannter Inhaltstyp (Bild, Websuche…), ein unerwarteter Absender, ein leeres Feld oder ein unlesbares Datum bringen nicht mehr die ganze Verarbeitung zum Absturz; sie werden allgemein angezeigt oder ignoriert.
- **Sicherheit**: `javascript:`-Links (und andere gefährliche Protokolle) werden entschärft; in einer Unterhaltung zitierte Bilder werden als Links angezeigt, ohne geladen zu werden (das Archiv bleibt offline lesbar, ohne Kontakt zu fremden Websites); der Export .odt / .docx kann keine Datei des Computers einbetten.
- **Robustheit**: Eine Unterhaltung, die nicht angezeigt werden kann, wird gemeldet und übersprungen, ohne die Erzeugung der Website abzubrechen; ein beschädigtes Archiv liefert eine klare Meldung; ein über mehrere Zeilen gespeichertes Projekt wird erkannt.
- **Code-Hervorhebung**.
- **LaTeX-Formeln**: vor Markdown geschützt (die `_`, `*` und `\\` der Formeln werden nicht mehr beschädigt) und dann von KaTeX 0.16.47 dargestellt, das im erzeugten Ordner mitgeliefert wird (keine Verbindung nötig). Schrittweise Darstellung beim Scrollen: Eine Seite mit 3000 Formeln öffnet sich in weniger als einer Sekunde; vor dem Drucken oder dem PDF-Export wird alles dargestellt.
- **Schaltfläche „Kopieren“** an jedem Code-Rahmen (Codeblöcke und Artefakte), mit dem Namen der Sprache, wie auf claude.ai; behebt nebenbei ein doppeltes `<code>` bei unbekannten Sprachen.
- **Fortlaufendes Archiv** der aufeinanderfolgenden Exporte: keine Duplikate, auf claude.ai gelöschte Unterhaltungen erhalten und markiert, gelöschte Teile einer Unterhaltung an ihrer Stelle erhalten, nur die geänderten Seiten werden neu erzeugt.
- **Geführter Download** anhand des Manifests: Links nacheinander im Browser geöffnet, Warten auf das Ende jedes Downloads, Ablage im Archiv, Import und Öffnen der Übersicht.
- **Markdown-Export** jeder Unterhaltung mit einem Klick, ohne vorher erstellte Datei (der Inhalt ist in die Seite eingebettet und die Datei wird vom Browser erzeugt).
- **Export .odt / .docx** über Pandoc (Befehl `--odt` / `--docx` oder mit einem Klick über den lokalen Server `--serve`); automatische Korrektur einer LaTeX-Konstruktion, die Pandoc ablehnt (`\textbf` innerhalb von `\text{…}`).
- **Mehrsprachig**: 12 Sprachen für Seiten, Konsole, Exporte und Symbol, mit einem Sprachmenü in der Übersicht.
- **Startsymbol** (`--install-icon`), lokaler Server, der sich selbst beendet (`--open`), Schaltfläche „Neues Manifest importieren“, durch ein Token geschützt; Kästchen „Andere Versionen einschließen“, um alles oder nur den Hauptverlauf zu exportieren.
- **Keine Abhängigkeit mehr von uv**: ein Starter `claude-export-viewer.py` für das `python3` des Systems.
- **Eigene Rubriken**, mit Filter und Verwaltung (umbenennen, zusammenführen, löschen), im Archiv gespeichert.
- **Einstellbarer Download-Ordner** (Übersicht oder `--downloads`), für einen Browser, der woanders speichert, oder einen USB-Stick.
- **Windows** (nicht getestet): Download-Ordner aus der Registry gelesen, Texte in UTF-8, `py`-Befehle mit Windows-Anführungszeichen, Verknüpfungen im Startmenü und auf dem Desktop.
- **Suche im Inhalt** der Unterhaltungen, mit hervorgehobenen Wörtern und Sprung von Fundstelle zu Fundstelle; Wörter, LaTeX-Befehle und Symbole.
- **Vollständige angehängte Dokumente** (keine Grenze von 3000 Zeichen mehr), mit dem Programm des Computers geöffnet; **Ihre Dateien** auf dem Computer wiedergefunden und in den Unterhaltungen angezeigt.
- **Lesen**: einklappbare Antworten von Claude, Kopieren einer Nachricht, Navigation mit Tastatur und Ziffernblock, langsames fortlaufendes Scrollen.

## Optionale Abhängigkeiten

- **Pandoc** (Exporte .odt und .docx; getestet mit Pandoc 3.7):
  - unter Linux Ubuntu: `sudo apt install pandoc`;
  - unter Windows: `winget install --source winget --exact --id JohnMacFarlane.Pandoc` (Befehl laut [pandoc.org](https://pandoc.org/installing.html));
  - unter macOS: `brew install pandoc`.

## Lizenz und Dank

Freie Software unter der **MIT-Lizenz** (Datei `LICENSE`): Sie dürfen sie frei nutzen, kopieren, verändern, weitergeben und verwerten, unter der einzigen Bedingung, den Copyright-Hinweis, der ihre Autoren nennt, und den Lizenztext beizubehalten. Sie wird „wie besehen“ bereitgestellt, ohne jede Gewährleistung: Ihre Autoren haften für keinerlei Schäden aus ihrer Nutzung.

- **Autor des ursprünglichen Projekts**: Judson Neer — [github.com/lordjabez](https://github.com/lordjabez), Projekt [claude-export-viewer](https://github.com/lordjabez/claude-export-viewer). Vielen Dank an ihn für diese klare und gut durchdachte Grundlage, ohne die es diese Version nicht gäbe.
- **Änderungen und Ergänzungen**: fordom.
- **KaTeX** (Formeldarstellung, mitgeliefert): MIT-Lizenz, Khan Academy und Mitwirkende, siehe `src/claude_export_viewer/static/katex/LICENSE`.

## Tests

```
sudo apt install python3-pytest      # Windows: py -m pip install pytest
python3 -m pytest tests/ -v          # Windows: py -m pytest tests/ -v
```

Die Windows-Besonderheiten werden unter Linux durch Simulation von Windows geprüft (`tests/test_windows.py`); die Testsuite wurde noch nicht unter Windows ausgeführt. Die Browser-Tests (`tests/test_topics_browser.py`) benötigen Playwright und Chromium; ohne sie werden sie übersprungen.
