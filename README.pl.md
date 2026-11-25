# Claude Export Viewer

[English](README.md) | [Français](README.fr.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Italiano](README.it.md) | [Português](README.pt.md) | [Nederlands](README.nl.md) | **Polski** | [Русский](README.ru.md) | [中文](README.zh.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

CEV zamienia eksport rozmów z Claude.ai w **lokalną bibliotekę**: stronę czytaną w przeglądarce, bez Internetu, w której można przeszukiwać, opisywać, porządkować i eksportować rozmowy. Każdy nowy eksport dołącza do poprzednich: nic nie ginie, nawet to, co zostało później usunięte w claude.ai.

> Niezależny projekt, niezwiązany z Anthropic. Claude jest znakiem towarowym Anthropic. Zaprojektowany i przetestowany w systemie Linux (Ubuntu 26.04, Python 3.14); Windows i macOS powinny działać, ale nie zostały jeszcze wypróbowane. 12 języków.

## Instalacja

1. Zainstaluj Pythona 3 i cztery biblioteki:
   - Ubuntu / Debian: `sudo apt install python3-jinja2 python3-mistune python3-pydantic python3-pygments`
   - Windows (Python 3.11 lub nowszy): `py -m pip install jinja2 mistune pydantic pygments`
2. Rozpakuj `claude-export-viewer.zip` i kliknij dwukrotnie **Installer CEV** (`.sh` w Linuksie, `.cmd` w Windows, `.command` w macOS).

Program trafia do `~/claude-export-viewer` i tworzy ikonę **Biblioteka Claude**. Aktualizacja przebiega tak samo, z nowym plikiem ZIP: rozmowy nigdy nie są naruszane.

## Pierwszy import

1. W claude.ai (strona internetowa lub aplikacja na komputer; nie w aplikacjach mobilnych): **Settings > Privacy > Export data** (Ustawienia > Prywatność > Eksportuj dane). Przychodzi e-mail z linkiem, ważnym 24 godziny, który pobiera mały plik „manifest”.
2. Otwórz **Bibliotekę Claude** jej ikoną. Na karcie **Zarządzanie danymi** kliknij ramkę **Importuj eksport**: CEV otwiera kolejno linki eksportu w przeglądarce, importuje wszystko i pokazuje rozmowy.

Powtarzaj to od czasu do czasu: nowe eksporty uzupełniają archiwum.

## Biblioteka: dwie części

Biblioteka ma dwie części: **spis**, w którym są wszystkie rozmowy, oraz stronę każdej **rozmowy**.

## Spis

![Górna część spisu](docs/en/sommaire.png)

U góry język, a potem trzy karty; otwarta jest tylko jedna naraz, a kliknięcie otwartej karty ją zamyka.

**Przegląd**: liczba rozmów, wiadomości i tokenów, rozmiar strony oraz aktywność tydzień po tygodniu. **Kliknięcie słupka zawęża listę do tego tygodnia.** Kafelek rozmiaru zmienia kolor, gdy zalecana jest kopia zapasowa; kliknięcie prowadzi wtedy do przycisku **Kopia zapasowa Biblioteki**.

![Przegląd](docs/en/vue-ensemble.png)

**Zarządzanie danymi**: import, a potem narzędzia Biblioteki. **Zarządzaj kategoriami** (zmiana nazwy, scalanie, usuwanie); **Kopia zapasowa Biblioteki** do pliku ZIP z datą; **Eksportuj wszystko** do Markdown, czytelnego bez CEV; **Zwolnij miejsce** (pliki już niepotrzebne); **Odzyskaj adnotacje** (CEV przechowuje 5 ostatnich stanów adnotacji); **Sprawdź archiwum** (i napraw uszkodzoną rozmowę z przechowywanych eksportów); **Odinstaluj**, po zaproponowaniu kopii wszystkiego.

![Zarządzanie danymi](docs/en/gestion.png)

**Filtry**: wyszukiwanie w tytułach i w treści (tekst, wzory: `\alpha` lub `α`), z liczbą **dopuszczalnych błędów**; kategoria, okres i sortowanie.

![Filtry](docs/en/filtres.png)

**Lista**: każda rozmowa z datą, rozmiarem i adnotacjami (ulubione, powiązania, notatki). Menu po prawej przypisuje jej **kategorię**. Aby **powiązać** dwie rozmowy, przeciągnij jedną na drugą.

![Lista rozmów](docs/en/liste.png)

## Rozmowa

![Górna część rozmowy](docs/en/discussion.png)

U góry: tytuł, a po prawej **Widok** (Czytanie lub Struktura). Poniżej karty, na początku zamknięte; otwarta jest tylko jedna naraz, a kliknięcie otwartej karty ją zamyka.

- **Dymki**: **Ukryj** odciąża ekran (zasoby AI, notatki, tytuły, numery, inne wersje i usunięcia); **Wyświetlanie** skraca każdy dymek do 1, 3 lub 5 wierszy; **Głosy** wybiera głosy czytania na głos. Wybór zostaje zachowany z jednej rozmowy na następną.
- **Eksport**: plik .md, .odt, .docx, .txt lub .pdf, z adnotacjami lub bez nich i z innymi wersjami lub bez, w razie potrzeby jako ZIP.
- **Powiązania**, **Ulubione**, **Notatki** i **Tytuły** strony: kliknięcie do nich prowadzi.

**Dymki** wyglądają jak w claude.ai: Markdown, kolorowany kod z przyciskiem Kopiuj, wzory matematyczne, artefakty (programy Claude działają na stronie, offline), pełne załączone dokumenty.

![Dymki](docs/en/bulles.png)

- Po dacie ikony dymku: **ulubione**, **notatka**, **tytuł**, kopiowanie, eksport tej wiadomości, oko (przy Twoich wiadomościach: pokaż lub ukryj odpowiedź Claude), **czytanie na głos**.
- Przed nazwą miejsce dymku w rozmowie: `1 ← 2 → 2.1 3` = pytanie 2 następuje po 1, ma inną odpowiedź (2.1), a po nim następuje 3. Kliknięcie znacznika do niego prowadzi.
- **Inna wersja**: gdy wiadomość została zmieniona albo odpowiedź wygenerowana ponownie, inne wersje pozostają czytelne w tych ramkach, na swoim miejscu.
- **Wyróżnienie** w 5 kolorach: zaznacz fragment, a potem pióro, które pojawia się obok (lub przycisk po prawej).

Bardzo długa rozmowa jest pokazywana na kilku stronach („Część 2 z 5”), nigdy nie oddzielając pytania od odpowiedzi; wyszukiwanie na stronie, Struktura i eksport dotyczą wtedy pokazanej części.

**Struktura** pokazuje schemat rozmowy: ponumerowane pytania, wersje jako gałęzie. Kliknięcie pokazuje pytanie ze wszystkimi odpowiedziami. Można **zmienić kolejność logiczną** (przeciągnąć pytanie za odpowiedź, odciąć gałąź, narysować zielone powiązanie logiczne) bez naruszania kolejności rzeczywistej; „Kolejność: rzeczywista · logiczna” na pasku Struktury przełącza między nimi.

![Struktura](docs/en/structure.png)

**Serie**: gdy rozmowa ma ciąg dalszy w innej, otwórz kartę **Powiązania** i przeciągnij powiązane rozmowy w wybranej kolejności. Każda strona serii pokazuje wtedy „← poprzednia · następna →”, u góry i u dołu.

![Seria](docs/en/suite.png)

<img src="docs/en/boutons.png" align="right" width="70" alt="Przyciski po prawej">

**Przyciski po prawej**, w dwóch ramkach. U góry: wyróżnienie (kółko myszy wybiera kolor), powrót do spisu, wyszukiwanie w rozmowie, ukrycie lub pokazanie wszystkich odpowiedzi Claude, muzyka w tle, jasny lub ciemny motyw, poprzednia lub następna strona (‹ ›). U dołu: Twoja poprzednia lub następna wiadomość, czytanie na głos całej rozmowy, **powolne przewijanie** (prędkość kółkiem myszy), początek, środek i koniec strony. Spis ma te same przyciski, poza tymi, które dotyczą tylko rozmowy.

**Czytanie na głos** korzysta z naturalnych głosów offline ([Piper](https://github.com/OHF-Voice/piper1-gpl)), instalowanych przy pierwszym użyciu za Twoją zgodą: jeden głos dla Ciebie, jeden dla Claude i głos języka każdego akapitu.

<br clear="right">

## Twoje dane

Wszystko, co ważne, jest w **`~/claude_site/archive/`**: rozmowy, oryginalne eksporty, adnotacje i ustawienia. Rozmowa usunięta w claude.ai zostaje tam, oznaczona „Usunięta w claude.ai”. Aby zrobić kopię zapasową, użyj **Kopia zapasowa Biblioteki** albo skopiuj ten folder; aby wszystko przywrócić, upuść kopię na pustą Bibliotekę.

## Wiersz poleceń

Wszystko jest też dostępne w terminalu (`python3 claude-export-viewer.py`, `py` w Windows); `--help` podaje pełną listę.

| Polecenie | Działanie |
| --- | --- |
| `~/Downloads -o ~/claude_site` | importuje najnowszy eksport z folderu |
| `-o ~/claude_site --serve` | otwiera Bibliotekę |
| `--odt "tytuł"`, `--docx "tytuł"` | eksportuje rozmowę |
| `--export-all` | wszystkie rozmowy do Markdown |
| `--verify`, `--repair` | sprawdza archiwum, naprawia, co się da |
| `--uninstall`, `--restore ZIP` | odinstalowuje, przywraca kopię zapasową |

## Dodatki i licencja

CEV wyrósł z [claude-export-viewer](https://github.com/lordjabez/claude-export-viewer) autorstwa Judsona Neera, któremu dziękujemy; od tego czasu został gruntownie przebudowany i rozbudowany.

- **Pandoc** do eksportu .odt i .docx: `sudo apt install pandoc` (Windows: `winget install --exact --id JohnMacFarlane.Pandoc`; macOS: `brew install pandoc`).
- **Piper** do czytania na głos: proponowany przez CEV przy pierwszym użyciu (około 200 MB, plus 60 MB na głos).

Wolne oprogramowanie na **licencji MIT** (plik `LICENSE`), bez gwarancji. W zestawie: KaTeX (MIT). Instalowany osobno na Twoją prośbę: Piper (GPL-3). Testy: `python3 -m pytest tests/`.
