import traceback
import config as a_config
import pyaudio
import socket
import threading
from queue import Queue


class AudioHandler:
    def __init__(self, audio_config, in_queue, out_queue):
        self.in_queue, self.out_queue = in_queue, out_queue
        self.in_thread, self.out_thread = None, None
        self.in_t_flag, self.out_t_flag = threading.Event(), threading.Event()
        self.audio_config = audio_config.AUDIO

        self.pa = pyaudio.PyAudio()
        self.stream = self.pa.open(
            format=self.audio_config["FORMAT"],
            channels=self.audio_config["CHANNELS"],
            rate=self.audio_config["SAMPLE RATE"],
            input=True,
            output=True,
            frames_per_buffer=self.audio_config["CHUNK"]
        )

    def start(self):
        self.in_t_flag.clear()
        self.out_t_flag.clear()

        self.stream.start_stream()

        self.in_thread = threading.Thread(target=self.aud_in_loop,
                                          args=(self.in_queue, self.stream, self.in_t_flag, self.audio_config),
                                          daemon=True)
        self.out_thread = threading.Thread(target=self.aud_out_loop,
                                           args=(self.out_queue, self.stream, self.out_t_flag),
                                           daemon=True)
        # daemon threads will simply exit when the program terminates.
        self.in_thread.start()
        self.out_thread.start()

    def stop(self):

        self.in_t_flag.set()
        self.out_t_flag.set()
        self.in_thread.join()
        self.out_thread.join()

        self.stream.stop_stream()
        self.stream.close()

    @staticmethod
    def aud_in_loop(queue, stream, terminated_flag, config):

        while not terminated_flag.is_set():
            # print("IN THREAD LOOP")
            data = stream.read(config["CHUNK"], exception_on_overflow=True)  # bytes
            queue.put(data)

    @staticmethod
    def aud_out_loop(queue, stream, terminated_flag):

        while not terminated_flag.is_set():
            data = queue.get()
            stream.write(data, exception_on_underflow=False)  # bytes


class Client:
    def __init__(self):
        self.aud_in, self.aud_out = Queue(), Queue()
        self.audio_handler = AudioHandler(a_config, self.aud_in, self.aud_out)
        self.client_thread, self.is_talking = None, threading.Event()
        self.c_socket = None

    def connect(self, ip, port):
        self.c_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            self.c_socket.connect((ip, port))
            self.c_socket.setblocking(False)
            self.c_socket.settimeout(a_config.SOCKET_TIMEOUT)  # around 0.01s is where reverb is noticeable.
        except ConnectionRefusedError as e:
            print(e)

    def start_talking(self):
        self.is_talking.set()
        self.client_thread = threading.Thread(target=self.client_loop,
                                              args=(self.c_socket, self.aud_in, self.aud_out, self.is_talking))
        self.client_thread.start()
        self.audio_handler.start()

    def stop_talking(self):
        self.is_talking.clear()
        self.client_thread.join()
        self.audio_handler.stop()

    @staticmethod
    def client_loop(c_socket, in_queue, out_queue, t_flag):
        while t_flag.is_set():
            try:
                try:
                    out_queue.put(c_socket.recv(a_config.AUDIO["CHUNK"]))
                except socket.error as e:
                    print(e)
                # print(in_queue.qsize())
                if not in_queue.empty():
                    outgoing_data = in_queue.get()
                    packet_size = c_socket.send(outgoing_data)

            except ConnectionResetError:
                print("Connection forcibly closed by host!")
                break


def main():
    try:
        c = Client()

        ip = input("IP: ")
        if ":" in ip:
            ip, port = ip.split(":")
            port = int(port)
        else:
            port = int(input("Port: "))

        c.connect(ip, port)
        c.start_talking()
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    main()
