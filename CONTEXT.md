# BaixarMusica

Uma GUI mínima sobre o spotdl: uma pasta, um link, um botão. O programa administra
os próprios binários, para que quem o recebe não precise instalar nada antes.

## Language

### O que se baixa

**Coleção**:
Um link que representa um conjunto — playlist, álbum ou artista. Ganha uma subpasta
própria dentro da pasta de destino, nomeada pelo próprio conjunto.
_Avoid_: lista, grupo

**Faixa avulsa**:
Qualquer entrada que não seja uma coleção — uma música solta, um vídeo do YouTube ou
uma busca por texto. Cai direto na raiz da pasta de destino, sem subpasta.
_Avoid_: single, track solta

**Pasta de destino**:
A pasta escolhida na janela, onde tudo é gravado. A última usada é lembrada entre
sessões.
_Avoid_: pasta de saída, output

### Duplicados

**Repetida**:
Dois ou mais arquivos com o mesmo artista e o mesmo título nas tags. É o único caso
que o programa se propõe a apagar, e mesmo assim só depois de perguntar.
_Avoid_: duplicata, cópia

**Possível repetida**:
Arquivos com o mesmo título mas artistas diferentes. Pode ser um cover, um dueto ou
uma versão ao vivo. É reportada e **nunca** apagada.
_Avoid_: provável duplicata

**Varredura**:
A comparação de repetidas dentro de uma pasta. Não atravessa subpastas: cada pasta de
coleção continua completa e tocável sozinha.
_Avoid_: scan, análise

### Componentes

**Componente**:
Um binário de terceiro que o programa precisa para funcionar mas não carrega dentro de
si — hoje, o spotdl e o ffmpeg. Vive fora do executável, num diretório do usuário, e é
obtido e mantido atualizado pelo próprio programa.
_Avoid_: dependência, plugin

**Preparo**:
Deixar todos os componentes presentes e utilizáveis. Acontece sozinho ao abrir a
janela, é visível no log, e nenhum download de música começa antes de terminar.
_Avoid_: instalação, setup, bootstrap
