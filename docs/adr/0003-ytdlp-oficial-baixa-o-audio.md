# O yt-dlp oficial baixa o áudio; o spotdl só acha a música

Em setembro de 2026 todo download passou a falhar com `AudioProviderError: YT-DLP
download error`, tanto de link do Spotify quanto do YouTube. Por baixo, o YouTube
respondia **HTTP 403** ao yt-dlp que vai congelado dentro do `spotdl.exe` 4.5.2. O
risco já estava registrado no [ADR 0001](./0001-spotdl-como-componente-externo.md): a
atualização automática do spotdl não adianta nada quando o próprio spotdl não lança
versão nova. E o 4.5.2 já era o release mais recente.

O yt-dlp oficial, na versão do mês, baixava o mesmo vídeo sem erro. Por isso a divisão
do trabalho passou a ser esta:

- **spotdl** entende o link. `spotdl save <link> --preload` devolve um `.spotdl` (JSON)
  com título, artistas, álbum, capa e o `download_url` do YouTube Music de cada faixa.
  Essa etapa não usa o yt-dlp embutido e continua funcionando.
- **yt-dlp** baixa o áudio de cada `download_url` e converte para mp3 320k.
- **nós** gravamos as tags ID3 com o mutagen, que já vai congelado no executável por
  causa da verificação de duplicados.

Links do YouTube nem passam pelo spotdl. O `save` refaz a busca e pode trocar o vídeo
que a pessoa mandou por outro, justamente o bug de
[docs/pesquisa-links-youtube-baixam-musica-errada.md](../pesquisa-links-youtube-baixam-musica-errada.md).
O yt-dlp lê o próprio vídeo, e o nome sai das tags dele.

## Considered Options

**Passar argumentos ao yt-dlp embutido** (`--yt-dlp-args` com `--js-runtimes` e
`--remote-components`). Testado: o 403 continua. O defeito é a versão do yt-dlp, não a
configuração dele.

**Apontar o spotdl para um yt-dlp mais novo.** O `spotdl.exe` é um executável
PyInstaller com o yt-dlp importado como biblioteca. Não há como substituí-lo por fora.

**Voltar a congelar o spotdl nós mesmos, com um yt-dlp novo.** É o que o ADR 0001
rejeitou, e continua caro pelos mesmos motivos. Além disso, a cada quebra do YouTube,
seria preciso fazer um rebuild nosso e reenviar o arquivo a cada pessoa.

## Consequences

O yt-dlp vira um **componente** com o mesmo tratamento do spotdl: release oficial
`yt-dlp.exe`, SHA256 conferido contra o `digest` da API, versão anterior preservada e
atualização a cada abertura. O yt-dlp lança versão com frequência, e agora cada uma
chega sozinha, sem depender do spotdl nem de nós.

O **deno** também entra, mas como único componente **opcional**. O YouTube passou a
exigir um desafio em JavaScript, e o deno é o runtime que o yt-dlp usa para resolvê-lo.
Por enquanto a maioria dos vídeos baixa sem ele (com aviso), então uma falha ao baixá-lo
não bloqueia o programa. Ele é baixado uma vez (zip de ~40 MB) e não é atualizado.

A primeira abertura passa a buscar ~130 MB em vez de ~72 MB.

O nome dos arquivos continua `{artistas} - {título}.mp3`, igual ao que o spotdl gerava.
Assim, o que já foi baixado nas versões anteriores é reconhecido e pulado. Isso
substitui o `--overwrite skip` do spotdl.

Perdemos o que o spotdl fazia no download e não reimplementamos: letras nas tags e os
formatos além de mp3. Nenhum dos dois era exposto na janela.
