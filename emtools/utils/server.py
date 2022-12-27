import sys
import json
import time
import traceback
import threading
import socket
from socketserver import BaseRequestHandler, ThreadingTCPServer
from datetime import datetime

from .pretty import Pretty


def send_object(s, obj):
    """ Send an object serialized as json. """
    objstr = json.dumps(obj)
    return s.sendall(bytes(objstr, encoding='utf-8'))


def recv_object(s, verbose=False):
    chunk = s.recv(4096)
    received = bytearray(chunk)
    while len(chunk) == 4096:
        chunk = s.recv(4096)
        if chunk:
            received.extend(chunk)

    if verbose:
        print(f"Received {len(received)} bytes")

    if not len(received):
        return None

    data = received.decode("utf-8")
    print(f"data: {data}")
    obj = json.loads(data)
    return obj


class JsonRequestHandler(BaseRequestHandler):

    def handle(self):
        obj = recv_object(self.request, verbose=True)
        if obj is None:
            return

        print(f"Received request from...{self.client_address[0]}, obj: {obj}, type: {type(obj)}")
        try:
            method = obj['method']
            args = obj.get('args', [])
            kwargs = obj.get('kwargs', {})
            function = getattr(self.server, method)
            result = function(*args, **kwargs) or {}
            r = {'result': result}
        except Exception as e:

            print(traceback.format_exc())
            r = {'error': 'Wrong input object'}
        send_object(self.request, r)


class JsonTCPServer(ThreadingTCPServer):
    def __init__(self, address):
        self._address = address
        self._refresh = 10  # 10 seconds by default
        self._starttime = None
        ThreadingTCPServer.__init__(self, address, JsonRequestHandler)

    def serve_forever(self, *args, **kwargs):
        print(f"Running server\n\taddress: {self._address}"
              f"\n\trefresh: {self._refresh} seconds")
        # Start a thread with the server -- that thread will then start one
        # more thread for each request
        update_thread = threading.Thread(target=self.__update_loop)
        update_thread.daemon = True
        update_thread.start()
        self._starttime = datetime.now()
        ThreadingTCPServer.serve_forever(self, *args, **kwargs)

    def __update_loop(self):
        while True:
            print(f"Service actions...{Pretty.now()}")
            time.sleep(self._refresh)

    def status(self):
        return {
            'address': f"{self._address}",
            'start_time': Pretty.datetime(self._starttime),
            'uptime': Pretty.delta(datetime.now() - self._starttime)
        }

    def set_refresh(self, seconds):
        self._refresh = seconds
        print(f"Setting refresh to {seconds} seconds.")


class JsonTCPClient:
    def __init__(self, address, verbose=False):
        self._address = address
        self._verbose = verbose

    def test(self):
        """ Test connection with the server. """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(3)
                sock.connect(self._address)
            return True
        except:
            return False

    def call(self, method, *args, **kwargs):
        obj = {
            'method': method,
            'args': args,
            'kwargs': kwargs
        }
        response = None
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect(self._address)
            send_object(sock, obj)
            response = recv_object(sock, verbose=self._verbose)
            if self._verbose:
                print("Received: {}".format(response))
        return response


if __name__ == "__main__":
    is_server = '--server' in sys.argv
    # Port 0 means to select an arbitrary unused port
    HOST, PORT = "localhost", 5555

    if is_server:
        with JsonTCPServer((HOST, PORT)) as server:
            server.serve_forever()
    else:
        ip, port = HOST, PORT
        obj = json.loads(sys.argv[1])
        client = JsonTCPClient((ip, port))
        client.call(obj['method'], *obj['args'], **obj['kwargs'])
