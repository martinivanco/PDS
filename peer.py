import sys
import time
import argparse
import threading
import socket
import ipaddress
import bencode
import tools

class HelloThread(threading.Thread):
    def __init__(self, packet, node):
        super(HelloThread, self).__init__()
        self.packet = packet
        self.node = (str(node[0]), node[1])
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.stop_event = threading.Event()
        
    def run(self):
        while not self.stop_event.is_set():
            self.packet["txid"] = tools.generate_txid()
            self.socket.sendto(bencode.encode(self.packet), self.node)
            self.stop_event.wait(10)
        self.packet["txid"] = tools.generate_txid()
        self.packet["ipv4"] = "0.0.0.0"
        self.packet["port"] = 0
        self.socket.sendto(bencode.encode(self.packet), self.node)
        self.socket.close()

class SendThread(threading.Thread):
    def __init__(self, node, peers, message = None):
        super(SendThread, self).__init__()
        self.node = (str(node[0]), node[1])
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.peerlist = peers
        self.message = message

    def run(self):
        packet = PeerDaemon.create_packet("getlist")
        self.socket.sendto(bencode.encode(packet), self.node)
        self.socket.settimeout(2)
        data, address = self.socket.recvfrom()
        response = self.check_data(data, address)
        if type(response) is bool:
            return response # Probably should try it again if false
        
        ack_flag = False
        if response["type"] == "ack":
            ack_flag = True
            if response["txid"] != packet["txid"]:
                return False # Probabaly should try it again
            data, address = self.socket.recvfrom()
            response = self.check_data(data, address)
            if response is False:
                return False # Probably should try it again

        if response["type"] == "list":
            updated_list = self.check_list(response, address)
            if not type(updated_list) == list:
                return False # Probably should try it again
            if not ack_flag:
                data, address = self.socket.recvfrom()
        else:
            self.send_error("Expected packet type 'list'. Got '" + response["type"], address)
            return False # Probably should try it again
        
        self.peerlist.clear()
        self.peerlist.append(updated_list)

        if self.message != None:
            address = self.find_peer_address(self.message["to"])
            if address == None:
                tools.err_print("Error: No peer with username '" + self.message["to"] + "' found.")
                return False
            self.socket.sendto(bencode.encode(self.message), address)
            data, address = self.socket.recvfrom(4096)
            response = self.check_data(data, address)
            if response["type"] == "ack" and response["txid"] == self.message["txid"]:
                return True
            return False # Probably should try it again

    def find_peer_address(self, username):
        for p in self.peerlist:
            if p["username"] == username:
                return (p["ipv4"], p["port"])
        return None

    def check_data(self, data, sender):
        try:
            packet = bencode.decode(data)
        except Exception:
            self.send_error("The packet could not be decoded.", sender)
            return False
        if not type(packet) == dict:
            self.send_error("Wrong packet format. Expected json.", sender)
            return False
        if not ("type" in packet and "txid" in packet):
            self.send_error("Missing fields in packet. Expected at least 'type' and 'txid'.", sender)
            return False
        if packet["type"] == "error":
            if "verbose" in packet:
                tools.err_print("Error: " + packet["verbose"])
            else:
                tools.err_print("Unknown error.")
            return True
        return packet

    def check_list(self, packet, sender):
        if not "peers" in packet:
            self.send_error("Missing 'peers' field.", sender)
            return False
        peers = packet["peers"]
        if not type(peers) == dict:
            self.send_error("Invalid contents of 'peers' field.", sender)
            return False
        updated_list = []
        for p in peers.values():
            updated_list.append(p)
        return updated_list

    def send_error(self, message, recipient):
        self.socket.sendto(PeerDaemon.create_packet("error", verbose = message), recipient)

class ListenThread(threading.Thread):
    def __init__(self, username, ip, port):
        super(ListenThread, self).__init__()
        self.username = username
        self.ip = ip
        self.port = port

    def run(self):
        # bind and listen
        # recieve message
        # check if not game over
        # error handling
        # send ACK
        print("message")

class PeerDaemon:
    def __init__(self, info):
        self.info = info
        self.hello_packet = PeerDaemon.create_packet("hello", username = info.username, ipv4 = str(info.chat_ipv4), port = info.chat_port)
        self.peers = []
        self.peers.append({"username": "xjerab21", "ipv4": "192.168.1.103", "port": 12345})
        self.listen_thread = None
        self.hello_thread = HelloThread(self.hello_packet, (self.info.reg_ipv4, self.info.reg_port))
        self.hello_thread.start()

    def send_message(self, sender, recipient, message):
        # what to do with sender?
        send_thread = SendThread((self.info.reg_ipv4, self.info.reg_port), self.peers,
            PeerDaemon.create_packet("message", fro = self.info.username, to = recipient, message = message))
        send_thread.start()
        return True

    def update_peer_list(self):
        send_thread = SendThread((self.info.reg_ipv4, self.info.reg_port), self.peers)
        send_thread.start()
        return True

    def get_peer_list(self):
        return self.peers
    
    def change_reg_node(self, ip_address, port):
        self.hello_thread.stop_event.set()
        self.info.reg_ipv4 = ipaddress.ip_address(ip_address)
        self.info.reg_port = port
        self.hello_thread.join()
        self.hello_thread = HelloThread(self.hello_packet, (self.info.reg_ipv4, self.info.reg_port))
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
        self.hello_thread.join()

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

