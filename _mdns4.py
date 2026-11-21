import socket, struct, time, re, sys

def query(name, timeout=3.0):
    parts = [p for p in name.split(".") if p]
    q = b""
    for p in parts:
        q += bytes([len(p)]) + p.encode()
    q += b"\x00"
    packet = struct.pack(">HHHHHH", 0, 0, 1, 0, 0, 0) + q + struct.pack(">HH", 12, 1)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.settimeout(0.4)
    s.sendto(packet, ("224.0.0.251", 5353))
    found = []
    end = time.time() + timeout
    while time.time() < end:
        try:
            data, addr = s.recvfrom(9000)
            found.append((addr, data))
        except socket.timeout:
            continue
    s.close()
    return found

for svc in ("_airplay._tcp.local", "_raop._tcp.local"):
    try:
        res = query(svc)
    except Exception as e:
        print(f"{svc}: EXC {e}")
        continue
    print(f"=== {svc}: {len(res)} responses ===")
    seen = set()
    for addr, data in res:
        for m in re.findall(rb"[ -~]{3,}", data):
            t = m.decode("ascii", "ignore")
            if t not in seen:
                seen.add(t)
                print("   ", t)
print("probe done")
