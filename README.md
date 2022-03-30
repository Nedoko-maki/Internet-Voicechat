# Internet-Voicechat
Barebones voicechat over the internet, using sockets, pyFLAC as an encoder, and pyaudio.

TO DO:

- TLS 1.3 Secure connection or encrypt the audio. -> Involves getting a private key and a CA cert. 
- Metadata prepended onto a packet for metadata/different types of data instead of just audio data. 
