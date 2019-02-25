import sys
import time
import argparse
import threading
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

class ListenThread(threading.Thread):
    def __init__(self, socket, packet_queue, peerlist):
        super(ListenThread, self).__init__()
        self.socket = socket
        self.packet_queue = packet_queue
        self.peerlist = peerlist

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
        tools.dbg_print("Recieved: {msg}\nFrom: {frm}\n- - - - - - - - - -".format(msg = packet, frm = sender))
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
        self.peerlist.update(peers)

    def process_message(self, message):
        if not all(f in ("from", "to", "message") for f in message):
            self.send_error("Missing fields in 'message' packet. Expected 'from', 'to' and 'message'.", sender)
            return False
        # TODO check if we are the correct recipient
        print("{frm}: {msg}".format(frm = message["from"], msg = message["message"]))

    def send_error(self, message, recipient):
        self.packet_queue.queue_message(PeerDaemon.create_packet("error", verbose = message), recipient)

class MessageThread(threading.Thread):
    def __init__(self, message, packet_queue, peerlist, node):
        super(MessageThread, self).__init__()
        self.message = message
        self.packet_queue = packet_queue
        self.peerlist = peerlist
        self.node = node

    def run(self):
        self.packet_queue.queue_message(PeerDaemon.create_packet("getlist"), self.node, 2, 2)
        if self.peerlist.update_event.wait(5):
            address = self.peerlist.get_address(self.message["to"])
            if not address == None:
                self.packet_queue.queue_message(self.message, address, 2, 2)

class PeerDaemon:
    def __init__(self, info):
        self.info = info
        self.hello_packet = PeerDaemon.create_packet("hello",
            username = info.username, ipv4 = str(self.info.chat_ipv4), port = self.info.chat_port)
        self.peerlist = PeerList()

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((str(self.info.chat_ipv4), self.info.chat_port))
        self.packet_queue = tools.PacketQueue()

        self.listen_thread = ListenThread(self.socket, self.packet_queue, self.peerlist)
        self.send_thread = tools.SendThread(self.socket, self.packet_queue)
        self.hello_thread = HelloThread(self.hello_packet, (str(self.info.reg_ipv4), self.info.reg_port), self.packet_queue)
        self.listen_thread.start()
        self.send_thread.start()
        self.hello_thread.start()

    def send_message(self, sender, recipient, message):
        # what to do with sender?
        message_thread = MessageThread(PeerDaemon.create_packet("message", fro = self.info.username, to = recipient, message = message),
            self.packet_queue, self.peerlist, (self.info.reg_ipv4, self.info.reg_port))
        message_thread.start()
        return True

    def update_peer_list(self):
        self.packet_queue.queue_message(PeerDaemon.create_packet("getlist"), (self.info.reg_ipv4, self.info.reg_port), 2, 2)
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
        self.send_thread.stop_event.set()
        self.socket.sendto(bytes("stop", "utf-8"), (str(self.info.chat_ipv4), self.info.chat_port))
        self.hello_thread.join()
        self.send_thread.join()
        self.listen_thread.join()
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
    try:
        daemon = PeerDaemon(args)
    except OSError as err:
        tools.err_print("OS error: {0}".format(err))
        return 1
    try:
        tools.run_server(daemon, args.id % 19991 + 10000)
    except KeyboardInterrupt:
        tools.err_print("\nStopping daemon...")
        daemon.finish()
        tools.err_print("Bye.")

if __name__ == "__main__":
    main()
