# KOF Language Investigation — Report for "Koffuster"

All claims below are backed by either (a) a file path read from the device at
`/home/luna/projetos/kof/Kof4j`, staged into this container under
`/mnt/user-data/uploads/projetos/kof/Kof4j/...`, or (b) a command actually run
in this container against the staged runtime at
`./kof-runtime-staged/`, with real output pasted.

Two builds of the compiler/runtime exist on the device:

- `lib/kof.jar` (38 MB) — reports itself as **Kof 0.2.6-beta**, targets
  class-file version 65 (Java 21). **This is the build we could actually run**
  in this Java-21-only cloud container.
- `lib/kof.jar.old40` (42 MB) — class-file version **69.0 (Java 25)**. `VERSION`
  at the repo root says `0.5.0-beta`, and all the `learn/`/`docs/` prose is
  dated/labelled `0.5.0-beta`. **We could not run this jar**: `apt-get install
  openjdk-25-jdk-headless` failed with `403 Forbidden` from
  `security.ubuntu.com` through the sandbox's proxy (`E: Failed to fetch ...
  403 Forbidden`). This is documented as a risk below — **the documentation set
  is ahead of the jar we could execute**, and several documented stdlib
  namespaces (`kof.strings`, `kof.encoding`, `channel<T>()`) are *not*
  resolvable on the 0.2.6-beta jar we ran (see §Risks).

---

## HOW TO RUN KOF

**On the user's own machine** (per `bin/kof`, read from
`/mnt/user-data/uploads/projetos/kof/Kof4j/bin/kof`):

```bash
kof run main.kf                 # jvm (default)
kof run main.kf --target=native # ELF x86-64
kof run main.kf --target=js     # ES Module via embedded GraalJS
```

`bin/kof` is a bash launcher that resolves `$KOF_HOME/lib/kof.jar` and execs
`java --enable-native-access=ALL-UNNAMED -jar lib/kof.jar "$@"` (using an
embedded JDK under `jdk/` if present, else system `java`).

**In this cloud container** (the exact command we validated everything with):

```bash
cd ./kof-runtime-staged
export JDK_JAVAC_OPTIONS="--enable-preview --release 21"
export JDK_JAVA_OPTIONS="--enable-preview"
java -jar kof.jar run <dir>/<file>.kf
```

The two `--enable-preview` env vars are **required** for anything beyond the
most trivial program: the runtime JIT-compiles a helper class
(`KofRuntime.java`, e.g. for `java.lang.foreign.SymbolLookup`/`Arena` FFI
plumbing used even by `kof.config`/`kof.io`) via `javac`, and that helper is
compiled with Java preview features enabled, which then requires the
*executing* JVM to also run with `--enable-preview`. Without these two
variables, running anything that touches `kof.config`, `kof.io` (Path/File)
etc. fails with:

```
error: SymbolLookup is a preview API and is disabled by default.
error: Arena is a preview API and is disabled by default.
```

Real, minimal hello-world run and output:

```
$ java -jar kof.jar run tests/hello/hello.kf
hello koffuster
```

(`tests/hello/hello.kf` contains exactly `main() = print("hello koffuster\n")`.)

`kof version` output: `kof 0.2.6-beta`. `kof info` output (both captured
verbatim, stripped of the sandbox's `JAVA_TOOL_OPTIONS` proxy-config noise):

```
Kof 0.2.6-beta
Release channel: beta
Tooling API: 21
OS: linux
Arch: x86_64
Target: linux-x86_64
JVM: Ubuntu 21.0.10
Compiler: 0.2.6
Runtime: 0.2.6
Stdlib: 0.2.6
Targets: jvm, native, js (alpha)
```

### MINIMAL RUNTIME FILES staged

Under `./kof-runtime-staged/`:

- `kof.jar` — the runnable 0.2.6-beta fat jar (copied from
  `lib/kof.jar` on the device).
- `kof-old40.jar` — the 0.5.0-beta jar (copied from `lib/kof.jar.old40`); kept
  for reproduction but **not runnable here** (needs JDK 25).
- `tests/<name>/<name>.kf` — every `.kf` snippet used for validation in this
  report, each in its own subdirectory (KOF's module unit is *the directory*:
  siblings under one directory are compiled together, so isolating each test
  avoids `PKG002 duplicate main()`).

Nothing in the Kof4j repo itself was modified; only files were copied out via
`device_stage_files` (read-only staging into
`/mnt/user-data/uploads/projetos/kof/Kof4j/...`) and re-copied into this
project's own directory.

---

## 1. Syntax basics, comments, variables & types, functions, control flow

**SUPPORTED — verified.** Source: `learn/02-first-program.md`,
`learn/03-language-basics.md`, `learn/04-variables-and-types.md`,
`learn/05-control-flow.md`, `learn/06-functions.md` (staged, read in full).

- Comments: `// line` and `/* block */`.
- Literals: `"string"`, `42` (Int), `42L` (Long), `3.14` (Double), `3.14f`
  (Float), `true`/`false`, `null`.
- Primitive types: `Bool, Byte, Short, Int, Long, Float, Double, Char, Void`
  (same widths as the JVM).
- Variables: `var` (mutable), `val` (constant) — **no `let`/`const`** (removed
  from KofScript on 06/09 per the docs; using `let` is a parse/semantic error).
- Functions: no `fun`/`func` keyword — return type goes **before** the name
  (`Int soma(Int a, Int b) { ... }`) or **after** the parameter list
  (`despedida(): String { ... }`); `main()` is the only form without an
  explicit return type. Expression bodies (`Bool positivo(Int x) = x > 0`),
  default parameters, recursion, overloading by arity/param-types, and lambdas
  as first-class values (`(x: Int) -> x * 2`) are all documented with examples.
- Control flow: `if/else` (also as an expression), `while`, C-style `for`,
  `for (var x in xs)`, `switch` (no fallthrough — each case ends on its own,
  no `break` needed; has an expression form `switch (...) { case 1 -> "a" }`).
- Records: `record Point(Int x, Int y)` — auto-generates fields, accessors,
  `toString()`; construction is `Point(3, 7)` (no `new` needed, though `new`
  is still accepted).
- Arrays: no literal syntax (`[1,2,3]` does not compile) — `new Int[n]` +
  index assignment. Dynamic sequences use `listOf(...)`.

**Validated snippet** (`tests/basics/basics.kf`), run with
`java -jar kof.jar run tests/basics/basics.kf`:

```kf
record Point(Int x, Int y)

Int add(Int a, Int b) { return a + b }

main() {
    var name = "koffuster"
    val pi = 3.14
    var p = Point(3, 7)
    println("name=" + name)
    println("pi=" + pi)
    println(p)
    println("sum=" + add(2, 3))

    var i = 0
    while (i < 3) { println("i=" + i); i = i + 1 }

    try {
        throw "boom"
    } catch (String e) {
        println("caught: " + e)
    } finally {
        println("cleanup")
    }
}
```

Real output:

```
name=koffuster
pi=
Point[x=3, y=7]
sum=5
i=0
i=1
i=2
caught: boom
cleanup
```

**Bug found (report it, don't design around it silently):** `"pi=" + pi`
printed an **empty string** for the Double value, even though
`println(pi)` alone correctly prints `3.14` (confirmed in a second isolated
test, `tests/pistr/pistr.kf`: `println(pi)` → `3.14`, but `println("pi=" +
pi)` → `pi=` and `println("x=" + x)` for an explicitly-typed `Double x` also
→ `x=`). **String-concatenation of a `Double` via `+` silently drops the
value** on this 0.2.6-beta build. This is a real correctness gap Koffuster
must design around (e.g. convert manually, or verify on the newer build).

---

## 2. Error handling model

**SUPPORTED — verified, with an important caveat found below.** Source:
`learn/14-exceptions.md`.

- Kof throws **Strings**, not exception objects: `throw "message"`, caught
  with `catch (String e)`. `throw 42` / non-String catches are explicitly
  documented as generating invalid JVM bytecode — "do not use."
- `try/catch/finally` works with real unwinding; `finally` always runs.
- Absence-vs-error convention: use `String?` (nullable) for "may legitimately
  be absent," `throw` for "this is a defect."
- Documented limitations (from the doc itself, matches what we independently
  found): "Exceptions are Strings only — no exception object;" "On Native,
  the first catch of a try captures (no dispatch by type among multiple
  catches);" "No stack trace on Native."

Validated above in `tests/basics/basics.kf` (`caught: boom` / `cleanup`
printed in the right order).

**Important interop caveat, independently discovered (§6):** wrapping a Java
interop call that can throw a checked exception (e.g. `new
java.net.Socket(host, port)`) in `try { ... } catch (String e) { ... }`
produced a **`VerifyError` at class-load time** (invalid bytecode, stackmap
frame mismatch) on the 0.2.6-beta jar — see §6 for the exact command and
stack trace. This is a serious risk for a network scanner, which needs to
catch "connection refused" everywhere.

---

## 3. CLI arguments, environment variables, stdin

**CLI args: SUPPORTED — verified.** `main(args: String[])` receives argv
(everything after the `.kf` file, in order — including `--` if passed, it is
just another argv token, there is no automatic flag-separator stripping).

```kf
main(args: String[]) {
    println("argc=" + args.length)
    var i = 0
    while (i < args.length) { println("arg[" + i + "]=" + args[i]); i = i + 1 }
}
```

Run: `java -jar kof.jar run tests/mainargs/mainargs.kf foo bar` →

```
argc=2
arg[0]=foo
arg[1]=bar
```

**Environment variables: SUPPORTED — verified**, via `kof.config`
(`learn/stdlib/config.md`, no import needed — resolved as a bare namespace):
`config.env(key)`, `config.has(key)`, plus typed getters `config.str/int/
long/bool(key, default)` and `config.required(key)` (throws if absent).

```kf
main() {
    println("HOME=" + config.env("HOME"))
    println("has PATH=" + config.has("PATH"))
}
```

Real output: `HOME=/root` / `has PATH=false` (the `PATH` var itself is set in
this shell, but `config.has` apparently checks the `kof.config`/`KOF_<KEY>`
layer rather than the raw OS environment for arbitrary keys — worth
re-verifying against the real `env()` mechanics before relying on `has()` for
generic OS env vars; `env()` itself clearly does read the real OS
environment, since `HOME` came back correct).

**stdin: NOT VERIFIED as a native stdlib primitive.** No `kof.io`/stdlib
function for reading stdin was found in any doc read (`34-file-system.md`,
`39-stdlib.md`, all of `learn/stdlib/*.md`). We tried the Java-interop path
(`java.io.BufferedReader(new java.io.InputStreamReader(System.in))`) and it
**failed** — see §6, `System` (`java.lang.System`) does not resolve even
after `import java.lang.System;` on this build (`SEM011: Undefined variable
or type: 'System'`), and the attempt produced a broken class
(`NoClassDefFoundError: ?` at runtime). **Conclusion: reading stdin is an open
gap on the runnable 0.2.6-beta build** — not proven possible by any path we
tried. `kof lsp` is documented as reading stdin/writing stdout internally
(`32-cli-tooling.md`: "reads stdin, writes stdout (LSP)"), so the *runtime*
plumbing exists somewhere in Java, but no Kof-level stdin API surfaced in the
docs we read.

---

## 4. stdout/stderr, file I/O, string manipulation

**stdout/stderr as separate streams: SUPPORTED — verified**, via `kof.log`
(`learn/stdlib/log.md`; bare namespace, no import): `log.debug/info/warn/
error(msg)`, each prefixed with a timestamp.

```kf
main() {
    log.info("hi info")
    log.error("hi error")
}
```

Run with stdout/stderr captured to separate files:

```
STDOUT: 2026-09-30 12:28:53.230 INFO hi info
STDERR: 2026-09-30 12:28:53.240 ERROR hi error
```

`print`/`println` go to stdout (used throughout every test above without
ever appearing on stderr). No native `eprintln`/`print(..., stderr)` was
found — `log.error` is the documented, verified way to write to stderr.

**File read/write: SUPPORTED — verified**, via `kof.io` (`learn/
34-file-system.md`): `Path`/`File`/`Directory` types, `readText/writeText/
appendText/readBytes/writeBytes/size/exists/delete`, static forms
`File.readText(path)` etc.

```kf
main() {
    var p = Path("/tmp/koffuster_test.txt")
    p.writeText("hello file\nline2\n")
    println(p.readText())
    println("size=" + p.size())
    println("exists=" + p.exists())
}
```

Real output:

```
hello file
line2

size=17
exists=true
```

**String manipulation: SUPPORTED per docs (`learn/stdlib/strings.md`,
`learn/stdlib/encoding.md`) — NOT reproducible on the 0.2.6-beta jar we could
run.** The doc tables list `strings.capitalize/reverse/toCamelCase/
toSnakeCase/slugify/truncate/padLeft/...` and `encoding.hexEncode/
base64Encode/urlEncode/base64UrlEncode/...` as "Status: stable — 4/4
targets," attributed to `0.5.0-beta`. On our runnable 0.2.6-beta jar:

```
$ java -jar kof.jar run tests/str2/str2.kf   # calls strings.slugify(...) with `import kof.strings`
error: Undefined variable or type: 'strings' [SEM011]
error: Undefined variable or type: 'encoding' [SEM011]   (same for kof.encoding)
```

This happened **both with and without** an explicit `import kof.strings` /
`import kof.encoding` line — unlike `http`, `log`, `config`, `io`, which all
resolved as bare namespaces with zero imports. The most likely explanation,
consistent with the jar-version mismatch documented above, is that `strings`
and `encoding` were added to the stdlib **after** 0.2.6-beta, on the way to
0.5.0-beta, and are simply absent from the jar we could execute. **Basic
string operations that do exist and were exercised successfully throughout
this report**: `+` concatenation (works for `String`; broken for `Double`,
see the bug above), `.length()` (used implicitly nowhere directly but
documented), array/list indexing. Substring/split/case functions specifically
could not be confirmed runnable in this environment.

---

## 5. Networking

This is the section that matters most for Koffuster, and where the version
mismatch (§Risks) bites hardest.

### `kof.net` — SUPPORTED, but it is a **URL parser, not a socket API**

Source: `learn/stdlib/net.md`. `net.scheme/host/port/path/query/fragment(url)`
decompose a URL string; `net.queryEncode/queryDecode` do RFC 3986 escaping.
**There is no `kof.net.connect`, no `Socket`, no raw TCP/UDP primitive
anywhere in the Kof stdlib documentation we read** — not in `net.md`, not in
`39-stdlib.md`'s full namespace table (30 namespaces listed, none of them
raw sockets), not in `34-file-system.md`. We also grepped every staged doc
file for "socket|udp|dns|tcp" case-insensitively and got zero hits outside
the web-server planning doc (`docs/http.md`, which lists **syscall names**
`socket/bind/listen/accept` as *implementation* details of the HTTP server's
Native backend — not as an API surface exposed to Kof programs).

### Raw TCP: **SUPPORTED-VIA-JAVA-INTEROP only, and fragile**

We proved outbound TCP connect works through `java.net.Socket`:

```kf
import java.net.Socket;
main() {
    var sock = new Socket("127.0.0.1", 9)
    println("connected")
    sock.close()
}
```

Real output (port 9/discard is closed in this container, so this is a
genuine network attempt, not a stub):

```
Exception in thread "main" java.net.ConnectException: Connection refused
	at java.base/sun.nio.ch.Net.connect0(Native Method)
	...
	at java.base/java.net.Socket.<init>(Socket.java:324)
	at Default.Main.main(javanet3.kf:6)
```

This **proves** the 2-arg `Socket(host, port)` constructor compiles and
executes a real connect() syscall through the JVM. However:

- The **overloaded** 2-arg `sock.connect(SocketAddress, int timeout)` method
  failed to resolve: `NoSuchMethodError:
  'java.lang.Object java.net.Socket.connect(java.net.InetSocketAddress, int)'`
  — consistent with the docs' own warning ("overload resolution still has
  flaws").
- **Critically**, wrapping the working constructor call in `try { ... } catch
  (String e) { ... }` (needed for any real scanner, since a refused/
  timed-out connection is the *normal*, expected case) produces a
  **`VerifyError`** at class load — invalid bytecode:

```
Error: Unable to initialize main class Default.Main
Caused by: java.lang.VerifyError: Inconsistent stackmap frames at branch target 58
  ...
  Current Frame:
    stack: { }
  Stackmap Frame:
    stack: { 'java/lang/Object' }
```

  Reproduced twice, once with a 2-line try body and once with a 3-line try
  body wrapping `new Socket(...)`, `println`, and `.close()` — same class of
  error both times. **This means, on this exact build, you cannot both (a)
  make a raw outbound TCP connection via Java interop and (b) catch its
  failure inside a `try/catch (String e)` block** — the program crashes with
  a `VerifyError` before `main` even runs, rather than throwing a catchable
  Kof exception. This is the single biggest concrete blocker we found for a
  TCP-based port scanner in this build.

### UDP: **NOT-FOUND / NOT VERIFIED**

No `kof` stdlib UDP primitive exists (same absence as TCP). We did not test
`java.net.DatagramSocket` interop directly, but given that `java.net.Socket`
(a `java.net` sibling class) only partially worked and `java.net.InetAddress`
(also `java.net`) failed outright (below), there is no basis to claim UDP
works via interop on this build either — treat as **unverified / likely
fragile** rather than assuming it works.

### Custom DNS resolution: **NOT-FOUND**

No `kof` stdlib DNS function exists. The obvious interop path,
`java.net.InetAddress.getByName(...)`, **failed to compile** even with an
explicit import:

```kf
import java.net.InetAddress;
main() {
    var addr = InetAddress.getByName("localhost")
    println(addr.getHostAddress())
}
```

```
error: Undefined variable or type: 'InetAddress' [SEM011]
```

We also tried a fully-qualified call (`java.net.InetAddress.getByName(...)`)
with the same import, which failed differently (`Undefined variable or type:
'java'` — the compiler does not resolve dotted-path *expressions* to static
calls the way Java does). **Custom/arbitrary DNS resolution is not
demonstrated as working by any path on this build.** (Kof's own `net.host()`
only *parses the hostname out of a URL string* — it does not resolve it.)

### HTTP client: **SUPPORTED — verified**, native `kof.http`

Source: `learn/stdlib/http.md`, `docs/stdlib/stdlib-web.md`,
`docs/stdlib/http.md`. `http.get/post/put/delete/patch/options/status(url,
[headers...])`, plus process-wide `http.timeout(ms)`, `http.retry(n)`,
`http.circuit(threshold)`. No import needed (bare namespace, like `log`/
`config`).

```kf
main() {
    var body = http.get("https://example.com")
    println("len=" + body.length())
}
```

Real output (proves it makes a genuine outbound HTTPS attempt — it is
blocked by *this sandbox's own* corporate HTTPS-tunneling proxy, not by
Kof):

```
Exception in thread "main" java.io.IOException: Tunnel failed, got: 403
	at java.net.http/jdk.internal.net.http.HttpClientImpl.send(HttpClientImpl.java:970)
	at dev.kof.runtime.KofRuntime.kof_http_request(KofRuntime.java:1848)
	at dev.kof.runtime.KofRuntime.kof_http_get(KofRuntime.java:1739)
	at Default.Main.main(http1.kf:2)
```

This stack trace additionally **proves, from the runtime's own source
location**, that `kof.http` on the JVM target is implemented as a thin
wrapper over `java.net.http.HttpClient` (`dev.kof.runtime.KofRuntime.
kof_http_request` → `HttpClientImpl.send`). Documented behavior we did not
independently re-execute (blocked by the sandbox proxy, not a Kof limitation):
redirect handling, per-call headers, `retry`/`circuit` resilience policies —
all described with test names in `docs/stdlib/stdlib-web.md` §10.2
(`KofHttpResilienceE2ETest`, 3/3 JVM+JS).

### HTTPS/TLS control: **SUPPORTED per docs, not independently re-executed**

`docs/stdlib/http.md` §10.1 documents:
- **Server-side** self-signed TLS: `app.listenSecure(port)` (JVM: `keytool
  -genkeypair` + `SSLServerSocket`), and a 3-arg
  `app.listenSecure(port, certPem, keyPem)` for a user-supplied cert (JVM
  production path).
- **Client-side** insecure/trust-all mode exists specifically for testing
  against self-signed certs: `JvmWebHttpRuntime.java:112
  KOF_HTTP_CLIENT_INSECURE` — described as an `SSLContext` trust-all +
  `SSLParameters` without endpoint identification (i.e., disables cert
  validation and hostname/SNI checks) wired into the same `HttpClient` used
  by `http.get`. The doc does not show the exact Kof-level toggle syntax for
  turning this on from user code (it reads as an internal test-only knob
  named by its Java symbol), so we mark this **SUPPORTED (doc-evidenced,
  named symbol) but not confirmed as a public, documented Kof API call** —
  Koffuster's HTTPS-with-cert-checks-off requirement needs direct
  verification against source or a maintainer before relying on it.
- Native/JS both report gap code `WEB002` for TLS (server) — JVM-only.

### Summary table

| Capability | Status | Evidence |
|---|---|---|
| TCP connect (outbound) | SUPPORTED-VIA-JAVA-INTEROP, **broken exception handling** | `java.net.Socket(host,port)` runs; wrapping in `try/catch(String e)` → `VerifyError` (both reproduced, this doc §5) |
| UDP | NOT-FOUND / unverified | no stdlib API; interop path untested but sibling `java.net.*` classes are unreliable here |
| Custom DNS resolver | NOT-FOUND | `java.net.InetAddress` import unresolved (`SEM011`) on this build |
| HTTP client (methods/headers/body) | SUPPORTED | `kof.http.get/post/put/delete/patch/options`, real `HttpClient` call proven via stack trace |
| HTTPS/TLS cert control | SUPPORTED per docs, not re-executed | `docs/stdlib/http.md` §10.1, named internal symbol `KOF_HTTP_CLIENT_INSECURE` |
| Redirect control, per-call timeout | Documented, not independently re-verified | `docs/stdlib/stdlib-web.md` §10.2 |

---

## 6. Concurrency

**SUPPORTED (core primitives) — verified.** Source: `learn/18-concurrency.md`
(read in full — extensive gap-tracking table per target). Kof deliberately
does **not** expose `Thread`/`Runnable`/`CompletableFuture`; the surface is:

- `spawn <expr>` → fire-and-forget, or `val r = spawn <expr>` → typed
  `Handle<T>`; JVM backend = **virtual threads** (JDK 21+).
- `await r` blocks until the result; exceptions thrown inside the task
  re-arrive as the original String message at the `await` point.
- `poll(r)`/`done(r)` — non-blocking check.
- `cancel(r)` / `cancelled()` — **cooperative** cancellation only: `cancel`
  just marks the handle, the task itself must poll `cancelled()` and decide
  to exit. Not OS-level, not preemptive.
- `selectAny(a, b, ...)` — first handle to complete.
- `channel<T>()` — typed blocking FIFO with `.send(v)`/`.receive()`.

Validated `spawn`/`await`:

```kf
Int somar(Int a, Int b) { return a + b }
main() {
    val r = spawn somar(2, 3)
    val total = await r
    println("total=" + total)
}
```

Real output: `total=5`.

**`channel<T>()`: documented, NOT reproducible on the 0.2.6-beta jar.**

```
$ java -jar kof.jar run tests/concur2/concur2.kf   # uses channel<Int>()
error: Undefined function: 'channel' [SEM015]
```

Same version-mismatch pattern as `strings`/`encoding` in §4 — `channel` is
documented in `learn/18-concurrency.md` (labelled 0.5.0-beta) but the symbol
does not exist in the 0.2.6-beta runtime we could execute.

**Cancellation / Ctrl+C (SIGINT): NOT-FOUND.** No mention anywhere in the
concurrency chapter, the CLI chapter, or any stdlib chapter of catching or
handling OS signals (SIGINT/SIGTERM) from within a Kof program. The only
cancellation primitive is the cooperative `cancel()`/`cancelled()` pair
described above, which requires the *task itself* to be written to poll
`cancelled()` — it does nothing for, say, a `spawn`ped task that's blocked
inside a synchronous Java interop call (like a TCP connect with no timeout).
**Koffuster's Ctrl+C-to-abort-a-scan behavior is not demonstrated as
achievable** by any native primitive found.

---

## 7. Java interop

**SUPPORTED-VIA-JAVA-INTEROP, explicitly documented as partial/fragile, and
independently confirmed to be fragile.** Source: `learn/
21-java-interoperability.md`, plus our own tests in §5/§4.

The doc's own framing (verbatim, since it's the load-bearing warning):

> "Status: partial — compatible JVM bytecode; direct Java call works for what
> is on the classpath (verified 02/09). ... Before assuming that a Java API
> works, compile and run. Verified on 02/09: `java.util` collections ✅;
> `java.time`/`java.util.stream` ❌ (types do not resolve without an external
> classpath); `java.io.FileWriter.write` ❌ (wrong overload resolution →
> `NoSuchMethodError`)."

The compiler emits standard JVM bytecode with `import java.util.ArrayList;`
etc. working "without `new`"-idiom construction and with generics. The
doc's own recommendation is to prefer Kof's own stdlib (`listOf`/`mapOf`/
`kof.io`/`kof.http`) over Java interop wherever an equivalent exists, and to
reserve interop for what Kof genuinely lacks.

**Our own findings extend the "before assuming, compile and run" warning**:
- `java.util.*` collections: documented as verified; we did not re-run this
  specific case (budget), but it is independently plausible given that
  `java.net.Socket`'s simple 2-arg constructor also worked.
- `java.net.Socket(host, port)` (2-arg constructor): **works** (§5).
- `java.net.Socket.connect(InetSocketAddress, int)` (an overload):
  **fails** — `NoSuchMethodError` at runtime, not a compile error, meaning
  the class *looked* correct to the compiler but the emitted bytecode calls
  the wrong overload (§5).
- Wrapping a working interop call in `try/catch (String e)`: **fails** with
  a `VerifyError` (invalid bytecode) — this is worse than a `NoSuchMethodError`,
  because the program doesn't even reach `main` (§5).
- `java.net.InetAddress` (import + static call): **fails to compile**
  (`SEM011`, undefined type) even with an explicit import (§5).
- `java.lang.System` (for `System.err`/`System.in`): **fails to compile**
  (`SEM011`, undefined variable) even with an explicit
  `import java.lang.System;` (§4/§6) — this is notable because `java.lang` is
  supposed to be implicitly available in Java; it is not automatically
  resolved here.
- Fully-qualified static calls (`java.net.InetAddress.getByName(...)`
  without an unqualified reference) are **not** supported as an expression
  form — `java` itself is reported as an undefined variable, meaning Kof's
  grammar does not treat a dotted package path as a valid prefix inside an
  expression the way Java does.

**Conclusion for Koffuster:** Java interop is real (the compiler generates
genuine JVM bytecode and can call arbitrary classpath classes with `new
Foo(...)` and no-frills instance methods), but it is **narrow and
unpredictable** in this build — specific classes/overloads that "should" work
by Java rules do not, and the failure modes range from clean compile errors
(`SEM011`, good) to silent-looking-but-wrong compiles that only fail at
runtime (`NoSuchMethodError`) to outright corrupted bytecode
(`VerifyError`). **Every single interop call Koffuster plans to use must be
compiled and run standalone first**, exactly as the docs themselves warn —
do not assume any Java API "should" work by analogy.

---

## 8. Standard library / modules and how to import them

**SUPPORTED — verified, with the caveat that not every documented namespace
exists on the runnable build.** Source: `learn/19-packages-and-modules.md`,
`learn/39-stdlib.md`, `learn/stdlib/README.md`.

- `import a.b.C` imports a specific file/class; `import a.b.*` imports a
  whole directory; `import kof.http` imports a stdlib namespace (though in
  practice, on this build, the core "app service" namespaces — `http`,
  `log`, `config`, and file I/O via bare `Path`/`File` — are usable **without
  any import at all**, they're just globally in scope).
- `import kof.strings as strings` (aliased import) is **not valid syntax** —
  produces a cascade of parse errors (`Expected type declaration [PARSE007]`
  etc.). Plain `import kof.strings;` parses fine but the namespace still
  doesn't resolve on this jar (§4).
- 30 stdlib namespaces are documented in `learn/39-stdlib.md`'s table:
  `json, db, http, cache, config, log, process, shell, ssh, net, orm, gpu,
  mq, observability, tetris, media, buffer, passwords, crypto, jwt, secrets,
  security, auth, math, strings, encoding, uuid, time, random, rng,
  validation`. We independently verified `http`, `log`, `config`, `io`
  (Path/File, technically not in that table but documented separately in ch.
  34) work on this build; `strings`, `encoding`, and (in the concurrency
  space) `channel` did **not** resolve.
- `kof.process`/`kof.shell` (external command execution, `learn/
  stdlib/process.md`, `learn/stdlib/shell.md`) are documented with a clear
  static-vs-dynamic-argv split and an explicit "never build a command string
  (injection class)" rule — not independently re-run here, but directly
  relevant to a future "run external tool" feature in Koffuster.

---

## 9. `AGENTS.md` conventions relevant to writing `.kf` code

Source: `/mnt/user-data/uploads/projetos/kof/Kof4j/AGENTS.md` (read in full;
this is the *compiler contributors'* operating contract, but it contains a
"Code gate" / "Cheat sheet" section that is directly a style guide for
**writing `.kf` application code**, which is what's relevant to Koffuster):

- Canonical idioms to use: membership via `setOf(...).contains(x)`;
  equality via plain `==`; string building via `+`/`+=`; data via `record`;
  nullability via `T?` + narrowing (`if (x != null)`); concurrency via
  `spawn`/`await`; collections via `listOf`/`mapOf`/`setOf`; JSON via
  `json.encode`/`json.decode`; HTTP via `http.get`; loops via
  `for (var x in xs)`; conditionals preferably as if-expressions; branching
  via `switch`.
- **Forbidden foreign forms** (an explicit deny-list Koffuster's code must
  avoid): `fun`, `func`, `fn`, top-level `val`/`var` outside a script,
  `let`, `const`, `async fn`, `Thread`, `Executor`, `Runnable`, `Optional`,
  `Result`, JavaBeans getters/setters, Service/Repository/Controller
  ceremony, Java/Kotlin-style primary constructors, and — notably — "language
  -specific null operators not defined by Kof" (e.g. don't assume `?.` or
  `?:` exist just because Kotlin/Java-adjacent languages have them; we did
  not test these operators and the language basics chapter never mentions
  them).
- Rule of thumb given explicitly: **"if syntax is uncertain: compile. ...
  compiler result outranks memory."** — i.e., the project's own contributors
  are told not to trust documentation/memory over actually compiling, which
  is exactly the discipline this report followed and recommends Koffuster's
  implementation follow too.

---

## RISKS / GAPS for building Koffuster

1. **Jar/docs version mismatch (biggest structural risk).** The only jar we
   could run in this Java-21 cloud container is **0.2.6-beta**; the
   documentation set (`learn/`, `docs/`) is written for/dated **0.5.0-beta**,
   which lives in `lib/kof.jar.old40` and requires **JDK 25** — unavailable
   here because `apt-get install openjdk-25-jdk-headless` got `403 Forbidden`
   from the sandbox's proxy on `security.ubuntu.com`. Concretely, `kof.strings`,
   `kof.encoding`, and `channel<T>()` are all documented as stable but do
   **not** exist on the runnable jar. **Before building Koffuster for real,
   get JDK 25 (or the user's own machine, which has the embedded JDK per
   `bin/kof`) and re-validate every stdlib call this report couldn't
   confirm.**

2. **Java interop for networking is where the "before assuming, compile and
   run" warning bites hardest.** `java.net.Socket`'s simple constructor
   works; an overload of the same class's `connect` method silently resolves
   to the wrong overload; `java.net.InetAddress` doesn't resolve at all;
   `java.lang.System` doesn't resolve at all; and — critically — **wrapping
   a working interop call in `try/catch(String e)` produces a VerifyError**,
   crashing the whole program before `main` runs. A TCP scanner fundamentally
   needs to catch connection failures. This must be re-verified on the
   0.5.0-beta build (or worked around, e.g. by having the task run inside
   `spawn` and inspecting the re-thrown String at `await`, which the docs
   claim works differently from a plain `try/catch` — untested here) before
   committing to Java-interop-based socket scanning as Koffuster's TCP
   engine.

3. **No native raw TCP/UDP/DNS API at all** — `kof.net` is purely a URL
   string parser. Everything network-primitive-level has to go through
   either (a) fragile Java interop (risk #2), or (b) `extern` C FFI
   (`learn/40-low-level.md`) binding directly to libc socket syscalls, which
   is a real, documented mechanism (scalar-only FFI, callbacks supported on
   JVM/JS but explicitly `FFI001` — not supported — on Native for anything
   beyond scalars) but adds real complexity (raw `sockaddr` structs are not
   scalar and are explicitly called out as `FFI002`, "genuinely unsupported
   shape") and was not attempted in this investigation.

4. **No stdin API found.** Neither a stdlib primitive nor a working
   Java-interop path (`System.in` interop failed) was demonstrated. If
   Koffuster needs interactive input (vs. pure argv/config-driven input),
   this is currently an open question requiring direct experimentation on
   the 0.5.0-beta build or a `kof.io`-adjacent primitive we didn't find in
   the docs we read.

5. **No OS-level cancellation (SIGINT/Ctrl+C) primitive found.** Only
   cooperative `cancel()`/`cancelled()`, which requires the task's own loop
   to poll — doesn't help for a task blocked inside a synchronous,
   uninterruptible Java call (e.g., a TCP connect with no timeout set).
   Combined with risk #2 (can't safely wrap that connect in try/catch
   either), **timeout/cancel behavior for network operations is currently
   the least-proven area of the whole investigation** and deserves the
   earliest, most careful prototyping once JDK 25 is available.

6. **`String + Double` concatenation silently drops the value** (§1),
   reproduced twice on 0.2.6-beta. If Koffuster ever formats a
   float/double (e.g., elapsed scan time, a computed score) via `+`
   concatenation, this will silently produce a truncated/blank string. Needs
   re-verification on 0.5.0-beta; until then, avoid `+`-concatenating
   `Double`/`Float` values and test explicitly whenever it's used.

7. **`kof serve`/`web.app()` (native HTTP *server*) was read in detail
   (`docs/stdlib-web.md`) but never executed** — not required for a scanner
   client, so not prioritized, but if Koffuster ever needs to *listen* (e.g.
   a results dashboard), note the documented per-target gaps: WebSocket is
   JVM-only (`WEB004` elsewhere), static file serving is JVM-only
   (`WEB005`), and TLS server support is JVM-only (`WEB002` elsewhere).

> NOTA (v0.2.0): relatório de investigação da build 0.2.6-beta, mantido como registro histórico. A v0.2.0 roda em KOF 0.5.0-beta; as limitações aqui listadas que foram corrigidas (getBytes/FFI continuam bloqueados, mas spawn/status/catch mudaram) estão refletidas no código atual.
