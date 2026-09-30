# Koffuster — Architecture (authoritative build spec)

> NOTA (v0.2.0): a implementação atual roda sobre **KOF 0.5.0-beta** (o
> `kof` da distribuição instalada, com JVM embutida). O texto abaixo
> documenta o desenho que orientou a 0.1.0 (0.2.6-beta) e continua
> descrevendo a estrutura; as seções que citam bloqueios de compilador do
> 0.2.6 (slots unrolled, spawn sem argumentos, `String` no catch) estão
> superadas — veja o cabeçalho de `src/sched.kf` e o README para o estado
> atual (spawn dinâmico, `catch (Exception e)`, status exato).

Koffuster is an active enumeration tool for the terminal, implemented in KOF
(Kof4j, targeting the **0.2.6-beta** runtime that the device's `bin/kof`
launcher actually runs). This document is the contract implementers follow.
It is grounded entirely in `docs/kof-report.md` and `docs/kof-cookbook.md`
(proven patterns). Do not invent capabilities; when a pattern is needed, use
the cookbook's proven form and cite it.

Ground rules for all code and docs in this project:
- No AI-tool or vendor attribution, generated-by comments, or agent references. Plain authorship.
- Never fake a feature. If something is blocked, report it honestly at runtime
  and in the README + requirements matrix, with the demonstrated reason.
- Results to **stdout**; banner, progress, summary, errors, logs to **stderr**.
- Secrets (passwords, cookies, tokens, auth) are redacted in any printed
  config, error, or log.

---

## 1. Runtime, invocation, launcher

- KOF module unit = a directory: all `.kf` files in one dir compile together as
  one module, share scope, and there must be exactly one `main()`. So all
  Koffuster source lives in **one directory** `src/` as multiple files
  (components), one of which holds `main()`.
- Required JVM env (the launcher sets these so behavior is identical to how we
  validated in the cloud):
  - `JDK_JAVAC_OPTIONS="--enable-preview --release 21"`
  - `JDK_JAVA_OPTIONS="--enable-preview -Djdk.httpclient.allowRestrictedHeaders=host"`
    (the `allowRestrictedHeaders=host` is mandatory for `vhost` mode; harmless
    for the others. `java`/`javac` pick these env vars up automatically, so no
    edit to `bin/kof` is needed.)
- Launcher `bin/koffuster` (bash): resolves its own real path (`readlink -f`),
  locates the install root and the `src/` module and `kof.jar`/`kof`
  command, exports the two env vars above (merging any `--proxy` mapping, see
  §7), then execs the KOF runtime on the module, forwarding all CLI args.
  MUST work when invoked from any working directory (resolve absolute paths).
  The core agent confirms the exact run syntax for a multi-file module + args
  (expected `kof run <src-dir> <args...>` or
  `java -jar <kof.jar> run <src-dir> <args...>`), and whether wordlist/output
  relative paths resolve against the caller's CWD (they must — resolve them
  from the process CWD, not the module dir).
- A Windows `.bat` is optional/best-effort; Linux bash launcher is required.

---

## 2. CLI grammar

```
koffuster <mode> [options]
koffuster --help | -h
koffuster --version
koffuster help <mode>
koffuster <mode> --help
```

Modes: `dir dns vhost fuzz s3 gcs tftp`.

Own hand-rolled arg parser (no stdlib argparse in KOF). Rules:
- Long `--name value` and `--name=value`; short `-x value`; boolean flags take
  no value. Unknown option → error to stderr + exit 2. Missing required option
  → clear error naming the option + the mode's help hint.
- Repeatable options accumulate (e.g. `-H` many times).
- `--` is not special; there are no positional args after `<mode>` except for
  `help <mode>`.

### Common options (shown per mode only where meaningful)
| Option | Meaning | Default |
|---|---|---|
| `-w, --wordlist <file\|->` | wordlist file, or `-` for stdin | required (dir/dns/vhost/fuzz/s3/gcs/tftp) |
| `-t, --threads <n>` | concurrency (bounded batch width) | 10 |
| `--timeout <sec>` | per-request timeout, **seconds** | 10 |
| `--delay <ms>` | per-worker delay between requests | 0 |
| `--rate <n>` | global max operations/second (all tasks incl. controls+retries) | 0 (unlimited) |
| `--retries <n>` | limited retries w/ progressive backoff (idempotent only) | 1 |
| `-o, --output <file>` | write results to file (append+flush per result) | stdout only |
| `--format <text\|jsonl>` | output format | text |
| `-H, --header <"K: V">` | request header, repeatable | — |
| `--cookie <"k=v; ...">` | Cookie header (redacted in config echo) | — |
| `--auth <user:pass>` | HTTP Basic auth (redacted) | — |
| `-a, --user-agent <ua>` | User-Agent | `koffuster/<version>` |
| `--proxy <url>` | HTTP proxy (mapped to JVM props by launcher; see §7) | — |
| `-s, --status <list>` | include-only these statuses (whitelist) | — |
| `-b, --exclude-status <list>` | exclude these statuses (blacklist) | `404` (see precedence) |
| `--exclude-length <list>` | exclude by body length; values + ranges `a-b` | — |
| `-k, --insecure` | allow invalid TLS certs (lab only) | off (TLS validated) |
| `-q, --quiet` | silent: no banner, no progress; results only | off |
| `--no-banner` | omit banner | off |
| `--color` | force ANSI colors on | off |
| `--no-color` | force colors off | (colors off by default) |
| `-v, --verbose` | extra progress/errors on stderr | off |
| `-h, --help` | help | — |
| `--version` | version | — |

Status/length lists: comma-separated; length supports ranges (`0,100-200,404`).

### Mode-specific
- `dir`: `-u/--url <base>` (required), `-x/--extensions <csv>` (e.g. `php,html`).
- `dns`: `-d/--domain <domain>` (required), `--resolver <doh-url>`
  (default a public DoH JSON endpoint), `--wildcard-tests <n>` (default 3).
- `vhost`: `-u/--url <target>` (required), `--domain <domain>`,
  `--append-domain` (candidate becomes `word.domain`).
- `fuzz`: `-u/--url <url-with-FUZZ>` (required unless FUZZ is in a header/body),
  FUZZ may also appear in `-H` values and `--body <data>`.
- `s3`: `--endpoint <tmpl>` (default `http://%s.s3.amazonaws.com/`), wordlist =
  bucket names.
- `gcs`: `--endpoint <tmpl>` (default `https://storage.googleapis.com/%s/`).
- `tftp`: `--server <host>`, `--port <n>` (default 69). See §Blockers.

---

## 3. Component layout (`src/`)

One module, files by responsibility (names indicative; keep flat in `src/`):
- `main.kf` — entry `main(args)`, top-level dispatch to modes, `--version`,
  `help`.
- `cli.kf` — arg tokenizer + a `Config` record + per-mode parse/validate,
  redaction of secrets, help text builders.
- `util_str.kf` — pure-KOF helpers: `percentEncode`, `base64Encode`, int/range
  list parsing, safe `Double`→string (avoid the `+`-concat Double bug: format
  numbers via Int math / manual, never `"" + aDouble`).
- `wordlist.kf` — load file or `/dev/stdin` (cookbook P4), split lines, policy
  for blanks/comments (`#` optional via flag; default: skip empty lines, keep
  everything else verbatim — do NOT silently trim internal spaces), extension
  expansion for `dir`.
- `sched.kf` — bounded concurrency: dynamic handle collection (spike first,
  §5), rate limiter, per-worker delay, retry w/ backoff, progress counters.
- `httpx.kf` — the ONE network primitive: `probe(url, headersString)` running
  `spawn`+`await`+`try/catch` (cookbook P1c/P1e). Returns a `Probe` record
  `{ok:Bool, status:Int, length:Int, err:String}`; never throws to callers.
  Does status+body as two probes when both needed. Applies timeout, UA,
  headers, auth, cookie.
- `classify.kf` — control/wildcard/soft-404 detection + filter engine
  (§6) + inclusive/exclusive precedence.
- `modes_dir.kf`, `modes_dns.kf`, `modes_vhost.kf`, `modes_fuzz.kf`,
  `modes_s3.kf`, `modes_gcs.kf`, `modes_tftp.kf` — one per mode.
- `output.kf` — text + JSONL writers (records + `json.encode(record)`),
  color handling, banner (`banner.txt`), final summary to stderr, append+flush
  to `-o`.

Records (flat, for `json.encode`): e.g.
```
record DirResult(String url, Int status, Int length, String note)
record DnsResult(String name, String outcome, String ip)
record VhostResult(String host, Int status, Int length, String note)
record FuzzResult(String url, Int status, Int length)
record StoreResult(String bucket, String url, Int status, String state)
```

---

## 4. HTTP primitive (`httpx.kf`) — mandatory pattern

Per cookbook P1: use `spawn`+`await`+`catch`; classify the caught String.
```kf
record Probe(Bool ok, Int status, Int length, String err)

Int statusOf(String url, String hdrs) { return http.status(url, hdrs) }
String bodyOf(String url, String hdrs) { return http.get(url, hdrs) }

Probe probeStatus(String url, String hdrs) {
    val r = spawn statusOf(url, hdrs)
    try { return Probe(true, await r, 0, "") }
    catch (String e) { return Probe(false, 0, 0, classifyErr(e)) }
}
```
- Multi-header MUST be one string joined by `\r\n` (cookbook P1e — multiple
  vararg header strings crash the compiler).
- `http.timeout(sec)` is process-wide and in **seconds**; set once at startup.
- Body length = `.length()` of the `http.get` string (no Content-Length API).
- `classifyErr`: `.contains("ConnectException")`→"refused";
  `"HttpTimeoutException"`→"timeout"; else "error: "+e (never leak secrets).

---

## 5. Concurrency & rate (`sched.kf`)

- **Spike first (blocking task for the core agent):** prove a dynamic
  collection of handles works, in this order, and use the first that compiles
  and runs on 0.2.6-beta:
  1. `var hs = listOf<Handle<Probe>>()` + `.add(spawn ...)` then iterate
     `await hs.get(i)`.
  2. `new Handle<Probe>[n]` array + index assign + `await hs[i]`.
  If BOTH fail, fall back to a fixed set of unrolled batch widths
  (`-t` snapped to nearest of 1,2,4,8,16,32) and document the limitation.
- Bounded model: process candidates in windows of `--threads` size. Launch a
  window of spawns, await each, collect results, apply per-worker `--delay`
  and the **global** `--rate` (a single shared token/timestamp gate covering
  ALL operations — control probes, retries, and normal probes alike; document
  the difference vs `--delay`, which is per worker between its own requests).
- Retries: `--retries` limited count, progressive backoff (e.g. 200ms, 400ms,
  800ms). Only retry idempotent GET/HEAD/status; never auto-retry POST/PUT/etc.
- Memory: never spawn one task per wordlist line; only a window's worth of
  handles live at once (cookbook P5).

---

## 6. Classification & filters (`classify.kf`)

- **Control probes (per target, before the scan):**
  - dir/fuzz: request several random unlikely paths → record status, body
    length, and whether it looks like a soft-404 (e.g. a `200` for a random
    path). Store the baseline signature(s).
  - dns: query `--wildcard-tests` random subdomains via DoH; if they all
    resolve (Status 0), wildcard is active → capture the wildcard IP(s).
  - vhost: request with one/few random control Host values → baseline
    status+length.
- **Deciding a hit:** compare a candidate's `{status, length, (redirect
  status)}` against the baseline. Do NOT treat body-length equality alone as
  proof to discard — require agreement on status too, and when the comparison
  is ambiguous, KEEP the result and mark `note="inconclusive"` rather than
  silently dropping it.
- **Filter precedence (explicit, no silent conflicts):**
  1. If `--status` (include/whitelist) is given → only those statuses are
     eligible; the default `404` exclusion is DISABLED (the user's explicit
     inclusion wins; no silent clash).
  2. Else default blacklist = `{404}` ∪ soft-404/wildcard signature.
  3. `--exclude-status` adds to the blacklist (applied after include).
  4. `--exclude-length` removes matching bodies (values + ranges) last.
  Document this order in `--help` and README.
- A reported result is an **enumeration finding**, never labeled a
  vulnerability.

---

## 7. Networking specifics per mode

- **dir**: preserve the base URL path and existing query string. Join base +
  candidate correctly (handle trailing `/`, avoid double `//`), keep `?query`.
  For each word, also emit `word.ext` for each `--extensions`. This is path
  CONSTRUCTION, distinct from `fuzz`'s free substitution. Two probes
  (status, and body only if length needed for filtering) — minimize requests:
  do `status` first; fetch body only when a length filter/baseline needs it.
- **dns**: DoH JSON. For each `word`, GET
  `<resolver>?name=word.domain&type=A` with header `Accept: application/dns-json`.
  Outcomes (cookbook P6): Status 0→"resolved" (scrape first `data` IP via
  string search — nested typed decode is broken), Status 3→"nxdomain",
  await-throw ConnectException→"resolver_down", HttpTimeoutException→"timeout".
  Apply wildcard filter (drop candidates whose IP == wildcard IP). `--resolver`
  is the custom DoH endpoint (this is how "custom resolver" is delivered; raw
  UDP DNS is unavailable — documented).
- **vhost**: connect to fixed `-u`; vary `Host` header (needs
  `allowRestrictedHeaders=host`, set by launcher). Candidate host = `word` or
  `word.domain` if `--append-domain`. No DNS resolution required per candidate.
  HTTPS/SNI note: with a fixed `-u` HTTPS target, SNI follows the URL host, not
  the `Host` header; with `-k` cert validation is disabled. Document + test.
- **fuzz**: require `FUZZ` present in url/header/body; error if absent. Replace
  ALL occurrences of `FUZZ` with the word. Apply context-aware encoding: when
  FUZZ is in the URL's query/path, percent-encode the word (util_str
  `percentEncode`); in headers/body, insert raw (document this). Document
  multi-FUZZ behavior (all replaced with the same word).
- **s3/gcs**: GET the bucket URL (no HEAD available). Map status →
  state: `404`→"absent", `403`→"exists_denied", `200`→"public",
  other/errors→"inconclusive" (NEVER treat 403 as absent). Read-only (GET);
  never write. Endpoints overridable via `--endpoint` (for lab mocks).
- **proxy**: `--proxy http://h:p` → launcher adds
  `-Dhttp.proxyHost/-Dhttp.proxyPort/-Dhttps.proxyHost/-Dhttps.proxyPort` to
  `JDK_JAVA_OPTIONS`. The network agent verifies KOF's HttpClient honors these;
  if not provable, document proxy as a known limitation (do not fake).
- **redirects**: default no-follow (HttpClient default). Because response
  headers are NOT readable on this build, redirect **targets cannot be shown**
  and `--follow-redirects` cannot be implemented faithfully → 3xx are reported
  by status only, and `--follow-redirects`/`--max-redirects`, if offered, must
  honestly state the limitation (prefer to OMIT the flag and document the
  constraint rather than ship a misleading one). Decide during build; default:
  omit follow flags, document.

---

## 8. Output (`output.kf`)

- Results → stdout. Progress, banner, summary, logs, errors → stderr
  (`log.info/error` for stderr; `println` for stdout results).
- **Text** (default): aligned columns, e.g.
  `200   1234   /admin` (dir). Colors ONLY if `--color` given
  (no reliable TTY detection on this build → default OFF so pipelines are
  clean; `NO_COLOR` env forces off; `--no-color` forces off; `--quiet` and
  `jsonl` force off). Document that auto-TTY detection is unavailable.
- **JSONL** (`--format jsonl`): one `json.encode(record)` per line to stdout,
  no banner/colors/progress mixed in. Never `json.encode(map)`.
- **`-o file`**: append+flush EACH result immediately (cookbook P9 — only way
  results survive Ctrl+C). Same format as chosen (text/jsonl).
- **Banner**: read `banner.txt` (see §9), print to stderr at start unless
  `--no-banner`/`--quiet`/`--format jsonl`. If `banner.txt` is empty/missing,
  print just `Koffuster`. Never invent ASCII art.
- **Summary** (stderr, unless `--quiet`): duration (format via Int ms — avoid
  Double concat bug), total operations, results found, errors.
- **Numbers**: never build display strings by `"" + someDouble` (proven to drop
  the value on 0.2.6). Use Int arithmetic / manual formatting.

---

## 9. Banner slot

- File `banner.txt` at project root, created now, holding a single space (or
  the exact art the user provides later). Preserve bytes exactly — do not
  reflow, re-indent, or normalize. The program reads it verbatim.
- The user is sending the banner as an image; exact byte transcription from an
  image is not guaranteed, so the file stays a clearly-marked placeholder until
  the user pastes raw text (README notes this).

---

## 10. Blockers (handle honestly)

1. **tftp / raw UDP** — demonstrated blocker on 0.2.6 (`getBytes()`/`byte[]`
   codegen crash; `DatagramPacket` needs a `byte[]`). Plan: the modes agent
   runs ONE time-boxed `extern`/C-FFI spike (libc `socket/sendto/recvfrom`).
   If it works → implement real TFTP read (RRQ, data/ACK, distinguish
   timeout vs file-absent; never write). If it fails → `tftp` mode is a
   registered mode with full `--help` that, on run, prints a clear honest
   message to stderr ("tftp/UDP is not supported on this KOF build: <reason>")
   and exits non-zero. This is NOT an empty stub-for-appearance: it documents a
   real, demonstrated limitation. Record the outcome in the matrix.
2. **No response headers / redirect targets / Content-Length** — documented;
   use body length; report redirects by status only.
3. **URL-encode & base64** — pure-KOF implementations in `util_str.kf`
   (interop blocked). Unit-test them against known vectors.
4. **Large wordlists** — whole file loaded to memory (no streaming API);
   documented memory tradeoff.
5. **Ctrl+C** — no SIGINT hook; durability via append+flush; no graceful
   summary on Ctrl+C (documented).
6. **Colors/TTY** — no TTY detection; default colors off.

---

## 11. Test plan (real KOF binary against local fixtures)

Reuse/extend `labs/` python fixtures. Every test runs the REAL Koffuster via
the launcher, from a directory OTHER than the project (prove out-of-tree run).
- dir: existing/nonexistent paths; soft-404 site; extensions; query preserved;
  base path preserved; length filter; status include/exclude precedence.
- dns: local mock DoH (resolved/nxdomain/resolver-down/timeout); wildcard.
- vhost: echo-Host server; baseline vs hit; append-domain.
- fuzz: FUZZ in url (encoded), header, body; missing-FUZZ error; multi-FUZZ.
- s3/gcs: mock endpoints returning 200/403/404 → public/exists_denied/absent;
  403 not treated as absent.
- tftp: local UDP/tftp fixture if FFI works, else assert the honest-failure
  message + non-zero exit.
- cross-cutting: JSONL validity (parse each line), stdout/stderr separation
  (results only on stdout), append+flush durability (kill mid-run, check file),
  timeouts/refused handled without crash, rate limit honored, run from another
  CWD, secret redaction in config echo.
- Reviews: a DIFFERENT agent reviews each component from the one that wrote it.

Requirements matrix lives at `docs/requirements-matrix.md`, updated as work
proceeds: requirement → implemented? → how tested → limitations.
