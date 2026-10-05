# Video Factory

Sistema 100% gratuito e local para transformar um roteiro em um curta-metragem completo
(1080p, narração, imagens, trilha sonora e legendas queimadas) — estilo "YouTube documentary/noir".

Nenhuma chave de API, nenhuma conta, nenhum custo. Tudo roda no seu PC.

---

## Como usar (jeito fácil)

1. Dê dois cliques em **`run.bat`** — o servidor local sobe e o navegador abre em `http://localhost:8765`.
2. Escolha o **tema visual** (Crime Noir, Documentário, Terror, Motivacional, Sci-Fi, Histórico, Cartoon).
3. Digite o **título** e escolha a **voz** (ou deixe a voz recomendada do tema).
4. **Cole o roteiro** na caixa de texto (veja o formato abaixo) e clique em **GERAR VÍDEO**.
5. Acompanhe a barra de progresso. Ao terminar, o vídeo aparece na página com botão de download.
6. Não gostou de alguma imagem? Na **galeria de imagens** abaixo do vídeo, clique em **refazer** naquela
   imagem: o sistema sorteia uma nova versão só dela (as outras não mudam), remonta o vídeo e atualiza
   o kit do YouTube. Se o sorteio novo falhar, a versão anterior é mantida automaticamente.

O MP4 final também fica salvo em `projects/<nome_do_projeto>/`.

> Não feche a janela preta do servidor enquanto estiver gerando.
> Só uma geração por vez.

---

## Como usar (linha de comando)

```
D:\video_loan_shark\python\python.exe pipeline.py --script roteiro.txt --title "Meu Video" --theme noir --voice pt-BR-AntonioNeural
```

- `--script`  arquivo .txt com o roteiro (obrigatório)
- `--title`   título do vídeo (opcional; se não passar, o sistema tenta achar no roteiro)
- `--theme`   noir | documentario | terror | motivacional | scifi | historico | cartoon
- `--voice`   qualquer voz edge-tts (ex.: `pt-BR-ThalitaNeural`, `en-US-GuyNeural`)

Se der ruim no meio (internet caiu etc.), é só rodar de novo com o mesmo comando:
o sistema **retoma de onde parou** (imagens, narrações e trechos já prontos são reaproveitados).

---

## Formato do roteiro (livre e tolerante)

O parser entende português ou inglês, com ou sem acento, e ignora o que não reconhece.
Palavras-chave (maiúsculas/minúsculas tanto faz):

```
TITLE: A Última Entrega          <- título do cartão de abertura

PERSONAGENS:                     <- opcional; ajuda a manter consistência nas imagens
- Rafael: entregador, 30 anos, jaqueta surrada
- Dona Marta: 70 anos, sorriso sereno

---                              <- separador de cena (ou use CENA 1 / CENA 2 / SCENE 1...)

CENA 1
VISUAL: rua estreita à noite, chuva fina, luzes alaranjadas
VISUAL: motocicleta antiga na porta de um prédio cinza

NARRADOR: Rafael tinha uma regra simples: entregar rápido, não fazer perguntas.
O envelope de hoje pesava diferente.            <- linhas normais viram narração também

MOOD: tense                      <- opcional: noir, tense, sad, hopeful, epic (muda a música)

TEXTO FINAL: Algumas entregas mudam o dia.       <- cartão de citação antes do fim
PERGUNTA FINAL: Você abriria o envelope?         <- tela preta com narração no final
```

Regras de bolso:

- **Sem linhas VISUAL:** as imagens são geradas a partir de trechos da própria narração.
- **Sem marcadores de cena:** o roteiro inteiro vira uma cena única (divida com `---` para ter cortes).
- **MOOD por cena** sobrepõe o mood do tema naquele trecho.
- Parágrafos longos são ditos com pausa natural; legendas são quebradas automaticamente.

---

## O que o sistema faz sozinho

| Etapa | Ferramenta | Custo |
|---|---|---|
| Imagens das cenas (Ken Burns 1080p) | Pollinations.ai (sem chave) | grátis |
| Narração neural + legendas sincronizadas | edge-tts (Microsoft, sem chave) | grátis |
| Trilha sonora por humor (pads, drone, chuva, piano, tensão) | sintetizada localmente com numpy | grátis |
| Cartões de título/citação (Cinzel/Cormorant) | PIL | grátis |
| Montagem, transições, mixagem, legendas queimadas | ffmpeg | grátis |

Detalhes técnicos: imagens 1024x576 do Pollinations recebem corte da faixa da marca d'água,
reencuadre 16:9 e upscale para 1792x1008; cada cena recebe movimento Ken Burns alternado
(zoom in/out, pans), fade preto de 0,8s, música pré-"duckada" sob a narração (envelope de
attenuação baseado nas legendas) e mixagem narração + trilha; legendas ASS georgia 50px
com fade 220ms.

---

## Tempos e tamanho

- Vídeo de ~2 min: cerca de 10 imagens, roda em ~4–8 min dependendo da internet (imagens) e do PC (codificação).
- Um filme de 10 min (como o Loan Shark): ~50 imagens, use em um dia tranquilo :)

---

## Estrutura de pastas

```
video_factory/
  run.bat              <- inicia tudo
  server.py            <- servidor web local
  pipeline.py          <- orquestrador (CLI)
  parser.py            <- leitor de roteiro + timeline + legendas ASS
  images.py            <- Pollinations + pós-tratamento
  ttsx.py              <- narração edge-tts
  music.py             <- trilha sintetizada (numpy)
  cards.py             <- cartões de título/citação
  assembly.py          <- montagem ffmpeg
  presets.py           <- temas, vozes, caminhos
  web/index.html       <- interface
  projects/            <- um pasta por vídeo gerado
    <projeto>/
      config.json               <- insumos salvos (usados pelo botão "refazer")
      roteiro_processado.json   <- como o sistema entendeu seu roteiro
      timeline.json             <- tempos calculados
      audio/                    <- narrações + trilhas
      images/                   <- imagens das cenas
      cards/  subs/  segments/
      A_Ultima_Entrega.mp4      <- RESULTADO FINAL
      status.json               <- progresso (usado pela interface)
```

---

## Problemas comuns

- **"tts tentativa N falhou"** — edge-tts usa um serviço online da Microsoft; normalmente resolve
  sozinho nas 3 tentativas. Se falhar sempre, verifique a internet e rode de novo (retoma).
- **Imagens demoram / falham** — Pollinations é um serviço gratuito compartilhado; em horários de pico
  pode demorar. O sistema tenta sozinho até 16 vezes por imagem e, no pior caso, insere um cartão escuro
  com o texto da cena (o vídeo sai de qualquer jeito). Rodar de novo preenche as que faltaram, e o
  botão **refazer** da galeria troca só a imagem escolhida.
- **"ffmpeg falhou"** — anote a mensagem; geralmente é falta de imagem (o sistema reclama da cena).
- **Porta 8765 ocupada** — feche outra instância do run.bat, ou mude `PORT` em `presets.py`.
- **Antivírus reclama do python.exe** — é o Python portátil que veio com o projeto do filme; inofensivo.

---

## Requisitos

- Windows (testado no 10/11)
- O ffmpeg e o Python portátil em `D:\video_loan_shark\` (já presentes neste PC)
- Internet só para: imagens (Pollinations) e narração (edge-tts). A montagem é 100% offline.
