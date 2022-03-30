# Internet-Voicechat
Barebones voicechat over the internet, using sockets, pyFLAC as an encoder, and pyaudio.

TO DO:

- TLS 1.3 Secure connection or encrypt the audio. -> Involves getting a private key and a CA cert. 
- Metadata prepended onto a packet for metadata/different types of data instead of just audio data. 

TO USE:

Instantiate a Server object on the server's machine and start the server with the start_server() method, which takes in a ip/hostname (str) and a port (int).  

Instantiate a Client object on the client's machine and connect with the server with the connect() method. Then begin talking with the start_talking() method.
