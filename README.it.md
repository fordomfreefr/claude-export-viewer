# Claude Export Viewer (versione 2026.10.26.16)

[English](README.md) | [Français](README.fr.md) | [Español](README.es.md) | [Deutsch](README.de.md) | **Italiano** | [Português](README.pt.md) | [Nederlands](README.nl.md) | [Polski](README.pl.md) | [Русский](README.ru.md) | [中文](README.zh.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

Trasforma la cronologia delle conversazioni di Claude.ai in un sito HTML locale, consultabile con qualsiasi browser senza connessione a Internet, e conserva un archivio cumulativo delle tue conversazioni, comprese quelle eliminate in seguito su Claude.ai.

![Schermata](docs/apercu.png)

Questo progetto si basa su [claude-export-viewer](https://github.com/lordjabez/claude-export-viewer) di Judson Neer, ampiamente modificato e ampliato (vedi «Licenza e ringraziamenti»).

> Questo progetto è indipendente e non affiliato ad Anthropic. Claude è un marchio di Anthropic.

> È stato progettato e testato su Linux Ubuntu 26.04, in Python 3.14 e JavaScript. Dovrebbe funzionare su Windows. Il codice è stato scritto con Claude (modello Opus 5.5, ragionamento elevato). Questo README è una traduzione automatica della versione francese.

## Avvio rapido su Linux Ubuntu / Debian

1. Recupera la cronologia delle conversazioni su claude.ai: **Impostazioni > Privacy > Esporta dati**. Riceverai una prima e-mail informativa, poi una seconda con un link per scaricare un file «manifesto».

2. Installa le 4 librerie e Pandoc da un terminale:  
`sudo apt install python3-jinja2 python3-mistune python3-pydantic python3-pygments pandoc`

3. Salva il programma `claude-export-viewer.zip` in `~/Scaricati`.

4. Decomprimilo nella tua cartella personale, poi avvialo: i file dell'esportazione vengono scaricati a partire dal manifesto e importati, poi si apre l'indice.  
`cd ~/Scaricati && unzip -o claude-export-viewer.zip`  
`rm -rf ~/claude-export-viewer && mv claude-export-viewer ~/`  
`cd ~/claude-export-viewer`  
`python3 claude-export-viewer.py ~/Scaricati -o ~/claude_site`  
(Il `rm -rf` elimina solo la versione precedente del programma: le tue conversazioni sono in `~/claude_site`.)

5. Una sola volta, crea l'icona di avvio sul desktop:  
`python3 claude-export-viewer.py -o ~/claude_site --install-icon`

## Funzionalità

- **Indice generale** di tutte le conversazioni, con:
  - ricerca nei titoli, con contatore dei risultati;
  - ordinamento delle conversazioni: per data di creazione, data dell'ultimo scambio, titolo, numero di messaggi;
  - **categorie** personali, scelte in un piccolo menu a destra di ogni conversazione, per filtrare a piacere;
  - la **ricerca nel contenuto** (da 3 lettere): restano solo le conversazioni che contengono tutte le parole, con il numero di passaggi trovati; una parola si cerca nel testo, un comando come `\alpha` nelle formule, un simbolo come `α` o `∞` in entrambi; maiuscole e accenti ignorati.
- **In ogni conversazione**:
  - data e ora locali, link **Apri su claude.ai** (se esiste ancora);
  - Markdown formattato (grassetto, elenchi, tabelle) e codice evidenziato (Pygments);
  - riquadri di codice con il nome del linguaggio e un pulsante **Copia** (copia il codice esatto negli appunti);
  - **formule matematiche visualizzate come in LaTeX** (KaTeX, incluso, offline): `$…$`, `$$…$$`, `\(…\)`, `\[…\]`; copiando un passaggio si copia il sorgente LaTeX delle sue formule; una formula che non può essere visualizzata resta come sorgente, con il motivo in un suggerimento;
  - artefatti mostrati (codice, documenti, HTML/SVG mostrati come codice, mai eseguiti);
  - ragionamenti, chiamate agli strumenti e risultati in blocchi comprimibili;
  - **più versioni**: quando un messaggio è stato modificato o una risposta rigenerata, la pagina segue la versione che porta all'ultimo scambio; le altre versioni sono in riquadri comprimibili «Altra versione», nel punto in cui la conversazione si è biforcata;
  - **esportazione in Markdown, LibreOffice (.odt) e Word (.docx) su richiesta**: un pulsante «.md» in ogni conversazione; il file contiene il filo principale e, in riquadri (citazioni) con etichette in corsivo, ogni altra versione nel suo punto di biforcazione (oppure, con la casella deselezionata, solo il filo principale); formule come `$…$`, codice, artefatti e nomi degli allegati inclusi (senza ragionamenti né risultati degli strumenti); leggibile con Typora, Obsidian, Zettlr, convertibile con Pandoc;
  - **esportazione in PDF** tramite la finestra di stampa del browser, formule comprese;
  - **parole cercate evidenziate** all'apertura dall'indice, con una piccola barra per passare da un passaggio all'altro;
  - **nascondere le risposte di Claude** per vedere solo i tuoi messaggi, uno sotto l'altro (piccola freccia dopo la data di ogni messaggio, pulsante in alto a destra per tutte);
  - **copiare un messaggio** in Markdown, formule in LaTeX, con l'icona accanto alla data;
  - **navigazione da tastiera**: ← e → (4 e 6 del tastierino numerico disattivato) per passare da un tuo messaggio all'altro, 7, 5 e 1 del tastierino per inizio, metà e fine pagina, M per nascondere le risposte, ? per l'elenco; gli stessi pulsanti a destra, con uno **scorrimento lento e continuo** a velocità regolabile (+ e −);
  - **documenti allegati**: testo completo (niente più taglio a 3000 caratteri), salvato come file e aperto con il programma del computer tramite un'icona; le istruzioni aggiunte automaticamente da claude.ai sono mostrate una sola volta.
- **I tuoi file ritrovati**: le immagini e i file che hai inviato, gli originali dei documenti allegati e i file creati da Claude che hai salvato vengono cercati con il loro nome esatto nelle cartelle scelte nell'indice (sottocartelle comprese), copiati nel sito e mostrati nella conversazione; pulsanti Sì / No per confermare che è il file giusto (e Modifica per cambiare la risposta); i file ancora mancanti vengono cercati a ogni avvio.
- **Archivio cumulativo**: le esportazioni successive si aggiungono senza duplicati, e le conversazioni eliminate in seguito su claude.ai vengono conservate.
- **12 lingue** (pagine, console, esportazioni), a scelta nell'indice.
- **Icona sul desktop** (Linux, Windows) che apre l'indice e importa una nuova esportazione con un clic.
- Tema chiaro o scuro in base all'impostazione del sistema.

## Installazione

Decomprimi questa cartella dove preferisci (disco, chiavetta USB…), poi installa le quattro librerie necessarie.

**Ubuntu / Debian**: vedi «Avvio rapido» sopra.

**Windows** (Python 3.11 o successivo, da [python.org](https://www.python.org/downloads/) o dal Microsoft Store), in un terminale (PowerShell o Prompt dei comandi):

```
py -m pip install jinja2 mistune pydantic pygments
```

Su Windows, sostituisci `python3` con `py` nei comandi di questo documento, e i percorsi `~/…` con percorsi Windows (`C:\Users\[Utente]\claude_site`, `E:\claude_site` per una chiavetta USB…). **Il supporto per Windows è stato scritto sulla base della documentazione di Python e di Windows, ma non è ancora stato provato su un computer Windows**: i riscontri sono benvenuti.

## L'icona «Archivio Claude» (il modo più semplice)

Dopo la prima importazione (vedi sotto), crea l'icona una volta:

```
python3 claude-export-viewer.py -o ~/claude_site --install-icon
```

Compare nel menu delle applicazioni e sul desktop (Linux; KDE può chiedere una volta di considerare attendibile il lanciatore), oppure nel menu Start e sul desktop (Windows: collegamenti creati da PowerShell, che avviano `pythonw.exe`, quindi senza finestra della console; non provato). Un clic apre l'indice nel browser, servito da un piccolo server locale (http://127.0.0.1:8000) che si arresta da solo 30 minuti dopo la chiusura dell'ultima pagina (`--idle` per cambiare questo intervallo). Un secondo clic riutilizza il server già avviato, a meno che non sia stato avviato da una versione precedente del programma: in quel caso viene arrestato e sostituito, affinché venga davvero usata la nuova versione. Metti il programma in una cartella stabile (ad esempio `~/claude-export-viewer`) prima di creare l'icona.

Aperto dall'icona, l'indice raccoglie le sue impostazioni in un riquadro in alto: i pulsanti **Importa un nuovo manifesto** e **Gestisci categorie**, poi la cartella dei download con il suo pulsante **Cambia**. Ogni pulsante apre il suo pannello; un secondo clic (o la croce) lo chiude. Il pulsante **Importa un nuovo manifesto**: dopo aver richiesto l'esportazione su claude.ai e cliccato sul link dell'e-mail che indica che i tuoi dati sono pronti, prende il manifesto più recente della tua cartella dei download, apre i link uno alla volta (vengono mostrati anche, cliccabili, nel registro della pagina), importa l'esportazione e ricarica l'indice. Chiudere il registro durante un'importazione non la interrompe: un altro clic lo mostra di nuovo.

Nello stesso riquadro, la riga **Cartella dei download** indica dove viene cercato il manifesto. Se il tuo browser salva i file altrove (la sua impostazione «Salva i file in» o «Percorso»), clicca su **Cambia** e indica quella cartella: viene memorizzata nell'archivio e cercata per prima, prima della cartella di sistema. Lasciare il campo vuoto torna alla cartella di sistema; se la cartella scelta scompare (chiavetta USB rimossa), viene usata la cartella di sistema.

E in ogni conversazione, le esportazioni .md, .odt e .docx funzionano con un clic.

**Sicurezza**: il server è in ascolto solo sul tuo computer (127.0.0.1) e non fornisce l'archivio grezzo. L'importazione richiede un «token segreto» che solo le pagine dell'indice possono leggere, e le richieste provenienti da un altro sito vengono rifiutate: una pagina web aperta nello stesso browser non può avviarle.

## Riga di comando

1. Su claude.ai: **Impostazioni > Privacy > Esporta dati**.
2. Quando arriva l'e-mail, clicca sul suo link: il browser scarica un piccolo file «manifesto» (l'elenco dei file dell'esportazione e dei loro link).
3. Esegui:

```
python3 claude-export-viewer.py ~/Scaricati -o ~/claude_site
```

Il programma prende il manifesto più recente della cartella, poi:

- apre da solo ogni link nel tuo browser (dove hai effettuato l'accesso a claude.ai), **uno alla volta**, aspettando la fine di ogni download (un link può smettere di funzionare dopo l'uso);
- riconosce i file già scaricati, anche se rinominati dal browser (`conversations-000 (1).zip`), e ignora quelli di un'esportazione precedente;
- sposta i file in `~/claude_site/archive/exports/<data>/`;
- importa l'esportazione nell'archivio e apre l'indice.

Per impostazione predefinita vengono recuperati solo i file utili (conversazioni, progetti, account). Opzioni:

- `--all`: recuperare tutti i 7 file dell'esportazione (backup completo);
- `--browser brave-browser`: scegliere il browser che apre i link;
- `--manual`: non aprire nulla; i link vengono mostrati uno alla volta nel terminale (Ctrl + clic per aprirli, oppure clic destro > copia indirizzo per incollarli nel browser che preferisci) e il programma passa al successivo appena il file è arrivato;
- `--timeout 600`: attendere fino a 600 s per ogni download (300 per impostazione predefinita, 900 in modalità manuale);
- `--no-browser`: non aprire l'indice alla fine;
- `--downloads CARTELLA`: memorizzare la cartella in cui il tuo browser salva i download (la stessa impostazione di «Cambia» nell'indice); `--downloads ""` torna alla cartella di sistema. Da sola, senza file da importare, l'opzione salva l'impostazione e si ferma.

Ogni opzione ha anche un nome francese (`--tout`, `--navigateur`, `--manuel`, `--delai`, `--sans-navigateur`, `--telechargements`…), mostrato da `--help`.

**Requisito**: aver effettuato l'accesso a claude.ai nel browser che apre i link (i link di esportazione funzionano solo in una sessione con accesso effettuato). In modalità automatica, ogni link viene mostrato anche nel terminale: se si è aperto il browser sbagliato, aprilo in quello giusto, il programma rileverà comunque il file. Ctrl + C interrompe in modo pulito; rieseguire lo stesso comando riprende da dove si era fermato.

Browser: tutti quelli che salvano nella cartella dei download abituale (download in corso `.crdownload` di Chrome, Brave, Edge, Opera, Vivaldi, `.part` di Firefox, `.download` di Safari), o nella cartella indicata con `--downloads`. La cartella di sistema viene trovata con `xdg-user-dir` su Linux e nel registro su Windows (anche se spostata, ad esempio su OneDrive). Testato su Linux; macOS e Windows dovrebbero funzionare ma non sono ancora stati provati.

I link scadono 24 ore dopo la creazione dell'esportazione; trascorso questo tempo, il programma lo segnala e ricorda come richiedere una nuova esportazione. Vengono aperti solo link verso `https://claude.ai/`, e nessuna credenziale viene gestita: il download avviene nel tuo stesso browser.

Puoi anche indicare direttamente i file ZIP (o la cartella estratta):

```
python3 claude-export-viewer.py ~/Scaricati/conversations-000.zip -o ~/claude_site
```

Le conversazioni senza alcun testo scambiato vengono escluse dal sito: è così che le conversazioni eliminate compaiono nell'esportazione, a volte con un residuo (immagine o file allegato, risposta vuota) che non conta come testo. Aggiungi `--keep-empty` per includerle comunque.

## Categorie

Ogni conversazione può ricevere una categoria a tua scelta («matematica», «medicina», «scienze»…), una per conversazione.

- **Scegliere**: quando l'indice è aperto dall'icona, un piccolo menu a destra di ogni conversazione propone le categorie esistenti, «Nessuna categoria» e **Nuova categoria…** per crearne una (40 caratteri al massimo; «Mate» e «mate» sono la stessa categoria).
- **Filtrare**: appena esiste una categoria, accanto agli altri filtri compare un menu «Tutte le categorie», con «Senza categoria» e ciascuna categoria. Si combina con la ricerca, gli altri filtri e tutti gli ordinamenti: con «Tutte le categorie», tutte le conversazioni restano visibili.
- **Gestire**: il pulsante **Gestisci categorie**, accanto al pulsante di importazione, mostra ogni categoria con il suo numero di conversazioni, per rinominarla (rinominarla come una categoria esistente le unisce) o eliminarla (le sue conversazioni restano, senza categoria).

Le categorie sono salvate nell'archivio (`archive/topics.json`): seguono il sito (chiavetta USB, altro browser) e sopravvivono alle importazioni successive. Aperto direttamente da `index.html`, senza il programma, l'indice mostra le categorie e permette di filtrare, ma non di modificarle.

## Dove mettere il programma e il sito

La cartella del programma (`claude-export-viewer`) e quella del sito (`claude_site`, scelta con `-o`) possono trovarsi ovunque, anche su una chiavetta USB:

```
python3 /media/io/USB/claude-export-viewer/claude-export-viewer.py ~/Scaricati -o /media/io/USB/claude_site
```

Il sito si apre poi da `index.html`, su qualsiasi computer, anche senza il programma (il pulsante di importazione e le esportazioni .odt/.docx richiedono il programma; le esportazioni .md e .pdf funzionano ovunque). L'icona e i comandi mostrati nelle pagine memorizzano percorsi completi: se la chiavetta viene montata altrove (altro computer, altra lettera di unità su Windows), ricrea l'icona dalla nuova posizione; le pagine vengono aggiornate alla prossima importazione.

## Lingue

Il programma parla 12 lingue: inglese, francese, spagnolo, tedesco, italiano, portoghese, olandese, polacco, russo, cinese (semplificato), giapponese e coreano.

- **Le pagine** si aprono nella lingua del browser, o in inglese se non è disponibile. Il menu in alto a destra dell'indice cambia la lingua di tutto il sito con un clic: indice, conversazioni, date (nel formato di ciascun paese), esportazioni e registro di importazione. Il browser ricorda la scelta.
- **I messaggi della console** seguono la lingua del sistema, o l'opzione `--lang` (`--langue`): `--lang it`, `--lang de`…
- **Il nome dell'icona** segue la lingua della sessione («Archivio Claude» in italiano, «Claude Archives» in inglese…).
- Le conversazioni stesse non vengono mai tradotte. Il codice e le formule sono contrassegnati affinché la traduzione automatica di un browser li lasci intatti.

Le traduzioni diverse dal francese e dall'inglese sono traduzioni automatiche: le correzioni sono benvenute. Ogni lingua è un semplice file di testo, `src/claude_export_viewer/i18n/<codice>.json`; una frase mancante in una lingua viene mostrata in inglese.

## Esportare una conversazione (.md, .odt, .docx, .pdf)

Ogni pagina di conversazione propone «Esporta: .md .odt .docx .pdf», seguito dalla casella **Includi le altre versioni e le parti eliminate**:

- selezionata (predefinito): viene esportato tutto, con le altre versioni e le parti eliminate in riquadri rientrati, nel loro punto di biforcazione;
- deselezionata: viene esportato solo il **filo principale** (quello mostrato nella pagina), e il nome del file termina con «(filo principale)».

Il browser ricorda l'ultima scelta. Dalla riga di comando, la casella deselezionata corrisponde all'opzione `--main-thread`.

- **.md** funziona sempre, direttamente nel browser.
- **.pdf** funziona sempre anche lui: apre la finestra di stampa del browser, dove basta scegliere «Salva come PDF». Le formule appaiono esattamente come sullo schermo, su sfondo bianco anche in modalità scura; il contenuto è lo stesso degli altri formati (senza ragionamenti né strumenti) e il nome del file viene proposto.
- **.odt** (LibreOffice) e **.docx** (Word) passano per Pandoc, che trasforma le formule LaTeX in vere formule modificabili. Installalo una volta (vedi «Dipendenze facoltative»). Due modi per usarle:
  - **con un clic**, consultando il sito tramite il piccolo server locale integrato:  
    `python3 claude-export-viewer.py -o ~/claude_site --serve`  
    poi si apre http://127.0.0.1:8000 (Ctrl + C per fermarlo). Il server è raggiungibile solo dal tuo computer;
  - **con un comando**, se la pagina è aperta senza server: il pulsante mostra il comando esatto da copiare, ad esempio  
    `python3 claude-export-viewer.py -o ~/claude_site --odt "Pitagora"`  
    (titolo, inizio del titolo o identificativo; `--export-dir` per scegliere dove scrivere il file).

Le formule che Pandoc non sa convertire restano in LaTeX nel documento, e il programma le segnala.

## Archivio cumulativo: aggiungere le esportazioni successive

Ogni esportazione di claude.ai è un'istantanea del tuo account in un dato momento. La cartella del sito contiene un **archivio** (`archive/`) che accumula tutte le esportazioni importate. Per una nuova esportazione, basta rieseguire lo stesso comando con la stessa cartella `-o`: vengono elaborate solo le conversazioni nuove o modificate.

- **Nessun duplicato**: ogni conversazione è riconosciuta dal suo identificativo.
- **Non si perde nulla**: una conversazione eliminata su claude.ai resta nell'archivio, con un'etichetta «Eliminata su claude.ai» nell'indice, un avviso nella sua pagina e un filtro per mostrarle o nasconderle.
- **Messaggi scomparsi**: l'esportazione contiene tutte le versioni di una conversazione (messaggi modificati, risposte rigenerate). Se comunque dei messaggi scomparissero da un'esportazione successiva, l'archivio li conserva e li mostra al loro posto, in un riquadro «Parte eliminata su claude.ai».
- **Qualsiasi ordine**: importare un'esportazione più vecchia dopo una più recente completa l'archivio senza sovrascrivere nulla.
- **Data di ogni esportazione**: il programma cerca il manifesto accanto allo zip (se ce ne sono diversi, tiene il primo creato dopo il messaggio più recente dell'esportazione); altrimenti prende la data di quel messaggio. Puoi anche indicarla con `--export-date AAAA-MM-GG`.

**Non eliminare la cartella del sito**: `archive/` contiene la copia delle tue conversazioni, comprese quelle che non esistono più su claude.ai. Per fare un backup, copia questa cartella. Per aggiornare il programma, sostituisci la cartella del programma, poi esegui il comando senza esportazione per rigenerare le pagine:

```
python3 claude-export-viewer.py -o ~/claude_site
```

Opzioni utili: `--rebuild` (rigenerare tutte le pagine), `--structure ESPORTAZIONE.zip` (mostra solo i nomi dei campi dell'esportazione, senza alcun contenuto: utile per segnalare un problema).

L'avanzamento viene mostrato ogni 50 conversazioni. Gli elementi illeggibili vengono saltati e segnalati con un avviso alla fine, senza interrompere l'elaborazione.

## Modifiche rispetto all'originale

- **Memoria costante**: le conversazioni vengono lette e scritte una alla volta (in flusso), invece di caricare tutta l'esportazione. Misurato su un'esportazione fittizia di 595 MB: 57 MB di memoria al massimo (l'originale richiede circa 4 volte la dimensione del file).
- **Nuovo formato di esportazione**: accetta l'esportazione suddivisa in più ZIP, una cartella o file `.json` / `.jsonl`, qualunque sia il loro nome esatto. L'originale cercava solo `conversations.json` e altrimenti indicava «0 conversazioni» senza errore.
- **Tolleranza**: un tipo di contenuto sconosciuto (immagine, ricerca web…), un mittente inatteso, un campo vuoto o una data illeggibile non bloccano più l'intera elaborazione; vengono mostrati in modo generico o ignorati.
- **Sicurezza**: i link `javascript:` (e altri protocolli pericolosi) vengono neutralizzati; le immagini citate in una conversazione sono mostrate come link, senza essere caricate (l'archivio resta leggibile offline, senza contattare siti terzi); l'esportazione .odt / .docx non può incorporare un file del computer.
- **Robustezza**: una conversazione impossibile da visualizzare viene segnalata e saltata senza interrompere la generazione del sito; un archivio danneggiato dà un messaggio chiaro; un progetto salvato su più righe viene riconosciuto.
- **Evidenziazione del codice**.
- **Formule LaTeX**: protette dal Markdown (i `_`, `*` e `\\` delle formule non vengono più danneggiati), poi visualizzate da KaTeX 0.16.47, incluso nella cartella generata (nessuna connessione necessaria). Visualizzazione progressiva durante lo scorrimento: una pagina di 3000 formule si apre in meno di un secondo; tutto viene visualizzato prima di stampare o esportare in PDF.
- **Pulsante «Copia»** su ogni riquadro di codice (blocchi di codice e artefatti), con il nome del linguaggio, come su claude.ai; corregge inoltre un doppio `<code>` per i linguaggi sconosciuti.
- **Archivio cumulativo** delle esportazioni successive: nessun duplicato, conversazioni eliminate su claude.ai conservate e segnalate, parti eliminate di una conversazione conservate al loro posto, rigenerazione delle sole pagine modificate.
- **Download guidato** a partire dal manifesto: link aperti uno alla volta nel browser, attesa della fine di ogni download, file riposti nell'archivio, importazione e apertura dell'indice.
- **Esportazione in Markdown** di ogni conversazione, con un clic, senza file creato in anticipo (il contenuto è incorporato nella pagina e il file viene creato dal browser).
- **Esportazione .odt / .docx** tramite Pandoc (comando `--odt` / `--docx`, o con un clic con il server locale `--serve`); correzione automatica di un costrutto LaTeX che Pandoc rifiuta (`\textbf` dentro `\text{…}`).
- **Multilingue**: 12 lingue per le pagine, la console, le esportazioni e l'icona, con un menu della lingua nell'indice.
- **Icona di avvio** (`--install-icon`), server locale che si arresta da solo (`--open`), pulsante «Importa un nuovo manifesto» protetto da un token; casella «Includi le altre versioni» per esportare tutto o solo il filo principale.
- **Nessuna dipendenza da uv**: un lanciatore `claude-export-viewer.py` per il `python3` del sistema.
- **Categorie** personali, con filtro e gestione (rinominare, unire, eliminare), salvate nell'archivio.
- **Cartella dei download** configurabile (indice o `--downloads`), per un browser che salva altrove o una chiavetta USB.
- **Windows** (non testato): cartella dei download letta dal registro, testi in UTF-8, comandi `py` con le virgolette di Windows, collegamenti nel menu Start e sul desktop.
- **Ricerca nel contenuto** delle conversazioni, con parole evidenziate e passaggio da un risultato all'altro; parole, comandi LaTeX e simboli.
- **Documenti allegati completi** (senza il limite di 3000 caratteri), aperti con il programma del computer; **i tuoi file ritrovati** sul computer e mostrati nelle conversazioni.
- **Lettura**: risposte di Claude ripiegabili, copia di un messaggio, navigazione da tastiera e tastierino numerico, scorrimento lento e continuo.

## Dipendenze facoltative

- **Pandoc** (esportazioni .odt e .docx; testato con Pandoc 3.7):
  - su Linux Ubuntu: `sudo apt install pandoc`;
  - su Windows: `winget install --source winget --exact --id JohnMacFarlane.Pandoc` (comando indicato da [pandoc.org](https://pandoc.org/installing.html));
  - su macOS: `brew install pandoc`.

## Licenza e ringraziamenti

Software libero con **licenza MIT** (file `LICENSE`): puoi usarlo, copiarlo, modificarlo, ridistribuirlo e sfruttarlo liberamente, alla sola condizione di conservare l'avviso di copyright, che cita i suoi autori, e il testo della licenza. È fornito «così com'è», senza alcuna garanzia: i suoi autori non sono responsabili di alcun danno derivante dal suo utilizzo.

- **Autore del progetto originale**: Judson Neer — [github.com/lordjabez](https://github.com/lordjabez), progetto [claude-export-viewer](https://github.com/lordjabez/claude-export-viewer). Un grande ringraziamento a lui per questa base chiara e ben progettata, senza la quale questa versione non esisterebbe.
- **Modifiche e aggiunte**: fordom.
- **KaTeX** (visualizzazione delle formule, incluso): licenza MIT, Khan Academy e collaboratori, vedi `src/claude_export_viewer/static/katex/LICENSE`.

## Test

```
sudo apt install python3-pytest      # Windows: py -m pip install pytest
python3 -m pytest tests/ -v          # Windows: py -m pytest tests/ -v
```

Le particolarità di Windows vengono verificate su Linux simulando Windows (`tests/test_windows.py`); la suite non è ancora stata eseguita su Windows. I test nel browser (`tests/test_topics_browser.py`) richiedono Playwright e Chromium; senza di essi vengono saltati.
