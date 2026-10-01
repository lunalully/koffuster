# labs/tftp_lab.py - servidor TFTP minimo para testes do modo tftp do
# Koffuster. Responde RRQ (opcode 1) na porta 18069:
#   - arquivos conhecidos (existe.txt, publico.txt) -> DATA (opcode 3, block 1)
#   - nomes "negado*" -> ERROR 2 (access violation)
#   - qualquer outro nome -> ERROR 1 (file not found)
# Nao implementa o restante do protocolo (WRQ, retransmissao, blocos >1):
# e um alvo de laboratorio, nao um servidor de producao.
import socket
import struct

FILES = {
    "existe.txt": b"conteudo de teste do lab\n",
    "publico.txt": b"publico\n",
}

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(("127.0.0.1", 18069))
print("tftp lab on 127.0.0.1:18069", flush=True)

while True:
    data, addr = s.recvfrom(2048)
    if len(data) < 2:
        continue
    op = struct.unpack(">H", data[:2])[0]
    if op != 1:
        print("skip opcode", op, "from", addr, flush=True)
        continue
    name, _, rest = data[2:].partition(b"\x00")
    mode, _, _ = rest.partition(b"\x00")
    name_s = name.decode("latin-1", "replace")
    print("RRQ", repr(name_s), "mode", mode.decode("latin-1", "replace"), "from", addr, flush=True)
    if name_s in FILES:
        resp = struct.pack(">HH", 3, 1) + FILES[name_s]
    elif name_s.startswith("negado"):
        resp = struct.pack(">HH", 5, 2) + b"Access violation\x00"
    else:
        resp = struct.pack(">HH", 5, 1) + b"File not found\x00"
    s.sendto(resp, addr)
