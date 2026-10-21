# MeshTCP — Transferência de Arquivos sobre Meshtastic

Protocolo simples e confiável para enviar arquivos entre dois nós Meshtastic via
rádio LoRa, com fragmentação, ACK por chunk, retransmissão e verificação MD5.

## Hardware e firmware de teste

Todo o desenvolvimento e os testes são feitos em:

- **2x Heltec WiFi LoRa 32 V3** (SoC **ESP32-S3**, rádio SX1262, USB CP210x)
- **Meshtastic firmware 2.7.15**
- Host **Linux**, acesso às placas via `/dev/ttyUSB*`

Outras placas Meshtastic com porta serial devem funcionar, mas não são validadas.

## Como funciona

Dois scripts Python conversam por porta serial USB com os rádios. O `sender.py`
quebra o arquivo em chunks de 200 bytes, envia pelo `portNum=256` (PRIVATE_APP) e
espera o ACK de cada chunk antes de mandar o próximo. O `receiver.py` remonta os
chunks por número, verifica o MD5 no final e responde `DONE`.

A confiabilidade vem de três camadas independentes do preset de rádio:

1. CRC físico do LoRa descarta pacotes corrompidos (chunk chega íntegro ou não chega).
2. ACK por chunk: chunk sem ACK é retransmitido.
3. MD5 no final confere o arquivo inteiro de ponta a ponta.

O sender espera o ACK do chunk atual; ACKs atrasados de chunks anteriores são
ignorados sem gastar retransmissão. O receiver envia um único ACK por chunk para
não congestionar o canal half-duplex.

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
- Dependências: `meshtastic>=2.7.8`, `psutil>=7.2.2` (ver `pyproject.toml`)

## Instalação

```bash
uv sync
# ou
uv pip install meshtastic psutil
```

## Configuração

Toda a configuração fica em `config.py`. Cada valor tem um default no código e
pode ser sobrescrito por variável de ambiente com prefixo `MESH_`, sem editar
arquivo. As listas `MODEM_PRESETS` e `LORA_REGIONS` documentam os valores válidos
e são validadas ao carregar.

Principais variáveis:

| Variável | Default | Descrição |
|----------|---------|-----------|
| `MESH_SENDER_ID` | node 7140 | node ID do transmissor (decimal, de `meshtastic --info`) |
| `MESH_RECEIVER_ID` | node 51a0 | node ID do receptor |
| `MESH_PRESET` | `LONG_FAST` | preset do rádio (ver tabela abaixo) |
| `MESH_REGION` | `BR_902` | região LoRa |
| `MESH_APPLY_RADIO` | `1` | aplica preset/região no rádio ao conectar |
| `MESH_CHUNK_DELAY` | `0.3` | pausa (s) após cada chunk com ACK |
| `MESH_ACK_TIMEOUT` | `15` | janela (s) de espera pelo ACK |
| `MESH_MAX_RETRIES` | `20` | retransmissões por chunk antes de abortar |

Os node IDs default já correspondem às duas placas de teste. Para outros rádios,
pegue o ID com `meshtastic --info` e ajuste em `config.py` ou via env.

Quando `MESH_APPLY_RADIO=1` (padrão), o script alinha o preset e a região do
rádio à config ao conectar, reiniciando a placa (~12s) apenas se algo mudou.
O PKC (chaves pública/privada) é desligado automaticamente, pois o protocolo
precisa do payload em claro no `portNum=256`.

### Presets de rádio e velocidade

Trocar o preset muda a relação velocidade x alcance (mesma rede, sem trocar
hardware). Os dois rádios precisam usar o mesmo preset.

| Preset | Taxa teórica | Banda | Uso |
|--------|--------------|-------|-----|
| `SHORT_TURBO` | 21.88 kbps | 500 kHz | mais rápido, alcance curto (nem toda região permite) |
| `SHORT_FAST` | 10.94 kbps | 250 kHz | rápido, alcance curto |
| `MEDIUM_FAST` | 3.52 kbps | 250 kHz | equilíbrio |
| `LONG_FAST` | 1.07 kbps | 250 kHz | default Meshtastic, maior alcance |

Medições na bancada com as duas Heltec V3 lado a lado:

- `LONG_FAST`: ~27 B/s
- `SHORT_FAST`: ~112 B/s, sem retransmissões, MD5 verificado

Para uma transferência rápida entre placas próximas:

```bash
MESH_PRESET=SHORT_FAST uv run python receiver.py
MESH_PRESET=SHORT_FAST uv run python sender.py arquivo.bin
```

## Uso

### Receptor

```bash
uv run python receiver.py
```

Escuta indefinidamente, salva em `received_files/` e reconecta sozinho se o USB
cair.

### Transmissor

```bash
uv run python sender.py caminho/do/arquivo.bin
```

Mostra a estimativa (chunks, tempo previsto) e pede confirmação `[y/N]` antes de
começar.

## Limites e cuidados

- **Tamanho prático pequeno.** LoRa é lento. Em `LONG_FAST`, ~5s por chunk de
  200 B; um arquivo de 10 KB leva minutos. `SHORT_FAST` reduz isso bastante em
  curta distância.
- **Payload Meshtastic.** O limite da biblioteca é 233 B por pacote; o protocolo
  usa 200 B de dados por chunk (o resto é o header `CHK|n|`).
- **Avisos automáticos:** tempo estimado > 5 min gera warning; arquivo > 50 KB
  gera alerta de risco de queda de USB em transferência longa.
- **Timeouts:** 15s esperando ACK, 20 retransmissões por chunk, depois `ABORT`.
- **Hop limit:** 3 (default Meshtastic).
- **Sem criptografia de aplicação.** A confiança é no canal Meshtastic; o PKC é
  desligado. O MD5 é só integridade, não segurança.
- **Um arquivo por vez.** Sem fila e sem múltiplos transmissores simultâneos para
  o mesmo receptor.
- **Sem resume.** Falha recomeça do zero.
- **Ordem dos chunks não importa** na recepção (guardados por número); o sender
  envia sequencialmente.
- **Duplicatas** são re-ACKadas e não duplicam o arquivo.

## Estrutura

```
config.py        # configuração central (defaults + override por env MESH_*)
meshtcp.py       # protocolo (parse/build de pacotes, MD5, PKC, config do rádio)
sender.py        # script de envio
receiver.py      # daemon de recepção
tests/           # testes
received_files/  # output do receiver
```

## Troubleshooting

- **"No meshtastic device found"** — sem `/dev/ttyUSB*`. Confira `dmesg` e a
  permissão de acesso à porta serial (grupo `uucp` ou `dialout`, conforme a
  distro).
- **"Could not exclusively lock port"** — outro processo está usando a porta
  (um receiver/sender já aberto). Feche-o antes.
- **USB cai em transferência longa** — o sender tenta reconectar 3x com 10s de
  espera; o receiver espera até 120s.
- **MD5 mismatch no final** — algum chunk chegou corrompido sem retransmissão
  bem-sucedida. Reenvie o arquivo.
- **Sender preso esperando ACK** — receptor offline, fora de alcance ou com
  preset diferente. Confira que os dois rádios usam o mesmo `MESH_PRESET`.
