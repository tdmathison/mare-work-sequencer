"""Deterministic harmless Ethernet/TCP HTTP handshake and request fixtures."""

from pathlib import Path
import socket
import struct


def checksum(data):
    if len(data) % 2:
        data += b"\0"
    total = sum(struct.unpack("!" + str(len(data) // 2) + "H", data))
    while total >> 16:
        total = (total & 65535) + (total >> 16)
    return (~total) & 65535


def packet(reverse, seq, ack, flags, payload=b""):
    a, b = ("192.0.2.20", "192.0.2.10") if reverse else ("192.0.2.10", "192.0.2.20")
    src, dst = socket.inet_aton(a), socket.inet_aton(b)
    sport, dport = (80, 40000) if reverse else (40000, 80)
    tcp = (
        struct.pack("!HHIIBBHHH", sport, dport, seq, ack, 0x50, flags, 65535, 0, 0)
        + payload
    )
    pseudo = src + dst + struct.pack("!BBH", 0, 6, len(tcp))
    value = checksum(pseudo + tcp)
    tcp = tcp[:16] + struct.pack("!H", value) + tcp[18:]
    ip = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + len(tcp), 1, 0, 64, 6, 0, src, dst)
    ip = ip[:10] + struct.pack("!H", checksum(ip)) + ip[12:]
    return b"\x02\0\0\0\0\x02\x02\0\0\0\0\x01\x08\0" + ip + tcp


def capture(path):
    request = f"GET {path} HTTP/1.1\r\nHost: example.test\r\n\r\n".encode()
    frames = [
        packet(False, 100, 0, 2),
        packet(True, 200, 101, 0x12),
        packet(False, 101, 201, 0x10),
        packet(False, 101, 201, 0x18, request),
        packet(True, 201, 101 + len(request), 0x10),
    ]
    raw = struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)
    for i, frame in enumerate(frames):
        raw += struct.pack("<IIII", 1700000000 + i, 0, len(frame), len(frame)) + frame
    return raw


if __name__ == "__main__":
    directory = Path(__file__).parent
    (directory / "target.pcap").write_bytes(capture("/mare-example"))
    (directory / "baseline.pcap").write_bytes(capture("/ordinary"))
