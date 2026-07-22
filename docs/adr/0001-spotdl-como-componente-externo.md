# O spotdl é um componente externo, gerenciado pelo próprio programa

Para distribuir o programa a pessoas que não têm Python instalado, o spotdl precisava
deixar de ser procurado na máquina alheia. Em vez de congelá-lo dentro do nosso
executável, usamos o binário oficial `win32` que o projeto spotDL publica a cada
release, guardado em `%APPDATA%\BaixarMusica\` e atualizado pelo próprio programa.

## Considered Options

**Congelar o spotdl dentro do nosso executável com PyInstaller.** Rejeitado por duas
razões. A árvore de dependências do spotdl inclui `fastapi`, `uvicorn`, `pydantic`,
`websockets` e `pykakasi` — congelar isso é um trabalho que o time do spotdl já faz e
publica pronto. E, congelado, o spotdl só se atualizaria com um rebuild nosso e um
reenvio do arquivo para cada pessoa.

**Embutir o `.exe` oficial deles como arquivo de dados dentro do nosso.** Melhor que
congelar, mas mantém a atualização presa ao nosso ciclo de release, infla o nosso
binário em 46 MB e coloca um executável aninhado dentro de outro — algo que antivírus
heurístico trata com mais desconfiança.

**Manter a busca por um Python do sistema** (o comportamento original). Rejeitado: é
exatamente o que impede a distribuição.

## Consequences

O programa **baixa e executa um binário de terceiro**. Isso é incomum o bastante para
ser lido como defeito, então é deliberado: o download é verificado por SHA256 contra o
digest que a API do GitHub publica, gravado num arquivo temporário e só então movido
para o lugar. A versão anterior é preservada, e se a nova não responder a `--version`
ela é revertida sozinha.

Herdamos a cadência de release do spotdl. Entre 08/10/2025 e 29/04/2026 eles passaram
sete meses sem lançar, enquanto o yt-dlp — que vai congelado dentro do binário deles —
lançou várias vezes. Numa seca dessas, atualizar o spotdl automaticamente não conserta
nada. Nenhuma opção acima conserta.

Dependemos de o projeto spotDL continuar publicando o build `win32`. Se pararem,
voltamos a congelar por conta própria.

Rodar `pythonw app.py` durante o desenvolvimento usa **os mesmos componentes** que a
versão distribuída, e não o spotdl do `pip` desta máquina. É proposital: o preparo é a
parte nova e frágil, e precisa ser exercitada aqui e não só na máquina de quem recebe.
A variável `BAIXARMUSICA_SPOTDL` sobrescreve o caminho quando for preciso testar outra
versão.
