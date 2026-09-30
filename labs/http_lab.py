import http.server, socketserver, time, json, sys, urllib.parse
class H(http.server.BaseHTTPRequestHandler):
    protocol_version="HTTP/1.1"
    def _send(self, code, body=b"", headers=None):
        self.send_response(code)
        for k,v in (headers or {}).items(): self.send_header(k,v)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Lab","yes")
        self.end_headers()
        if self.command!="HEAD": self.wfile.write(body)
    def handle_any(self):
        p=self.path
        ln=int(self.headers.get("Content-Length") or 0)
        data=self.rfile.read(ln) if ln else b""
        if p.startswith("/200"): self._send(200,b"hello-200")
        elif p.startswith("/404"): self._send(404,b"not found body")
        elif p.startswith("/500"): self._send(500,b"boom")
        elif p.startswith("/301"): self._send(301,b"moved",{"Location":"/200"})
        elif p.startswith("/slow"): time.sleep(5); self._send(200,b"slow")
        elif p.startswith("/echo"):
            out="METHOD=%s\nHOST=%s\nUA=%s\nXTEST=%s\nBODY=%s\n"%(self.command,self.headers.get("Host"),self.headers.get("User-Agent"),self.headers.get("X-Test"),data.decode())
            self._send(200,out.encode())
        elif p.startswith("/doh-ok"):
            self._send(200,json.dumps({"Status":0,"Answer":[{"name":"a.example.","type":1,"TTL":60,"data":"1.2.3.4"}]}).encode(),{"Content-Type":"application/dns-json"})
        elif p.startswith("/doh-nx"):
            self._send(200,json.dumps({"Status":3}).encode(),{"Content-Type":"application/dns-json"})
        elif p.startswith("/doh-slow"):
            time.sleep(5)
            self._send(200,json.dumps({"Status":0,"Answer":[{"data":"9.9.9.9"}]}).encode())
        elif p.startswith("/doh"):
            # mock DoH JSON resolver, keyed by ?name= — always answers HTTP 200
            # (a real DoH resolver does too, even for NXDOMAIN) per architecture.
            qs = urllib.parse.urlparse(p).query
            params = urllib.parse.parse_qs(qs)
            name = (params.get("name") or [""])[0]
            # any name under wild.example. "resolves" to the same wildcard IP,
            # simulating a wildcard DNS record
            if name.endswith("wild.example.") or name.endswith("wild.example"):
                self._send(200, json.dumps({"Status":0,"Answer":[{"data":"10.10.10.10"}]}).encode())
            elif name.startswith("www.") or name.startswith("real.") or name.startswith("api."):
                self._send(200, json.dumps({"Status":0,"Answer":[{"data":"5.6.7.8"}]}).encode())
            else:
                self._send(200, json.dumps({"Status":3}).encode())
        elif p.startswith("/s3/") or p.startswith("/gcs/"):
            bucket = p.rsplit("/",1)[-1]
            if bucket == "public-bucket": self._send(200, b"<ListBucketResult>public</ListBucketResult>")
            elif bucket == "private-bucket": self._send(403, b"<Error>AccessDenied</Error>")
            else: self._send(404, b"<Error>NoSuchBucket</Error>")
        elif p.startswith("/vhostroute"):
            # a route whose body length depends on the Host header, so vhost
            # mode has something real to diff against a random-Host baseline
            host = self.headers.get("Host","")
            if host.startswith("admin."):
                self._send(200, b"admin-panel-secret-content-here")
            else:
                self._send(200, b"generic")
        else: self._send(404,b"nf")
    do_GET=do_POST=do_HEAD=do_PUT=do_DELETE=do_OPTIONS=handle_any
    def log_message(self,*a): sys.stderr.write("REQ %s %s\n"%(self.command,self.path))
class S(socketserver.ThreadingMixIn,http.server.HTTPServer): daemon_threads=True
S(("127.0.0.1",18080),H).serve_forever()
