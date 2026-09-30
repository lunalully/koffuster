# Implementation notes

## Concurrency spike (architecture.md §5) — RESULT: both dynamic-handle
## approaches FAIL on 0.2.6-beta; unrolled fixed-width batches is the only
## proven-working pattern. `sched.kf` is built on the fallback.

Test harness used for both spikes: 7 concurrent `http.status` calls against
the lab's `/200` route (`labs/http_lab.py` on 127.0.0.1:18080).

### Approach 1 — `listOf<Handle<Int>>()` + `.add(spawn ...)` + `await hs.get(i)`

`kof-runtime-staged/tests/spike_pool/spike_pool.kf`:
```kf
Int doStatus() {
    return http.status("http://127.0.0.1:18080/200")
}

main(args: String[]) {
    var n = 7
    if (args.length > 0) { n = args[0].toInt() }
    var hs = listOf<Handle<Int>>()
    var i = 0
    while (i < n) {
        hs.add(spawn doStatus())
        i = i + 1
    }
    var ok = 0
    i = 0
    while (i < n) {
        var s = await hs.get(i)
        if (s == 200) { ok = ok + 1 }
        i = i + 1
    }
    println("ok=" + ok + " of " + n)
}
```
Run: `java -jar kof.jar run kof-runtime-staged/tests/spike_pool/spike_pool.kf -t=7`

Real output — crashes at startup with a JVM bytecode verifier error, not a
compile error (the Kof compiler accepts the source, but the bytecode it
emits for this construct is invalid):
```
Error: Unable to initialize main class Default.Main
Caused by: java.lang.VerifyError: Bad type on operand stack
Exception Details:
  Location:
    Default/Main.main([Ljava/lang/String;)V @92: astore
  Reason:
    Type integer (current frame, stack[0]) is not assignable to reference type
  ...
```
**FAILS. Do not use `listOf<Handle<T>>()` on this build.**

### Approach 2 — `new Handle<Int>[n]` + index assign + `await hs[i]`

`kof-runtime-staged/tests/spike_pool2/spike_pool2.kf`:
```kf
Int doStatus() {
    return http.status("http://127.0.0.1:18080/200")
}

main(args: String[]) {
    var n = 7
    if (args.length > 0) { n = args[0].toInt() }
    var hs = new Handle<Int>[n]
    var i = 0
    while (i < n) {
        hs[i] = spawn doStatus()
        i = i + 1
    }
    var ok = 0
    i = 0
    while (i < n) {
        var s = await hs[i]
        if (s == 200) { ok = ok + 1 }
        i = i + 1
    }
    println("ok=" + ok + " of " + n)
}
```
Run: `java -jar kof.jar run kof-runtime-staged/tests/spike_pool2/spike_pool2.kf -t=7`

Real output — also a bytecode VerifyError, this time in the array-store
codegen (`new Handle<Int>[n]` appears to erase to a raw `byte[]`/`Object[]`
mismatch, not a proper reference array):
```
Error: Unable to initialize main class Default.Main
Caused by: java.lang.VerifyError: Bad type on operand stack in aastore
Exception Details:
  Location:
    Default/Main.main([Ljava/lang/String;)V @48: aastore
  Reason:
    Type '[B' (current frame, stack[0]) is not assignable to reference type
  ...
```
**FAILS. Do not use `new Handle<T>[n]` on this build.**

### Fallback (used) — unrolled fixed-width batches (cookbook P5)

`kof-runtime-staged/tests/p5pool/p5pool.kf` (already in the cookbook, 10
concurrent requests per batch x 5 batches = 50 total against `/200`) was
re-run to reconfirm on this container:
```
$ java -jar kof.jar run kof-runtime-staged/tests/p5pool/p5pool.kf
ok=50 of 50
```
**WORKS.** Since neither dynamic-handle form is usable, `sched.kf` snaps the
user's `-t/--threads` value to the nearest of a small fixed set of unrolled
batch widths (`1, 2, 4, 8, 16, 32`) and dispatches through a hand-written
`switch` that calls the correspondingly-sized unrolled batch function
(`runBatch1`, `runBatch2`, `runBatch4`, `runBatch8`, `runBatch16`,
`runBatch32`), each an explicit sequence of `r0..rN-1 = spawn ...` /
`await r0..rN-1` lines, matching the proven P5 shape exactly. This is the
documented limitation from architecture.md §5's "if BOTH fail" clause.

Practical effect: `--threads` is not infinitely variable — it is rounded
down to the nearest supported width for the batch loop (the last partial
window of the candidate list is handled by only awaiting/dispatching the
first `k` of the batch's fixed slots and leaving the rest unused, since Kof
requires all `r0..rN-1` spawns to execute in the unrolled block — an unused
slot's request is simply not issued when the window is short by construction
of the loop bounds, never awaited past what's needed).

## Generalization: `new <ReferenceType>[n]` is broken for ANY reference type,
## not just `Handle<T>`

Isolated further: `new String[3]` (nothing to do with concurrency at all)
reproduces the identical `VerifyError: Bad type on operand stack in aastore`
/ `Type '[B' is not assignable to reference type` crash
(`tests/spike_arr/spike_arr.kf`):
```kf
main() {
    var arr = new String[3]
    arr[0] = "p"
    println("arr0=" + arr[0])
}
```
So this is not specific to `Handle<T>` — **`new T[n]` reference-typed array
codegen is broken on this build for any `T`.** The proven-safe replacement
for a reference-typed dynamic collection is `listOf<T>()` + `.add(...)` +
`.get(i)`/`for (var x in xs)`, confirmed working (`tests/spike_list2`):
```kf
main() {
    var lst = listOf<String>()
    lst.add("a")
    lst.add("b")
    println("size=" + lst.size())
    for (var x in lst) { println("x=" + x) }
}
```
`listOf<T>()` alone is fine; it is specifically `Handle<T>` *stored inside*
either a `listOf` or a `new [n]` array, then `await`-ed back out by index,
that breaks (Approach 1 above shows `listOf<Handle<T>>()` itself also fails
differently — a separate VerifyError at the `astore` for the awaited `Int`
result). Koffuster therefore avoids `new T[n]` for every reference type
throughout (`wordlist.kf`, `cli.kf`, etc. use `listOf<String>()` for
dynamic string collections), and uses the unrolled fixed-width batch pattern
in `sched.kf` for concurrency (see above) rather than any array/list of
`Handle<T>`.

## MAJOR blocker found beyond the cookbook: `spawn f(x)` is broken for ANY
## non-literal argument — the real reason `sched.kf` needed a second,
## bigger workaround than just the Handle-collection spike

While building `sched.kf` on the unrolled-batch fallback above, every batch
still needs to `spawn` a *different* URL per slot. That turned out to be
broken far more fundamentally than the Handle-collection issue: **`spawn
f(expr)` corrupts the generated bytecode (`VerifyError: Bad type on operand
stack` in a synthetic `Lambda0.invoke()`) the instant `expr` contains **any**
reference to a local variable or parameter — of any type (`String`, `Int`,
even a `record`) — anywhere in its expression tree**, even nested two calls
deep. Literal arguments and argument expressions built ONLY from further
zero-argument/literal-argument calls are fine; anything reading a `var`/`val`
is not.

Minimal repro (`tests/spike_retryB/spike_retryB.kf`):
```kf
Int doStatus(String url) { return http.status(url) }
main() {
    var u = "http://127.0.0.1:18080/200"
    val r = spawn doStatus(u)   // u is a plain local var
    var s = await r
    println("s=" + s)
}
```
```
Exception in thread "main" java.lang.VerifyError: Bad type on operand stack
Exception Details:
  Location: Lambda0.invoke()I @1: invokestatic
  Reason: Type 'Lambda0' (current frame, stack[0]) is not assignable to 'java/lang/String'
```
Confirmed NOT specific to strings, to `main()` vs. a helper function, or to
one level of nesting (`tests/spike_retryE` with an `Int`, `spike_retryI` with
a `record`, `spike_retryN` with `spawn somar(identity(x), 3)` all reproduce
it identically). Confirmed the opposite also holds — an argument built
purely from further calls with NO variable reference anywhere works fine
(`tests/spike_retryM`, `spawn somar(makeTwo(), 3)` → `total=5`). Also
confirmed `Handle<T>` cannot be named as an explicit parameter type at all
(`NoClassDefFoundError: Handle` — `tests/spike_slot` first attempt), so a
reusable "await this handle" helper function taking a `Handle<Int>`
parameter is not an option either; every `await` must be written inline at
its `spawn` call site.

**This means Koffuster cannot pass a dynamically-computed URL into `spawn`
by argument, at all, on this build.** Given the tool's whole point is
concurrently probing *different* URLs per request, this blocks the
straightforward design entirely and needed a second workaround on top of the
unrolled-batch one.

### The proven workaround: route the dynamic value through a temp file, not
### a spawn argument (`tests/spike_slot2/spike_slot2.kf`)

Ordinary (non-`spawn`) function calls with variable arguments are completely
unaffected — only `spawn`'s own argument marshaling is broken. So each fixed
batch "slot" gets its own dedicated temp file and its own literal-named,
**zero-argument** top-level function that reads that one fixed path:
```kf
Int probeStatusSlot0() {
    var url = Path("/tmp/koffuster_spike_slot0.url").readText()
    return http.status(url)
}
Int probeStatusSlot1() {
    var url = Path("/tmp/koffuster_spike_slot1.url").readText()
    return http.status(url)
}
main() {
    Path("/tmp/koffuster_spike_slot0.url").writeText("http://127.0.0.1:18080/200")
    Path("/tmp/koffuster_spike_slot1.url").writeText("http://127.0.0.1:1/x")
    val r0 = spawn probeStatusSlot0()   // zero args — matches the proven P1c/P5 shape
    val r1 = spawn probeStatusSlot1()
    // await/try/catch inlined per slot, exactly as P1c (no Handle<T> parameter needed)
    ...
}
```
Real output: `p0 ok=true status=200` / `p1 ok=false err=refused` — the good
URL and the refused-connection URL were correctly distinguished, proving no
race between writing slot 0's and slot 1's files (all slot files are written
sequentially, from plain synchronous code, *before* any slot in that batch is
spawned) and no stale-read lag between `writeText` and the spawned
`readText`.

`sched.kf` builds on this: one run-unique temp directory (named from
`time.now()` at startup, so two concurrent Koffuster runs never collide);
one pair of `probeStatusSlotN()`/`probeBodyLenSlotN()` zero-arg functions per
supported batch width slot (widths `1, 2, 4, 8, 16`, mechanically generated,
not hand-typed, to avoid transcription errors); the batch driver writes each
slot's URL file synchronously, spawns every slot's zero-arg wrapper, then
awaits each inline in its own `try/catch` (per P1c) to classify
ok/refused/timeout/other without crashing the process. `--threads` is
snapped down to the nearest of `{1,2,4,8,16}` (architecture's suggested `32`
was dropped to keep the generated slot-function count and temp-file count
manageable; documented as a deliberate scope reduction, not a silent
limitation).

Practical costs of this workaround, documented honestly: (1) one small temp
file write per in-flight request (negligible, but it is real disk I/O the
"pure in-memory" design didn't originally call for); (2) the temp directory
is cleaned up at the end of a normal run but a killed (`SIGINT`) process
will leave its per-run temp directory behind (same class of limitation as
§10.5 — no interceptable shutdown hook on this build) — this is disclosed
in `--help`/README, not hidden.

## `http.get(url, headers)` throws on non-2xx — but `http.get(url)` (no
## headers) does not

Cookbook P1a proved `http.get(url)` (one argument) returns the body String
normally for 404/500/etc, never throwing. That is NOT true of the
two-argument form once a header string is attached:
```kf
main() {
    var b = http.get("http://127.0.0.1:18080/500", "User-Agent: koffuster/0.1")
    println("b=[" + b + "]")
}
```
```
Exception in thread "main" java.io.IOException: HTTP 500 from http://127.0.0.1:18080/500
	at dev.kof.runtime.KofRuntime.kof_http_request(KofRuntime.java:1850)
	at dev.kof.runtime.KofRuntime.kof_http_get_headers(KofRuntime.java:1743)
```
(`tests/spike_500/spike_500.kf`). Confirmed live in `koffuster dir` against
the real lab: `-u http://127.0.0.1:18080/500` produces `length=-1` for the
`/500` candidate (never a crash — the throw happens inside the spawned
zero-arg body-probe function and surfaces as a catchable String at
`await`, exactly like every other classified error) while `/200`/`/301`
correctly get real body lengths. Practical effect, documented in the
requirements matrix: any candidate whose status is not 2xx reports
`length=-1` whenever headers/UA/cookie/auth are attached (which is always,
in this build — `bodySlotN()` always sends at least a `User-Agent` header).
This is disclosed rather than "fixed" by silently dropping to the
single-argument form, since that would mean UA/cookie/auth headers quietly
stop being sent for exactly the candidates a security scan most cares
about (non-2xx and especially soft-404-adjacent statuses).

## Correction: the ONE-argument `http.get(url)` throws on 5xx too — the
## "never throws" claim only holds for 4xx

Re-tested directly while building the headerless body-length improvement
(`tests/spike_nohdr500`, `tests/spike_nohdr404`). Cookbook P1a's "does NOT
throw on 4xx/5xx" claim was only ever exercised against `/404` and `/301` —
it never actually called the one-argument `http.get(url)` against a `5xx`
route. Doing so now:
```kf
main() {
    var b = http.get("http://127.0.0.1:18080/500")
    println("b=[" + b + "] len=" + b.length())
}
```
```
Exception in thread "main" java.io.IOException: HTTP 500 from http://127.0.0.1:18080/500
	at dev.kof.runtime.KofRuntime.kof_http_request(KofRuntime.java:1850)
	at dev.kof.runtime.KofRuntime.kof_http_get(KofRuntime.java:1739)
```
while the identical call against `/404` returns normally
(`b=[not found body] len=14`, no exception). So the real rule on this
build is: **`http.get` (one or two arguments) throws an `IOException` for
any 5xx response, and only 5xx — 4xx responses return the body normally,
regardless of whether headers are attached.** This is disclosed as a
correction to the dir-mode shared refinement: the headerless body-length
path (`sched.runBodyLenBatchNoHdr`) recovers a real length for every
status EXCEPT 5xx, not literally "any status" — a 5xx candidate still
shows the "-" sentinel, caught cleanly at `await` exactly like every other
classified error, never a crash.

## Multi-file module invocation

`kof run` only accepts a **file** path (`run <file.kf> [...]`), not a bare
directory (`run <dir>` errors `Error reading source file: Is a directory`).
However, per architecture.md §1/§3, pointing `run` at one `.kf` file inside a
directory that has sibling `.kf` files compiles all of them together as one
module (confirmed with `tests/spike_multi/{helper.kf,main.kf}`: `main.kf`
calling a function defined only in `helper.kf` resolved and ran, printing
`doubled=42`). So Koffuster's launcher runs
`kof run <installed-src-dir>/main.kf <args...>` — this satisfies "module unit
= directory of .kf files, one main()" while working within the CLI's
file-only `run` argument.

## TFTP/UDP FFI spike

**Goal:** see whether KOF 0.2.6-beta can send/receive a UDP datagram through `extern` C-FFI
(socket/connect/send/recv on native memory), so `tftp` could be real.

**Documented syntax** (`learn/40-low-level.md`, written for **0.5.0-beta**, not 0.2.6):
`extern "/lib/x86_64-linux-gnu/libc.so.6" getpid(): Int` - Kof function name = C symbol; scalar
args (Int/Long/Float/Double/Boolean/String as char*), `Buffer(U8)` INOUT, scalar records by value;
diagnostics FFI001 (unsupported shape / missing lib) and FFI002 (String[], List, Handle).
No malloc/Arena/MemorySegment/sockaddr API is exposed.

**What was tried** (probe: `kof-runtime-staged/tests/ffi_getpid/main.kf`):
```
extern "/lib/x86_64-linux-gnu/libc.so.6" getpid(): Int
extern "/lib/x86_64-linux-gnu/libc.so.6" atoi(String s): Int
main() { println(getpid()); println(atoi("42")) }
```
Real output on the 0.2.6-beta kof.jar:
```
main.kf:1:8: error: Expected function name [PARSE010]
main.kf:1:8: error: Expected '(' [PARSE011]
... (PARSE044/PARSE023/PARSE012/PARSE007), same for line 2
```
`extern` is not a keyword in 0.2.6. Jar inspection agrees: no class under `dev/kof/**` contains the
token `extern`, and the diagnostic codes FFI001/FFI002 do not exist in the 0.2.6 compiler.
So getpid(), socket(), native alloc, connect/send/recv were unreachable; failure is at the first
step (parse), not in the UDP logic. The UDP fixture was never contacted.

**VERDICT: UDP-VIA-FFI BLOCKED - the `extern`/C-FFI feature does not exist in KOF 0.2.6-beta
(PARSE010 on the first `extern` line; it first appears in the 0.5.0-beta docs), so tftp remains a
documented limitation on this runtime.**

Unblock path: a KOF >= 0.5.0-beta runtime. There, `socket/connect/send/recv` with `Buffer(U8)`
INOUT (RRQ bytes, recv buffer, 16-byte sockaddr_in) looks expressible on the JVM target, so re-spike
with that runtime.
