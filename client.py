import logging
import queue
import socket
import threading

import numpy
import pyflac
import select
import sounddevice as sd

import config

logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(levelname)s:\t%(message)s',
    level=logging.INFO,
    datefmt='%H:%M:%S')


class AudioHandler:

    # AudioHandler class takes care of the audio IO.
    # No user-threads required! All handled by callback functions.

    def __init__(self, outgoing_buffer, incoming_buffer, audio_devices=None):

        if audio_devices:
            sd.default.device = audio_devices

        self._stream = sd.RawStream(samplerate=config.SAMPLE_RATE,
                                    blocksize=config.PACKET_SIZE,
                                    channels=config.CHANNELS,
                                    dtype=numpy.int16,
                                    callback=self._audio_callback)

        self._encoder = pyflac.StreamEncoder(write_callback=self._encoder_callback, sample_rate=config.SAMPLE_RATE,
                                             blocksize=config.PACKET_SIZE)
        self._decoder = pyflac.StreamDecoder(write_callback=self._decoder_callback)

        self._outgoing_buffer = outgoing_buffer
        self._incoming_buffer = incoming_buffer

        self._out_buf = None

    def _audio_callback(self, in_data, out_data, *_) -> None:
        self._encoder.process(numpy.frombuffer(in_data, dtype=numpy.int16))

        if self._incoming_buffer.qsize() > 0:
            data = self._incoming_buffer.get(block=False)
            out_data[:] = data.tobytes()

    def _encoder_callback(self, buffer, *_):
        self._outgoing_buffer.put(buffer)  # buffer is a built-in bytes object.

    def _decoder_callback(self, data, *_):
        self._incoming_buffer.put(data)

    def start(self):
        self._stream.start()

    def stop(self):
        self._stream.stop()
        self._stream.close()


class Client:
    def __init__(self, default_audio_devices=None):

        # Client class handles the internet IO, and passes the audio data to the AudioHandler class.

        self._outgoing_buffer = queue.Queue()
        self._incoming_buffer = queue.Queue()
        self._audio_handler = AudioHandler(self._outgoing_buffer, self._incoming_buffer,
                                           audio_devices=default_audio_devices)

        self._socket = None
        self._is_connected = False

        self._internet_io_flag = threading.Event()
        self._internet_thread = threading.Thread(target=Client._internet_io, args=(self,), daemon=False)

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
                    self._audio_handler._decoder.process(data)  # messy but since the callback audio func only runs
                    # whenever it has enough samples of audio to send, the audio needs to be processed by the time it
                    # does a callback.

                except ConnectionResetError:
                    logging.info("Disconnected!")
                    break

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
    def _add_header(buffer, metadata):
        return bytearray(f"{metadata:<{config.HEADER_SIZE}}") + bytearray(buffer)

    @staticmethod
    def get_sound_devices():
        return sd.query_devices()

    def connect(self, ip: str, port: int) -> bool:
        """
        :param ip: IP/Hostname of the server.
        :param port: Port of the server.
        :return: Boolean if the client is successfully connected.
        """

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # Putting the socket here so if the
        # socket closes, a new socket instance can be made on method call.

        self._is_connected = False
        logging.info(f"Connecting to {ip}: {port}...")

        try:
            self._socket.connect((ip, port))
            self._socket.setblocking(False)
            self._socket.settimeout(config.SOCKET_TIMEOUT)
            self._is_connected = True

            logging.info("Connected!")

        except ConnectionRefusedError as error:
            logging.info(error)

        return self._is_connected

    def disconnect(self):
        if self._is_connected:
            self._socket.close()
            self._is_connected = False
        else:
            logging.info("Not connected to a socket!")

    def start_talking(self):

        if self._is_connected:
            self._audio_handler.start()
            self._internet_thread.start()
        else:
            logging.info("Not connected to a socket!")

    def stop_talking(self):
        self._audio_handler.stop()
