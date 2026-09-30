# Koffuster

> Enumeração ativa de terminal, escrita em KOF — um binário, seis modos, zero exploração.

Koffuster é uma ferramenta de enumeração ativa para terminal, escrita em KOF
(Kof4j), voltada ao runtime **0.5.0-beta**. Ela reúne em um único binário os
modos mais comuns de reconhecimento:

| Modo | O que faz |
|---|---|
| `dir` | força bruta de diretórios/arquivos |
| `dns` | enumeração de subdomínios via DNS-over-HTTPS |
| `vhost` | enumeração de virtual hosts (novo nesta versão!) |
| `fuzz` | substituição de payloads com `FUZZ` em URL/cabeçalho/corpo |
| `s3` / `gcs` | verificação de existência/permissão de buckets S3 e GCS |
| `tftp` | registrado por completude, mas se recusa a rodar de forma honesta (veja [Limitações](#limitações-conhecidas)) |

Todo achado é reportado como **achado de enumeração**, nunca como
vulnerabilidade — Koffuster não explora nada, apenas sonda e reporta.

---

## O que mudou para o KOF 0.5.0-beta (v0.2.0)

A versão 0.2.0 foi reescrita para o runtime **KOF 0.5.0-beta** e aproveita o
que essa build corrigiu em relação à 0.2.6-beta:

- **`spawn` dinâmico com argumentos**: o 0.5.0 permite `spawn f(x)` e
  `listOf<Handle<T>>()`, então o motor de concorrência (que era ~1200 linhas
  de slots desenrolados à mão) virou um punhado de funções genéricas. O
  `sched.kf` atual tem ~150 linhas.
- **Status exato para qualquer resposta**: `http.status()` não lança mais por
  código de status — 200, 404, 403, 500... todos são reportados com precisão.
- **`http.get` com headers não lança em 4xx**: o corpo de uma resposta
  404/403 agora é lido normalmente, então o tamanho real aparece em
  candidatos que antes mostravam `-` (sentinela).
- **Erros de rede classificados por exceção `Exception`** (o catch `String e`
  do 0.2.6 não existe mais).
- **Modo `vhost` implementado de verdade** — na versão 0.1.0 o modo estava
  registrado no help e no dispatch, mas o arquivo do driver não existia; ele
  agora funciona.

E a CLI foi **simplificada**:

- `--threads` aceita **qualquer número** (antes era arredondado para
  1/2/4/8/16 por limitação do compilador).
- Removidas opções sem efeito real: `-k/--insecure`, `--no-banner`,
  `--delay`, `--rate`, `--wildcard-tests`.
- Atalho novo: `-f` para `--format`.
- Helps por modo reescritos em português, diretos e com exemplos.

---

## Requisitos e dependências

- Um runtime **KOF 0.5.0-beta** instalado: o comando `kof` no `PATH`, ou
  `$KOF_HOME/bin/kof` (a distribuição traz a própria JVM embutida — nenhuma
  instalação de Java é necessária).
- **Koffuster não é um executável independente.** Ele é código-fonte KOF
  (`src/*.kf`) que o runtime `kof` compila e executa a cada chamada, através
  do launcher `bin/koffuster`. Não existe binário nativo separado.

O launcher exporta automaticamente a cada execução:

```
JDK_JAVA_OPTIONS="-Djdk.httpclient.allowRestrictedHeaders=host"
```

Essa flag é obrigatória para o modo `vhost` (o runtime precisa sobrescrever
o header `Host`, que a JVM normalmente proíbe o cliente de alterar).

## Instalação e o launcher `bin/koffuster`

Não há passo de "instalação": basta ter o runtime KOF (veja acima) e chamar
`bin/koffuster`. O launcher:

1. Resolve o próprio caminho real (funciona via symlink e de qualquer
   diretório de trabalho) e localiza `src/` e `banner.txt`.
2. Exporta a flag JVM do vhost, mesclando com o que o chamador já tiver.
3. Se `--proxy <url>` for passado, mapeia para as propriedades
   `http(s).proxyHost`/`http(s).proxyPort` da JVM.
4. Limpa o stderr do processo filho: remove as linhas "Picked up
   JDK_JAVA_OPTIONS ..." e o prefixo de timestamp+nível que o `log.error` do
   runtime adiciona. O stdout nunca é tocado.
5. Executa (`exec`) o runtime KOF apontando para `src/main.kf`, repassando
   todos os argumentos exatamente como recebidos.

**Funciona a partir de qualquer diretório.** Caminhos relativos em
`-w/--wordlist` e `-o/--output` são resolvidos contra o diretório onde você
chamou `koffuster`, não contra a raiz do projeto.

Ordem de escolha do runtime: `$KOFFUSTER_KOF_JAR` (jar staged, para testes)
→ `$KOF_HOME/bin/kof` → `kof` no `PATH`.

---

## Como executar

```
koffuster <modo> [opções]
koffuster --help | -h
koffuster --version
koffuster help <modo>
koffuster <modo> --help
```

Modos: `dir dns vhost fuzz s3 gcs tftp`.

### Um exemplo real por modo

```bash
# dir — força bruta de diretórios/arquivos
koffuster dir -u http://alvo/ -w wordlist.txt -x php,html -t 16 -s 200,301

# dns — subdomínios via DNS-over-HTTPS
koffuster dns -d exemplo.com -w subdominios.txt --resolver https://dns.google/resolve

# vhost — virtual hosts variando o cabeçalho Host
koffuster vhost -u http://10.0.0.5/ -w hosts.txt --domain exemplo.com

# fuzz — substituição de FUZZ na URL, cabeçalho ou corpo
koffuster fuzz -u "http://alvo/busca?q=FUZZ" -w payloads.txt -s 200

# s3 — existência/permissão de bucket S3 (somente leitura)
koffuster s3 -w buckets.txt

# gcs — mesma ideia, endpoint do Google Cloud Storage
koffuster gcs -w buckets.txt --endpoint "https://storage.googleapis.com/%s/"

# tftp — registrado, mas sempre recusa rodar (veja Limitações)
koffuster tftp --server 10.0.0.9 --port 69 -w arquivos.txt
```

Todo exemplo acima é aceito literalmente pelo parser — não são pseudo-código.

### Códigos de saída

| Código | Significado |
|---|---|
| `0` | Execução ok, inclusive uma execução limpa que simplesmente não achou nada |
| `1` | A execução terminou com zero resultados **e** pelo menos um erro operacional (toda requisição recusada/expirou, alvo inalcançável) |
| `2` | Erro de uso: opção desconhecida ou opção obrigatória faltando |
| `3` | Só no `tftp`: modo não suportado nesta build |

---

## Opções

### Comuns a todos os modos ativos (dir/dns/vhost/fuzz/s3/gcs)

| Opção | Significado | Padrão |
|---|---|---|
| `-w, --wordlist <arquivo\|->` | wordlist, ou `-` para stdin | obrigatório |
| `-t, --threads <n>` | concorrência (qualquer número ≥ 1) | 8 |
| `--timeout <seg>` | timeout por requisição | 10 |
| `-o, --output <arquivo>` | grava resultados também em arquivo (append+flush) | só stdout |
| `-f, --format <text\|jsonl>` | formato de saída | text |
| `--proxy <url>` | proxy HTTP, mapeado pelo launcher para a JVM | — |
| `-q, --quiet` | sem banner/progresso, só resultados | off |
| `--color` | força cores ANSI (padrão: desligadas) | off |
| `-v, --verbose` | ecoa a configuração efetiva (segredos redigidos) no stderr | off |

### Autenticação e headers (dir/vhost/fuzz)

| Opção | Significado |
|---|---|
| `-H, --header <'Chave: Valor'>` | header extra, repetível |
| `--cookie <c>` | cookie (redigido no `-v`) |
| `--auth <user:pass>` | HTTP Basic Auth (redigido no `-v`) |
| `-a, --user-agent <ua>` | User-Agent (padrão `koffuster/0.2`) |

### Específicas por modo

- **dir**: `-u/--url <base>` (obrigatório), `-x/--extensions <csv>`,
  `-s/--status <lista>`, `-b/--exclude-status <lista>` (padrão `404`),
  `--exclude-length <lista>` (valores e faixas, ex. `0,100-200`).
- **dns**: `-d/--domain <domínio>` (obrigatório), `--resolver <url-DoH>`
  (padrão `https://dns.google/resolve`). Não aceita os filtros HTTP de `dir`
  (não fazem sentido para DNS).
- **vhost**: `-u/--url <alvo>` (obrigatório), `-d/--domain <domínio>`
  (faz o Host virar `palavra.domínio`).
- **fuzz**: `-u/--url` (obrigatório, com `FUZZ`), `-X/--method` (GET/POST/
  PUT/DELETE), `--body <dados>`, `-s/--status`, `-b/--exclude-status`,
  `--exclude-length`.
- **s3/gcs**: `--endpoint <modelo>` (`%s` vira o nome do bucket).
- **tftp**: `--server`/`-u`, `--port` — aceitos só por simetria; o modo
  sempre se recusa a rodar.

Filtros do dir/fuzz: `-s/--status` (se dado) desliga a exclusão padrão de
404; `-b/--exclude-status` aplica depois; `--exclude-length` por último.

---

## Formatos de saída

- **Resultados sempre vão para stdout.** Banner, progresso e resumo final
  vão para stderr — `koffuster dir ... 2>/dev/null` numa pipeline só entrega
  as linhas de resultado.
- **Texto** (padrão): colunas alinhadas, ex. `200   1234    /admin`.
- **JSONL** (`-f jsonl`): uma linha JSON por resultado no stdout, sem
  banner/cores/progresso misturados — cada linha é `json.loads`-ável
  isoladamente.
- **Cores**: desligadas por padrão (sem detecção confiável de TTY na build
  do KOF). `--color` força ligar; `NO_COLOR`, `-q` e `-f jsonl` forçam
  desligar.
- **`-o/--output <arquivo>`**: cada resultado é gravado (append) e
  imediatamente `flush`ado assim que é produzido — os resultados sobrevivem
  a um `Ctrl+C` no meio da execução.

---

## Banner

O banner vem de um arquivo `banner.txt` separado na raiz do projeto. Se ele
estiver vazio ou não existir, Koffuster imprime apenas a palavra
`Koffuster`. **Este projeto não inventa arte ASCII** — o conteúdo exato do
banner precisa ser colado como texto puro por quem o mantém, preservando os
bytes exatamente como fornecidos.

---

## Solução de problemas

- **"Picked up JDK_JAVA_OPTIONS..." no stderr**: já filtrado pelo launcher.
  Se você rodar o runtime KOF diretamente, essas linhas voltam — é a JVM
  avisando, não um erro do Koffuster.
- **Timeouts (`timeout` nos resultados)**: aumente `--timeout` se o alvo for
  lento, ou reduza `-t/--threads` para não saturar rede/alvo.
- **Conexão recusada (`refused`)**: porta fechada ou alvo fora do ar;
  Koffuster nunca trava, reporta o erro e segue (contabilizado no resumo).
- **Wordlist grande consumindo muita memória**: não existe API de leitura em
  streaming nesta build do KOF — o arquivo inteiro (ou todo o stdin) é
  carregado de uma vez. Para wordlists enormes, divida em partes menores.

---

## Limitações conhecidas

- **`tftp`/UDP não é suportado.** TFTP exige montar pacotes binários
  (`byte[]`), e `String.getBytes()` ainda derruba o runtime mesmo no
  0.5.0-beta (erro de runtime JavaFX). O FFI/`extern` documentado para o
  0.5.0 ainda não resolve no parser das builds atuais. Sem nenhuma das duas
  rotas, nenhum pacote TFTP pode ser montado. O modo está registrado (com
  `--help` completo), mas sempre imprime uma linha honesta no stderr e sai
  com código 3 — nunca finge um resultado.
- **Status exato com headers custom só para 5xx.** `http.status()` não
  aceita headers nesta build, e `http.get(url, headers)` retorna apenas o
  corpo (sem o código) para 2xx-4xx; só 5xx aparece na exceção (`HTTP 5xx`).
  Consequência: em `vhost` (que sempre usa Host custom) e em `dir`/`fuzz`
  com `-H`/`--cookie`/`--auth`, um candidato 2xx-4xx é reportado com status
  `200` e o tamanho real do corpo, e 5xx com o status verdadeiro. No modo
  `dir` sem headers custom (o caminho mais comum), o status é sempre exato.
- **Sem leitura de cabeçalhos de resposta.** O runtime KOF não expõe API
  para ler cabeçalhos da resposta HTTP: não há como seguir redirecionamentos
  (o destino de um `3xx` não pode ser lido, então `--follow-redirects` não
  existe) e o "tamanho" é sempre `.length()` do corpo já baixado.
- **Cores desligadas por padrão.** Sem detecção confiável de TTY nesta
  build, Koffuster nunca adivinha — cores só com `--color` explícito, para
  manter pipelines (`| grep`, `| jq`) sempre limpas.
- **Sem captura de `Ctrl+C` no código**, mas isso não perde resultado:
  cada linha em `-o/--output` é gravada com append+flush imediatamente, então
  o que já foi encontrado permanece no arquivo mesmo se o processo morrer sem
  resumo final.

---

## Estrutura do projeto

```
koffuster/
├── bin/koffuster        # launcher bash (resolve o runtime KOF e executa o módulo)
├── src/                 # código-fonte KOF (compila como um único módulo)
│   ├── main.kf          # dispatch de modos, --version, help top
│   ├── cli.kf           # parser de argumentos + textos de ajuda
│   ├── sched.kf         # concorrência com spawn dinâmico (KOF 0.5.0)
│   ├── classify.kf      # baseline soft-404, filtros, helpers DoH
│   ├── httpx.kf         # headers e classificação de erro HTTP
│   ├── output.kf        # formatação text/JSONL, banner, resumo
│   ├── wordlist.kf      # leitura de wordlist + expansão de extensões
│   ├── util_str.kf      # percent-encoding, base64, ranges, redação
│   ├── modes_dir.kf     # dir
│   ├── modes_dns.kf     # dns
│   ├── modes_vhost.kf   # vhost
│   ├── modes_fuzz.kf    # fuzz
│   ├── modes_store.kf   # s3/gcs
│   └── modes_tftp.kf    # tftp (recusa honesta)
├── docs/                # documentação técnica (arquitetura, relatórios)
├── labs/                # laboratórios locais de teste (HTTP/UDP/DoH)
├── banner.txt           # arte ASCII do banner (placeholder até receber o texto real)
└── README.md
```