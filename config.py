import pyaudio

AUDIO = {
    "FORMAT": pyaudio.paInt16,
    "CHANNELS": 1,
    "SAMPLE RATE": 44100,
    "CHUNK": 1024
}

SOCKET_TIMEOUT = 0.05
MAX_JOIN = 4
PORT = 1234
