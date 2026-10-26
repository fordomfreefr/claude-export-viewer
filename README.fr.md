# Claude Export Viewer (version 2026.10.26.16)

[English](README.md) | **Français** | [Español](README.es.md) | [Deutsch](README.de.md) | [Italiano](README.it.md) | [Português](README.pt.md) | [Nederlands](README.nl.md) | [Polski](README.pl.md) | [Русский](README.ru.md) | [中文](README.zh.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

Transformez l'historique des discussions du site Claude.ai en un site HTML local, consultable dans n'importe quel navigateur, sans connexion Internet, et gardez une archive cumulative de vos conversations, y compris celles supprimées depuis sur le site Claude.ai.

![Aperçu](docs/apercu.png)

Ce projet est basé sur [claude-export-viewer](https://github.com/lordjabez/claude-export-viewer) de Judson Neer, largement modifié et complété (voir « Licence et remerciements »).

> Ce projet est indépendant et non affilié à Anthropic. Claude est une marque d'Anthropic.

> Il a été conçu et testé sous Linux Ubuntu 26.04, en Python 3.14 et JavaScript. Il devrait fonctionner sous Windows. La programmation a été conçue avec Claude (modèle Opus 5.5, réflexion élevée).

## Démarrage rapide sous Linux Ubuntu / Debian

1. Récupérez l'historique des conversations sur claude.ai : **Paramètres > Confidentialité > Exporter les données**. Vous recevrez un premier e-mail d'information, puis un second permettant de télécharger un fichier « manifeste ».

2. Installez les 4 bibliothèques et Pandoc depuis un terminal :  
`sudo apt install python3-jinja2 python3-mistune python3-pydantic python3-pygments pandoc`

3. Enregistrez le programme `claude-export-viewer.zip` dans `~/Téléchargements`.

4. Décompressez-le dans votre dossier personnel, puis lancez-le : les fichiers de l'export sont téléchargés à partir du manifeste, importés, puis le sommaire s'ouvre.  
`cd ~/Téléchargements && unzip -o claude-export-viewer.zip`  
`rm -rf ~/claude-export-viewer && mv claude-export-viewer ~/`  
`cd ~/claude-export-viewer`  
`python3 claude-export-viewer.py ~/Téléchargements -o ~/claude_site`  
(Le `rm -rf` ne supprime que l'ancienne version du programme : vos conversations sont dans `~/claude_site`.)

5. Une seule fois, créez l'icône de lancement sur le bureau :  
`python3 claude-export-viewer.py -o ~/claude_site --installer-icone`

## Fonctionnalités

- **Sommaire général** de toutes les discussions permettant :
  - la recherche dans les titres, avec compteur de résultats ;
  - le tri des conversations : par date de création, date du dernier échange, titre, nombre de messages ;
  - la création de **rubriques** de classement, choisies dans un petit menu à droite de chaque conversation, pour des filtrages personnalisés ;
  - la **recherche dans le contenu** (dès 3 lettres) : seules les conversations contenant tous les mots restent, avec le nombre de passages trouvés ; un mot cherche dans le texte, une commande comme `\alpha` dans les formules, un symbole comme `α` ou `∞` dans les deux ; majuscules et accents ignorés.
- **Dans chaque conversation** :
  - date et heure locales, lien **Ouvrir sur claude.ai** (s'il existe encore) ;
  - Markdown mis en forme (gras, listes, tableaux) et code coloré (Pygments) ;
  - cadres de code avec le nom du langage et un bouton **Copier** (copie le code exact dans le presse-papiers) ;
  - **formules mathématiques rendues comme en LaTeX** (KaTeX, inclus, hors ligne) : `$…$`, `$$…$$`, `\(…\)`, `\[…\]` ; copier un passage copie la source LaTeX des formules ; une formule non reconnue reste affichée en source, avec la raison en info-bulle ;
  - artefacts affichés (code, documents, HTML/SVG montrés comme code, jamais exécutés) ;
  - réflexions, appels d'outils et résultats dans des bandeaux repliables ;
  - **versions multiples** : quand un message a été modifié ou une réponse relancée, la page suit la version qui mène au dernier échange ; les autres versions sont dans des cadres repliables « Autre version », à l'endroit où la conversation a bifurqué ;
  - **export en Markdown, LibreOffice (.odt) et Word (.docx) à la demande** : bouton « .md » sur chaque conversation ; le fichier contient le fil principal et, dans des cadres (citations) aux libellés en italique, toutes les autres versions à leur point de bifurcation (ou, case décochée, le fil principal seul) ; formules en `$…$`, code, artefacts et noms des pièces jointes inclus (sans les réflexions ni les résultats d'outils) ; lisible par Typora, Obsidian, Zettlr, convertible par Pandoc ;
  - **export PDF** par la fenêtre d'impression du navigateur, formules comprises ;
  - **mots recherchés surlignés** à l'ouverture depuis le sommaire, avec une petite barre pour aller d'un passage à l'autre ;
  - **masquer les réponses de Claude** pour ne garder que vos messages, les uns sous les autres (petite flèche après la date de chaque message, bouton en haut à droite pour toutes) ;
  - **copier un message** en Markdown, formules en LaTeX, par l'icône à côté de la date ;
  - **navigation au clavier** : ← et → (4 et 6 du pavé numérique désactivé) pour passer d'un de vos messages à l'autre, 7, 5 et 1 du pavé pour le haut, le milieu et le bas de la page, M pour masquer les réponses, ? pour la liste ; les mêmes boutons à droite, avec un **défilement lent et continu** à vitesse réglable (+ et −) ;
  - **documents joints** : texte complet (plus de coupure à 3 000 caractères), enregistré comme fichier et ouvert avec le logiciel de l'ordinateur par une icône ; les instructions ajoutées automatiquement par claude.ai ne sont affichées qu'une fois.
- **Vos fichiers retrouvés** : les images et fichiers que vous avez envoyés, les originaux des documents joints et les fichiers créés par Claude que vous avez enregistrés sont cherchés par leur nom exact dans les dossiers choisis sur le sommaire (sous-dossiers compris), copiés dans le site et affichés dans la conversation ; boutons Oui / Non pour confirmer qu'il s'agit du bon fichier (et Modifier pour revenir sur sa réponse) ; les fichiers encore manquants sont recherchés à chaque lancement.
- **Archive cumulative** : les exports successifs s'ajoutent sans doublons, et les conversations supprimées depuis sur claude.ai sont conservées.
- **12 langues** (pages, console, exports), au choix sur le sommaire.
- **Icône de bureau** (Linux, Windows) qui ouvre le sommaire et permet d'importer un nouvel export d'un clic.
- Thème clair ou sombre selon le réglage du système.

## Installation

Décompressez ce dossier où vous voulez (disque, clé USB…), puis installez les quatre bibliothèques nécessaires.

**Ubuntu / Debian** : voir « Démarrage rapide » ci-dessus.

**Windows** (Python 3.11 ou plus récent, depuis [python.org](https://www.python.org/downloads/) ou le Microsoft Store), dans un terminal (PowerShell ou Invite de commandes) :

```
py -m pip install jinja2 mistune pydantic pygments
```

Sous Windows, remplacez `python3` par `py` dans les commandes de ce document, et les chemins `~/…` par des chemins Windows (`C:\Users\[Utilisateur]\claude_site`, `E:\claude_site` pour une clé USB…). **Le fonctionnement sous Windows a été écrit d'après la documentation de Python et de Windows, mais pas encore essayé sur une machine Windows** : vos retours sont bienvenus.

## L'icône « Archives Claude » (le plus simple)

Après le premier import (voir plus bas), créez une fois l'icône :

```
python3 claude-export-viewer.py -o ~/claude_site --installer-icone
```

Elle apparaît dans le menu des applications et sur le bureau (Linux ; KDE peut demander une fois de faire confiance au lanceur), ou dans le menu Démarrer et sur le bureau (Windows : raccourcis créés par PowerShell, qui lancent `pythonw.exe`, donc sans fenêtre de console ; non essayé). Un clic ouvre le sommaire dans le navigateur, servi par un petit serveur local (http://127.0.0.1:8000) qui s'arrête seul 30 minutes après la fermeture de la dernière page (`--arret-auto` pour changer ce délai). Un second clic réutilise le serveur déjà lancé, sauf s'il a été démarré par une version précédente du programme : il est alors arrêté et remplacé, pour que la nouvelle version soit bien utilisée. Placez le programme dans un dossier stable (par exemple `~/claude-export-viewer`) avant de créer l'icône.

Ouvert par l'icône, le sommaire réunit ses réglages dans un cadre, en haut : les boutons **Importer un nouveau manifeste** et **Gérer les rubriques**, puis le dossier des téléchargements et son bouton **Changer**. Chaque bouton ouvre son volet ; un second clic (ou la croix) le referme. Le bouton **Importer un nouveau manifeste** : après avoir demandé l'export sur claude.ai et cliqué sur le lien de l'e-mail « Vos données sont prêtes à être téléchargées », ce bouton prend le manifeste le plus récent de vos Téléchargements, ouvre les liens un par un (ils s'affichent aussi, cliquables, dans le journal de la page), importe l'export et recharge le sommaire. Refermer le journal pendant un import ne l'interrompt pas : un nouveau clic le réaffiche.

Dans le même cadre, la ligne **Dossier des téléchargements** indique où le manifeste est cherché. Si votre navigateur enregistre ailleurs (réglage « Enregistrer les fichiers dans » ou « Emplacement »), cliquez sur **Changer** et indiquez ce dossier : il est retenu dans l'archive et cherché en premier, avant le dossier du système. Laisser le champ vide revient au dossier du système ; si le dossier choisi disparaît (clé USB retirée), le dossier du système est utilisé.

Et sur chaque conversation, les exports .md, .odt et .docx fonctionnent au clic.

**Sécurité** : le serveur n'écoute que sur votre ordinateur (127.0.0.1) et ne sert pas l'archive brute. L'import exige un « jeton secret » que seules les pages du sommaire peuvent lire, et les demandes venant d'un autre site sont refusées : une page web ouverte dans le même navigateur ne peut pas les déclencher.

## Utilisation en ligne de commande

1. Sur claude.ai : **Paramètres > Confidentialité > Exporter les données**.
2. Quand l'e-mail arrive, cliquez sur son lien : le navigateur télécharge un petit fichier « manifeste » (la liste des fichiers de l'export et de leurs liens).
3. Lancez :

```
python3 claude-export-viewer.py ~/Téléchargements -o ~/claude_site
```

Le programme prend le manifeste le plus récent du dossier, puis :

- ouvre lui-même chaque lien dans votre navigateur (où vous êtes connecté à claude.ai), **un par un**, en attendant la fin de chaque téléchargement (un lien peut ne plus fonctionner après usage) ;
- repère les fichiers déjà téléchargés, même renommés par le navigateur (`conversations-000 (1).zip`), et ignore ceux d'un export précédent ;
- range les fichiers dans `~/claude_site/archive/exports/<date>/` ;
- importe l'export dans l'archive et ouvre le sommaire.

Par défaut, seuls les fichiers utiles sont récupérés (conversations, projets, compte). Options :

- `--tout` : récupérer les 7 fichiers de l'export (sauvegarde complète) ;
- `--navigateur brave-browser` : choisir le navigateur qui ouvre les liens ;
- `--manuel` : ne rien ouvrir ; les liens s'affichent un par un dans le terminal (Ctrl + clic pour les ouvrir, ou clic droit > copier l'adresse pour les coller dans le navigateur de votre choix) et le programme passe au suivant dès que le fichier est arrivé ;
- `--delai 600` : attendre jusqu'à 600 s chaque téléchargement (300 par défaut, 900 en mode manuel) ;
- `--sans-navigateur` : ne pas ouvrir le sommaire à la fin ;
- `--telechargements DOSSIER` : retenir le dossier où votre navigateur enregistre les téléchargements (le même réglage que « Changer » sur le sommaire) ; `--telechargements ""` revient au dossier du système. Seule, sans fichier à importer, l'option enregistre le réglage et s'arrête.

Chaque option a aussi un nom anglais (`--all`, `--browser`, `--manual`, `--timeout`, `--no-browser`, `--downloads`…), affiché par `--help`.

**Condition** : être connecté à claude.ai dans le navigateur qui ouvre les liens (les liens d'export ne fonctionnent que dans une session connectée). En mode automatique, chaque lien est aussi affiché dans le terminal : si le mauvais navigateur s'est ouvert, ouvrez-le dans le bon, le programme détectera le fichier quand même. Ctrl + C interrompt proprement ; relancer la même commande reprend là où on en était.

Navigateurs : tous ceux qui enregistrent dans le dossier de téléchargement habituel (téléchargements en cours `.crdownload` de Chrome, Brave, Edge, Opera, Vivaldi, `.part` de Firefox, `.download` de Safari), ou dans le dossier indiqué par `--telechargements`. Le dossier du système est trouvé par `xdg-user-dir` sous Linux et dans le registre sous Windows (même déplacé, par exemple vers OneDrive). Testé sous Linux ; macOS et Windows devraient fonctionner mais n'ont pas encore été essayés.

Les liens expirent 24 heures après la création de l'export ; passé ce délai, le programme le signale et rappelle comment demander un nouvel export. Seuls des liens vers `https://claude.ai/` sont ouverts, et aucun identifiant n'est manipulé : le téléchargement se fait dans votre propre navigateur.

On peut aussi donner directement les fichiers ZIP (ou le dossier extrait) :

```
python3 claude-export-viewer.py ~/Téléchargements/conversations-000.zip -o ~/claude_site
```

Les conversations sans aucun texte échangé sont écartées du site : c'est ainsi qu'apparaissent les conversations supprimées dans l'export, parfois avec un reste (image ou fichier joint, réponse vide) qui ne compte pas comme du texte. Ajoutez `--garder-vides` pour les inclure quand même.

## Rubriques

Chaque conversation peut recevoir une rubrique de votre choix (« math », « médecine », « sciences »…), une seule par conversation.

- **Choisir** : quand le sommaire est ouvert par l'icône, un petit menu à droite de chaque conversation propose les rubriques existantes, « Aucune rubrique », et **Nouvelle rubrique…** pour en créer une (40 caractères au plus ; « Math » et « math » sont la même rubrique).
- **Filtrer** : dès qu'une rubrique existe, un menu « Toutes les rubriques » apparaît à côté des autres filtres, avec « Sans rubrique » et chacune des rubriques. Il se combine avec la recherche, les autres filtres et tous les tris : sur « Toutes les rubriques », toutes les conversations restent affichées.
- **Gérer** : le bouton **Gérer les rubriques**, à côté du bouton d'import, affiche chaque rubrique avec son nombre de conversations, pour la renommer (renommer en une rubrique existante fusionne les deux) ou la supprimer (ses conversations restent, sans rubrique).

Les rubriques sont enregistrées dans l'archive (`archive/topics.json`) : elles suivent le site (clé USB, autre navigateur) et survivent aux imports suivants. Ouvert directement par `index.html`, sans le programme, le sommaire montre les rubriques et permet de filtrer, mais pas de les modifier.

## Où placer le programme et le site

Le dossier du programme (`claude-export-viewer`) et celui du site (`claude_site`, choisi par `-o`) peuvent être n'importe où, y compris sur une clé USB :

```
python3 /media/fordom/CLE/claude-export-viewer/claude-export-viewer.py ~/Téléchargements -o /media/fordom/CLE/claude_site
```

Le site s'ouvre ensuite par `index.html`, sur n'importe quel ordinateur, même sans le programme (le bouton d'import et les exports .odt/.docx demandent le programme ; les exports .md et .pdf fonctionnent partout). L'icône et les commandes affichées dans les pages retiennent les chemins complets : si la clé est montée ailleurs (autre ordinateur, autre lettre de lecteur sous Windows), recréez l'icône depuis le nouvel emplacement ; les pages sont mises à jour au prochain import.

## Langues

Le programme parle 12 langues : anglais, français, espagnol, allemand, italien, portugais, néerlandais, polonais, russe, chinois (simplifié), japonais et coréen.

- **Les pages** s'ouvrent dans la langue du navigateur, ou en anglais si elle n'est pas disponible. Le menu en haut à droite du sommaire change la langue de tout le site d'un clic : sommaire, conversations, dates (au format de chaque pays), exports et journal d'import. Le navigateur retient le choix.
- **Les messages de la console** suivent la langue du système, ou celle de l'option `--langue` (`--lang`) : `--langue en`, `--langue de`…
- **Le nom de l'icône** suit la langue de la session (« Archives Claude » en français, « Claude Archives » en anglais…).
- Les conversations elles-mêmes ne sont jamais traduites. Le code et les formules sont marqués pour que la traduction automatique d'un navigateur ne les abîme pas.

Les traductions autres que le français et l'anglais sont des traductions automatiques : les corrections sont les bienvenues. Chaque langue est un simple fichier texte, `src/claude_export_viewer/i18n/<code>.json` ; une phrase absente d'une langue s'affiche en anglais.

## Exporter une conversation (.md, .odt, .docx, .pdf)

Chaque page de conversation propose « Exporter : .md .odt .docx .pdf », suivi de la case **Inclure les autres versions et les parties supprimées** :

- cochée (par défaut) : tout est exporté, les autres versions et les parties supprimées dans des cadres en retrait, à leur point de bifurcation ;
- décochée : seul le **fil principal** est exporté (celui affiché sur la page), et le nom du fichier se termine par « (fil principal) ».

Le navigateur retient le dernier choix. En ligne de commande, l'équivalent de la case décochée est l'option `--fil-principal`.

- **.md** fonctionne toujours, directement dans le navigateur.
- **.pdf** fonctionne toujours aussi : il ouvre la fenêtre d'impression du navigateur, où il suffit de choisir « Enregistrer au format PDF ». Les formules y sont exactement comme à l'écran, sur fond blanc même en mode sombre ; le contenu est le même que pour les autres formats (sans les réflexions ni les outils) et le nom de fichier est proposé.
- **.odt** (LibreOffice) et **.docx** (Word) passent par Pandoc, qui transforme les formules LaTeX en vraies formules modifiables. Installez-le une fois (voir « Dépendances facultatives »). Deux façons de s'en servir :
  - **au clic**, en consultant le site par le petit serveur local intégré :  
    `python3 claude-export-viewer.py -o ~/claude_site --serveur`  
    puis http://127.0.0.1:8000 s'ouvre (Ctrl + C pour arrêter). Le serveur n'est accessible que depuis votre ordinateur ;
  - **par une commande**, si la page est ouverte sans serveur : le bouton affiche la commande exacte à copier, par exemple  
    `python3 claude-export-viewer.py -o ~/claude_site --odt "Pythagore"`  
    (titre, début de titre ou identifiant ; `--dossier-export` pour choisir où écrire le fichier).

Les formules que Pandoc ne sait pas convertir restent en LaTeX dans le document, et le programme les signale.

## Archive cumulative : ajouter les exports suivants

Chaque export de claude.ai est une photo de votre compte à un instant donné. Le dossier du site contient une **archive** (`archive/`) qui cumule tous les exports importés. Pour un nouvel export, relancez simplement la même commande avec le même dossier `-o` : seules les conversations nouvelles ou modifiées sont traitées.

- **Pas de doublons** : chaque conversation est reconnue par son identifiant.
- **Rien n'est perdu** : une conversation supprimée sur claude.ai reste dans l'archive, avec un badge « Supprimée sur claude.ai » dans le sommaire, un bandeau sur sa page et un filtre pour les afficher ou les masquer.
- **Messages disparus** : l'export contient toutes les versions d'une conversation (messages modifiés, réponses relancées). Si des messages venaient malgré tout à disparaître d'un export suivant, l'archive les garde et les affiche à leur place, dans un cadre « Partie supprimée sur claude.ai ».
- **Ordre libre** : importer un export plus ancien après un plus récent complète l'archive sans rien écraser.
- **Date de chaque export** : le programme cherche le manifeste posé à côté du zip (s'il y en a plusieurs, il retient le premier créé après le message le plus récent de l'export) ; à défaut, il prend la date de ce message. Vous pouvez aussi la donner avec `--date-export AAAA-MM-JJ`.

**Ne supprimez pas le dossier du site** : `archive/` contient la copie de vos conversations, y compris celles qui n'existent plus sur claude.ai. Pour sauvegarder, copiez ce dossier. Pour mettre le programme à jour, remplacez le dossier du programme, puis lancez la commande sans export pour régénérer les pages :

```
python3 claude-export-viewer.py -o ~/claude_site
```

Options utiles : `--reconstruire` (régénérer toutes les pages), `--structure EXPORT.zip` (affiche seulement les noms des champs de l'export, sans aucun contenu : utile pour signaler un problème).

La progression s'affiche toutes les 50 conversations. Les éléments illisibles sont ignorés et signalés par un avertissement à la fin, sans arrêter le traitement.

## Modifications par rapport à l'original

- **Mémoire constante** : les conversations sont lues et écrites une par une (lecture en flux), au lieu de charger tout l'export. Mesuré sur un faux export de 595 Mo : 57 Mo de mémoire au maximum (l'original en demande environ 4 fois la taille du fichier).
- **Nouveau format d'export** : accepte l'export découpé en plusieurs ZIP, un dossier, ou des fichiers `.json` / `.jsonl`, quel que soit leur nom exact. L'original cherchait uniquement `conversations.json` et annonçait « 0 conversations » sans erreur sinon.
- **Tolérance** : un type de contenu inconnu (image, recherche web…), un expéditeur inattendu, un champ vide ou une date illisible ne font plus planter tout le traitement ; ils sont affichés de façon générique ou ignorés.
- **Sécurité** : les liens `javascript:` (et autres protocoles dangereux) sont neutralisés ; les images citées dans une conversation sont affichées comme des liens, sans être chargées (l'archive reste lisible hors ligne, sans connexion à des sites tiers) ; l'export .odt / .docx ne peut pas y insérer un fichier de l'ordinateur.
- **Robustesse** : une conversation impossible à afficher est signalée et ignorée sans arrêter la génération du site ; une archive abîmée donne un message clair ; un projet enregistré sur plusieurs lignes est bien reconnu.
- **Coloration du code**.
- **Formules LaTeX** : protégées du Markdown (les `_`, `*` et `\\` des formules ne sont plus abîmés) puis rendues par KaTeX 0.16.47, inclus dans le dossier produit (aucune connexion nécessaire). Rendu progressif au défilement : une page de 3 000 formules s'ouvre en moins d'une seconde ; tout est rendu avant une impression ou un export PDF.
- **Bouton « Copier »** sur chaque cadre de code (blocs de code et artefacts), avec le nom du langage, comme sur claude.ai ; correction au passage d'un double `<code>` pour les langages inconnus.
- **Archive cumulative** des exports successifs : sans doublons, conversations supprimées sur claude.ai conservées et signalées, parties supprimées d'une conversation conservées à leur place, régénération des seules pages modifiées.
- **Téléchargement guidé** depuis le manifeste : ouverture des liens un par un dans le navigateur, attente de la fin de chaque téléchargement, rangement dans l'archive, import et ouverture du sommaire.
- **Export Markdown** de chaque conversation, au clic, sans fichier créé à l'avance (le contenu est intégré à la page et le fichier fabriqué par le navigateur).
- **Export .odt / .docx** via Pandoc (commande `--odt` / `--docx`, ou au clic avec le serveur local `--serveur`) ; correction automatique d'une construction LaTeX que Pandoc refuse (`\textbf` dans `\text{…}`).
- **Multilingue** : 12 langues pour les pages, la console, les exports et l'icône, avec un menu de langue sur le sommaire.
- **Icône de lancement** (`--installer-icone`), serveur local à arrêt automatique (`--ouvrir`), bouton « Importer un nouveau manifeste » protégé par jeton ; case « Inclure les autres versions » pour exporter tout ou le fil principal seul.
- **Plus de dépendance à uv** : lanceur `claude-export-viewer.py` pour le `python3` du système.
- **Rubriques** personnelles, avec filtre et gestion (renommer, fusionner, supprimer), enregistrées dans l'archive.
- **Dossier des téléchargements** réglable (sommaire ou `--telechargements`), pour un navigateur qui enregistre ailleurs ou une clé USB.
- **Windows** (non testé) : dossier Téléchargements lu dans le registre, textes en UTF-8, commandes `py` avec les guillemets de Windows, raccourcis dans le menu Démarrer et sur le bureau.
- **Recherche dans le contenu** des conversations, avec mots surlignés et passage d'un résultat à l'autre ; mots, commandes LaTeX et symboles.
- **Documents joints complets** (plus de limite à 3 000 caractères), ouverts avec le logiciel de l'ordinateur ; **vos fichiers retrouvés** sur l'ordinateur et affichés dans les conversations.
- **Lecture** : réponses de Claude repliables, copie d'un message, navigation au clavier et au pavé numérique, défilement lent et continu.

## Dépendances facultatives

- **Pandoc** (exports .odt et .docx ; testé avec Pandoc 3.7) :
  - sous Linux Ubuntu : `sudo apt install pandoc` ;
  - sous Windows : `winget install --source winget --exact --id JohnMacFarlane.Pandoc` (commande donnée par [pandoc.org](https://pandoc.org/installing.html)) ;
  - sous macOS : `brew install pandoc`.

## Licence et remerciements

Logiciel libre sous **licence MIT** (fichier `LICENSE`) : vous pouvez l'utiliser, le copier, le modifier, le redistribuer et l'exploiter librement, à la seule condition de conserver l'avis de copyright, qui cite ses auteurs, et le texte de la licence. Il est fourni « tel quel », sans aucune garantie : ses auteurs ne sont responsables d'aucun dommage lié à son utilisation.

- **Auteur du projet d'origine** : Judson Neer — [github.com/lordjabez](https://github.com/lordjabez), projet [claude-export-viewer](https://github.com/lordjabez/claude-export-viewer). Un grand merci à lui pour cette base claire et bien conçue, sans laquelle cette version n'existerait pas.
- **Modifications et ajouts** : fordom.
- **KaTeX** (rendu des formules, inclus) : licence MIT, Khan Academy et contributeurs, voir `src/claude_export_viewer/static/katex/LICENSE`.

## Tests

```
sudo apt install python3-pytest      # Windows : py -m pip install pytest
python3 -m pytest tests/ -v          # Windows : py -m pytest tests/ -v
```

Les particularités de Windows sont vérifiées sous Linux en simulant Windows (`tests/test_windows.py`) ; la suite n'a pas encore été lancée sous Windows. Les tests dans le navigateur (`tests/test_topics_browser.py`) demandent Playwright et Chromium ; sans eux, ils sont ignorés.
