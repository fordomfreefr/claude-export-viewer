# Claude Export Viewer

[English](README.md) | [Français](README.fr.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Italiano](README.it.md) | [Português](README.pt.md) | **Nederlands** | [Polski](README.pl.md) | [Русский](README.ru.md) | [中文](README.zh.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

CEV maakt van de export van uw Claude.ai-gesprekken een **lokale bibliotheek**: een site die u offline in de browser leest en waarin u uw gesprekken kunt doorzoeken, van aantekeningen voorzien, herordenen en exporteren. Elke nieuwe export komt bij de vorige: er gaat niets verloren, ook niet wat intussen op claude.ai is verwijderd.

> Onafhankelijk project, niet verbonden aan Anthropic. Claude is een handelsmerk van Anthropic. Ontworpen en getest op Linux (Ubuntu 26.04, Python 3.14); Windows en macOS zouden moeten werken, maar zijn nog niet uitgeprobeerd. 12 talen.

## Installatie

1. Installeer Python 3 en vier bibliotheken:
   - Ubuntu / Debian: `sudo apt install python3-jinja2 python3-mistune python3-pydantic python3-pygments`
   - Windows (Python 3.11 of nieuwer): `py -m pip install jinja2 mistune pydantic pygments`
2. Pak `claude-export-viewer.zip` uit en dubbelklik op **Installer CEV** (`.sh` op Linux, `.cmd` op Windows, `.command` op macOS).

Het programma komt in `~/claude-export-viewer` en maakt het pictogram **Claude-bibliotheek**. Een update gaat op dezelfde manier, met de nieuwe ZIP: uw gesprekken worden nooit aangeraakt.

## Eerste import

1. Op claude.ai (website of desktop-app; niet vanuit de mobiele apps): **Settings > Privacy > Export data** (Instellingen > Privacy > Gegevens exporteren). Er komt een e-mail met een link, 24 uur geldig, die een klein ‘manifest’-bestand downloadt.
2. Open de **Claude-bibliotheek** met haar pictogram. Klik op het tabblad **Gegevensbeheer** op het kader **Een export importeren**: CEV opent de links van de export een voor een in uw browser, importeert alles en toont uw gesprekken.

Herhaal dit af en toe: nieuwe exports vullen het archief aan.

## De Bibliotheek: twee delen

De Bibliotheek heeft twee delen: de **inhoudsopgave**, met al uw gesprekken, en de pagina van elk **gesprek**.

## De inhoudsopgave

![Het bovenste deel van de inhoudsopgave](docs/en/sommaire.png)

Bovenaan de taal, dan drie tabbladen; er is er steeds maar één open, en een klik op het open tabblad sluit het.

**Overzicht**: het aantal gesprekken, berichten en tokens, de grootte van de site en de activiteit per week. **Een klik op een balk filtert de lijst op die week.** De tegel van de grootte krijgt een kleur wanneer een back-up wordt aangeraden; een klik leidt dan naar de knop **Back-up van de Bibliotheek maken**.

![Overzicht](docs/en/vue-ensemble.png)

**Gegevensbeheer**: de import, dan de hulpmiddelen van de Bibliotheek. **Rubrieken beheren** (hernoemen, samenvoegen, verwijderen); **Back-up van de Bibliotheek maken** in een gedateerde ZIP; **Alles exporteren** als Markdown, leesbaar zonder CEV; **Ruimte vrijmaken** (bestanden die niet meer nodig zijn); **Aantekeningen herstellen** (CEV bewaart de laatste 5 toestanden van uw aantekeningen); **Archief controleren** (en een beschadigd gesprek herstellen uit de bewaarde exports); **Verwijderen**, nadat kopieën van alles zijn aangeboden.

![Gegevensbeheer](docs/en/gestion.png)

**Filters**: zoeken in de titels en in de inhoud (tekst, formules: `\alpha` of `α`), met een aantal **toegestane fouten**; rubriek, periode en sortering.

![Filters](docs/en/filtres.png)

**De lijst**: elk gesprek met datum, grootte en aantekeningen (favorieten, koppelingen, notities). Het menu rechts geeft het een **rubriek**. Om twee gesprekken te **koppelen**, sleept u het ene op het andere.

![De lijst van gesprekken](docs/en/liste.png)

## Het gesprek

![Het bovenste deel van een gesprek](docs/en/discussion.png)

Bovenaan: de titel, met rechts de **Weergave** (Lezen of Structuur). Daaronder tabbladen die eerst gesloten zijn; er is er steeds maar één open, en een klik op het open tabblad sluit het.

- **Tekstballonnen**: **Verbergen** maakt het scherm rustiger (hulpmiddelen van de AI, notities, titels, nummers, andere versies en verwijderingen); **Hoogte** beperkt elke tekstballon tot 1, 3 of 5 regels; **Stemmen** kiest de stemmen voor het voorlezen. Uw keuzes blijven van het ene gesprek naar het andere bewaard.
- **Exporteren**: een bestand .md, .odt, .docx, .txt of .pdf, met of zonder uw aantekeningen en de andere versies, desgewenst als ZIP.
- **Koppelingen**, **Favorieten**, **Notities** en **Titels** van de pagina: een klik brengt u erheen.

**De tekstballonnen** worden getoond zoals op claude.ai: Markdown, gekleurde code met een knop Kopiëren, wiskundige formules, artefacten (de programma’s van Claude draaien in de pagina, offline), volledige bijgevoegde documenten.

![Tekstballonnen](docs/en/bulles.png)

- Na de datum de pictogrammen van de tekstballon: **favoriet**, **notitie**, **titel**, kopiëren, dit bericht exporteren, het oog (bij uw berichten: het antwoord van Claude tonen of verbergen), **voorlezen**.
- Vóór de naam de plaats van de tekstballon in het gesprek: `1 ← 2 → 2.1 3` = vraag 2 volgt op 1, heeft een ander antwoord (2.1) en wordt gevolgd door 3. Een klik op een stip brengt u erheen.
- **Andere versie**: als een bericht is bewerkt of een antwoord opnieuw gegenereerd, blijven de andere versies leesbaar in deze kaders, op hun plaats.
- **Markering** in 5 kleuren: selecteer een passage en dan de pen die ernaast verschijnt (of de knop rechts).

Een heel lang gesprek wordt over meerdere pagina’s verdeeld (‘Deel 2 van 5’), zonder ooit een vraag van haar antwoord te scheiden; zoeken in de pagina, de Structuur en de export gelden dan voor het getoonde deel.

**De Structuur** toont het schema van het gesprek: genummerde vragen, versies als takken. Een klik toont een vraag met al haar antwoorden. U kunt de **logische volgorde herordenen** (een vraag achter een antwoord slepen, een tak afsnijden, een groene logische koppeling trekken) zonder de werkelijke volgorde aan te raken; ‘Volgorde: werkelijk · logisch’, in de balk van de Structuur, wisselt tussen beide.

![De structuur](docs/en/structure.png)

**Reeksen**: als een gesprek in een ander verdergaat, opent u het tabblad **Koppelingen** en sleept u de gekoppelde gesprekken in de gewenste volgorde. Elke pagina van de reeks toont dan ‘← vorige · volgende →’, boven en onder.

![Een reeks](docs/en/suite.png)

<img src="docs/en/boutons.png" align="right" width="70" alt="De knoppen rechts">

**De knoppen rechts**, in twee kaders. Boven: markering (het muiswiel kiest de kleur), terug naar de inhoudsopgave, zoeken in het gesprek, alle antwoorden van Claude verbergen of tonen, achtergrondmuziek, licht of donker thema, vorige of volgende pagina (‹ ›). Onder: uw vorige of volgende bericht, het voorlezen van het hele gesprek, het **langzaam scrollen** (snelheid met het muiswiel), het begin, het midden en het einde van de pagina. De inhoudsopgave heeft dezelfde knoppen, behalve die welke alleen bij een gesprek horen.

Het **voorlezen** gebruikt natuurlijke offline stemmen ([Piper](https://github.com/OHF-Voice/piper1-gpl)), bij het eerste gebruik met uw toestemming geïnstalleerd: een stem voor u, een voor Claude, en de stem van de taal van elke alinea.

<br clear="right">

## Uw gegevens

Alles wat ertoe doet staat in **`~/claude_site/archive/`**: uw gesprekken, de oorspronkelijke exports, uw aantekeningen en uw instellingen. Een gesprek dat op claude.ai is verwijderd, blijft daar, gemarkeerd ‘Verwijderd op claude.ai’. Voor een back-up gebruikt u **Back-up van de Bibliotheek maken** of kopieert u deze map; om alles terug te zetten, sleept u de back-up naar een lege Bibliotheek.

## Opdrachtregel

Alles bestaat ook in een terminal (`python3 claude-export-viewer.py`, `py` op Windows); `--help` geeft de volledige lijst.

| Opdracht | Effect |
| --- | --- |
| `~/Downloads -o ~/claude_site` | importeert de nieuwste export uit de map |
| `-o ~/claude_site --serve` | opent de Bibliotheek |
| `--odt "titel"`, `--docx "titel"` | exporteert een gesprek |
| `--export-all` | alle gesprekken als Markdown |
| `--verify`, `--repair` | controleert het archief, herstelt wat kan |
| `--uninstall`, `--restore ZIP` | verwijdert CEV, zet een back-up terug |

## Aanvullingen en licentie

CEV is ontstaan uit de [claude-export-viewer](https://github.com/lordjabez/claude-export-viewer) van Judson Neer, die we daarvoor bedanken; het is sindsdien grondig veranderd en uitgebreid.

- **Pandoc** voor exports naar .odt en .docx: `sudo apt install pandoc` (Windows: `winget install --exact --id JohnMacFarlane.Pandoc`; macOS: `brew install pandoc`).
- **Piper** voor het voorlezen: door CEV aangeboden bij het eerste gebruik (ongeveer 200 MB, plus 60 MB per stem).

Vrije software onder de **MIT-licentie** (bestand `LICENSE`), zonder garantie geleverd. Inbegrepen: KaTeX (MIT). Op uw verzoek apart geïnstalleerd: Piper (GPL-3). Tests: `python3 -m pytest tests/`.
