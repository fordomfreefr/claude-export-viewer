# Claude Export Viewer (versão 2026.10.25.1)

[English](README.md) | [Français](README.fr.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Italiano](README.it.md) | **Português** | [Nederlands](README.nl.md) | [Polski](README.pl.md) | [Русский](README.ru.md) | [中文](README.zh.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

Transforme o histórico de conversas do Claude.ai em um site HTML local, que qualquer navegador abre sem conexão com a Internet, e mantenha um arquivo cumulativo das suas conversas, inclusive das que foram excluídas depois no Claude.ai.

Este projeto é baseado no [claude-export-viewer](https://github.com/lordjabez/claude-export-viewer) de Judson Neer, amplamente modificado e ampliado (veja “Licença e agradecimentos”).

> Este projeto é independente e não tem afiliação com a Anthropic. Claude é uma marca da Anthropic.

> Foi projetado e testado no Linux Ubuntu 26.04, em Python 3.14 e JavaScript. Deve funcionar no Windows. O código foi escrito com o Claude (modelo Opus 5.5, raciocínio elevado). Este README é uma tradução automática da versão francesa.

## Início rápido no Linux Ubuntu / Debian

1. Obtenha o histórico de conversas no claude.ai: **Configurações > Privacidade > Exportar dados**. Você receberá um primeiro e-mail informativo e depois um segundo, com um link para baixar um arquivo “manifesto”.

2. Instale as 4 bibliotecas e o Pandoc em um terminal:  
`sudo apt install python3-jinja2 python3-mistune python3-pydantic python3-pygments pandoc`

3. Salve o programa `claude-export-viewer.zip` em `~/Downloads`.

4. Descompacte-o na sua pasta pessoal e execute-o: os arquivos da exportação são baixados a partir do manifesto e importados, e depois o índice se abre.  
`cd ~/Downloads && unzip -o claude-export-viewer.zip`  
`rm -rf ~/claude-export-viewer && mv claude-export-viewer ~/`  
`cd ~/claude-export-viewer`  
`python3 claude-export-viewer.py ~/Downloads -o ~/claude_site`  
(O `rm -rf` só remove a versão anterior do programa: suas conversas ficam em `~/claude_site`.)

5. Uma única vez, crie o ícone de inicialização na área de trabalho:  
`python3 claude-export-viewer.py -o ~/claude_site --install-icon`

## Recursos

- **Índice geral** de todas as conversas, com:
  - busca nos títulos, com contador de resultados;
  - ordenação das conversas: por data de criação, data da última troca, título, número de mensagens;
  - **categorias** próprias, escolhidas em um pequeno menu à direita de cada conversa, para filtrar como quiser.
- **Em cada conversa**:
  - data e hora locais, link **Abrir no claude.ai** (se ela ainda existir lá);
  - Markdown formatado (negrito, listas, tabelas) e código destacado (Pygments);
  - quadros de código com o nome da linguagem e um botão **Copiar** (copia o código exato para a área de transferência);
  - **fórmulas matemáticas exibidas como no LaTeX** (KaTeX, incluído, offline): `$…$`, `$$…$$`, `\(…\)`, `\[…\]`; copiar um trecho copia o código-fonte LaTeX das suas fórmulas; uma fórmula que não pode ser exibida fica como código-fonte, com o motivo em uma dica;
  - artefatos exibidos (código, documentos, HTML/SVG mostrados como código, nunca executados);
  - raciocínios, chamadas de ferramentas e resultados em blocos recolhíveis;
  - **várias versões**: quando uma mensagem foi editada ou uma resposta gerada novamente, a página segue a versão que leva à última troca; as outras versões ficam em quadros recolhíveis “Outra versão”, no ponto em que a conversa se ramificou;
  - **exportação para Markdown, LibreOffice (.odt) e Word (.docx) sob demanda**: um botão “.md” em cada conversa; o arquivo contém o fio principal e, em quadros (citações) com rótulos em itálico, todas as outras versões no seu ponto de ramificação (ou, com a caixa desmarcada, só o fio principal); fórmulas como `$…$`, código, artefatos e nomes dos anexos incluídos (sem raciocínios nem resultados de ferramentas); legível no Typora, Obsidian, Zettlr, conversível pelo Pandoc;
  - **exportação para PDF** pela janela de impressão do navegador, fórmulas incluídas.
- **Arquivo cumulativo**: as exportações sucessivas são acrescentadas sem duplicatas, e as conversas excluídas depois no claude.ai são mantidas.
- **12 idiomas** (páginas, console, exportações), à escolha no índice.
- **Ícone na área de trabalho** (Linux, Windows) que abre o índice e importa uma nova exportação com um clique.
- Tema claro ou escuro conforme a configuração do sistema.

## Instalação

Descompacte esta pasta onde quiser (disco, pen drive…) e instale as quatro bibliotecas necessárias.

**Ubuntu / Debian**: veja “Início rápido” acima.

**Windows** (Python 3.11 ou mais recente, em [python.org](https://www.python.org/downloads/) ou na Microsoft Store), em um terminal (PowerShell ou Prompt de Comando):

```
py -m pip install jinja2 mistune pydantic pygments
```

No Windows, substitua `python3` por `py` nos comandos deste documento, e os caminhos `~/…` por caminhos do Windows (`C:\Users\[Usuário]\claude_site`, `E:\claude_site` para um pen drive…). **O suporte ao Windows foi escrito a partir da documentação do Python e do Windows, mas ainda não foi testado em um computador com Windows**: seus comentários são bem-vindos.

## O ícone “Arquivo do Claude” (o jeito mais simples)

Depois da primeira importação (veja abaixo), crie o ícone uma vez:

```
python3 claude-export-viewer.py -o ~/claude_site --install-icon
```

Ele aparece no menu de aplicativos e na área de trabalho (Linux; o KDE pode pedir uma vez para confiar no lançador), ou no menu Iniciar e na área de trabalho (Windows: atalhos criados pelo PowerShell, que executam `pythonw.exe`, então nenhuma janela de console se abre; não testado). Um clique abre o índice no navegador, servido por um pequeno servidor local (http://127.0.0.1:8000) que se encerra sozinho 30 minutos depois do fechamento da última página (`--idle` para mudar esse prazo). Um segundo clique reutiliza o servidor já em execução, a menos que ele tenha sido iniciado por uma versão anterior do programa: nesse caso ele é encerrado e substituído, para que a nova versão seja realmente usada. Coloque o programa em uma pasta fixa (por exemplo `~/claude-export-viewer`) antes de criar o ícone.

Aberto pelo ícone, o índice reúne as configurações em um quadro no topo: os botões **Importar um novo manifesto** e **Gerir categorias**, e abaixo a pasta de downloads com o botão **Alterar**. Cada botão abre o seu painel; um segundo clique (ou o X) o fecha. O botão **Importar um novo manifesto**: depois que você solicitou a exportação no claude.ai e clicou no link do e-mail informando que seus dados estão prontos, ele pega o manifesto mais recente da sua pasta de downloads, abre os links um por um (eles também aparecem, clicáveis, no registro da página), importa a exportação e recarrega o índice. Fechar o registro durante uma importação não a interrompe: outro clique o mostra de novo.

No mesmo quadro, a linha da **pasta de downloads** indica onde o manifesto é procurado. Se o seu navegador salva os arquivos em outro lugar (a configuração “Salvar arquivos em” ou “Local”), clique em **Alterar** e informe essa pasta: ela fica registrada no arquivo e é procurada primeiro, antes da pasta do sistema. Deixar o campo vazio volta à pasta do sistema; se a pasta escolhida desaparecer (pen drive removido), a pasta do sistema é usada.

E em cada conversa, as exportações .md, .odt e .docx funcionam com um clique.

**Segurança**: o servidor só escuta no seu computador (127.0.0.1) e não fornece o arquivo bruto. A importação exige um “token secreto” que só as páginas do índice conseguem ler, e as solicitações vindas de outro site são recusadas: uma página da web aberta no mesmo navegador não consegue acioná-las.

## Linha de comando

1. No claude.ai: **Configurações > Privacidade > Exportar dados**.
2. Quando o e-mail chegar, clique no link dele: o navegador baixa um pequeno arquivo “manifesto” (a lista dos arquivos da exportação e dos seus links).
3. Execute:

```
python3 claude-export-viewer.py ~/Downloads -o ~/claude_site
```

O programa pega o manifesto mais recente da pasta e então:

- abre ele mesmo cada link no seu navegador (onde você está conectado ao claude.ai), **um por um**, esperando o fim de cada download (um link pode deixar de funcionar depois de usado);
- reconhece os arquivos já baixados, mesmo renomeados pelo navegador (`conversations-000 (1).zip`), e ignora os de uma exportação anterior;
- move os arquivos para `~/claude_site/archive/exports/<data>/`;
- importa a exportação no arquivo e abre o índice.

Por padrão, só os arquivos úteis são obtidos (conversas, projetos, conta). Opções:

- `--all`: obter os 7 arquivos da exportação (backup completo);
- `--browser brave-browser`: escolher o navegador que abre os links;
- `--manual`: não abrir nada; os links aparecem um por um no terminal (Ctrl + clique para abri-los, ou clique direito > copiar endereço para colá-los no navegador que preferir) e o programa passa ao próximo assim que o arquivo chega;
- `--timeout 600`: esperar até 600 s por cada download (300 por padrão, 900 no modo manual);
- `--no-browser`: não abrir o índice no final;
- `--downloads PASTA`: registrar a pasta onde o seu navegador salva os downloads (a mesma configuração que “Alterar” no índice); `--downloads ""` volta à pasta do sistema. Sozinha, sem arquivo para importar, a opção salva a configuração e termina.

Cada opção também tem um nome em francês (`--tout`, `--navigateur`, `--manuel`, `--delai`, `--sans-navigateur`, `--telechargements`…), mostrado por `--help`.

**Requisito**: estar conectado ao claude.ai no navegador que abre os links (os links de exportação só funcionam em uma sessão conectada). No modo automático, cada link também aparece no terminal: se o navegador errado abriu, abra-o no certo, o programa detectará o arquivo mesmo assim. Ctrl + C interrompe de forma limpa; executar o mesmo comando de novo retoma de onde parou.

Navegadores: todos os que salvam na pasta de downloads habitual (downloads em andamento `.crdownload` do Chrome, Brave, Edge, Opera, Vivaldi, `.part` do Firefox, `.download` do Safari), ou na pasta indicada com `--downloads`. A pasta do sistema é encontrada pelo `xdg-user-dir` no Linux e no registro no Windows (mesmo que tenha sido movida, por exemplo para o OneDrive). Testado no Linux; macOS e Windows devem funcionar, mas ainda não foram testados.

Os links expiram 24 horas depois da criação da exportação; passado esse prazo, o programa avisa e lembra como solicitar uma nova exportação. Só são abertos links para `https://claude.ai/`, e nenhuma credencial é manipulada: o download acontece no seu próprio navegador.

Também é possível indicar diretamente os arquivos ZIP (ou a pasta extraída):

```
python3 claude-export-viewer.py ~/Downloads/conversations-000.zip -o ~/claude_site
```

As conversas sem nenhum texto trocado são excluídas do site: é assim que as conversas excluídas aparecem na exportação, às vezes com um resto (imagem ou arquivo anexado, resposta vazia) que não conta como texto. Acrescente `--keep-empty` para incluí-las mesmo assim.

## Categorias

Cada conversa pode receber uma categoria de sua escolha (“matemática”, “medicina”, “ciências”…), uma por conversa.

- **Escolher**: quando o índice é aberto pelo ícone, um pequeno menu à direita de cada conversa oferece as categorias existentes, “Nenhuma categoria” e **Nova categoria…** para criar uma (no máximo 40 caracteres; “Mat” e “mat” são a mesma categoria).
- **Filtrar**: assim que existe uma categoria, um menu “Todas as categorias” aparece ao lado dos outros filtros, com “Sem categoria” e cada uma das categorias. Ele se combina com a busca, os outros filtros e todas as ordenações: em “Todas as categorias”, todas as conversas continuam visíveis.
- **Gerir**: o botão **Gerir categorias**, ao lado do botão de importação, mostra cada categoria com o seu número de conversas, para renomeá-la (renomear com o nome de uma categoria existente junta as duas) ou excluí-la (as suas conversas ficam, sem categoria).

As categorias são salvas no arquivo (`archive/topics.json`): acompanham o site (pen drive, outro navegador) e sobrevivem às importações seguintes. Aberto diretamente pelo `index.html`, sem o programa, o índice mostra as categorias e permite filtrar, mas não alterá-las.

## Onde colocar o programa e o site

A pasta do programa (`claude-export-viewer`) e a do site (`claude_site`, escolhida com `-o`) podem ficar em qualquer lugar, inclusive em um pen drive:

```
python3 /media/eu/PENDRIVE/claude-export-viewer/claude-export-viewer.py ~/Downloads -o /media/eu/PENDRIVE/claude_site
```

O site então se abre pelo `index.html`, em qualquer computador, mesmo sem o programa (o botão de importação e as exportações .odt/.docx precisam do programa; as exportações .md e .pdf funcionam em qualquer lugar). O ícone e os comandos mostrados nas páginas guardam caminhos completos: se o pen drive for montado em outro lugar (outro computador, outra letra de unidade no Windows), crie o ícone de novo a partir do novo local; as páginas são atualizadas na próxima importação.

## Idiomas

O programa fala 12 idiomas: inglês, francês, espanhol, alemão, italiano, português, holandês, polonês, russo, chinês (simplificado), japonês e coreano.

- **As páginas** abrem no idioma do navegador, ou em inglês se ele não estiver disponível. O menu no canto superior direito do índice muda o idioma de todo o site com um clique: índice, conversas, datas (no formato de cada país), exportações e registro de importação. O navegador lembra a escolha.
- **As mensagens do console** seguem o idioma do sistema, ou a opção `--lang` (`--langue`): `--lang pt`, `--lang de`…
- **O nome do ícone** segue o idioma da sessão (“Arquivo do Claude” em português, “Claude Archives” em inglês…).
- As conversas em si nunca são traduzidas. O código e as fórmulas são marcados para que a tradução automática de um navegador os deixe intactos.

As traduções que não são em francês nem em inglês são traduções automáticas: correções são bem-vindas. Cada idioma é um simples arquivo de texto, `src/claude_export_viewer/i18n/<código>.json`; uma frase que falta em um idioma aparece em inglês.

## Exportar uma conversa (.md, .odt, .docx, .pdf)

Cada página de conversa oferece “Exportar: .md .odt .docx .pdf”, seguido da caixa **Incluir as outras versões e as partes excluídas**:

- marcada (padrão): tudo é exportado, com as outras versões e as partes excluídas em quadros recuados, no seu ponto de ramificação;
- desmarcada: só o **fio principal** é exportado (o que aparece na página), e o nome do arquivo termina com “(fio principal)”.

O navegador lembra a última escolha. Na linha de comando, a caixa desmarcada corresponde à opção `--main-thread`.

- **.md** sempre funciona, diretamente no navegador.
- **.pdf** também sempre funciona: abre a janela de impressão do navegador, onde basta escolher “Salvar como PDF”. As fórmulas ficam exatamente como na tela, com fundo branco mesmo no modo escuro; o conteúdo é o mesmo dos outros formatos (sem raciocínios nem ferramentas) e o nome do arquivo é sugerido.
- **.odt** (LibreOffice) e **.docx** (Word) passam pelo Pandoc, que transforma as fórmulas LaTeX em fórmulas reais e editáveis. Instale-o uma vez (veja “Dependências opcionais”). Duas maneiras de usá-las:
  - **com um clique**, navegando pelo site através do pequeno servidor local integrado:  
    `python3 claude-export-viewer.py -o ~/claude_site --serve`  
    e então http://127.0.0.1:8000 se abre (Ctrl + C para parar). O servidor só é acessível a partir do seu computador;
  - **com um comando**, se a página estiver aberta sem o servidor: o botão mostra o comando exato a copiar, por exemplo  
    `python3 claude-export-viewer.py -o ~/claude_site --odt "Pitágoras"`  
    (título, início do título ou identificador; `--export-dir` para escolher onde gravar o arquivo).

As fórmulas que o Pandoc não consegue converter ficam em LaTeX no documento, e o programa as indica.

## Arquivo cumulativo: acrescentar as próximas exportações

Cada exportação do claude.ai é um retrato da sua conta em um dado momento. A pasta do site contém um **arquivo** (`archive/`) que acumula todas as exportações importadas. Para uma nova exportação, basta executar o mesmo comando com a mesma pasta `-o`: só as conversas novas ou alteradas são processadas.

- **Sem duplicatas**: cada conversa é reconhecida pelo seu identificador.
- **Nada se perde**: uma conversa excluída no claude.ai continua no arquivo, com um selo “Excluída no claude.ai” no índice, um aviso na sua página e um filtro para mostrá-las ou ocultá-las.
- **Mensagens desaparecidas**: a exportação contém todas as versões de uma conversa (mensagens editadas, respostas geradas novamente). Se ainda assim mensagens sumirem de uma exportação posterior, o arquivo as guarda e as mostra no lugar, em um quadro “Parte excluída no claude.ai”.
- **Qualquer ordem**: importar uma exportação mais antiga depois de uma mais recente completa o arquivo sem sobrescrever nada.
- **Data de cada exportação**: o programa procura o manifesto ao lado do zip (se houver vários, fica com o primeiro criado depois da mensagem mais recente da exportação); senão, usa a data dessa mensagem. Você também pode informá-la com `--export-date AAAA-MM-DD`.

**Não exclua a pasta do site**: `archive/` contém a cópia das suas conversas, inclusive as que não existem mais no claude.ai. Para fazer backup, copie essa pasta. Para atualizar o programa, substitua a pasta do programa e execute o comando sem exportação para gerar as páginas de novo:

```
python3 claude-export-viewer.py -o ~/claude_site
```

Opções úteis: `--rebuild` (gerar de novo todas as páginas), `--structure EXPORTACAO.zip` (mostra só os nomes dos campos da exportação, sem nenhum conteúdo: útil para relatar um problema).

O progresso aparece a cada 50 conversas. Os itens ilegíveis são ignorados e indicados por um aviso no final, sem interromper o processamento.

## Mudanças em relação ao original

- **Memória constante**: as conversas são lidas e gravadas uma de cada vez (em fluxo), em vez de carregar toda a exportação. Medido em uma exportação fictícia de 595 MB: no máximo 57 MB de memória (o original precisa de cerca de 4 vezes o tamanho do arquivo).
- **Novo formato de exportação**: aceita a exportação dividida em vários ZIP, uma pasta ou arquivos `.json` / `.jsonl`, qualquer que seja o nome exato. O original só procurava `conversations.json` e, caso contrário, informava “0 conversas” sem erro.
- **Tolerância**: um tipo de conteúdo desconhecido (imagem, busca na web…), um remetente inesperado, um campo vazio ou uma data ilegível não travam mais todo o processamento; eles são mostrados de forma genérica ou ignorados.
- **Segurança**: os links `javascript:` (e outros protocolos perigosos) são neutralizados; as imagens citadas em uma conversa aparecem como links, sem serem carregadas (o arquivo continua legível offline, sem contatar sites de terceiros); a exportação .odt / .docx não consegue incorporar um arquivo do computador.
- **Robustez**: uma conversa impossível de exibir é indicada e ignorada sem interromper a geração do site; um arquivo danificado dá uma mensagem clara; um projeto salvo em várias linhas é reconhecido.
- **Destaque do código**.
- **Fórmulas LaTeX**: protegidas do Markdown (os `_`, `*` e `\\` das fórmulas não são mais danificados), depois exibidas pelo KaTeX 0.16.47, incluído na pasta gerada (sem precisar de conexão). Exibição progressiva durante a rolagem: uma página de 3.000 fórmulas abre em menos de um segundo; tudo é exibido antes de imprimir ou exportar para PDF.
- **Botão “Copiar”** em cada quadro de código (blocos de código e artefatos), com o nome da linguagem, como no claude.ai; corrige de quebra um `<code>` duplo para linguagens desconhecidas.
- **Arquivo cumulativo** das exportações sucessivas: sem duplicatas, conversas excluídas no claude.ai mantidas e sinalizadas, partes excluídas de uma conversa mantidas no lugar, só as páginas alteradas são geradas de novo.
- **Download guiado** a partir do manifesto: links abertos um por um no navegador, espera pelo fim de cada download, arquivos guardados no arquivo, importação e abertura do índice.
- **Exportação para Markdown** de cada conversa, com um clique, sem arquivo criado antecipadamente (o conteúdo fica embutido na página e o arquivo é criado pelo navegador).
- **Exportação .odt / .docx** pelo Pandoc (comando `--odt` / `--docx`, ou com um clique com o servidor local `--serve`); correção automática de uma construção LaTeX que o Pandoc recusa (`\textbf` dentro de `\text{…}`).
- **Multilíngue**: 12 idiomas para as páginas, o console, as exportações e o ícone, com um menu de idioma no índice.
- **Ícone de inicialização** (`--install-icon`), servidor local que se encerra sozinho (`--open`), botão “Importar um novo manifesto” protegido por token; caixa “Incluir as outras versões” para exportar tudo ou só o fio principal.
- **Sem dependência do uv**: um lançador `claude-export-viewer.py` para o `python3` do sistema.
- **Categorias** próprias, com filtro e gerenciamento (renomear, juntar, excluir), salvas no arquivo.
- **Pasta de downloads** configurável (índice ou `--downloads`), para um navegador que salva em outro lugar ou um pen drive.
- **Windows** (não testado): pasta de downloads lida do registro, textos em UTF-8, comandos `py` com as aspas do Windows, atalhos no menu Iniciar e na área de trabalho.

## Dependências opcionais

- **Pandoc** (exportações .odt e .docx; testado com o Pandoc 3.7):
  - no Linux Ubuntu: `sudo apt install pandoc`;
  - no Windows: `winget install --source winget --exact --id JohnMacFarlane.Pandoc` (comando indicado por [pandoc.org](https://pandoc.org/installing.html));
  - no macOS: `brew install pandoc`.

## Licença e agradecimentos

Software livre sob a **licença MIT** (arquivo `LICENSE`): você pode usá-lo, copiá-lo, modificá-lo, redistribuí-lo e explorá-lo livremente, com a única condição de manter o aviso de copyright, que cita os seus autores, e o texto da licença. Ele é fornecido “como está”, sem nenhuma garantia: os seus autores não se responsabilizam por nenhum dano decorrente do seu uso.

- **Autor do projeto original**: Judson Neer — [github.com/lordjabez](https://github.com/lordjabez), projeto [claude-export-viewer](https://github.com/lordjabez/claude-export-viewer). Muito obrigado a ele por esta base clara e bem pensada, sem a qual esta versão não existiria.
- **Modificações e acréscimos**: fordom.
- **KaTeX** (exibição das fórmulas, incluído): licença MIT, Khan Academy e colaboradores, veja `src/claude_export_viewer/static/katex/LICENSE`.

## Testes

```
sudo apt install python3-pytest      # Windows: py -m pip install pytest
python3 -m pytest tests/ -v          # Windows: py -m pytest tests/ -v
```

As particularidades do Windows são verificadas no Linux simulando o Windows (`tests/test_windows.py`); a bateria de testes ainda não foi executada no Windows. Os testes no navegador (`tests/test_topics_browser.py`) precisam do Playwright e do Chromium; sem eles, são ignorados.
