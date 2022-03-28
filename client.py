import config
import logging
import numpy
import pyaudio
import pyflac
import queue
import threading
import time
import traceback
import select
import socket

logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(levelname)s:\t%(message)s',
    level=logging.INFO,
    datefmt='%H:%M:%S')


class AudioHandler:

    # AudioHandler class takes care of the audio IO.

    # 1 thread for the audio output, the rest is taken care by callback functions.

    def __init__(self, outgoing_buffer, incoming_buffer):
        self._pa_obj = pyaudio.PyAudio()
        self._encoder = pyflac.StreamEncoder(write_callback=self._encoder_callback, sample_rate=config.SAMPLE_RATE)
        self._decoder = pyflac.StreamDecoder(write_callback=self._decoder_callback)
        self._stream = None

        self._outgoing_buffer = outgoing_buffer
        self._incoming_buffer = incoming_buffer

        self._aud_out_flag = threading.Event()
        self._aud_out_thread = threading.Thread(target=self._audio_out_loop,
                                               args=(self._decoder, self._incoming_buffer, self._aud_out_flag))

    def start(self):
        self._stream = self._pa_obj.open(
            format=config.AUDIO_FORMAT,
            channels=config.CHANNELS,
            rate=config.SAMPLE_RATE,
            input=True,
            output=True,
            stream_callback=self._audio_callback
        )
        self._aud_out_thread.start()

    def stop(self):

        self._aud_out_flag.set()
        self._aud_out_thread.join()

        self._stream.stop_stream()
        self._stream.close()

    @staticmethod
    def _audio_out_loop(decoder, _queue, t_flag):
        while t_flag.is_set():
            try:
                decoder.process(_queue.get(block=False, timeout=config.DECODER_TIMEOUT))
                # Making the queue.get() method non-blocking so if the thread needs to be terminated, it can be.
            except queue.Empty:
                logging.info("Time out on decoder.")

    def _audio_callback(self, in_data, frame_count, time_info, status):
        data = numpy.frombuffer(in_data, dtype=config.NUMPY_AUDIO_FORMAT)
        self._encoder.process(data)
        return in_data, pyaudio.paContinue

    def _encoder_callback(self, buffer, num_bytes, num_samples, current_frame):
        self._outgoing_buffer.put(buffer)

    def _decoder_callback(self, data, sample_rate, num_channels, num_samples):
        self._stream.write(data)


class Client:
    def __init__(self):
        # Client class handles the internet IO, and passes the audio data to the AudioHandler class.

        self._outgoing_buffer = queue.Queue()
        self._incoming_buffer = queue.Queue()
        self._audio_handler = AudioHandler(self._outgoing_buffer, self._incoming_buffer)

        self._socket = None
        self._is_connected = False

        self._internet_io_flag = threading.Event()
        self._internet_thread = threading.Thread(target=self._internet_io,
                                                 args=(self._socket, self._outgoing_buffer,
                                                       self._incoming_buffer, self._internet_io_flag))

    @staticmethod
    def _internet_io(_socket, outgoing_buffer, incoming_buffer, t_flag):
        while t_flag.is_set():
            readable, writable, exceptional = select.select([_socket], [_socket], [_socket])

            if readable:
                incoming_buffer.put(_socket.recv(config.PACKET_SIZE))

            if writable and outgoing_buffer.qsize() > 0:
                _socket.send(outgoing_buffer.get())

            if exceptional:
                logging.info("Disconnected!")
                break

    def connect(self, ip, port):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # Putting the socket here so if the
        # socket closes, a new socket instance can be made on method call.

        self._is_connected = False

        try:
            self._socket.connect((ip, port))
            self._socket.setblocking(False)
            self._socket.settimeout(config.SOCKET_TIMEOUT)
            self._is_connected = True

        except ConnectionRefusedError as error:
            logging.info(error)

    def start_talking(self):

        if self._is_connected:
            self._audio_handler.start()
            self._internet_thread.start()
        else:
            logging.info("Not connected to a socket!")

    def stop_talking(self):
        self._audio_handler.stop()
        
