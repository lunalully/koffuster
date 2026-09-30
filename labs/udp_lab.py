import socket
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.bind(("127.0.0.1",18069))
while True:
    d,a=s.recvfrom(2048); print("UDP got",d,flush=True); s.sendto(b"echo:"+d,a)
