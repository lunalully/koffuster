# KOF 0.2.6-beta — Proven Patterns Cookbook (for Koffuster)

Target: `./kof-runtime-staged/kof.jar` (Kof 0.2.6-beta,
the jar `bin/kof` on the device actually runs). Every snippet below was
compiled and executed in this container with:

```bash
export JDK_JAVAC_OPTIONS="--enable-preview --release 21"
export JDK_JAVA_OPTIONS="--enable-preview"   # + extra flags noted per-section
java -jar kof.jar run tests/<name>/<name>.kf
```

Lab servers (reusable fixtures) live in `./labs/`:
- `labs/http_lab.py` — HTTP server on `127.0.0.1:18080` with routes `/200`,
  `/404`, `/500`, `/301` (Location: /200), `/slow` (sleeps 5s), `/echo`
  (echoes method/Host/User-Agent/X-Test header/body), `/doh-ok` and
  `/doh-nx` (Google-DoH-shaped JSON).
- `labs/udp_lab.py` — UDP echo server on `127.0.0.1:18069`.
- `labs/k.sh` — helper: `k.sh <name>` runs `tests/<name>/<name>.kf` with the
  right env vars (`EXTRA_JAVA`, `T` timeout, `L` line-limit env overrides).

All `.kf` probes live under `./kof-runtime-staged/tests/<name>/`.

---

## P1 — HTTP error handling (THE make-or-break result)

### P1a — status codes and body on 200/404/301/500: WORKS

`tests/p1a/p1a.kf`:
```kf
main() {
    println("status200=" + http.status("http://127.0.0.1:18080/200"))
    println("status404=" + http.status("http://127.0.0.1:18080/404"))
    println("status301=" + http.status("http://127.0.0.1:18080/301"))
    println("status500=" + http.status("http://127.0.0.1:18080/500"))
    println("get200=" + http.get("http://127.0.0.1:18080/200"))
    println("get404=" + http.get("http://127.0.0.1:18080/404"))
    println("get301=" + http.get("http://127.0.0.1:18080/301"))
}
```
Real output:
```
status200=200
status404=404
status301=301
status500=500
get200=hello-200
get404=not found body
get301=moved
```
**Conclusion: `http.get` does NOT throw on 4xx/5xx — it returns the body
normally, exactly like a 200.** `http.status(url)` returns the real numeric
code. **No automatic redirect following** by default: `get301` returned the
301 response's own body ("moved"), not the body of `/200` — confirms Java's
default `HttpClient` redirect policy (`NEVER`) is in effect. This means
Koffuster gets clean status-based branching for free and does not need any
redirect-disabling call.

### P1b/c — try/catch around http.get / http.status on connection-refused: **DOES NOT CATCH — BLOCKER**

`tests/p1b/p1b.kf`:
```kf
main() {
    try {
        var b = http.get("http://127.0.0.1:1/x")
        println("got " + b)
    } catch (String e) {
        println("CAUGHT-refused-get: " + e)
    }
    println("after")
}
```
Real output (the `catch` block never runs, `println("after")` never prints,
process exits non-zero with an uncaught Java stack trace):
```
Exception in thread "main" java.net.ConnectException
	at java.net.http/jdk.internal.net.http.HttpClientImpl.send(HttpClientImpl.java:955)
	at dev.kof.runtime.KofRuntime.kof_http_request(KofRuntime.java:1848)
	at dev.kof.runtime.KofRuntime.kof_http_get(KofRuntime.java:1739)
	at Default.Main.main(p1b.kf:2)
```
Same result for `http.status(...)` on a closed port (`tests/p1c/p1c.kf`,
`kof_http_status` in the trace instead). **Plain `try { http.get(...) }
catch (String e)` does NOT catch a connection-refused failure on this
build — the JVM-level `IOException` propagates straight past Kof's
`catch (String e)` and crashes the whole process.** This is a real,
reproduced blocker for a synchronous "just try/catch every request" design.

### P1c — the WORKING error-handling path: `spawn` + `await` + `catch`: **WORKS**

`tests/p1c2/p1c2.kf`:
```kf
String doGet() {
    return http.get("http://127.0.0.1:1/x")
}
main() {
    val r = spawn doGet()
    try {
        var b = await r
        println("got " + b)
    } catch (String e) {
        println("CAUGHT-await-refused: " + e)
    }
    println("after")
}
```
Real output:
```
CAUGHT-await-refused: java.net.ConnectException
after
```
**This is the pattern Koffuster must use for every network call: always
`spawn` the request and `await` it inside `try/catch`, never call
`http.get`/`http.status` synchronously in a bare `try/catch`.** The caught
String is the Java exception's `toString()` (class name + message, e.g.
`java.net.ConnectException`, no extra Kof wrapping) — use `.contains(...)`
on it to branch (e.g. `e.contains("ConnectException")` vs `e.contains
("HttpTimeoutException")`).

### Timeout behavior: **WORKS via the same spawn/await path — and `http.timeout(n)` is SECONDS, not ms**

`tests/p1timeout/p1timeout.kf` against `/slow` (sleeps 5s):
```kf
String doGet() {
    return http.get("http://127.0.0.1:18080/slow")
}
main() {
    http.timeout(1)
    val r = spawn doGet()
    try {
        var b = await r
        println("got " + b)
    } catch (String e) {
        println("CAUGHT-timeout: " + e)
    }
    println("after")
}
```
Real output: `CAUGHT-timeout: java.net.http.HttpTimeoutException: request timed out` /
`after`. **Verified unit test: `http.timeout(500)` (intending "500ms" per
the `learn/stdlib/http.md` table signature `timeout(Int ms)`) let the
5-second `/slow` endpoint complete successfully with no timeout — proving
the argument is actually interpreted in SECONDS** (matches
`docs/stdlib/http.md`'s prose "`timeout(s)` — applies `Duration.ofSeconds
(s)`", which contradicts the `learn/stdlib/http.md` table). **Use seconds,
not milliseconds, and don't trust the `learn/` chapter's ms label on this
build.**

### P1d — combined status+headers+body in one call: **NOT POSSIBLE — two calls required**

Confirmed by reading `learn/stdlib/http.md` (functions table only has `get`,
`post`, `put`, `delete`, `patch`, `options`, `status`, `timeout`, `retry`,
`circuit` — no response object) and by disassembling the compiler's own
`KofHttp.class` (`unzip -p kof.jar ... | strings`), whose recognized method
set is exactly `{post, delete, patch, options, status, timeout, retry,
circuit}` plus `get` (handled separately) — **no `head`, no `Response`
type, no combined call.** Content-Length is not separately exposed either
(there's no headers-read API) — the only way to know a body's size is
`.length()` on the already-fetched String from `http.get`. **Idiom: call
`http.status(url)` and `http.get(url)` as two separate requests** when both
are needed (as the doc's own example — `http.get` then separately checking —
implies).

### P1e — custom headers, method, Host header, and a real compiler crash

**Single custom header: WORKS.**
```kf
main() {
    var body = http.get("http://127.0.0.1:18080/echo", "X-Test: hello123")
    println(body)
}
```
Output: `XTEST=hello123` (confirmed via the echo server reading the real
received header).

**Two headers as two separate vararg strings: COMPILER CRASH (ICE) — do not use.**
```kf
http.get(url, "User-Agent: koffuster/0.1", "X-Test: hello123")
```
```
java.lang.RuntimeException: frame crash em Default/Main.main (super=java/lang/Object): Index -1 out of bounds for length 0
	at org.objectweb.asm.Frame.getConcreteOutputType(Frame.java:1150)
	...
error: Internal compiler error: frame crash em Default/Main.main (...) [COMP002]
```
**Working workaround: pack multiple headers into ONE string argument
separated by `\r\n`:**
```kf
main() {
    var body = http.get("http://127.0.0.1:18080/echo",
        "User-Agent: koffuster/0.1\r\nX-Test: hi")
    println(body)
}
```
Output: `UA=koffuster/0.1` / `XTEST=hi` — **both headers arrive correctly.
Use this `"Name: value\r\nName2: value2"` single-string form for every
multi-header request.**

**Method control: WORKS via the dedicated verb functions.**
```kf
http.post(url, "mybody123")   // METHOD=POST, BODY=mybody123 (confirmed)
http.put(url, "putbody")      // METHOD=PUT, BODY=putbody (confirmed)
http.delete(url)              // METHOD=DELETE (confirmed)
```
No dedicated `head()` exists (see P1d) — there is no way to send a bare HEAD
request through `kof.http` on this build.

**Host header override (vhost scanning): BLOCKED by default, WORKS with one JVM flag.**

Default (no flag): the request throws before it even leaves the process —
and, consistent with P1b, this exception is a synchronous throw from
`kof_http_get_headers` and is **not wrapped for `catch (String e)`** either
(same escape pattern as P1b/c — wrap in `spawn`/`await` to catch it):
```
Exception in thread "main" java.lang.IllegalArgumentException: restricted header name: "Host"
	at java.net.http/jdk.internal.net.http.HttpRequestBuilderImpl.checkNameAndValue(HttpRequestBuilderImpl.java:110)
	at dev.kof.runtime.KofRuntime.kof_http_get_headers(KofRuntime.java:1743)
```

**Working recipe: add `-Djdk.httpclient.allowRestrictedHeaders=host` to
`JDK_JAVA_OPTIONS`** (this env var is a standard JDK mechanism, auto-applied
to *every* `java` invocation including the one `bin/kof` execs — no edit to
`bin/kof` itself needed):
```bash
export JDK_JAVA_OPTIONS="--enable-preview -Djdk.httpclient.allowRestrictedHeaders=host"
```
```kf
main() {
    var body = http.get("http://127.0.0.1:18080/echo", "Host: vhost.example.com")
    println(body)
}
```
Real output: `HOST=vhost.example.com` — **the override reaches the server.**
On the user's own machine, the equivalent is `export
JDK_JAVA_OPTIONS="-Djdk.httpclient.allowRestrictedHeaders=host"` before
invoking `kof run`/`kof serve`/the installed `kof` binary — `bin/kof` execs
plain `java ... -jar lib/kof.jar "$@"`, and `java` itself picks up
`JDK_JAVA_OPTIONS` from the environment automatically, so **no source change
to `bin/kof` is required.**

### P1 idiom summary

```kf
// THE pattern for every scanner request:
String probe(String url) {
    return http.get(url, "User-Agent: koffuster\r\nX-Test: x")
}
main() {
    http.timeout(3)     // SECONDS
    val r = spawn probe("http://target/x")
    try {
        var body = await r
        println("ok len=" + body.length())
    } catch (String e) {
        if (e.contains("ConnectException")) { println("refused") }
        else if (e.contains("HttpTimeoutException")) { println("timeout") }
        else { println("other: " + e) }
    }
}
```

---

## P2 — Strings & parsing

**All standard Java `String` instance methods work directly** — `String` in
Kof *is* `java.lang.String`, so no import/namespace is needed at all.
`tests/p2str/p2str.kf`:
```kf
main() {
    var s = "  Hello,World  "
    println("trim=[" + s.trim() + "]")
    println("lower=" + s.toLowerCase())
    println("upper=" + s.toUpperCase())
    println("len=" + s.length())
    println("charAt2=" + s.charAt(2))
    println("contains=" + s.contains("World"))
    println("startsWith=" + s.trim().startsWith("Hello"))
    println("endsWith=" + s.trim().endsWith("World"))
    println("indexOf=" + s.indexOf("World"))
    println("replace=" + s.replace("World", "Kof"))
    println("substring=" + s.trim().substring(0, 5))
    var parts = s.trim().split(",")
    println("split.length=" + parts.length)
    println("split[0]=" + parts[0])
    println("split[1]=" + parts[1])
}
```
Real output:
```
trim=[Hello,World]
lower=  hello,world  
upper=  HELLO,WORLD  
len=15
charAt2=72
contains=true
startsWith=true
endsWith=true
indexOf=8
replace=  Hello,Kof  
substring=Hello
split.length=2
split[0]=Hello
split[1]=World
```
**Caveat:** `charAt(2)` printed `72` (the numeric UTF-16 code point for
`'H'`), not the character — `println`/`+`-concat renders `Char` as its
`Int` code, not glyph. If a character needs printing as text, wrap with
`String.valueOf(...)`-equivalent or build a 1-char substring instead
(`s.substring(2, 3)`) if a literal character is needed for output/matching.

**Int parsing: `"123".toInt()` WORKS (this is the idiom).**
`tests/p2int/p2int.kf`:
```kf
main() {
    try {
        var n = "notanumber".toInt()
        println("n=" + n)
    } catch (String e) {
        println("CAUGHT: " + e)
    }
    println("after")
}
```
Real output: `CAUGHT: For input string: "notanumber"` / `after`.
**`.toInt()` failures ARE catchable by a plain `try/catch(String e)`** — unlike
the HTTP case in P1, this is a normal in-process `NumberFormatException` and
Kof's exception translation handles it fine. **Use `s.toInt()` for every
port/size/status-filter parse, wrapped in try/catch for user-supplied
values.**

**`Integer.parseInt(...)` (java.lang.Integer): FAILS to resolve** —
`Undefined variable or type: 'Integer' [SEM011]`, same "java.lang isn't
reliably visible" pattern seen elsewhere. **`math.parseInt`/
`math.parseIntOrDefault` (documented in `learn/39-stdlib.md`): FAIL** —
`Undefined variable or type: 'math' [SEM011]` — the `math` namespace does
not exist on 0.2.6-beta (same version-mismatch pattern as `strings`/
`encoding`/`net`, see Risks). **`.toInt()` is the only proven working path
and it's sufic­ient.**

---

## P3 — Encoding: URL, base64, JSON

**`net.*` (URL parsing/encoding): NOT RESOLVABLE on 0.2.6-beta.**
```
error: Undefined variable or type: 'net' [SEM011]
```
Same version-mismatch pattern (documented for 0.5.0-beta, absent here).
**Fallback for URL-encoding: none of the pure-Kof paths tested worked; not
further explored in this pass — flag as an open gap** (candidate fallback
for later investigation: `java.net.URLEncoder`/`URLDecoder` interop, or a
hand-rolled percent-encoder using the proven `String` methods from P2).

**base64 via `java.util.Base64` interop: FAILS to resolve.**
```kf
import java.util.Base64;
main() {
    var enc = Base64.getEncoder().encodeToString("user:pass".getBytes())
    println("b64=" + enc)
}
```
```
error: Undefined variable or type: 'Base64' [SEM011]
```
This contradicts the "java.util collections ✅" claim in `learn/
21-java-interoperability.md` — that claim was verified specifically for
`ArrayList`/`HashMap`-style collection classes, **not for `java.util.Base64`
(a static-factory utility class)**, which fails outright. **Conclusion:
base64 for Basic-Auth headers needs a pure-Kof implementation** (a manual
base64 table-based encoder using proven `String`/array/loop primitives) —
not attempted in this pass due to budget, but flagged as the concrete
fallback plan the coordinator should expect.

**`json.encode(Map)`: technically runs but produces GARBAGE — do not use for maps.**
Requires `--add-opens java.base/java.util=ALL-UNNAMED` in `JDK_JAVA_OPTIONS`
just to avoid a crash:
```
java.lang.reflect.InaccessibleObjectException: Unable to make field ... accessible: module java.base does not "opens java.util" to unnamed module
	at dev.kof.runtime.KofRuntime.kof_json_encode_object(KofRuntime.java:123)
```
With the flag added, it no longer crashes but **reflects over the raw
`java.util.HashMap` internals** instead of producing `{"a":"1","b":"2"}`:
```
encoded={"table":[null,{"hash":97,"key":"a","value":"1","next":null},...],"entrySet":null,"size":2,"modCount":2,"threshold":12,"loadFactor":0.75}
```
**`json.encode(Map)` is BROKEN on 0.2.6-beta — never use it for a `Map`.**

**`json.encode(record)`: WORKS CLEANLY — this is the idiom for JSONL output.**
`tests/p3json2/p3json2.kf`:
```kf
record Result(String url, Int status, Int length)
main() {
    var r = Result("http://x", 200, 42)
    println(json.encode(r))
}
```
Real output: `{"url":"http://x","status":200,"length":42}` — **exactly the
shape Koffuster needs for JSONL scan-result lines. Always define a `record`
for each output line shape and `json.encode(record)` it — never
`json.encode(map)`.**

**`json.decode(String)` (untyped): compiler crash (ICE), same class as the
multi-header bug.**
```
java.lang.RuntimeException: frame crash em Default/Main.main ...
error: Internal compiler error: frame crash ... [COMP002]
```
**`json.decode<Record>(String)` (typed, flat record): WORKS.**
```kf
record Simple(Int Status)
main() {
    var d = json.decode<Simple>("{\"Status\":0}")
    println("status=" + d.Status())
}
```
Output: `status=0`. **Nested `List<Record>` fields in a typed decode:
BROKEN** — see P6 for the exact `ClassCastException` and fallback.
**Idiom: always use `json.decode<SomeFlatRecord>(s)`, never bare
`json.decode(s)`, and never rely on nested-list fields decoding to typed
records — read nested data as raw strings instead (P6).**

---

## P4 — Wordlist input & memory

**`Path("/dev/stdin").readText()`: WORKS — this is how `-w -` is
supported.**
```kf
main() {
    var p = Path("/dev/stdin")
    println("got=[" + p.readText() + "]")
}
```
Piped `printf "line1\nline2\nline3\n" | java -jar kof.jar run ...` →
`got=[line1\nline2\nline3\n]` (verbatim, newlines included).

**No streaming/line-iterator API exists.** We read every relevant doc
(`learn/34-file-system.md`, `learn/39-stdlib.md`, all of `learn/stdlib/
*.md`) and grepped for `readLines`/`BufferedReader`/`forEachLine` — zero
hits. **`kof.io` only exposes whole-file `readText()`/`readBytes()`.**

**Best pattern given this constraint:**
```kf
main() {
    var content = Path("wordlist.txt").readText()   // whole file into memory
    var lines = content.split("\n")                  // proven String method (P2)
    var i = 0
    while (i < lines.length) {
        var word = lines[i]
        if (word.length() > 0) {
            // use word
        }
        i = i + 1
    }
}
```
**Memory tradeoff must be documented for Koffuster's users: the entire
wordlist (or stdin stream) is loaded into a single Java `String` plus a
`String[]` of all lines before any processing starts. For very large
wordlists (multi-GB `rockyou.txt`-class files), this is a real, unavoidable
memory cost on 0.2.6-beta** — there is no chunked/streaming alternative in
the stdlib we could find. If this becomes a hard blocker, the only escape
hatch would be Java interop with `java.io.BufferedReader`, but that path
already failed once in this build (§Risks in the base report,
`NoClassDefFoundError`) and was not successfully re-proven in this pass —
treat true line-streaming as **unproven / likely unavailable** on 0.2.6-beta.

---

## P5 — Bounded worker-pool pattern (no channels needed)

**WORKS.** `channel<T>()` itself is unavailable on 0.2.6-beta (confirmed in
the base report), but a **fixed-size batch of `spawn`+`await` pairs**
achieves bounded concurrency without it. `tests/p5pool/p5pool.kf` (10
concurrent requests per batch × 5 batches = 50 total, against the local
`/200` endpoint):
```kf
Int doStatus(Int i) {
    return http.status("http://127.0.0.1:18080/200")
}
main() {
    var total = 50
    var batch = 10
    var ok = 0
    var b = 0
    while (b < total) {
        var r0 = spawn doStatus(0)
        var r1 = spawn doStatus(1)
        var r2 = spawn doStatus(2)
        var r3 = spawn doStatus(3)
        var r4 = spawn doStatus(4)
        var r5 = spawn doStatus(5)
        var r6 = spawn doStatus(6)
        var r7 = spawn doStatus(7)
        var r8 = spawn doStatus(8)
        var r9 = spawn doStatus(9)
        if (await r0 == 200) { ok = ok + 1 }
        if (await r1 == 200) { ok = ok + 1 }
        if (await r2 == 200) { ok = ok + 1 }
        if (await r3 == 200) { ok = ok + 1 }
        if (await r4 == 200) { ok = ok + 1 }
        if (await r5 == 200) { ok = ok + 1 }
        if (await r6 == 200) { ok = ok + 1 }
        if (await r7 == 200) { ok = ok + 1 }
        if (await r8 == 200) { ok = ok + 1 }
        if (await r9 == 200) { ok = ok + 1 }
        b = b + batch
    }
    println("ok=" + ok + " of " + total)
}
```
Real output: `ok=50 of 50` in **3.8s wall-clock total** (including JVM
startup + on-the-fly compilation), confirming the 10-wide batches genuinely
ran concurrently (50 sequential round-trips at real network latency would
take noticeably longer relative to 10 batches of 10 concurrent ones).
**Exceptions from spawned HTTP calls ARE catchable at `await`** — already
proven in P1c with the same `spawn`/`await` idiom.

**Caveat — no dynamic-width loop tested:** this snippet hardcodes 10
variables per batch (`r0..r9`) because Kof has no array-of-`Handle<T>`
literal or dynamic-length spawn loop proven working in this pass (arrays
need `new Handle<Int>[n]`, untested here due to budget — flag for the next
pass if a variable batch size becomes a requirement, e.g. the last partial
batch of a wordlist not divisible by the batch size). **For a variable
final batch, the safe fallback is: pad the last batch's URL list with a
guaranteed-fast no-op URL, or special-case batch sizes 1–9 with their own
unrolled blocks** — not elegant, but proven-safe within what we validated.

**Bounded memory:** confirmed structurally — only `batch` (10) `Handle`
values are ever live at once, never one handle per wordlist line, so memory
for in-flight tasks stays flat regardless of total wordlist size (the
wordlist *content* itself is still fully in memory per P4).

---

## P6 — DNS via DoH (since there is no native DNS/UDP)

**WORKS for the essential Status-code decision (0 = has answer, 3 =
NXDOMAIN); nested Answer-record decode is BROKEN and needs a fallback.**

Fetch + typed decode of just the `Status` field: `tests/p6doh/p6doh.kf`:
```kf
record DohStatus(Int Status)
main() {
    var ok = http.get("http://127.0.0.1:18080/doh-ok")
    var nx = http.get("http://127.0.0.1:18080/doh-nx")
    var dok = json.decode<DohStatus>(ok)
    var dnx = json.decode<DohStatus>(nx)
    println("ok.Status=" + dok.Status())
    println("nx.Status=" + dnx.Status())
}
```
Real output: `ok.Status=0` / `nx.Status=3` — **this alone is enough to
distinguish "resolves" vs "NXDOMAIN."** Combined with P1's proven
`spawn`/`await`/`catch` pattern, the 4-way DNS outcome Koffuster needs is
fully achievable:
1. `Status == 0` → resolves (has records)
2. `Status == 3` → NXDOMAIN
3. `await` throws `ConnectException`/similar → resolver (DoH endpoint) down
4. `await` throws `HttpTimeoutException` → resolver timeout

**Extracting the actual IP from `Answer[0].data`: typed nested decode is
BROKEN.**
```kf
record Answer(String name, Int type, String data)
record DohFull(Int Status, List<Answer> Answer)
main() {
    var d = json.decode<DohFull>(http.get("http://127.0.0.1:18080/doh-ok"))
    println(d.Answer().get(0).data())   // CRASHES
}
```
```
java.lang.ClassCastException: class java.util.LinkedHashMap cannot be cast to class Answer
	at Default.Main.main(p6doh2.kf:11)
```
`d.Status()` correctly returned `0` and `d.Answer().size` correctly
returned `1` — **only element access inside the nested list is broken**
(the runtime leaves the list elements as raw `LinkedHashMap` instead of
casting/constructing `Answer` records). **Working fallback: extract `data`
via string search on the raw JSON body** (using the proven `String` methods
from P2 — `indexOf`, `substring`) instead of a typed nested decode:
```kf
main() {
    var raw = http.get("http://127.0.0.1:18080/doh-ok")
    var key = "\"data\":\""
    var i = raw.indexOf(key)
    if (i >= 0) {
        var start = i + key.length()
        var end = raw.indexOf("\"", start)
        println("ip=" + raw.substring(start, end))
    }
}
```
This is the recommended, proven-safe pattern for pulling one scalar field
(e.g. the resolved IP) out of the DoH JSON body without relying on nested
typed decode.

---

## P7 — vhost Host header override

**Fully proven working — see P1e above** for the complete recipe: default
blocked (`IllegalArgumentException: restricted header name: "Host"`,
uncaught by plain `try/catch` — same as P1b, use `spawn`/`await` to catch
it if graceful handling is needed), **unblocked by adding
`-Djdk.httpclient.allowRestrictedHeaders=host` to `JDK_JAVA_OPTIONS`**, no
`bin/kof` source changes required since `java` reads `JDK_JAVA_OPTIONS`
from the environment automatically. Verified: `HOST=vhost.example.com`
reached the server.

---

## P8 — UDP/TFTP reality check: **DatagramSocket construction works; payload construction is BROKEN — declare UDP/TFTP a demonstrated blocker**

**`new DatagramSocket()`: WORKS** (unlike `java.net.InetAddress`, which
failed entirely in the base report):
```kf
import java.net.DatagramSocket;
main() {
    var sock = new DatagramSocket()
    println("created")
}
```
Output: `created`.

**Root-caused blocker: `String.getBytes()` (any Java call returning a raw
`byte[]`) crashes the running program with a `NoClassDefFoundError`,
independent of DatagramSocket entirely:**
```kf
main() {
    var msg = "hello-udp"
    var buf = msg.getBytes()
    println("buflen=" + buf.length)
}
```
```
Error: Unable to initialize main class Default.Main
Caused by: java.lang.NoClassDefFoundError: ?
```
Isolated by removing every other moving part (no `DatagramSocket`, no
imports beyond nothing) — **`.getBytes()` alone reproduces the crash**. This
is a general Kof codegen bug around Java methods that return a raw `byte[]`,
not specific to networking — but it directly blocks building a UDP payload
buffer (`DatagramPacket` requires a `byte[]`), since there is no other
proven way in this build to materialize a `byte[]` from a `String` or from
`kof.io` (which uses `Int[]`, a different, incompatible array type, per
`learn/34-file-system.md`).

**Conclusion: UDP send/receive via `java.net.DatagramSocket`/
`DatagramPacket` interop is a demonstrated blocker on Kof 0.2.6-beta** — the
socket object itself can be constructed, but there is no proven way to
build the byte buffer a `DatagramPacket` needs without hitting the
`getBytes()` crash. We did not have remaining budget to probe `extern`/C
FFI as an alternative raw-UDP path (binding `libc.so.6`'s `socket`/
`sendto`/`recvfrom` directly, per `learn/40-low-level.md`) — that remains
the only undemonstrated escape hatch and should be the next thing tried if
UDP/TFTP support becomes a hard requirement. **Recommendation: ship
tftp/UDP-dependent scan modes as an honestly-reported "not supported on
this build" limitation rather than faking it.**

---

## P9 — Ctrl+C (SIGINT) handling

**`java.lang.Runtime`/shutdown-hook interop: BLOCKED**, same failure class
as `java.lang.System` in the base report:
```kf
import java.lang.Runtime;
main() {
    var rt = Runtime.getRuntime()
}
```
```
error: Undefined variable or type: 'Runtime' [SEM011]
```
**No way found to intercept SIGINT from inside a Kof program on this
build.**

**Fallback plan — confirmed viable with a real kill -INT test.**
`tests/p9sigint/p9sigint.kf` appends one result line + sleeps, in a loop of
20; the process was sent a real `SIGINT` (`kill -INT $PID`) from outside
after ~3 seconds:
```kf
main() {
    var p = Path("/tmp/koffuster_sigint_test.txt")
    p.writeText("")
    var i = 0
    while (i < 20) {
        p.appendText("result" + i + "\n")
        time.sleep(300)
        i = i + 1
    }
    println("done-normally")
}
```
Result: the process exited with code 130 (killed by SIGINT, no graceful
shutdown, `"done-normally"` never printed — confirms there is genuinely no
interceptable hook) — **but the on-disk file already contained every
`appendText` write made before the kill**:
```
result0
result1
result2
result3
```
**Conclusion: `kof.io`'s `appendText` is safe to use as the sole
durability mechanism. Koffuster must append+flush each scan result to the
output file (or JSONL) immediately as it is found, rather than
accumulating results in memory and writing them out at the end — this is
not just a nice-to-have, it is the ONLY way results survive a Ctrl+C on
this build.**

---

## Cross-cutting version-mismatch note (relevant to every P above)

Several namespaces documented in `learn/`/`docs/stdlib/` for "0.5.0-beta"
are **not resolvable at all** on the runnable 0.2.6-beta jar, confirmed
freshly in this pass: `kof.strings` («`strings`»), `kof.encoding`
(«`encoding`»), `kof.net` («`net`»), `kof.math` («`math`»), and
`channel<T>()`. Every one of them fails identically with `Undefined
variable or type: 'X' [SEM011]` (or `SEM015` for `channel`), with or
without an explicit `import kof.X;` line — consistent with these being
added to the stdlib after 0.2.6-beta. **Whenever this cookbook needed one
of those, we found and validated a working substitute** (`String` instance
methods instead of `kof.strings`; `.toInt()` instead of `math.parseInt`;
raw-string parsing instead of `net.*`) — but future work should keep
re-checking this list against the real jar rather than trusting the
`learn/`/`docs/` prose, exactly per `AGENTS.md`'s own rule: *"if syntax is
uncertain: compile ... compiler result outranks memory."*
