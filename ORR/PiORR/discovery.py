import socket
import time

def broadcast_presence():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    message = b"BLUEBOT_DISCOVERY"

    while True:
        sock.sendto(message, ('<broadcast>', 9999))
        time.sleep(2)