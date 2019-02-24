import sys
import time
import argparse
import threading
import queue
import socket
import bencode
import tools

class PeerList:
    def __init__(self):
        self.peers = []
        self.update_event = threading.Event()
    
    def get_list(self):
        return self.peers

    def get_address(self, username):
        for p in self.peers:
            if p["username"] == username:
                return (p["ipv4"], p["port"])
        return None

    def update(self, updated_list):
        self.peers.clear()
        for p in updated_list:
            self.peers.append(p)
        self.update_event.set()
        self.update_event.clear()

class PacketQueue:
    def __init__(self):
        self.send_queue = queue.Queue()
        self.ack_queue = [] # TODO MUTEX

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
            return 

    def queue_ack(self, message):
        message["timestamp"] = time.time()
        self.ack_queue.append(message)

    def pop_ack(self, txid):
        for a in self.ack_queue:
            # lock it
            if a["packet"]["txid"] == txid:
                self.ack_queue.remove(a)
                return True
            # unlock it
        return False

class TimerThread(threading.Thread):
    def __init__(self, socket, packet_queue):
        super(TimerThread, self).__init__()
        # TODO

class HelloThread(threading.Thread):
    def __init__(self, packet, node, packet_queue):
        super(HelloThread, self).__init__()
        self.packet = packet
        self.node = node
        self.packet_queue = packet_queue
        self.stop_event = threading.Event()
        
    def run(self):
        while not self.stop_event.is_set():
            self.packet["txid"] = tools.generate_txid()
            self.packet_queue.queue_message(self.packet, self.node)
            self.stop_event.wait(10)
        self.packet["txid"] = tools.generate_txid()
        self.packet["ipv4"] = "0.0.0.0"
        self.packet["port"] = 0
        self.packet_queue.queue_message(self.packet, self.node)

class SendThread(threading.Thread):
    def __init__(self, socket, packet_queue):
        super(SendThread, self).__init__()
        self.socket = socket
        self.packet_queue = packet_queue
        self.stop_event = threading.Event()

    def run(self):
        while not self.stop_event.is_set():
            message = self.packet_queue.pop_message()
            if message is not None:
                tools.dbg_print("Sending: " + message["packet"] + "\nTo: " + message["address"])
                self.socket.sendto(bencode.encode(message["packet"]), message["address"])
            else
                self.stop_event.wait(0.1)

class ListenThread(threading.Thread):
    def __init__(self, socket, packet_queue, peer_list):
        super(ListenThread, self).__init__()
        self.socket = socket
        self.packet_queue = packet_queue
        self.peer_list = peer_list

    def run(self):
        while True:
            message = self.recieve()
            if message == "stop":
                break
            if message is False:
                continue

            if message["type"] == "list":
                self.process_list(message)
            elif message["type"] == "message":
                self.process_message(message)
            elif message["type"] == "ack":
                self.packet_queue.pop_ack(message["txid"])
            else:
                tools.err_print("Error: Unexpected packet of type '{}'".format(message["type"]))

    def recieve(self):
        try:
            data, address = self.socket.recvfrom(4096)
        except OSError as err:
            tools.err_print("OS error: {0}".format(err))
            return tools.ERR_FATAL
        if data == "stop":
            return "stop"
        return self.check_data(data, address)

    def check_data(self, data, sender):
        try:
            packet = bencode.decode(data)
        except Exception:
            self.send_error("The packet could not be decoded.", sender)
            return False
        if type(packet) is not dict:
            self.send_error("Wrong packet format. Expected json.", sender)
            return False
        if not all(f in ("type", "txid") for f in packet):
            self.send_error("Missing fields in packet. Expected at least 'type' and 'txid'.", sender)
            return False

        if packet["type"] == "error":
            if "verbose" in packet:
                tools.err_print("Error: " + packet["verbose"])
            else:
                tools.err_print("Unknown error.")
            return False
        
        packet["address"] = sender
        return packet

    def process_list(self, message):
        if not "peers" in message:
            self.send_error("Missing 'peers' field in packet of type 'list'.", message["address"])
            return False
        peers = packet["peers"]
        if not type(peers) == dict:
            self.send_error("Invalid contents of 'peers' field.", message["address"])
            return False
        # TODO peer record format check

        ack = PeerDaemon.create_packet("ack")
        ack["txid"] = message["txid"]
        self.packet_queue.queue_message(ack, message["address"])
        self.peer_list.update(peers)

    def process_message(self, message):
        if not all(f in ("from", "to", "message") for f in message):
            self.send_error("Missing fields in 'message' packet. Expected 'from', 'to' and 'message'.", sender)
            return False
        # TODO check if we are the correct recipient
        print("{frm}: {msg}".format(frm = message["from"], msg = message["message"]))

    def send_error(self, message, recipient):
        self.packet_queue.queue_message(PeerDaemon.create_packet("error", verbose = message), recipient)

class MessageThread(threading.Thread):
    def __init__(self, message, peerlist, send_thread):
        super(MessageThread, self).__init__()
        self.message = message
        self.peerlist = peerlist
        self.send_thread = send_thread

    def run(self):
        pass # TODO

    def send_message(self):
        address = self.find_peer_address(self.message["to"])
        if address == None:
            tools.err_print("Error: No peer with username '" + self.message["to"] + "' found.")
            return tools.ERR_FATAL

        tools.dbg_print("sending message")
        self.socket.sendto(bencode.encode(self.message), address)
        response = self.recieve()
        if type(response) is int:
            return response

        if response["type"] == "ack":
            if response["txid"] == self.message["txid"]:
                tools.dbg_print("everything went fine")
                return tools.OK
            self.send_error("Unexpected acknowledgement for transaction " + str(response["txid"]) + ".", response["address"])
        return tools.ERR_RECOVER

class PeerDaemon:
    def __init__(self, info):
        self.info = info
        self.hello_packet = PeerDaemon.create_packet("hello",
            username = info.username, ipv4 = str(self.info.chat_ipv4), port = self.info.chat_port)
        self.peerlist = PeerList()

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((self.info.char_ipv4, self.info.chat_port))
        self.packet_queue = PacketQueue()
        self.timer_thread = TimerThread()

        # self.listen_thread = ListenThread(self.socket, self)
        # self.send_thread = SendThread(self.socket, self)
        self.hello_thread = HelloThread(self.hello_packet, (str(self.info.reg_ipv4), self.info.reg_port), self.packet_queue)
        # self.listen_thread.start()
        # self.send_thread.start()
        self.hello_thread.start()

    def send_message(self, sender, recipient, message):
        # what to do with sender?
        message_thread = MessageThread(PeerDaemon.create_packet("message", fro = self.info.username, to = recipient, message = message), self.peerlist, self.send_thread)
        message_thread.start()
        return True

    def update_peer_list(self):
        self.send_thread.queue(PeerDaemon.create_packet("getlist"))
        return True

    def get_peer_list(self):
        return self.peerlist.get_list()
    
    def change_reg_node(self, ip_address, port):
        self.hello_thread.stop_event.set()
        self.info.reg_ipv4 = ip_address
        self.info.reg_port = port
        self.hello_thread.join()
        self.hello_thread = HelloThread(self.hello_packet, (self.info.reg_ipv4, self.info.reg_port), self.packet_queue)
        self.hello_thread.start()
        return True

    @staticmethod
    def create_packet(ptype, fro = None, to = None, message = None, username = None, ipv4 = None, port = None, verbose = None):
        packet = {"type": ptype, "txid": tools.generate_txid()}
        if not fro == None:
            packet["from"] = fro
            packet["to"] = to
            packet["message"] = message
        if not username == None:
            packet["username"] = username
            packet["ipv4"] = ipv4
            packet["port"] = port
        if not verbose == None:
            packet["verbose"] = verbose
        return packet

    def finish(self):
        self.hello_thread.stop_event.set()
        # TODO wait for 0 HELLO is sent after finish
        # self.send_thread.stop_event.set()
        # self.listen_thread.stop_event.set()
        self.hello_thread.join()
        # self.send_thread.join()
        # self.listen_thread.join()
        self.socket.close() 

def main():
    parser = argparse.ArgumentParser(description="Peer Daemon for PDS18 P2P Chat")
    parser.add_argument("-i", "--id", type = tools.id_check, required = True, metavar = "<id>",
        help = "unique id of the peer")
    parser.add_argument("-u", "--username", required = True, metavar = "<username>",
        help = "unique username of the peer")

    parser.add_argument("-ci", "--chat-ipv4", type = tools.ip_check, required = True, metavar = "<ip addr>",
        help = "IP address on which the chat peer should listen for messages")
    parser.add_argument("-cp", "--chat-port", type = tools.port_check, required = True, metavar = "<port>",
        help = "port on which the chat peer should listen for messages")

    parser.add_argument("-ri", "--reg-ipv4", type = tools.ip_check, required = True, metavar = "<ip addr>",
        help = "IP address of registration node")
    parser.add_argument("-rp", "--reg-port", type = tools.port_check, required = True, metavar = "<port>",
        help = "port on which registration node listens for connections")
    args = parser.parse_args()
    daemon = PeerDaemon(args)
    try:
        tools.run_server(daemon, args.id % 19991 + 10000)
    except KeyboardInterrupt:
        tools.err_print("\nStopping daemon...")
        daemon.finish()
        tools.err_print("Bye.")

if __name__ == "__main__":
    main()
