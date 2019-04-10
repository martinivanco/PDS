import sys
import argparse
import uuid
import queue
import threading
import ipaddress
import bencode
import time
import logging
from xmlrpc.server import SimpleXMLRPCServer
from xmlrpc.server import SimpleXMLRPCRequestHandler
from xmlrpc.client import ServerProxy

class RequestHandler(SimpleXMLRPCRequestHandler):
    rpc_paths = ('/RPC2',)

class PacketQueue:
    def __init__(self):
        self.send_queue = queue.Queue()
        self.ack_queue = []
        self.ack_queue_lock = threading.Lock()
        self.queue_event = threading.Event()

    def empty(self):
        with self.ack_queue_lock:
            return len(self.ack_queue) == 0 and self.send_queue.qsize() == 0

    def queue_message(self, packet, address, attempts = 1, timeout = 0, last_chance = 0, ack_event = None):
        self.send_queue.put({"packet": packet, "address": address,
            "attempts": attempts, "timeout": timeout, "last_chance": last_chance, "ack_event": ack_event})
        self.queue_event.set()
    
    def pop_message(self):
        if self.send_queue.qsize() == 0:
            return None
        else:
            message = self.send_queue.get()
            if self.send_queue.qsize() == 0:
                self.queue_event.clear()
            if message["timeout"] > 0:
                self.queue_ack(message)
            return message

    def queue_ack(self, message):
        message["timestamp"] = time.time()
        with self.ack_queue_lock:
            self.ack_queue.append(message)
        timer = threading.Timer(message["timeout"], self.check_ack, args=(message,))
        timer.start()

    def pop_ack(self, txid):
        with self.ack_queue_lock:
            for a in self.ack_queue:
                if a["packet"]["txid"] == txid:
                    try:
                        self.ack_queue.remove(a)
                    except ValueError:
                        return None
                    return a
            return None

    def check_ack(self, message):
        if self.pop_ack(message["packet"]["txid"]) is not None:
            message["attempts"] -= 1
            if message["attempts"] == 1 and message["last_chance"] != 0:
                err_print("ERROR: ACK for packet {} timed out. Performing triple resend.".format(message["packet"]["txid"]))
                for x in range(message["last_chance"]):
                    self.queue_message(message["packet"], message["address"])
                return
            if message["attempts"] > 0:
                err_print("ERROR: ACK for packet {} timed out. Trying again.".format(message["packet"]["txid"]))
                self.queue_message(message["packet"], message["address"], message["attempts"], message["timeout"], message["last_chance"])
            else:
                err_print("ERROR: ACK for packet {} timed out.".format(message["packet"]["txid"]))

class SendThread(threading.Thread):
    def __init__(self, socket, packet_queue):
        super(SendThread, self).__init__()
        self.socket = socket
        self.packet_queue = packet_queue
        self.stop_event = threading.Event()

    def run(self):
        while not (self.stop_event.is_set() and self.packet_queue.empty()):
            self.packet_queue.queue_event.wait()
            message = self.packet_queue.pop_message()
            if not message == None:
                dbg_print("Sending: {msg}\nTo: {to}\n- - - - - - - - - -".format(msg = message["packet"], to = message["address"]))
                try:
                    self.socket.sendto(bencode.encode(message["packet"]), message["address"])
                except OSError as err:
                    err_print("OS error: {0}".format(err))

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
            self.send_error(generate_txid(), "The packet could not be decoded.", sender)
            return False
        if type(packet) is not dict:
            self.send_error(generate_txid(), "Wrong packet format. Expected json.", sender)
            return False
        if not all(f in packet for f in ("type", "txid")):
            self.send_error(generate_txid(), "Missing fields in packet. Expected at least 'type' and 'txid'.", sender)
            return False
        dbg_print("Recieved: {msg}\nFrom: {frm}\n- - - - - - - - - -".format(msg = packet, frm = sender))
        if packet["type"] == "error":
            self.packet_queue.pop_ack(packet["txid"])
            if "verbose" in packet:
                err_print("Error: " + packet["verbose"])
            else:
                err_print("Unknown error.")
            return False
        
        packet["address"] = sender
        return packet

    def send_error(self, txid, message, recipient):
        packet = create_packet("error", verbose = message)
        packet["txid"] = txid
        self.packet_queue.queue_message(packet, recipient)

def run_server(daemon, port):
    with SimpleXMLRPCServer(('localhost', port), requestHandler = RequestHandler, logRequests = False) as server:
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

def create_packet(ptype, fro = None, to = None, message = None, username = None, ipv4 = None, port = None, peers = None, db = None, verbose = None):
    packet = {"type": ptype, "txid": generate_txid()}
    if not fro == None:
        packet["from"] = fro
        packet["to"] = to
        packet["message"] = message
    if not username == None:
        packet["username"] = username
        packet["ipv4"] = ipv4
        packet["port"] = port
    if not peers == None:
        packet["peers"] = peers
    if not db == None:
        packet["db"] = db
    if not verbose == None:
        packet["verbose"] = verbose
    return packet

def err_print(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

def dbg_print(sentence):
    print(sentence)