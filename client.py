import logging
import queue
import socket
import threading
import traceback

import numpy
import pyflac
import select
import sounddevice as sd

import config

logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(levelname)s:\t%(message)s',
    level=logging.INFO,
    datefmt='%H:%M:%S')


class _AudioHandler:

    # _AudioHandler class takes care of the audio IO.
    # No user-threads required! All handled by callback functions.

    # TO-DO:
    # - switch to UDP
    # - add headers to packets (problem since the send and recv funcs decide what they like and send
    # packets of varying sizes.)

    def __init__(self, outgoing_buffer, incoming_buffer, audio_devices=None):

        if audio_devices:
            sd.default.device = audio_devices

        self._stream = self._stream = sd.RawStream(samplerate=config.SAMPLE_RATE,
                                                   blocksize=config.PACKET_SIZE,
                                                   channels=config.CHANNELS,
                                                   dtype=numpy.int16,
                                                   callback=self._audio_callback)

        self._encoder = pyflac.StreamEncoder(write_callback=self._encoder_callback, sample_rate=config.SAMPLE_RATE,
                                             blocksize=config.PACKET_SIZE)
        self._decoder = pyflac.StreamDecoder(write_callback=self._decoder_callback)

        self._outgoing_buffer = outgoing_buffer
        self._incoming_buffer = incoming_buffer

        self._is_muted = False

    def _audio_callback(self, in_data, out_data, *_) -> None:
        if not self._is_muted:
            self._encoder.process(numpy.frombuffer(in_data, dtype=numpy.int16))

        if self._incoming_buffer.qsize() > 0:
            data = self._incoming_buffer.get(block=False)
            out_data[:] = data.tobytes()

        elif self._incoming_buffer.qsize() == 0:
            out_data[:] = bytes(config.PACKET_SIZE * 2)

    def _encoder_callback(self, buffer, *_):
        self._outgoing_buffer.put(buffer)  # buffer is a built-in bytes object.

    def _decoder_callback(self, data, *_):
        self._incoming_buffer.put(data)

    def _toggle_mute(self):
        self._outgoing_buffer.queue.clear()  # this is for when muting, some packets haven't returned yet and will play
        #  once un-muted from the buffer. Since I haven't implemented a UDP system where each packet is timestamped and
        #  reconstructed chronologically (hence dropping older packets and making this issue moot), 
        #  this will have to do. 
        self._is_muted = False if self._is_muted else True

    def start(self):
        self._incoming_buffer.queue.clear()
        self._outgoing_buffer.queue.clear()
        self._stream.start()

    def stop(self):
        self._stream.stop()


class Client:
    def __init__(self, default_audio_devices=None):

        # Client class handles the internet IO, and passes the audio data to the AudioHandler class.

        """
        :param default_audio_devices: Query by name or index, the audio devices to be used. Use get_sound_devices() method to list all audio devices.

        Client class that handles audio and internet IO.
        """
        self._is_muted = threading.Event()
        self._outgoing_buffer = queue.Queue()
        self._incoming_buffer = queue.Queue()
        self._audio_handler = _AudioHandler(self._outgoing_buffer, self._incoming_buffer,
                                            audio_devices=default_audio_devices)

        self._socket = None
        self._is_connected = False

        self._internet_io_flag = threading.Event()
        self._internet_thread = None

    def _internet_io(self, ):

        while not self._internet_io_flag.is_set():
            try:
                readable, writable, exceptional = select.select([self._socket], [self._socket], [self._socket])
            except ValueError:
                logging.info("Disconnect!")
                break

            if readable:
                try:
                    data = self._socket.recv(config.PACKET_SIZE)
                    # data, header = self._read_header(packed_data)
                    self._audio_handler._decoder.process(data)  # messy but since the callback audio func only runs
                    # whenever it has enough samples of audio to send, the audio needs to be processed by the time it
                    # does a callback.

                except ConnectionResetError:
                    logging.error("Disconnected!")
                    break

                except TimeoutError:
                    logging.error(f"Timed out! {traceback.format_exc()}")

            if writable and self._outgoing_buffer.qsize() > 0:
                data = self._outgoing_buffer.get()
                try:
                    self._socket.send(data)

                except ConnectionResetError:
                    logging.info("Disconnected!")
                    break

            if exceptional:
                logging.info("Disconnected!")
                break

    @staticmethod
    def _add_header(data, metadata):
        return bytearray(f"{metadata:<{config.HEADER_SIZE}}", "utf-8") + bytearray(data)

    @staticmethod
    def _read_header(data):
        return bytes(data[config.HEADER_SIZE:]), data[:config.HEADER_SIZE].decode("utf-8", errors="ignore")

    @staticmethod
    def get_sound_devices(*args):
        return sd.query_devices(*args)

    def connect(self, ip: str, port: int) -> bool:
        """
        :param ip: IP/Hostname of the server.
        :param port: Port of the server.
        :return: Boolean if the client is successfully connected.
        """

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # Putting the socket here so if the
        # socket closes, a new socket instance can be made on method call.

        self._internet_io_flag.clear()
        self._internet_thread = threading.Thread(target=Client._internet_io, args=(self,), daemon=True)
        self._internet_thread.start()

        self._is_connected = False
        logging.info(f"Connecting to {ip}: {port}...")

        try:
            self._socket.connect((ip, int(port)))
            self._socket.setblocking(False)
            self._socket.settimeout(config.SOCKET_TIMEOUT)
            self._is_connected = True

            logging.info("Connected!")

        except ConnectionRefusedError as error:
            logging.info(error)

        return self._is_connected

    def disconnect(self):
        if self._is_connected:
            self._audio_handler.stop()
            self._internet_io_flag.set()
            self._socket.close()
            self._is_connected = False
        else:
            logging.info("Not connected to a socket!")

    def start_talking(self):

        if self._is_connected:
            self._audio_handler.start()
        else:
            logging.info("Not connected to a socket!")

    def stop_talking(self):
        self._audio_handler.stop()

    def toggle_mute(self):
        self._audio_handler._toggle_mute()
