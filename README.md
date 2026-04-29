# MeshTCP — Transferência de Arquivos sobre Meshtastic

Protocolo simples e confiável para enviar arquivos entre dois nós Meshtastic via rádio LoRa, com fragmentação, ACK por chunk, retransmissão e verificação MD5.

## Como funciona

Dois scripts Python conversam por porta serial USB com rádios Meshtastic. O `sender.py` quebra o arquivo em chunks de 200 bytes, envia pelo `portNum=256` (PRIVATE_APP) e espera ACK de cada chunk. O `receiver.py` remonta na ordem, verifica MD5 e responde `DONE`.

### Formato dos pacotes

```
HEADER:  FILE|filename|total_chunks|md5
CHUNK:   CHK|n|<data>
ACK:     ACK|n
NACK:    NAK|n
DONE:    DONE|md5_ok | DONE|md5_fail
ABORT:   ABORT
```

## Requisitos

- Python >= 3.11
- 2x rádios Meshtastic (testado com placas baseadas em CP210x)
- Linux com acesso a `/dev/ttyUSB*` ou `/dev/ttyACM*`
- Dependências: `meshtastic>=2.7.8`, `psutil>=7.2.2`

## Instalação

```bash
uv sync
# ou
pip install meshtastic psutil
```

## Configuração

Antes de rodar, edite os IDs dos nós nos dois arquivos:

- `sender.py` — variável `DEST_ID` = node ID do receptor
- `receiver.py` — variável `SENDER_ID` = node ID do transmissor

Pega node ID com `meshtastic --info` na porta serial do rádio.

> Os scripts desligam PKC (chaves pública/privada) automaticamente ao conectar, pois pacotes criptografados chegam codificados e o protocolo precisa do payload em claro no `portNum=256`.

## Uso

### Receptor

```bash
python receiver.py
```

Escuta indefinidamente. Salva arquivos em `received_files/`. Reconecta automaticamente se USB cair.

### Transmissor

```bash
python sender.py caminho/do/arquivo.bin
```

Mostra estimativa (chunks, tempo previsto) e pede confirmação `[y/N]` antes de começar.

## Limites e cuidados

- **Tamanho prático: < 10 KB.** LoRa é lento. ~5s por chunk de 200 B. Arquivo de 10 KB ≈ 50 chunks ≈ 4 min.
- **Payload Meshtastic máx: 228 B.** Usa só 200 B de dados por chunk (resto é header `CHK|n|`).
- **Avisos automáticos:**
  - tempo estimado > 5 min → warning
  - arquivo > 50 KB → caution (risco de USB cair em transferência longa)
- **Timeouts:** 15s esperando ACK, 5 retries por chunk, depois `ABORT`.
- **Hop limit:** 3 (default Meshtastic).
- **Sem criptografia de aplicação.** Confiança no canal Meshtastic. PKC é desligado.
- **Um arquivo por vez.** Sem fila, sem múltiplos transmissores simultâneos para o mesmo receptor.
- **Sem resume.** Falha = recomeça do zero.
- **Ordem dos chunks não importa** na recepção (são guardados por número), mas o sender envia sequencialmente.
- **Duplicatas** são re-ACKadas mas não duplicam o arquivo.
- **MD5** apenas para integridade, não segurança.

## Estrutura

```
meshtcp.py    # protocolo (parse/build de pacotes, MD5, disable PKC)
sender.py     # script de envio
receiver.py   # daemon de recepção
tests/        # testes
received_files/  # output do receiver
```

## Troubleshooting

- **"No meshtastic device found"** — sem `/dev/ttyUSB*`. Confere `dmesg`, permissão (`dialout` group).
- **USB cai em transferência longa** — sender tenta reconectar 3x com 10s de espera. Receiver espera até 120s.
- **MD5 mismatch no final** — algum chunk corrompido sem ACK negativo. Re-envia o arquivo.
- **Sender preso esperando ACK** — receptor offline ou fora de alcance LoRa. Ctrl+C.
