import time

import config
from queue import Queue
import socket
import threading


class Server:
    def __init__(self):
        self.s_socket, self.server_thread, self.connection_thread = None, None, None
        self.is_running = threading.Event()
        self.connection_queue = Queue()

    def start(self):

        self.is_running.clear()

        self.s_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s_socket.bind((socket.gethostbyname(socket.getfqdn()), config.PORT))
        self.s_socket.listen(config.MAX_JOIN)

        self.server_thread = threading.Thread(target=self.server_loop, args=(self.is_running, self.connection_queue))
        self.connection_thread = threading.Thread(target=self.connection_loop,
                                                  args=(self.is_running, self.s_socket, self.connection_queue))
        self.server_thread.start()
        self.connection_thread.start()

    def stop(self):
        self.is_running.set()
        self.server_thread.join()
        self.connection_thread.join()

    @staticmethod
    def connection_loop(t_flag, s_socket, connection_queue):
        while not t_flag.is_set():
            client_socket, ip_address = s_socket.accept()
            client_socket.setblocking(False)
            client_socket.settimeout(config.SOCKET_TIMEOUT)
            connection_queue.put((client_socket, ip_address))
            print(f"Connection successful from: {ip_address}")

    @staticmethod
    def server_loop(t_flag, connection_queue):

        connections = {}
        disconnects = []

        while not t_flag.is_set():

            for d in disconnects:
                connections[d].close()
                del connections[d]
            disconnects = []

            if not connection_queue.empty():
                _client, _ip_address = connection_queue.get()
                connections[_ip_address] = _client

            for idx, (key, client) in enumerate(connections.items()):
                try:
                    try:
                        data = client.recv(config.AUDIO["CHUNK"])
                    except socket.error:
                        data = bytes()  # It likes timing out a lot.

                    for idx_2, (key, client_2) in enumerate(connections.items()):
                        # if not idx == idx_2:
                        client_2.send(data)
                except ConnectionResetError as e:
                    print(f"Disconnect from {key}")
                    disconnects.append(key)


def main():
    print(socket.gethostbyname(socket.getfqdn()))

    s = Server()
    s.start()


if __name__ == "__main__":
    main()
