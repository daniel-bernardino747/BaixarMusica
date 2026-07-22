# Baixamos o ffmpeg nós mesmos, e não pelo `spotdl --download-ffmpeg`

O spotdl oferece `--download-ffmpeg`, que resolveria o assunto em cinco linhas. Não
usamos: a implementação dele (`spotdl/utils/ffmpeg.py`) é um `requests.get(url).content`
sem streaming, o que significa carregar 76 MB na memória **sem nenhum progresso
observável** e com um `timeout=10` que não controlamos. Como o preparo acontece em
segundo plano e é mostrado no log, uma barra parada durante a maior das duas
transferências anularia justamente o que o preparo existe para fazer.

## Consequences

Usamos a mesma origem que eles usam — `eugeneware/ffmpeg-static`, tag `b4.4` — mas o
ativo `win32-x64.gz` em vez do `win32-x64` cru: **26 MB em vez de 76 MB**, e `gzip` é
stdlib. É um único membro, então descompactar é um `copyfileobj`, sem layout de arquivo
compactado para navegar. É ffmpeg 4.4, de 2021; para transcodificar mp3 320k com
libmp3lame isso é indiferente.

Como esse release é antigo demais para a API do GitHub publicar `digest`, o SHA256 do
`.gz` está **fixado no código** (`preparo.SHA_FFMPEG`), conferido à mão. Se um dia a URL
mudar, o hash precisa mudar junto.

Passamos `--ffmpeg <caminho>` explicitamente ao spotdl. Sem isso, o `get_ffmpeg_path()`
deles prefere qualquer `ffmpeg` que esteja no PATH, o que faria o programa usar um
binário diferente em cada máquina — inclusive na de quem desenvolve.

O custo marginal desta decisão é quase nulo: o downloader com progresso, retry e
verificação de hash já existe para o spotdl (ver [ADR 0001](./0001-spotdl-como-componente-externo.md)).
É a mesma função com outra URL.
