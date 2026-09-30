# Koffuster — requirements matrix

## Pass 1 scope: `dir` mode + shared components

`dir` mode plus every shared component it needs (`cli.kf`, `util_str.kf`,
`wordlist.kf`, `sched.kf`, `httpx.kf`, `classify.kf`, `output.kf`,
`main.kf`, `modes_dir.kf`) and the `bin/koffuster` launcher.

| Requirement | Implemented? | How tested | Limitations |
|---|---|---|---|
| Module layout: one `src/` dir, one `main()` | Yes | `kof run src/main.kf ...` compiles all sibling `.kf` files together (confirmed via `tests/spike_multi`) | `kof run` only accepts a **file** argument, not a bare directory (`Error reading source file: Is a directory`); the launcher points it at `src/main.kf` |
| `bin/koffuster` launcher: self-resolving, sets JVM env, works from any CWD | Yes | Ran via absolute launcher path from `/tmp/koffuster_outoftree_test`, wordlist/`-o` resolved against that CWD, not the install root | Prefers `$KOF_HOME/bin/kof` or a `kof` on `PATH` on a real machine; falls back to `$KOFFUSTER_KOF_JAR` for this environment's staged jar (no system `kof` installed here) |
| `koffuster dir -u <base> -w <wordlist\|->` | Yes | Multiple runs against `labs/http_lab.py`; `-w -` not re-verified in this pass beyond `Path("/dev/stdin").readText()` (cookbook P4) but the code path is identical | — |
| `-x/--extensions` expansion | Yes | `wordlist.expandExtensions` unit logic exercised via the `dir` runs above (word + word.ext emitted) | — |
| Base URL path/query preserved, no `//`, trailing-slash intent kept | Yes | `classify.joinDirUrl` unit-tested directly against 6 cases (`tests/spike_join`): no path, trailing slash, `?query`, `?a=1&b=2` — all correct | — |
| `-t/--threads` bounded concurrency | Yes, with a documented cap | `runDirMode` snaps `-t` to the nearest of `{1,2,4,8,16}` | Neither dynamic-Handle-collection approach in architecture.md section 5 survives the JVM verifier on this build (VerifyError, both forms — see `docs/impl-notes.md`); fell back to unrolled fixed widths, capped at 16 (architecture's suggested 32 dropped to keep the generated slot-function/temp-file count sane — deliberate scope reduction) |
| `--timeout` (seconds), connection-refused/timeout handled without crashing | Yes | Live: closed port `127.0.0.1:1` → 6/6 candidates correctly reported "refused", 0 crashes; `/slow` with `--timeout 2` → correctly reported "timeout" | `http.status`/`http.get` calls must go through `spawn`+`await`+`catch` (cookbook P1c) — a bare synchronous `try/catch` does not catch these on this build |
| `--delay`, `--rate` | Implemented as documented approximations | Code path exercised in every `dir` run (rate/delay gates); not independently timed against a numeric target in this pass | No persistent "worker" threads exist across batches on this build, so `--delay` is applied once per batch rather than truly per-worker, and `--rate` paces at batch granularity rather than per individual request; both documented in `sched.kf`/`modes_dir.kf` comments and `--help` |
| `--retries` with backoff, idempotent only | Yes | `sched.statusWithRetries` used for connection-refused/timeout candidates; verified via closed-port run (no crash, no retry amplification into a hang) | dir mode only ever issues GET/status probes, so "idempotent only" is unconditionally true — no verb branching was needed |
| `-o/--output` append+flush per result | Yes | Killed a live run with real `SIGINT` mid-scan (`-t 1`, a `/slow` candidate in flight) — the output file already contained the prior result, process exited 130 | Killing the process leaves that run's `/tmp/.koffuster_slot_*` temp files behind (no interceptable shutdown hook on this build, same limitation class as Ctrl+C durability itself) |
| `--format text\|jsonl` | Yes | `--format jsonl` output parsed line-by-line with Python's `json.loads` — every line valid JSON, no banner mixed in | — |
| stdout/stderr separation (results only on stdout) | Yes | Captured stdout/stderr to separate files for a live run: stdout had exactly the 3 result lines, stderr had banner/progress/summary only | `System.err.println` does **not** resolve on this build at all (re-verified directly, contradicting what the cookbook's own `tests/stderr1` file implied but never actually confirmed with real output) — every stderr line goes through `log.error` instead, which prepends a timestamp + "ERROR" tag even for non-error lines (banner, progress, summary) |
| `-H/--header`, `--cookie`, `--auth`, `-a/--user-agent` | Partially | `--auth` verified end-to-end (base64 encode checked against Python's `base64` module, live request against `/echo` succeeded); `-H`/`--cookie` share the same `buildHeaders` code path but weren't independently re-verified this pass | **`http.status(url, hdrs)` — the two-argument form — crashes the compiler** (same internal frame-crash class as cookbook P1e's multi-header vararg bug), so status probes can never carry headers on this build; only the body-length probe (`http.get`, whose two-arg form works) does. Documented in `sched.kf` and `--help`. Separately: `http.get(url, hdrs)` **throws on non-2xx** (unlike the single-arg form proven in P1a) — so a non-2xx candidate's body length is `-1` whenever headers are attached, which is always in this build |
| `--proxy` | Implemented in the launcher, not independently verified | `bin/koffuster` maps `--proxy host:port` to the four JVM proxy system properties | Whether KOF's HttpClient actually honors them was not re-proven against a real proxy in this pass — documented as unverified rather than claimed working |
| `-s/--status` include vs default `404` exclusion, `-b/--exclude-status`, `--exclude-length`, exact precedence order | Yes, after a real bug fix | Four live runs: default (404 excluded), `--status 404` (both 404s now shown — this caught and fixed a real bug where the default `excludeStatus="404"` value was silently re-excluding an explicit `--status 404` whitelist), `--status 200,404 --exclude-status 404` (exclude wins, only 200 shown), `--exclude-length 3` (triggers the body-length pass, filters correctly) | — |
| Control probes / soft-404 baseline, ambiguous → "inconclusive" not dropped | Yes | Live runs show `soft-404 baseline status=404 length=2` detected against the lab (whose unmatched-path fallback returns 404/"nf"); the "inconclusive" path (status matches baseline, length differs) is implemented in `classify.decideResult` but not independently forced in a live run this pass | Control-probe "random" paths are a deterministic clock+salt mix, not a real RNG — `random.*` does not resolve on this build; documented as good enough for its one job (avoiding a wordlist collision), not a security property |
| `-k/--insecure` | Accepted, no effect | Flag parses and is echoed in `-v` output | No TLS-configuration API is exposed by `kof.http` on this build — honestly disclosed rather than silently ignored |
| `-q/--quiet`, `--no-banner`, `--color`, `--no-color`, `NO_COLOR` env | Yes | Verified `-q` suppresses banner/candidate-count line; color decision logic (`colorsEnabled`) covers all five inputs (`--color`, `--no-color`, `--quiet`, `format`, `NO_COLOR` env) | Colors default OFF (no TTY detection API exists on this build) |
| `-v/--verbose` config echo with secret redaction | Yes | Live run with `--auth admin:sup3rsecret --cookie session=topsecret123 -v`: echo shows `cookie=<redacted> auth=<redacted>`, never the real values | — |
| Banner from `banner.txt`, empty→"Koffuster" | Yes | `banner.txt` is currently a placeholder (0 bytes, per architecture.md section 9 — real art not yet supplied); every run correctly falls back to printing plain "Koffuster" | The launcher exports `KOFFUSTER_BANNER` (an absolute path) so this resolves correctly even when Koffuster is invoked from a different working directory than the install root — this was tested and fixed during this pass (an earlier version used a bare relative `Path("banner.txt")`, which silently fell back to "Koffuster" from any other CWD instead of showing the real banner) |
| `--version`, `-h/--help`, `help <mode>` | Yes | `koffuster --version` → `koffuster 0.1.0`; `koffuster help dir` prints the full option table | — |
| Run from a different CWD than the project; relative wordlist/`-o` resolve against caller's CWD | Yes | Full run from `/tmp/koffuster_outoftree_test` using the launcher and relative `mywords.txt`/`myout2.txt` — both resolved correctly against that directory, not the install root | — |
| Numbers never built with `"literal" + someDouble` | Yes, and Double is avoided entirely | `util_str.intToStr` documents the rule; every duration in the codebase is tracked via `time.now()` (which returns **Long**, not Int — a second, separate gotcha found and worked around, since `Long.toInt()` also crashes codegen on this build; the fix is a round-trip through `String` + `.toInt()`, proven safe) | — |
| Reported results are "enumeration findings", never labeled vulnerabilities | Yes | Text/JSONL output only ever shows status/length/note — no severity or vulnerability language anywhere in `output.kf` | — |
| `tftp`/raw UDP | See Pass 2 below | — | — |

## Pass 2 scope: dns, vhost, fuzz, s3, gcs, tftp modes

Adds `modes_dns.kf`, `modes_vhost.kf`, `modes_fuzz.kf`, `modes_store.kf`
(shared by s3/gcs), `modes_tftp.kf`, and extends `cli.kf`, `classify.kf`,
`output.kf`, `sched.kf`, `main.kf` for the new modes. Also refines `dir`
mode and the shared body-length path (see "Shared refinement" below).

### Shared refinement: real body lengths, sentinel display

`http.get(url)` (one argument) was previously believed (per the cookbook's
P1a note) to "never throw". Directly re-tested against `/500`: it **does**
throw `IOException: HTTP 500` — the corrected rule (see `docs/impl-notes.md`)
is that the one-argument form throws for any 5xx and only 5xx; 4xx returns
normally either way. Because of this, when the user supplied no custom
headers/cookie/auth, `dir` (and any mode reusing the same helper) now uses
the one-argument `http.get` to fetch a real body length for every status
except 5xx (where the sentinel `"-"` is shown, not a fake `-1`). When the
user did supply headers/cookie/auth, the original header-bearing path is
kept, which only yields a length for 2xx (headers up the specificity but
lose the 4xx/5xx body — documented, not worked around, same as Pass 1).
`length` is a `String` field everywhere now (not `Int`), so the sentinel
`"-"` can be represented directly in both text and JSONL output, instead of
overloading `-1` as a fake numeric value. Re-verified live: `dir` against
`/200` (no headers) → length 9 (real), `/301` → length 5 (real), `/500` →
`-` (sentinel, request still correctly thrown/caught, no crash).

The slot protocol (`sched.kf`) was extended so each batch slot can also
read a per-candidate HEADERS file and a per-candidate BODY-to-POST file,
written synchronously before that slot is spawned (same race-free pattern
as the existing per-candidate URL file from Pass 1). This is what lets
`vhost` vary the `Host` header and `fuzz` vary URL+header+body per
candidate, despite `spawn f(x)` crashing on any variable argument
(impl-notes.md item 2) — every new per-candidate value still has to go in
through a file, not a function argument.

| Requirement | Implemented? | How tested | Limitations |
|---|---|---|---|
| `dns -d <domain> -w <wordlist>` via DoH | Yes | `koffuster dns -d example.mock --resolver http://127.0.0.1:18080/doh -w /tmp/dnswords.txt --wildcard-tests 1 -v`: `www`/`real` → `resolved` with the mocked IP, `nope123xyz` → correctly suppressed (nxdomain, not printed by default — see below) | No native DNS/UDP API exists on this build (same `String.getBytes()`/byte[] blocker as tftp) — "custom resolver" means a custom **DoH JSON endpoint**, never raw UDP DNS; disclosed in `--help dns` |
| DoH Status parsing (0=resolved, 3=nxdomain) instead of HTTP status | Yes | Lab's `/doh` route always answers HTTP 200; `resolved` vs `nxdomain` is read from the decoded JSON `Status` field only, confirmed both branches live against the mock resolver | `json.decode<FlatRecord>` cannot deserialize the DoH response's nested `Answer`/`data` list (Pass 1's nested-record `ClassCastException` blocker) — the first `data` IP is scraped via `indexOf`/`substring` instead of proper JSON list decoding |
| `resolver_down` / `timeout` outcomes | Yes | `spawn`+`await`+`catch` around the DoH GET classifies `ConnectException`→`resolver_down`, `HttpTimeoutException`→`timeout`, reusing the Pass 1 catch pattern (bare try/catch does not catch these on this build) | — |
| `--wildcard-tests N`, wildcard IP detection and candidate suppression | Yes | `--wildcard-tests 1` against the mock resolver; separately confirmed the drop-on-match branch reads correctly in code (`modes_dns.kf`) — not forced with a live wildcard-matching candidate in this exact run, but the same code path that resolves `www`/`real` proves the IP-compare logic executes | Wildcard probe names use the same deterministic clock+salt token as Pass 1's control probes (`random.*` does not resolve on this build), not a real RNG |
| nxdomain not printed by default | Yes, and deliberate | Live: `nope123xyz.example.mock` correctly produced no stdout line and no JSONL row, counted correctly in the summary's request total | Mirrors `dir` mode's "don't show 404 by default" precedent (architecture.md §6) — verbose mode (`-v`) does log it to stderr for visibility |
| `dns -o/--output` durability | Yes | `--format jsonl -o /tmp/dnsout.jsonl` — file contents matched stdout exactly, both lines parsed as valid JSON via Python | — |
| `vhost -u <target> -w <wordlist>`, Host header varied per candidate | Yes | `koffuster vhost -u http://127.0.0.1:18080/vhostroute -w /tmp/vhostwords.txt -v` (no `--append-domain`): baseline length correctly detected as 7 (the lab's generic-Host body), candidate words `ok`/`real` correctly produced 0 hits (same length as baseline, correctly filtered) | Requires `-Djdk.httpclient.allowRestrictedHeaders=host` (already set by `bin/koffuster`) since the JDK HttpClient normally refuses to let callers set `Host` at all |
| vhost baseline + diff-from-baseline hit detection | Yes | Two random-token Host values probed first; when both return the same length, that becomes `baselineLen` and every candidate is only reported if its length differs — confirmed by the 0-hit run above (baseline matched) | Header-bearing GET only returns a body length for 2xx (same Pass-1 build limit); a baseline or candidate that itself answers non-2xx is reported via the error/"no-baseline" path honestly rather than guessing a status, and `--help vhost` documents the exact-status-only-for-2xx limit |
| `--append-domain` (word → word.domain as Host) | Yes | Code path (`vhostHost`) exercised in earlier session testing with `--domain` + `--append-domain` against a two-body-by-Host lab route (admin.-prefixed Host → distinct 31-byte body, correctly flagged a hit); this session re-confirmed the complementary no-domain plain-word path | — |
| `fuzz`: FUZZ substitution in URL/headers/body | Yes | `koffuster fuzz -u "http://127.0.0.1:18080/echo?x=FUZZ" -w /tmp/fuzz200.txt --format jsonl -o /tmp/fuzzout.jsonl`: both candidates produced valid JSONL rows, file matched stdout exactly; header/body substitution independently confirmed earlier this session by comparing Koffuster's fuzzed request against an equivalent hand-built `curl` request — both produced an identical 91-byte `/echo` response | Multi-FUZZ (same marker present in more than one of url/headers/body) replaces **every** occurrence with the same word — documented in `--help fuzz`, not independently re-verified with all three populated simultaneously this session |
| FUZZ-missing error | Yes | `-u` with no `FUZZ` anywhere and no `-H`/`--body` containing it → `koffuster fuzz: FUZZ not found in -u/-H/--body` to stderr, exit 2, no request sent | — |
| Context-aware encoding: percent-encoded in URL, raw in headers/body | Yes | `fuzzSubstituteUrl` routes through the same `percentEncode` used by Pass 1's extension-expansion path; `fuzzSubstituteRaw` is a plain `.replace`, confirmed by the curl-comparison test above (header/body values arrived unescaped) | Documented explicitly in `--help fuzz`, not a bug — a word containing characters that need escaping in a header value is the caller's responsibility |
| `-X/--method` GET/POST/PUT/DELETE | Yes | GET path verified live (URL-FUZZ-only fast path, exact status via the plain status probe); POST/PUT/DELETE route through the new `runPostBatch`/`runPutBatch`/`runDeleteBatch` slot families, exercised at compile+dispatch level and via the curl-comparison POST-body test | Only GET with FUZZ confined to the URL and no custom headers gets an exact status (fast path); POST/PUT/DELETE and any header-bearing GET only report an exact status for 2xx, same build-wide limit as `vhost` — documented in `--help fuzz` |
| fuzz connection-refused handling | Yes | `-u http://127.0.0.1:1/FUZZ` → 2 candidates, 0 results, 2 errors, no crash | — |
| `s3 -w <bucket-wordlist>` | Yes | `koffuster s3 -w /tmp/vhostwords.txt --endpoint "http://127.0.0.1:18080/s3/%s" -v`: `ok`/`real` both mapped to the lab's default (non-public, non-private) branch → 404 → `absent` → correctly suppressed from output (0 results) | — |
| s3 status mapping, 403 never treated as absent | Yes | Lab's `/s3/<bucket>` route: confirmed via curl that `public-bucket`→200, `private-bucket`→403, anything else→404; Koffuster's mapping (`404`→absent/hidden, `403`→exists_denied/shown, `200`→public/shown, else→inconclusive/shown) reuses the plain status probe (no headers needed, so no compiler-blocker workaround required here) | GET/status only, never writes — confirmed by code inspection (`modes_store.kf` only ever calls the status-probe batch family) |
| `--endpoint` template (`%s`→bucket) | Yes | Custom `--endpoint` pointed at the lab's mock route in every s3/gcs test this session, confirmed correct substitution via the printed candidate URL | Default is the real `http://%s.s3.amazonaws.com/` form; not tested against real AWS (would require a real bucket/account and is out of scope for a local-lab pass) |
| `gcs` (shares s3 logic) | Yes | `runGcsMode` delegates to the same `runStoreMode` as s3 with a different default `--endpoint`; exercised against the lab's `/gcs/<bucket>` route (same public/private/absent branching as `/s3/<bucket>`, confirmed via curl) earlier this session | Same limitations as s3 |
| `tftp`: time-boxed spike + honest blocker if unsupported | Blocked, not faked | See "tftp spike result" below | Registered as a real mode with full `--help`; running it always prints one honest line to stderr and exits non-zero (confirmed live, exit code 3), never fakes a result |

### tftp spike result (updated in the review pass — see below for the
### definitive, two-path answer; the FFI half of this was resolved after
### the paragraph below was originally written)

TFTP is a UDP protocol built entirely out of raw `byte[]` packets (an RRQ
is opcode + filename + mode bytes; `DatagramPacket`'s constructor requires
a `byte[]`). Cookbook P8 and this project's own Pass-1 testing confirmed
that `String.getBytes()` — the only candidate path on this build to
produce a `byte[]` from a `String` — crashes the runtime with
`NoClassDefFoundError`, unconditionally, with nothing else in play. A
dedicated TFTP/UDP FFI spike (docs/impl-notes.md, "TFTP/UDP FFI spike")
then tried the other possible path, `extern` C-FFI straight to libc's
`socket`/`sendto`/`recvfrom`: `extern` is not a recognized keyword on KOF
0.2.6-beta at all (parse error on the first `extern` line; jar inspection
confirms no `extern`/FFI machinery exists in this compiler — it first
appears in the 0.5.0-beta docs). With neither the pure-Java byte[] path
nor the FFI path available, there is no way to materialize a TFTP packet's
payload at all on this build, through any API. `tftp` is registered as a
full mode (`main.kf` dispatches to it, `--help tftp` documents it fully,
`--server`/`--port` accepted for symmetry) that always prints one honest
line to stderr and exits with status 3, rather than emulating a fake read
check. Verified live: `koffuster tftp --server 10.0.0.9 --port 69 -w
files.txt` → the honest message on stderr, exit code 3, no stdout output,
no crash. Never implements TFTP write (WRQ) even if a future build (KOF
0.5.0-beta+, which documents FFI) lifts this blocker.

## Compiler/runtime blockers found and worked around this pass

See `docs/impl-notes.md` for full repros. Summary:

1. Neither `listOf<Handle<T>>()`+`.add()`/`.get()` nor `new Handle<T>[n]`
   survives the JVM bytecode verifier — both crash with `VerifyError` at
   process start. **Fallback: unrolled fixed batch widths (1/2/4/8/16),
   matching cookbook P5's proven shape.**
2. `spawn f(x)` where `x` references *any* local variable or parameter
   (any type, any nesting depth) also crashes with `VerifyError` — this
   was not caught by the cookbook because every cookbook example spawned a
   zero-argument function. **Fallback: every batch "slot" is a hardcoded,
   literal-named, zero-argument function that reads its target URL from a
   small dedicated temp file, written synchronously right before that
   slot is spawned.**
3. `http.status(url, hdrs)` (two-argument) crashes the compiler with the
   same internal frame-crash class as the cookbook's known multi-header
   vararg bug. Status probes can never carry headers on this build.
4. `http.get(url, hdrs)` (two-argument, headers attached) throws on any
   non-2xx status, unlike the proven-safe single-argument form. Documented
   rather than worked around, to avoid silently dropping headers exactly
   for the candidates most worth inspecting closely.
5. `System` does not resolve at all on this build (`System.err.println`,
   `System.exit` both fail) — `log.error` (confirmed stderr) and
   `process.exit` (`kof.process`, confirmed working) are the real,
   verified substitutes.
6. `time.now()` returns `Long`; `Long.toInt()` crashes codegen, and there
   is no `(Int)` cast syntax or `Int(x)` conversion function. Worked
   around via a `"" + longValue` then `.toInt()` round-trip through
   `String` (proven safe — `String.toInt()` throws a catchable,
   normal-exception `NumberFormatException`-style error, never crashes).
7. A record field declared with a collection type must use `List<T>` in
   the type position; `listOf<T>` is only the construction function, not a
   valid type name (`NoClassDefFoundError`/similar if used as a type).
8. `new T[n]` (a reference-typed array) is broken generically for any
   `T`, not just `Handle<T>` — confirmed independently with `new
   String[3]`. `listOf<T>()` is the only proven-safe dynamic reference
   collection.

## Correctness bug found and fixed during this pass' own testing

`defaultConfig()` originally pre-seeded `excludeStatus` with `"404"` to
match the CLI table's documented default. Combined with
`classify.decideResult` applying `--exclude-status` unconditionally after
the include decision, this silently re-excluded an explicit `--status 404`
whitelist — exactly the "silent conflict" architecture.md section 6
requires avoiding. Fixed by defaulting `excludeStatus` to `""` and
handling the *default* 404 exclusion entirely inside `decideResult`'s own
"no whitelist given" branch, where it was already correctly implemented.
Caught by a live run (`--status 404` returned 0 results before the fix, 2
after) rather than by inspection — logged here as the kind of bug this
matrix is meant to surface.

## Review pass (independent verification + fixes)

| Area | Change / finding | Verified by |
|---|---|---|
| Launcher JVM noise | `bin/koffuster` now filters only the `Picked up JDK_JAVA_OPTIONS/JAVA_TOOL_OPTIONS/_JAVA_OPTIONS` (and `NOTE: `-prefixed) lines from the child's stderr; stdout untouched, SIGINT still reaches the JVM | `--version` stderr empty; dir run stdout md5 identical to an unfiltered direct run |
| `NO_COLOR` / `KOFFUSTER_BANNER` | `config.has()` does not see OS environment variables on this build (returns false for a set var); replaced with `envIsSet()` (`config.env(k) != null`). Before: `NO_COLOR=1 --color` still emitted ANSI, and the launcher-provided banner path was never read | `NO_COLOR=1 ... --color` -> 0 ANSI codes; banner shown from another CWD |
| `--help` / `help <mode>` / `<mode> --help` | Now printed to stdout (was stderr with a log prefix); every mode has Examples; top-level help lists modes; unknown `help <mode>` exits 2 | all 7 modes x 3 forms exit 0; examples executed against the lab |
| Numeric options | `-t/--timeout/--delay/--rate/--retries/--wildcard-tests/--port` reject non-integers/negatives (and 0 for `-t`/`--timeout`) with exit 2; previously silently fell back to the default | `-t abc`, `-t 0` |
| Missing wordlist file | Clear error + exit 2 (was an NPE stack trace) | `-w nofile.txt` |
| fuzz | Status filters (`-s/-b/--exclude-length`, default 404 exclusion) now applied, same engine as dir; results carry the substituted `word` (text shows `(FUZZ=word)` when FUZZ is not in the URL) so header/body fuzz rows are distinguishable | live runs |
| s3/gcs | Connection errors report status `0` (text `-`) instead of `-1` | refused-port run |
| tftp | Parser accepts `--server` (alias of `-u`) and `--port` per the spec; blocked decision untouched | exit 3 |
| Secret redaction | Userinfo in `-u`/`--resolver`/`--endpoint` (`user:pass@host`) is redacted in every stderr line | grep of stderr for the secret = 0 |
| Non-ASCII | Em-dashes in messages/help were mangled to `?` by the runtime's default charset; replaced with `-` | help output |

## Review pass, round 2 (coordinator-requested fixes)

| # | Area | Change | Verified by |
|---|---|---|---|
| 1 | stderr chrome | `log.error` (the only stderr writer on this build) prepends a `YYYY-MM-DD HH:MM:SS.mmm LEVEL ` prefix to every line, including the banner/progress/summary, which are not errors. `bin/koffuster`'s stderr filter now also strips that leading timestamp+level prefix with `sed`, in the same pipe that already drops the JVM's "Picked up ..." notices. stdout is untouched (the filter only ever touches fd 2) | `koffuster dir -u <url> -w empty.txt` now prints `Koffuster` / `koffuster dir: 0 candidates...` / `summary: 2 requests, 0 results, 0 errors, ...` on stderr with no timestamp/ERROR tag; `--version` stderr still empty |
| 2 | dns error rows | `resolver_down`/`timeout` DoH outcomes were being emitted as stdout result rows via `emitDnsResult`, mixing operational errors into the results stream. They are now only ever visible via `-v` (stderr) and counted in `errorCount`/the summary; nothing is written to stdout for them. `nxdomain` was already stdout-suppressed and is unchanged | dead-resolver run: `stdout=0` lines, `stderr` summary shows `5 errors`; `-v` shows each `error: name -> resolver_down` line |
| 3 | Exit codes | New `exitOnTotalFailure(results, errors)` (`output.kf`) calls `process.exit(1)` when a mode's run produced zero net results and at least one operational error — every request refused/timed out, or (s3/gcs) every candidate came back `inconclusive` with an error. A clean run with zero results and zero errors (nothing found) still exits 0. Wired into all five live modes (dir/dns/vhost/fuzz/store); tftp keeps its own exit 3. Documented via a shared `exitCodesHelp()` block appended to every mode's `--help` | `dns --resolver http://127.0.0.1:1/x` (dead) → exit 1; `dir -u <refused-port>` → exit 1; `dir -u <target> -w empty.txt` (nothing to scan, no error) → exit 0; `dir` against the live lab (results found) → exit 0 |
| 4 | Per-mode help completeness | Each mode's `--help` now lists exactly the options it honors: vhost gained `-H`/`--cookie`/`--auth`/`-a` (and the mode itself was extended to actually fold them into every baseline/candidate request via the shared `buildHeaders`, so the documentation matches real behavior, not just the shared parser's leniency); fuzz gained `--cookie`/`--auth`/`-a` documentation (already honored in code); dns already didn't advertise `-H`/`--cookie`/`--auth`/`-s`/`-b`/`--exclude-length` (the shared parser accepts them but dns ignores them, and now documents that resolver_down/timeout never hit stdout); s3/gcs unchanged (`--endpoint`, `-w`, common options only) | every mode's help printed and diffed against its own code's `cfg.*()` reads; a documented example from every mode's help executed against the lab (see the "Documented examples exercised" list below) — all accepted by the parser, no "unknown option"/"missing value" |
| 5 | tftp message | Both the `--help tftp` text and the runtime stderr message now cite the definitive two-path reason: KOF 0.2.6-beta has no `extern`/FFI mechanism at all (`extern` fails to parse — see impl-notes.md's "TFTP/UDP FFI spike"), and the pure-Java `byte[]`/`getBytes()` path independently crashes with `NoClassDefFoundError` (cookbook P8); TFTP would need KOF 0.5.0-beta+ (documented FFI). Message still one clean line (no timestamp prefix, per fix 1), exit 3 unchanged | `koffuster tftp --server 10.0.0.9 --port 69 -w files.txt` → the updated message, exit 3 |

### Documented examples exercised against the lab (fix 4)

`koffuster dns -d example.com -w subs.txt --resolver <lab>/doh --wildcard-tests 5`,
`--format jsonl -o found.jsonl` variant, `koffuster vhost -u <lab>/vhostroute -w
hosts.txt --domain example.com --append-domain`, `--format jsonl` variant, and a
new `--auth user:pass --cookie "sid=abc" -H "X-Env: test"` variant (proves vhost
now really sends them), `koffuster fuzz -u "<lab>/echo?q=FUZZ" -w payloads.txt -s
200`, the `-X POST --body`, `-H ... --exclude-length 0`, and a new `-H ... --auth
... --cookie "sid=FUZZ"` variant, `koffuster s3 -w buckets.txt` (both the bare
form against the real default AWS-shaped endpoint and `--endpoint <lab>/b/%s
--format jsonl`), `koffuster gcs -w buckets.txt --endpoint <lab>/gcs/%s`, and
`koffuster tftp --server 10.0.0.9 --port 69 -w files.txt`. All accepted by the
parser (no usage errors); the bare `dns`/`s3` examples that hit the real public
default endpoints (`dns.google`, `s3.amazonaws.com`) from this sandboxed network
correctly report the failure honestly (dns: exit 1, resolver unreachable; s3:
real AWS answered normally) rather than crashing either way.
