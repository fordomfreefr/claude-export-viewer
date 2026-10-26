# Claude Export Viewer (versie 2026.10.25.1)

[English](README.md) | [Français](README.fr.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Italiano](README.it.md) | [Português](README.pt.md) | **Nederlands** | [Polski](README.pl.md) | [Русский](README.ru.md) | [中文](README.zh.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

Zet de gespreksgeschiedenis van Claude.ai om in een lokale HTML-site die elke browser zonder internetverbinding kan openen, en bewaar een doorlopend archief van uw gesprekken, ook van de gesprekken die sindsdien op Claude.ai zijn verwijderd.

Dit project is gebaseerd op [claude-export-viewer](https://github.com/lordjabez/claude-export-viewer) van Judson Neer, sterk aangepast en uitgebreid (zie „Licentie en dank”).

> Dit project is onafhankelijk en niet verbonden aan Anthropic. Claude is een merk van Anthropic.

> Het is ontworpen en getest op Linux Ubuntu 26.04, in Python 3.14 en JavaScript. Het zou ook op Windows moeten werken. De code is geschreven met Claude (model Opus 5.5, hoog redeneerniveau). Deze README is een automatische vertaling van de Franse versie.

## Snel aan de slag op Linux Ubuntu / Debian

1. Haal de gespreksgeschiedenis op via claude.ai (de interface is in het Engels): **Settings > Privacy > Export data** (Instellingen > Privacy > Gegevens exporteren). U ontvangt eerst een informatieve e-mail en daarna een tweede met een link om een „manifest”-bestand te downloaden.

2. Installeer de 4 bibliotheken en Pandoc vanuit een terminal:  
`sudo apt install python3-jinja2 python3-mistune python3-pydantic python3-pygments pandoc`

3. Sla het programma `claude-export-viewer.zip` op in `~/Downloads`.

4. Pak het uit in uw persoonlijke map en start het: de bestanden van de export worden aan de hand van het manifest gedownload en geïmporteerd, daarna opent het overzicht.  
`cd ~/Downloads && unzip -o claude-export-viewer.zip`  
`rm -rf ~/claude-export-viewer && mv claude-export-viewer ~/`  
`cd ~/claude-export-viewer`  
`python3 claude-export-viewer.py ~/Downloads -o ~/claude_site`  
(De `rm -rf` verwijdert alleen de vorige versie van het programma: uw gesprekken staan in `~/claude_site`.)

5. Maak eenmalig het startpictogram op het bureaublad:  
`python3 claude-export-viewer.py -o ~/claude_site --install-icon`

## Functies

- **Algemeen overzicht** van al uw gesprekken, met:
  - zoeken in de titels, met een teller van de resultaten;
  - sorteren van de gesprekken: op aanmaakdatum, datum van de laatste uitwisseling, titel, aantal berichten;
  - eigen **rubrieken**, gekozen in een klein menu rechts van elk gesprek, om naar wens te filteren.
- **In elk gesprek**:
  - lokale datum en tijd, een link **Openen op claude.ai** (als het daar nog bestaat);
  - opgemaakte Markdown (vet, lijsten, tabellen) en gemarkeerde code (Pygments);
  - codekaders met de naam van de taal en een knop **Kopiëren** (kopieert de exacte code naar het klembord);
  - **wiskundige formules weergegeven zoals in LaTeX** (KaTeX, meegeleverd, offline): `$…$`, `$$…$$`, `\(…\)`, `\[…\]`; bij het kopiëren van een passage wordt de LaTeX-bron van de formules gekopieerd; een formule die niet kan worden weergegeven blijft als bron staan, met de reden in een tooltip;
  - artefacten weergegeven (code, documenten, HTML/SVG als code getoond, nooit uitgevoerd);
  - denkstappen, aanroepen van hulpmiddelen en resultaten in inklapbare blokken;
  - **meerdere versies**: als een bericht is bewerkt of een antwoord opnieuw is gegenereerd, volgt de pagina de versie die naar de laatste uitwisseling leidt; de andere versies staan in inklapbare kaders „Andere versie”, op het punt waar het gesprek zich vertakte;
  - **export naar Markdown, LibreOffice (.odt) en Word (.docx) op verzoek**: een knop „.md” in elk gesprek; het bestand bevat de hoofdlijn en, in kaders (citaten) met cursieve labels, elke andere versie op haar vertakkingspunt (of, met het vakje uitgevinkt, alleen de hoofdlijn); formules als `$…$`, code, artefacten en namen van bijlagen inbegrepen (zonder denkstappen en resultaten van hulpmiddelen); leesbaar met Typora, Obsidian, Zettlr, om te zetten met Pandoc;
  - **PDF-export** via het afdrukvenster van de browser, formules inbegrepen.
- **Doorlopend archief**: opeenvolgende exports worden zonder duplicaten toegevoegd, en gesprekken die sindsdien op claude.ai zijn verwijderd, blijven bewaard.
- **12 talen** (pagina's, console, exports), te kiezen in het overzicht.
- **Bureaubladpictogram** (Linux, Windows) dat het overzicht opent en met één klik een nieuwe export importeert.
- Licht of donker thema, volgens de systeeminstelling.

## Installatie

Pak deze map uit waar u maar wilt (schijf, USB-stick…) en installeer de vier benodigde bibliotheken.

**Ubuntu / Debian**: zie „Snel aan de slag” hierboven.

**Windows** (Python 3.11 of nieuwer, van [python.org](https://www.python.org/downloads/) of uit de Microsoft Store), in een terminal (PowerShell of Opdrachtprompt):

```
py -m pip install jinja2 mistune pydantic pygments
```

Vervang op Windows `python3` door `py` in de opdrachten van dit document, en de paden `~/…` door Windows-paden (`C:\Users\[Gebruiker]\claude_site`, `E:\claude_site` voor een USB-stick…). **De ondersteuning voor Windows is geschreven op basis van de documentatie van Python en Windows, maar is nog niet op een Windows-computer uitgeprobeerd**: feedback is welkom.

## Het pictogram „Claude-archief” (de eenvoudigste manier)

Maak na de eerste import (zie hieronder) eenmalig het pictogram:

```
python3 claude-export-viewer.py -o ~/claude_site --install-icon
```

Het verschijnt in het toepassingenmenu en op het bureaublad (Linux; KDE kan eenmalig vragen de starter te vertrouwen), of in het menu Start en op het bureaublad (Windows: snelkoppelingen die PowerShell aanmaakt en die `pythonw.exe` starten, dus zonder consolevenster; niet uitgeprobeerd). Een klik opent het overzicht in de browser, geleverd door een kleine lokale server (http://127.0.0.1:8000) die zichzelf 30 minuten na het sluiten van de laatste pagina stopt (`--idle` om deze termijn te wijzigen). Een tweede klik hergebruikt de server die al draait, tenzij die door een eerdere versie van het programma is gestart: dan wordt hij gestopt en vervangen, zodat echt de nieuwe versie wordt gebruikt. Zet het programma in een vaste map (bijvoorbeeld `~/claude-export-viewer`) voordat u het pictogram maakt.

Via het pictogram geopend, bundelt het overzicht de instellingen bovenaan in een kader: de knoppen **Een nieuw manifest importeren** en **Rubrieken beheren**, daaronder de downloadmap met de knop **Wijzigen**. Elke knop opent zijn paneel; een tweede klik (of het kruisje) sluit het. De knop **Een nieuw manifest importeren**: nadat u de export op claude.ai hebt aangevraagd en op de link in de e-mail hebt geklikt die meldt dat uw gegevens klaarstaan, neemt hij het meest recente manifest uit uw downloadmap, opent de links een voor een (ze worden ook, klikbaar, in het logboek van de pagina getoond), importeert de export en laadt het overzicht opnieuw. Het logboek sluiten tijdens een import onderbreekt die niet: een nieuwe klik toont het weer.

In hetzelfde kader geeft de regel **Downloadmap** aan waar naar het manifest wordt gezocht. Als uw browser bestanden elders opslaat (de instelling „Bestanden opslaan in” of „Locatie”), klik dan op **Wijzigen** en geef die map op: die wordt in het archief onthouden en als eerste doorzocht, vóór de systeemmap. Een leeg veld gaat terug naar de systeemmap; als de gekozen map verdwijnt (USB-stick verwijderd), wordt de systeemmap gebruikt.

En in elk gesprek werken de exports .md, .odt en .docx met één klik.

**Beveiliging**: de server luistert alleen op uw computer (127.0.0.1) en levert het ruwe archief niet uit. Importeren vereist een „geheim token” dat alleen de pagina's van het overzicht kunnen lezen, en verzoeken van een andere site worden geweigerd: een webpagina die in dezelfde browser is geopend, kan ze niet in gang zetten.

## Opdrachtregel

1. Op claude.ai: **Settings > Privacy > Export data** (Instellingen > Privacy > Gegevens exporteren).
2. Als de e-mail binnenkomt, klik dan op de link: de browser downloadt een klein „manifest”-bestand (de lijst van de bestanden van de export en hun links).
3. Start:

```
python3 claude-export-viewer.py ~/Downloads -o ~/claude_site
```

Het programma neemt het meest recente manifest uit de map en:

- opent zelf elke link in uw browser (waarin u bij claude.ai bent aangemeld), **een voor een**, en wacht tot elke download klaar is (een link kan na gebruik ongeldig worden);
- herkent bestanden die al zijn gedownload, ook als de browser ze heeft hernoemd (`conversations-000 (1).zip`), en negeert die van een eerdere export;
- verplaatst de bestanden naar `~/claude_site/archive/exports/<datum>/`;
- importeert de export in het archief en opent het overzicht.

Standaard worden alleen de nuttige bestanden opgehaald (gesprekken, projecten, account). Opties:

- `--all`: alle 7 bestanden van de export ophalen (volledige back-up);
- `--browser brave-browser`: de browser kiezen die de links opent;
- `--manual`: niets openen; de links worden een voor een in de terminal getoond (Ctrl + klik om ze te openen, of rechtsklik > adres kopiëren om ze in de browser van uw keuze te plakken) en het programma gaat door naar de volgende zodra het bestand is aangekomen;
- `--timeout 600`: tot 600 s op elke download wachten (standaard 300, in handmatige modus 900);
- `--no-browser`: het overzicht aan het eind niet openen;
- `--downloads MAP`: de map onthouden waarin uw browser downloads opslaat (dezelfde instelling als „Wijzigen” in het overzicht); `--downloads ""` gaat terug naar de systeemmap. Alleen gebruikt, zonder te importeren bestand, slaat de optie de instelling op en stopt.

Elke optie heeft ook een Franse naam (`--tout`, `--navigateur`, `--manuel`, `--delai`, `--sans-navigateur`, `--telechargements`…), getoond door `--help`.

**Voorwaarde**: aangemeld zijn bij claude.ai in de browser die de links opent (exportlinks werken alleen in een aangemelde sessie). In automatische modus wordt elke link ook in de terminal getoond: als de verkeerde browser is geopend, open hem dan in de juiste, het programma merkt het bestand toch op. Ctrl + C stopt netjes; dezelfde opdracht opnieuw uitvoeren gaat verder waar hij was gebleven.

Browsers: alle browsers die in de gebruikelijke downloadmap opslaan (lopende downloads `.crdownload` van Chrome, Brave, Edge, Opera, Vivaldi, `.part` van Firefox, `.download` van Safari), of in de map die met `--downloads` is opgegeven. De systeemmap wordt op Linux gevonden met `xdg-user-dir` en op Windows in het register (ook als hij is verplaatst, bijvoorbeeld naar OneDrive). Getest op Linux; macOS en Windows zouden moeten werken, maar zijn nog niet uitgeprobeerd.

De links verlopen 24 uur na het aanmaken van de export; daarna meldt het programma dit en herinnert het eraan hoe u een nieuwe export aanvraagt. Er worden alleen links naar `https://claude.ai/` geopend, en er worden geen inloggegevens verwerkt: de download gebeurt in uw eigen browser.

U kunt de ZIP-bestanden (of de uitgepakte map) ook rechtstreeks opgeven:

```
python3 claude-export-viewer.py ~/Downloads/conversations-000.zip -o ~/claude_site
```

Gesprekken zonder enige uitgewisselde tekst worden van de site weggelaten: zo verschijnen verwijderde gesprekken in de export, soms met een restant (afbeelding of bijgevoegd bestand, leeg antwoord) dat niet als tekst telt. Voeg `--keep-empty` toe om ze toch op te nemen.

## Rubrieken

Elk gesprek kan een rubriek naar keuze krijgen („wiskunde”, „geneeskunde”, „wetenschap”…), één per gesprek.

- **Kiezen**: als het overzicht via het pictogram is geopend, biedt een klein menu rechts van elk gesprek de bestaande rubrieken, „Geen rubriek” en **Nieuwe rubriek…** om er een te maken (hoogstens 40 tekens; „Wisk” en „wisk” zijn dezelfde rubriek).
- **Filteren**: zodra er een rubriek bestaat, verschijnt naast de andere filters een menu „Alle rubrieken”, met „Zonder rubriek” en elke rubriek afzonderlijk. Het is te combineren met de zoekfunctie, de andere filters en alle sorteringen: bij „Alle rubrieken” blijven alle gesprekken zichtbaar.
- **Beheren**: de knop **Rubrieken beheren**, naast de importknop, toont elke rubriek met het aantal gesprekken, om haar te hernoemen (hernoemen naar een bestaande rubriek voegt beide samen) of te verwijderen (haar gesprekken blijven, zonder rubriek).

De rubrieken worden in het archief opgeslagen (`archive/topics.json`): ze volgen de site (USB-stick, andere browser) en blijven behouden bij latere imports. Rechtstreeks via `index.html` geopend, zonder het programma, toont het overzicht de rubrieken en kunt u erop filteren, maar ze niet wijzigen.

## Waar u het programma en de site plaatst

De programmamap (`claude-export-viewer`) en de map van de site (`claude_site`, gekozen met `-o`) kunnen overal staan, ook op een USB-stick:

```
python3 /media/ik/USB/claude-export-viewer/claude-export-viewer.py ~/Downloads -o /media/ik/USB/claude_site
```

De site opent daarna via `index.html`, op elke computer, ook zonder het programma (de importknop en de exports .odt/.docx hebben het programma nodig; de exports .md en .pdf werken overal). Het pictogram en de opdrachten die in de pagina's worden getoond, onthouden volledige paden: als de stick ergens anders wordt gekoppeld (andere computer, andere stationsletter op Windows), maak het pictogram dan opnieuw vanaf de nieuwe locatie; de pagina's worden bij de volgende import bijgewerkt.

## Talen

Het programma spreekt 12 talen: Engels, Frans, Spaans, Duits, Italiaans, Portugees, Nederlands, Pools, Russisch, Chinees (vereenvoudigd), Japans en Koreaans.

- **De pagina's** openen in de taal van de browser, of in het Engels als die niet beschikbaar is. Het menu rechtsboven in het overzicht wijzigt met één klik de taal van de hele site: overzicht, gesprekken, datums (in het formaat van elk land), exports en importlogboek. De browser onthoudt de keuze.
- **De consoleberichten** volgen de systeemtaal, of de optie `--lang` (`--langue`): `--lang nl`, `--lang de`…
- **De naam van het pictogram** volgt de taal van de sessie („Claude-archief” in het Nederlands, „Claude Archives” in het Engels…).
- De gesprekken zelf worden nooit vertaald. Code en formules zijn zo gemarkeerd dat de automatische vertaling van een browser ze ongemoeid laat.

Vertalingen anders dan Frans en Engels zijn automatische vertalingen: correcties zijn welkom. Elke taal is een eenvoudig tekstbestand, `src/claude_export_viewer/i18n/<code>.json`; een zin die in een taal ontbreekt, wordt in het Engels getoond.

## Een gesprek exporteren (.md, .odt, .docx, .pdf)

Elke gesprekspagina biedt „Exporteren: .md .odt .docx .pdf”, gevolgd door het vakje **De andere versies en de verwijderde delen opnemen**:

- aangevinkt (standaard): alles wordt geëxporteerd, de andere versies en de verwijderde delen in ingesprongen kaders, op hun vertakkingspunt;
- uitgevinkt: alleen de **hoofdlijn** wordt geëxporteerd (die op de pagina wordt getoond), en de bestandsnaam eindigt op „(hoofdlijn)”.

De browser onthoudt de laatste keuze. Op de opdrachtregel komt het uitgevinkte vakje overeen met de optie `--main-thread`.

- **.md** werkt altijd, rechtstreeks in de browser.
- **.pdf** werkt ook altijd: het opent het afdrukvenster van de browser, waar u alleen „Opslaan als PDF” kiest. De formules zien er precies zo uit als op het scherm, op een witte achtergrond, ook in de donkere modus; de inhoud is dezelfde als bij de andere formaten (zonder denkstappen en hulpmiddelen) en de bestandsnaam wordt voorgesteld.
- **.odt** (LibreOffice) en **.docx** (Word) gaan via Pandoc, dat LaTeX-formules omzet in echte, bewerkbare formules. Installeer het eenmalig (zie „Optionele afhankelijkheden”). Twee manieren om ze te gebruiken:
  - **met één klik**, door de site te bekijken via de kleine ingebouwde lokale server:  
    `python3 claude-export-viewer.py -o ~/claude_site --serve`  
    daarna opent http://127.0.0.1:8000 (Ctrl + C om te stoppen). De server is alleen vanaf uw computer bereikbaar;
  - **met een opdracht**, als de pagina zonder server is geopend: de knop toont de exacte opdracht om te kopiëren, bijvoorbeeld  
    `python3 claude-export-viewer.py -o ~/claude_site --odt "Pythagoras"`  
    (titel, begin van de titel of identificatie; `--export-dir` om te kiezen waar het bestand wordt geschreven).

Formules die Pandoc niet kan omzetten, blijven als LaTeX in het document staan, en het programma meldt ze.

## Doorlopend archief: de volgende exports toevoegen

Elke export van claude.ai is een momentopname van uw account. De map van de site bevat een **archief** (`archive/`) dat alle geïmporteerde exports verzamelt. Voor een nieuwe export voert u gewoon dezelfde opdracht uit met dezelfde map `-o`: alleen nieuwe of gewijzigde gesprekken worden verwerkt.

- **Geen duplicaten**: elk gesprek wordt herkend aan zijn identificatie.
- **Er gaat niets verloren**: een gesprek dat op claude.ai is verwijderd, blijft in het archief, met een label „Verwijderd op claude.ai” in het overzicht, een melding op zijn pagina en een filter om ze te tonen of te verbergen.
- **Verdwenen berichten**: de export bevat alle versies van een gesprek (bewerkte berichten, opnieuw gegenereerde antwoorden). Mochten er toch berichten uit een latere export verdwijnen, dan bewaart het archief ze en toont ze op hun plaats, in een kader „Verwijderd deel op claude.ai”.
- **Willekeurige volgorde**: een oudere export die na een nieuwere wordt geïmporteerd, vult het archief aan zonder iets te overschrijven.
- **Datum van elke export**: het programma zoekt het manifest naast de zip (als er meerdere zijn, neemt het het eerste dat is aangemaakt na het meest recente bericht van de export); anders neemt het de datum van dat bericht. U kunt hem ook opgeven met `--export-date JJJJ-MM-DD`.

**Verwijder de map van de site niet**: `archive/` bevat de kopie van uw gesprekken, ook van de gesprekken die niet meer op claude.ai bestaan. Kopieer deze map om een back-up te maken. Om het programma bij te werken, vervangt u de programmamap en voert u de opdracht zonder export uit om de pagina's opnieuw te genereren:

```
python3 claude-export-viewer.py -o ~/claude_site
```

Nuttige opties: `--rebuild` (alle pagina's opnieuw genereren), `--structure EXPORT.zip` (toont alleen de veldnamen van de export, zonder inhoud: handig om een probleem te melden).

De voortgang wordt elke 50 gesprekken getoond. Onleesbare elementen worden overgeslagen en aan het eind met een waarschuwing gemeld, zonder de verwerking te onderbreken.

## Wijzigingen ten opzichte van het origineel

- **Constant geheugengebruik**: de gesprekken worden een voor een gelezen en geschreven (streaming), in plaats van de hele export te laden. Gemeten op een fictieve export van 595 MB: hoogstens 57 MB geheugen (het origineel heeft ongeveer 4 keer de bestandsgrootte nodig).
- **Nieuw exportformaat**: accepteert de export verdeeld over meerdere ZIP-bestanden, een map of `.json`- / `.jsonl`-bestanden, ongeacht hun exacte naam. Het origineel zocht alleen naar `conversations.json` en meldde anders zonder fout „0 gesprekken”.
- **Tolerantie**: een onbekend inhoudstype (afbeelding, zoeken op het web…), een onverwachte afzender, een leeg veld of een onleesbare datum laten niet langer de hele verwerking vastlopen; ze worden algemeen getoond of genegeerd.
- **Beveiliging**: `javascript:`-links (en andere gevaarlijke protocollen) worden onschadelijk gemaakt; afbeeldingen die in een gesprek worden genoemd, worden als links getoond, zonder ze te laden (het archief blijft offline leesbaar, zonder contact met sites van derden); de export .odt / .docx kan geen bestand van de computer insluiten.
- **Robuustheid**: een gesprek dat niet kan worden weergegeven, wordt gemeld en overgeslagen zonder de opbouw van de site te onderbreken; een beschadigd archief geeft een duidelijke melding; een project dat over meerdere regels is opgeslagen, wordt herkend.
- **Codemarkering**.
- **LaTeX-formules**: beschermd tegen Markdown (de `_`, `*` en `\\` van formules worden niet langer beschadigd), daarna weergegeven door KaTeX 0.16.47, meegeleverd in de gegenereerde map (geen verbinding nodig). Geleidelijke weergave tijdens het scrollen: een pagina met 3000 formules opent in minder dan een seconde; alles wordt weergegeven vóór het afdrukken of de PDF-export.
- **Knop „Kopiëren”** bij elk codekader (codeblokken en artefacten), met de naam van de taal, zoals op claude.ai; herstelt en passant een dubbele `<code>` bij onbekende talen.
- **Doorlopend archief** van opeenvolgende exports: geen duplicaten, op claude.ai verwijderde gesprekken bewaard en gemarkeerd, verwijderde delen van een gesprek op hun plaats bewaard, alleen de gewijzigde pagina's opnieuw gegenereerd.
- **Begeleide download** aan de hand van het manifest: links een voor een in de browser geopend, wachten tot elke download klaar is, bestanden in het archief opgeborgen, import en opening van het overzicht.
- **Markdown-export** van elk gesprek, met één klik, zonder vooraf aangemaakt bestand (de inhoud is in de pagina ingebed en het bestand wordt door de browser gemaakt).
- **Export .odt / .docx** via Pandoc (opdracht `--odt` / `--docx`, of met één klik via de lokale server `--serve`); automatische correctie van een LaTeX-constructie die Pandoc weigert (`\textbf` binnen `\text{…}`).
- **Meertalig**: 12 talen voor de pagina's, de console, de exports en het pictogram, met een taalmenu in het overzicht.
- **Startpictogram** (`--install-icon`), lokale server die zichzelf stopt (`--open`), knop „Een nieuw manifest importeren” beveiligd met een token; vakje „De andere versies opnemen” om alles of alleen de hoofdlijn te exporteren.
- **Geen afhankelijkheid meer van uv**: een starter `claude-export-viewer.py` voor de `python3` van het systeem.
- **Eigen rubrieken**, met filter en beheer (hernoemen, samenvoegen, verwijderen), opgeslagen in het archief.
- **Instelbare downloadmap** (overzicht of `--downloads`), voor een browser die elders opslaat of een USB-stick.
- **Windows** (niet getest): downloadmap uit het register gelezen, teksten in UTF-8, `py`-opdrachten met Windows-aanhalingstekens, snelkoppelingen in het menu Start en op het bureaublad.

## Optionele afhankelijkheden

- **Pandoc** (exports .odt en .docx; getest met Pandoc 3.7):
  - op Linux Ubuntu: `sudo apt install pandoc`;
  - op Windows: `winget install --source winget --exact --id JohnMacFarlane.Pandoc` (opdracht volgens [pandoc.org](https://pandoc.org/installing.html));
  - op macOS: `brew install pandoc`.

## Licentie en dank

Vrije software onder de **MIT-licentie** (bestand `LICENSE`): u mag hem vrij gebruiken, kopiëren, wijzigen, verspreiden en exploiteren, op de enige voorwaarde dat u de copyrightvermelding, die de auteurs noemt, en de licentietekst behoudt. Hij wordt geleverd „zoals hij is”, zonder enige garantie: de auteurs zijn niet aansprakelijk voor enige schade die uit het gebruik voortvloeit.

- **Auteur van het oorspronkelijke project**: Judson Neer — [github.com/lordjabez](https://github.com/lordjabez), project [claude-export-viewer](https://github.com/lordjabez/claude-export-viewer). Hartelijk dank aan hem voor deze heldere en goed ontworpen basis, zonder welke deze versie niet zou bestaan.
- **Wijzigingen en aanvullingen**: fordom.
- **KaTeX** (weergave van formules, meegeleverd): MIT-licentie, Khan Academy en bijdragers, zie `src/claude_export_viewer/static/katex/LICENSE`.

## Tests

```
sudo apt install python3-pytest      # Windows: py -m pip install pytest
python3 -m pytest tests/ -v          # Windows: py -m pytest tests/ -v
```

De Windows-specifieke zaken worden op Linux gecontroleerd door Windows te simuleren (`tests/test_windows.py`); de testreeks is nog niet op Windows uitgevoerd. De browsertests (`tests/test_topics_browser.py`) hebben Playwright en Chromium nodig; zonder die worden ze overgeslagen.
