import maki_vc.config as config
import logging
import queue
import threading
import select
import socket


logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(levelname)s:\t%(message)s',
    level=logging.INFO,
    datefmt='%H:%M:%S')


class Server:
    def __init__(self):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setblocking(False)

        self._server_running_flag = threading.Event()
        self._server_thread = threading.Thread(target=self._server_loop, args=(self._socket, self._server_running_flag))

    @staticmethod
    def _server_loop(server_socket, t_flag):

        inputs = [server_socket]
        outputs = []
        data_buffers = {}

        while not t_flag.is_set():
            readable, writable, exceptional = select.select(inputs, outputs, inputs)

            for sock in readable:
                if sock is server_socket:
                    client_socket, client_address = sock.accept()
                    #  if the server socket turns up in the inputs list, it means a new socket has connected to the
                    #  server socket.

                    # ssl_sock = context.wrap_socket(client_socket, server_side=True)

                    client_socket.setblocking(False)
                    inputs.append(client_socket)
                    data_buffers[client_socket] = queue.Queue()

                    logging.info(f"Connection successful from {client_address}")

                else:
                    data = sock.recv(config.PACKET_SIZE)
                    if data:  # if the data isn't determined to be falsey, then add to the buffer.
                        for out_sock in outputs:  # if the socket isn't the same one that received it, put into
                            # all other sockets' outgoing buffers. 
                            if out_sock != sock:
                                data_buffers[out_sock].put(data)
                        
                        if sock not in outputs:
                            outputs.append(sock)

                    else:  # if empty, remove/disconnect client socket

                        logging.info(f"Disconnect from {sock.getpeername()}, Empty.")

                        inputs.remove(sock)
                        if sock in outputs:
                            outputs.remove(sock)
                        sock.close()
                        del data_buffers[sock]

            for sock in writable:
                try:
                    data = data_buffers[sock].get_nowait()
                except queue.Empty:
                    outputs.remove(sock)
                else:
                    sock.send(data)

            for sock in exceptional:  # if any errors happen with the client socket, disconnect the socket.
                logging.info(f"Disconnect from {sock.getpeername()}")

                inputs.remove(sock)
                if sock in outputs:
                    outputs.remove(sock)
                sock.close()
                del data_buffers[sock]

    def start_server(self, ip: str, port: int) -> bool:
        self._server_running_flag.clear()

        try:
            self._socket.bind((ip, port))
            self._socket.listen(config.MAX_JOINABLE_CLIENTS)
            self._server_thread.start()

            logging.info(f"Server started from IP: {ip}, port: {port}")

        except ConnectionResetError as e:
            logging.info(e)
            self._server_running_flag.set()

        return self._server_running_flag.is_set()

    def stop_server(self):
        self._server_running_flag.set()
        self._socket.close()
