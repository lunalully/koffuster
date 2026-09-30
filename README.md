# Koffuster

> Enumeração ativa de terminal, escrita em KOF — um binário, seis modos, zero exploração.

Koffuster é uma ferramenta de enumeração ativa para terminal, escrita em KOF
(Kof4j), voltada ao runtime **0.2.6-beta**. Ela reúne em um único binário os
modos mais comuns de reconhecimento:

| Modo | O que faz |
|---|---|
| `dir` | força bruta de diretórios/arquivos |
| `dns` | enumeração de subdomínios via DNS-over-HTTPS |
| `vhost` | enumeração de virtual hosts |
| `fuzz` | substituição de payloads com `FUZZ` em URL/cabeçalho/corpo |
| `s3` / `gcs` | verificação de existência/permissão de buckets S3 e GCS |
| `tftp` | registrado por completude, mas se recusa a rodar de forma honesta (veja [Limitações](#limitações-conhecidas-comprovadas-não-hipotéticas)) |

Todo achado é reportado como **achado de enumeração**, nunca como
vulnerabilidade — Koffuster não explora nada, apenas sonda e reporta.

---

## Requisitos e dependências

- Um runtime **KOF 0.2.6-beta** instalado na máquina: o comando `kof` no
  `PATH`, ou `$KOF_HOME/bin/kof`, ou (para desenvolvimento/testes) um
  `kof.jar` staged apontado pela variável `KOFFUSTER_KOF_JAR`.
- Uma **JVM Java 21** (o runtime KOF roda sobre ela e precisa das flags
  `--enable-preview`).
- **Koffuster não é um executável independente.** Ele é código-fonte KOF
  (`src/*.kf`) que o runtime `kof` compila e executa a cada chamada, através
  do launcher `bin/koffuster`. Não existe um binário nativo separado para
  distribuir — quem roda Koffuster precisa ter o runtime KOF disponível.

Variáveis de ambiente que o launcher exporta automaticamente a cada execução
(o usuário não precisa setá-las manualmente):

```
JDK_JAVAC_OPTIONS="--enable-preview --release 21"
JDK_JAVA_OPTIONS="--enable-preview -Djdk.httpclient.allowRestrictedHeaders=host"
```

A segunda flag (`allowRestrictedHeaders=host`) é obrigatória para o modo
`vhost` funcionar (ele precisa sobrescrever o cabeçalho `Host`, que a JVM
normalmente proíbe o código de cliente alterar).

---

## Instalação e o launcher `bin/koffuster`

Não há passo de "instalação" em si: basta ter o runtime KOF disponível (veja
acima) e chamar o script `bin/koffuster`. Ele:

1. Resolve seu próprio caminho real, mesmo se chamado via symlink, e a partir
   dele localiza a raiz do projeto (`INSTALL_ROOT`), a pasta `src/` e o
   `banner.txt`.
2. Exporta as duas variáveis de JVM acima, mesclando com qualquer valor que o
   chamador já tivesse definido.
3. Se `--proxy <url>` for passado, mapeia isso para as propriedades de
   sistema `http(s).proxyHost`/`http(s).proxyPort` da JVM.
4. Limpa o stderr do processo filho: remove as linhas "Picked up
   JDK_JAVA_OPTIONS/JAVA_TOOL_OPTIONS ..." que a própria JVM imprime, e tira o
   prefixo de timestamp+nível que o `log.error` do runtime KOF adiciona a toda
   linha (já que é o único jeito de escrever em stderr disponível nesta
   build). O stdout nunca é tocado por esse filtro.
5. Executa (`exec`) o runtime KOF apontando para `src/main.kf` (que compila
   junto todos os `.kf` irmãos do diretório — essa é a unidade de módulo do
   KOF), repassando todos os argumentos exatamente como recebidos.

**Funciona a partir de qualquer diretório de trabalho.** Caminhos relativos
passados em `-w`/`--wordlist` e `-o`/`--output` são resolvidos contra o
diretório onde o usuário chamou `koffuster`, não contra a raiz do projeto —
então rodar `koffuster dir -u http://alvo/ -w minhas_palavras.txt` de dentro
de `/home/voce/testes` lê `minhas_palavras.txt` dali, não da pasta do
Koffuster.

Ordem de escolha do runtime: `$KOFFUSTER_KOF_JAR` (jar staged, usado nesta
build/ambiente de testes) → `$KOF_HOME/bin/kof` → `kof` no `PATH`. Se nenhum
existir, o launcher falha com uma mensagem clara.

---

## Como executar

```
koffuster <modo> [opções]
koffuster --help | -h
koffuster --version
koffuster help <modo>
koffuster <modo> --help
```

Modos disponíveis: `dir dns vhost fuzz s3 gcs tftp`.

### Um exemplo real por modo

```bash
# dir — força bruta de diretórios/arquivos
koffuster dir -u http://alvo/ -w wordlist.txt -x php,html -t 16 -s 200,301

# dns — subdomínios via DNS-over-HTTPS
koffuster dns -d exemplo.com -w subdominios.txt --resolver https://dns.google/resolve

# vhost — virtual hosts variando o cabeçalho Host
koffuster vhost -u http://10.0.0.5/ -w hosts.txt --domain exemplo.com --append-domain

# fuzz — substituição de FUZZ na URL, cabeçalho ou corpo
koffuster fuzz -u "http://alvo/busca?q=FUZZ" -w payloads.txt -s 200

# s3 — existência/permissão de bucket S3 (somente leitura)
koffuster s3 -w buckets.txt

# gcs — mesma ideia, endpoint do Google Cloud Storage
koffuster gcs -w buckets.txt --endpoint "https://storage.googleapis.com/%s/"

# tftp — registrado, mas sempre recusa rodar (veja Limitações conhecidas)
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

## Opções por modo

Cada modo documenta suas próprias opções em `koffuster help <modo>` /
`koffuster <modo> --help`, com valor padrão e pelo menos um exemplo. Resumo:

### Comuns a todos os modos ativos (dir/dns/vhost/fuzz/s3/gcs)

| Opção | Significado | Padrão |
|---|---|---|
| `-w, --wordlist <arquivo\|->` | wordlist, ou `-` para stdin | obrigatório |
| `-t, --threads <n>` | concorrência, arredondada para 1/2/4/8/16 | 10 → 8 |
| `--timeout <seg>` | timeout por requisição, em segundos | 10 |
| `--delay <ms>` | pausa entre lotes | 0 |
| `--rate <n>` | limite global de operações/segundo, 0 = sem limite | 0 |
| `--retries <n>` | tentativas extras (só para operações idempotentes) | 1 |
| `-o, --output <arquivo>` | grava resultados também em arquivo (append+flush) | só stdout |
| `--format <text\|jsonl>` | formato de saída | text |
| `--proxy <url>` | proxy HTTP, mapeado pelo launcher para propriedades da JVM | — |
| `-q, --quiet` | sem banner/progresso, só resultados | off |
| `--no-banner` | omite o banner | off |
| `--color` / `--no-color` | força cores ligadas/desligadas | desligadas |
| `-v, --verbose` | ecoa a configuração efetiva (segredos redigidos) no stderr | off |

### Específicas por modo

- **dir**: `-u/--url <base>` (obrigatório), `-x/--extensions <csv>`,
  `-H/--header`, `--cookie`, `--auth`, `-a/--user-agent`, `-s/--status`,
  `-b/--exclude-status` (padrão `404`), `--exclude-length`, `-k/--insecure`
  (aceito, sem efeito real nesta build).
- **dns**: `-d/--domain <domínio>` (obrigatório), `--resolver <url-DoH>`
  (padrão `https://dns.google/resolve`), `--wildcard-tests <n>` (padrão 3).
  Não aceita/ignora os filtros HTTP de `dir` (não fazem sentido para DNS).
- **vhost**: `-u/--url <alvo>` (obrigatório), `--domain`, `--append-domain`,
  `-H/--header`, `--cookie`, `--auth`, `-a/--user-agent` (todos realmente
  enviados em cada requisição, não só aceitos pelo parser).
- **fuzz**: `-u/--url` (obrigatório, com `FUZZ`), `-X/--method`, `--body`,
  `-H/--header`, `--cookie`, `--auth`, `-a/--user-agent`, `-s/--status`,
  `-b/--exclude-status`, `--exclude-length`.
- **s3/gcs**: `--endpoint <modelo>` (`%s` vira o nome do bucket), `-w`.
- **tftp**: `--server`/`-u`, `--port` — aceitos só por simetria; o modo
  sempre se recusa a rodar.

---

## Formatos de saída

- **Resultados sempre vão para stdout.** Banner, progresso e resumo final
  vão para stderr — então `koffuster dir ... 2>/dev/null` numa pipeline só
  entrega as linhas de resultado.
- **Texto** (padrão): colunas alinhadas, ex. `200   1234    /admin`.
- **JSONL** (`--format jsonl`): uma linha JSON por resultado no stdout, sem
  banner/cores/progresso misturados — cada linha é `json.loads`-ável
  isoladamente.
- **Cores**: desligadas por padrão (não há detecção confiável de TTY nesta
  build do KOF). `--color` força ligar; `--no-color`, a variável de ambiente
  `NO_COLOR`, `--quiet` e `--format jsonl` forçam desligar.
- **`-o/--output <arquivo>`**: cada resultado é gravado (append) e
  imediatamente `flush`ado no arquivo assim que é produzido — é assim que os
  resultados sobrevivem a um `Ctrl+C` no meio da execução (veja Limitações).

---

## Banner

O banner vem de um arquivo `banner.txt` separado na raiz do projeto. Se ele
estiver vazio ou não existir, Koffuster imprime apenas a palavra `Koffuster`.
**Este projeto não inventa arte ASCII** — o conteúdo exato do banner precisa
ser colado como texto puro por quem o mantém, para preservar os bytes
exatamente como fornecidos (uma transcrição a partir de uma imagem não é
garantidamente fiel byte a byte, então o arquivo fica como placeholder até
receber o texto real).

---

## Solução de problemas

- **"Picked up JDK_JAVA_OPTIONS..." aparecendo no stderr**: já filtrado pelo
  launcher `bin/koffuster`. Se você rodar o runtime KOF diretamente (sem
  passar pelo launcher), essas linhas voltam a aparecer — isso é a JVM
  avisando sobre as variáveis de ambiente, não um erro do Koffuster.
- **Timeouts (`timeout` nos resultados)**: ajuste `--timeout <seg>` para um
  valor maior se o alvo for lento, ou reduza `-t/--threads` para não saturar
  a rede/o alvo.
- **Conexão recusada (`refused`)**: normalmente significa porta fechada ou
  alvo fora do ar; Koffuster nunca trava nesse caso, só reporta o erro e
  segue para o próximo candidato (contabilizado no resumo final).
- **Wordlist grande consumindo muita memória**: não existe API de leitura em
  streaming nesta build do KOF — o arquivo inteiro (ou tudo que vem do stdin)
  é carregado de uma vez na memória antes de começar. Para wordlists muito
  grandes, isso é uma limitação real, não um bug; considere dividir a
  wordlist em partes menores.

---

## Limitações conhecidas (comprovadas, não hipotéticas)

- **`tftp`/UDP não é suportado nesta build do KOF.** TFTP exige montar
  pacotes binários (`byte[]`) crus. Duas rotas foram tentadas e as duas
  falham: (1) `String.getBytes()` — e qualquer chamada que devolva `byte[]`
  — derruba o runtime com `NoClassDefFoundError`; (2) `extern`/FFI para
  `libc` (que permitiria montar o pacote via `socket`/`sendto`/`recvfrom`)
  simplesmente **não existe como palavra-chave no KOF 0.2.6-beta** — o
  parser rejeita a primeira linha `extern` (esse recurso só aparece na
  documentação do 0.5.0-beta). Sem nenhuma das duas rotas, não há como
  montar um pacote TFTP nesta build, ponto final. O modo `tftp` está
  registrado normalmente (com `--help` completo), mas sempre imprime uma
  única linha honesta no stderr e sai com código 3 — nunca finge um
  resultado.
- **Sem leitura de cabeçalhos de resposta.** O runtime KOF não expõe uma API
  para ler cabeçalhos da resposta HTTP. Consequência: não há como seguir
  redirecionamentos (o destino de um `3xx` não pode ser lido, então
  `--follow-redirects` simplesmente não existe — seria enganoso oferecer a
  flag e não conseguir cumpri-la), e não há `Content-Length`; o "tamanho" que
  Koffuster reporta é sempre `.length()` do corpo da resposta já baixado.
- **Status exato só para respostas 2xx quando há cabeçalhos/autenticação
  anexados.** A forma de duas chamadas do `http.get` (a única capaz de
  carregar cabeçalhos/UA/cookie/auth) lança exceção para qualquer resposta
  não-2xx nesta build, então um candidato não-2xx com cabeçalhos anexados
  aparece com o tamanho como `-` (sentinela), nunca um valor inventado. Isso
  afeta `vhost`, e `dir`/`fuzz` sempre que `-H`/`--cookie`/`--auth` forem
  usados.
- **`-t/--threads` limitado ao conjunto `{1,2,4,8,16}`.** Nem
  `listOf<Handle<T>>()` nem `new Handle<T>[n]` sobrevivem ao verificador de
  bytecode da JVM nesta build (`VerifyError` nos dois casos) — a única forma
  comprovadamente estável de concorrência é um conjunto fixo de lotes
  desenrolados manualmente, então `--threads` é arredondado para o valor
  suportado mais próximo, nunca é livremente variável.
- **Sem captura de `Ctrl+C` (SIGINT) no código do Koffuster**, mas isso não
  é um problema de durabilidade: como cada resultado em `-o/--output` é
  gravado com append+flush imediatamente ao ser produzido, os resultados já
  encontrados até o momento do `Ctrl+C` continuam no arquivo mesmo que o
  processo termine sem um resumo final. (Uma execução interrompida assim
  pode deixar para trás o diretório temporário daquela execução, já que não
  há hook de encerramento interceptável nesta build.)
- **Cores desligadas por padrão.** Não existe API confiável de detecção de
  TTY nesta build do KOF, então Koffuster nunca tenta adivinhar — cores só
  aparecem com `--color` explícito, para manter pipelines (`| grep`, `| jq`
  etc.) sempre limpas por padrão.
- **Interoperabilidade Java/FFI ausente no 0.2.6-beta de forma mais geral.**
  Vários recursos "óbvios" de Java (arrays de tipo referência, `System.*`,
  decodificação JSON aninhada, o cast `Long`→`Int`, chamadas HTTP com
  cabeçalhos em status-only) simplesmente não funcionam de forma confiável
  nesta build e exigiram soluções alternativas documentadas em
  `docs/impl-notes.md` e `docs/kof-cookbook.md`. Nenhuma dessas limitações é
  escondida: onde o comportamento é degradado, o texto de `--help` e a saída
  em tempo de execução dizem isso explicitamente.

---

## Estrutura do projeto

```
koffuster/
├── bin/koffuster        # launcher bash (resolve o runtime KOF e executa o módulo)
├── src/                 # código-fonte KOF (compila como um único módulo)
├── docs/                # arquitetura, notas de implementação, cookbook e relatórios
├── labs/                # laboratórios locais de teste (HTTP/UDP)
├── banner.txt           # arte ASCII do banner (placeholder até receber o texto real)
└── README.md
```

Para o detalhamento requisito-a-requisito (o que foi implementado, como foi
testado e qual a limitação exata de cada item), veja
`docs/requirements-matrix.md` — é a fonte única de verdade sobre o estado do
projeto.