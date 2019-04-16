#!/usr/bin/python3

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
        self.peers_lock = threading.Lock()
        self.update_event = threading.Event()
    
    def get_list(self):
        with self.peers_lock:
            return self.peers.copy()

    def get_address(self, username):
        with self.peers_lock:
            for p in self.peers:
                if p["username"] == username:
                    return (p["ipv4"], p["port"])
            return None

    def update(self, updated_list):
        with self.peers_lock:
            self.peers.clear()
            self.peers.extend(updated_list.values())
            self.update_event.set()
            self.update_event.clear()

class HelloThread(threading.Thread):
    def __init__(self, packet, node, packet_queue):
        super(HelloThread, self).__init__()
        self.packet = packet.copy()
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

class ListenThread(tools.ListenThread):
    def __init__(self, socket, packet_queue, peerlist, username):
        super(ListenThread, self).__init__(socket, packet_queue)
        self.peerlist = peerlist
        self.username = username

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
                ack = self.packet_queue.pop_ack(message["txid"])
                if ack["ack_event"] is not None:
                    ack["ack_event"].set()
            else:
                self.send_error(message["txid"], "Error: Unexpected packet of type '{}'".format(message["type"]), message["address"])

    def process_list(self, message):
        if not "peers" in message:
            self.send_error(message["txid"], "Missing 'peers' field in packet of type 'list'.", message["address"])
            return False
        peers = message["peers"]
        if type(peers) is not dict:
            self.send_error(message["txid"], "Invalid contents of 'peers' field.", message["address"])
            return False
        for p in peers:
            if not self.check_peer_record(peers[p]):
                self.send_error(message["txid"], "Invalid contents of 'peers' field.", message["address"])
                return False

        ack = tools.create_packet("ack")
        ack["txid"] = message["txid"]
        self.packet_queue.queue_message(ack, message["address"])
        self.peerlist.update(peers)

    def check_peer_record(self, record):
        if not all(f in record for f in ("username", "ipv4", "port")):
            return False
        if type(record["username"]) is not str:
            return False
        try:
            tools.ip_check(record["ipv4"])
            tools.port_check(record["port"])
        except argparse.ArgumentTypeError:
            return False
        return True

    def process_message(self, message):
        if not all(f in message for f in ("from", "to", "message")):
            self.send_error(message["txid"], "Missing fields in 'message' packet. Expected 'from', 'to' and 'message'.", message["address"])
            return False
        if not message["to"] == self.username:
            self.send_error(message["txid"], "Incorrect IP or username.", message["address"])
            return False

        ack = tools.create_packet("ack")
        ack["txid"] = message["txid"]
        self.packet_queue.queue_message(ack, message["address"])
        print("{frm}: {msg}".format(frm = message["from"], msg = message["message"]))

class MessageThread(threading.Thread):
    def __init__(self, message, packet_queue, peerlist, node):
        super(MessageThread, self).__init__()
        self.message = message
        self.packet_queue = packet_queue
        self.peerlist = peerlist
        self.node = node

    def run(self):
        ack_wait_event = threading.Event()
        self.packet_queue.queue_message(tools.create_packet("getlist"), self.node, 1, 2, ack_event = ack_wait_event)
        if not ack_wait_event.wait(2):
            tools.err_print("ERROR: GETLIST not ACK'ed.")
            return

        if self.peerlist.update_event.wait(2):
            address = self.peerlist.get_address(self.message["to"])
            if not address == None:
                self.packet_queue.queue_message(self.message, address, 2, 2)
            else:
                tools.err_print("ERROR: No peer with username {} found.".format(self.message["to"]))
        else:
            tools.err_print("ERROR: No LIST recieved.")

class GetListThread(threading.Thread):
    def __init__(self, packet_queue, peerlist, node):
        super(GetListThread, self).__init__()
        self.packet_queue = packet_queue
        self.peerlist = peerlist
        self.node = node

    def run(self):
        ack_wait_event = threading.Event()
        self.packet_queue.queue_message(tools.create_packet("getlist"), self.node, 1, 2, ack_event = ack_wait_event)
        if not ack_wait_event.wait(2):
            tools.err_print("ERROR: GETLIST not ACK'ed.")
            return

        if self.peerlist.update_event.wait(5):
            print(self.peerlist.get_list())
        else:
            tools.err_print("ERROR: No LIST recieved.")

class PeerDaemon:
    def __init__(self, info):
        self.info = info
        self.hello_packet = tools.create_packet("hello",
            username = self.info.username, ipv4 = str(self.info.chat_ipv4), port = self.info.chat_port)
        self.peerlist = PeerList()

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((str(self.info.chat_ipv4), self.info.chat_port))
        self.packet_queue = tools.PacketQueue()

        self.listen_thread = ListenThread(self.socket, self.packet_queue, self.peerlist, self.info.username)
        self.send_thread = tools.SendThread(self.socket, self.packet_queue)
        self.hello_thread = HelloThread(self.hello_packet, (str(self.info.reg_ipv4), self.info.reg_port), self.packet_queue)
        self.listen_thread.start()
        self.send_thread.start()
        self.hello_thread.start()

    def send_message(self, sender, recipient, message):
        if sender != self.info.username:
            tools.err_print("Warning: --from argument value does not match the username set to peer. Using the --from value anyway.")
        MessageThread(tools.create_packet("message", fro = sender, to = recipient, message = message),
            self.packet_queue, self.peerlist, (str(self.info.reg_ipv4), self.info.reg_port)).start()
        return True

    def update_peer_list(self):
        self.packet_queue.queue_message(tools.create_packet("getlist"), (str(self.info.reg_ipv4), self.info.reg_port), 2, 2)
        return True

    def get_peer_list(self):
        GetListThread(self.packet_queue, self.peerlist, (str(self.info.reg_ipv4), self.info.reg_port)).start()
        return True
    
    def change_reg_node(self, ip_address, port):
        self.hello_thread.stop_event.set()
        self.info.reg_ipv4 = ip_address
        self.info.reg_port = port
        self.hello_thread.join()
        self.hello_thread = HelloThread(self.hello_packet, (str(self.info.reg_ipv4), self.info.reg_port), self.packet_queue)
        self.hello_thread.start()
        return True

    def finish(self):
        self.hello_thread.stop_event.set()
        self.send_thread.stop_event.set()
        self.socket.sendto(bytes("stop", "utf-8"), (str(self.info.chat_ipv4), self.info.chat_port))
        self.packet_queue.queue_event.set()
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
