import sys
import argparse
import uuid
import queue
import threading
import ipaddress
import bencode
from xmlrpc.server import SimpleXMLRPCServer
from xmlrpc.server import SimpleXMLRPCRequestHandler
from xmlrpc.client import ServerProxy

ERR_FATAL = 4
ERR_RECOVER = 1
OK = 2

class RequestHandler(SimpleXMLRPCRequestHandler):
    rpc_paths = ('/RPC2',)

class PacketQueue:
    def __init__(self):
        self.send_queue = queue.Queue()
        self.ack_queue = []
        self.ack_queue_lock = threading.Lock()

    def queue_message(self, packet, address, attempts = 1, timeout = 0):
        self.send_queue.put({"packet": packet, "address": address,
            "attempts": attempts, "timeout": timeout})
    
    def pop_message(self):
        if self.send_queue.empty():
            return None
        else:
            message = self.send_queue.get()
            if message["timeout"] > 0:
                self.queue_ack(message)
            return message

    def queue_ack(self, message):
        message["timestamp"] = time.time()
        self.ack_queue_lock.acquire() # TODO really forever?
        self.ack_queue.append(message["txid"])
        self.ack_queue_lock.release()
        timer = threading.Timer(message["timeout"], self.check_ack, message)
        timer.start()

    def pop_ack(self, txid):
        for a in self.ack_queue:
            if a == txid:
                self.ack_queue_lock.acquire() # TODO really forever?
                try:
                    self.ack_queue.remove(a)
                except ValueError:
                    return False
                self.ack_queue_lock.release()
                return True
        return False

    def check_ack(self, message):
        if self.pop_ack(message["txid"]):
            message["attempts"] -= 1
            if message["attempts"] > 0:
                self.queue_message(message["packet"], message["address"], message["attempts"], message["timeout"])

class SendThread(threading.Thread):
    def __init__(self, socket, packet_queue):
        super(SendThread, self).__init__()
        self.socket = socket
        self.packet_queue = packet_queue
        self.stop_event = threading.Event()

    def run(self):
        while not self.stop_event.is_set():
            message = self.packet_queue.pop_message()
            if not message == None:
                dbg_print("Sending: {msg}\nTo: {to}\n- - - - - - - - - -".format(msg = message["packet"], to = message["address"]))
                try:
                    self.socket.sendto(bencode.encode(message["packet"]), message["address"])
                except OSError as err:
                    err_print("OS error: {0}".format(err))
            else:
                self.stop_event.wait(0.1) # TODO Make this cleaner

class ListenThread(threading.Thread):
    def __init__(self, socket, packet_queue):
        super(ListenThread, self).__init__()
        self.socket = socket
        self.packet_queue = packet_queue

    def run(self):
        pass

    def recieve(self):
        try:
            data, address = self.socket.recvfrom(4096)
        except OSError as err:
            err_print("OS error: {0}".format(err))
            return False
        if data == bytes("stop", "utf-8"):
            return "stop"
        return self.check_data(data, address)

    def check_data(self, data, sender):
        try:
            packet = bencode.decode(data)
        except Exception:
            self.send_error("The packet could not be decoded.", sender)
            return False
        if not type(packet) is dict:
            self.send_error("Wrong packet format. Expected json.", sender)
            return False
        if not all(f in ("type", "txid") for f in packet):
            self.send_error("Missing fields in packet. Expected at least 'type' and 'txid'.", sender)
            return False
        dbg_print("Recieved: {msg}\nFrom: {frm}\n- - - - - - - - - -".format(msg = packet, frm = sender))
        if packet["type"] == "error": # TODO ERROR -> ACK
            if "verbose" in packet:
                err_print("Error: " + packet["verbose"])
            else:
                err_print("Unknown error.")
            return False
        
        packet["address"] = sender
        return packet

    def send_error(self, message, recipient):
        self.packet_queue.queue_message(PeerDaemon.create_packet("error", verbose = message), recipient)

def run_server(daemon, port):
    with SimpleXMLRPCServer(('localhost', port), requestHandler = RequestHandler) as server:
        server.register_instance(daemon)
        server.serve_forever()

def get_stub(port):
    return ServerProxy('http://localhost:' + str(port))

def id_check(value):
    msg = "%r is not a valid id - must be a positive integer" % value
    try:
        id_val = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(msg)
    if id_val <= 0:
        raise argparse.ArgumentTypeError(msg)
    return id_val

def ip_check(value):
    msg = "%r is not a valid IPv4 address" % value
    try:
        ip_val = ipaddress.ip_address(value)
    except ValueError:
        raise argparse.ArgumentTypeError(msg)
    if ip_val.version != 4:
        raise argparse.ArgumentTypeError(msg)
    return ip_val

def port_check(value):
    msg = "%r is not a valid port" % value
    try:
        port_val = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(msg)
    if port_val < 0 or port_val > (2**16 - 1):
        raise argparse.ArgumentTypeError(msg)
    return port_val

def generate_txid():
    return uuid.uuid4().int & 0xffff

def err_print(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

def dbg_print(sentence):
    print(sentence)