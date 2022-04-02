import logging
import queue
import socket
import threading

import select

import config

logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(levelname)s:\t%(message)s',
    level=logging.INFO,
    datefmt='%H:%M:%S')


class Server:
    def __init__(self):
        self._socket = None

        self._server_running_flag = threading.Event()
        self._server_thread = None

    def _server_loop(self, ):

        inputs = [self._socket]
        outputs = []
        data_buffers = {}

        while not self._server_running_flag.is_set():
            readable, writable, exceptional = select.select(inputs, outputs, inputs)

            for sock in readable:
                if sock is self._socket:
                    client_socket, client_address = sock.accept()
                    #  if the server socket turns up in the inputs list, it means a new socket has connected to the
                    #  server socket.

                    # ssl_sock = context.wrap_socket(client_socket, server_side=True)

                    client_socket.setblocking(False)
                    inputs.append(client_socket)
                    data_buffers[client_socket] = queue.Queue()

                    logging.info(f"Connection successful from {client_address}")

                else:
                    try:
                        data = sock.recv(config.PACKET_SIZE)
                    except ConnectionResetError as e:
                        data = None
                    if data:  # if the data isn't determined to be falsey, then add to the buffer.
                        if sock not in outputs:
                            outputs.append(sock)

                        for out_sock in outputs:  # if the socket isn't the same one that received it, put into
                            # all other sockets' outgoing buffers.
                            # if out_sock != sock:
                            data_buffers[out_sock].put(data)

                    else:  # if empty, remove/disconnect client socket
                        exceptional.append(sock)

            for sock in writable:
                try:
                    data = data_buffers[sock].get_nowait()
                except queue.Empty:
                    outputs.remove(sock)
                else:
                    try:
                        sock.send(data)
                    except ConnectionResetError:
                        exceptional.append(sock)

            for sock in exceptional:  # if any errors happen with the client socket, disconnect the socket.
                logging.info(f"Disconnect from {sock.getpeername()}")

                inputs.remove(sock)
                if sock in outputs:
                    outputs.remove(sock)
                sock.close()
                del data_buffers[sock]

        self._socket.close()

    def start_server(self, ip: str, port: int) -> bool:
        """
        :param ip: IP/Hostname of the server.
        :param port: Port of the server.
        :return: Boolean if the server has successfully started.
        """

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setblocking(False)
        self._server_running_flag.clear()

        try:
            self._socket.bind((ip, int(port)))
            self._socket.listen(config.MAX_JOINABLE_CLIENTS)
            self._server_thread = threading.Thread(target=Server._server_loop, args=(self,), daemon=True)
            self._server_thread.start()

            logging.info(f"Server started from IP: {ip}, port: {port}")

        except ConnectionResetError as e:
            logging.info(e)
            self._server_running_flag.set()

        return self._server_running_flag.is_set()

    def stop_server(self):
        self._server_running_flag.set()
