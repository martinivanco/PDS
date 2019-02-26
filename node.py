import sys
import time
import argparse
import threading
import socket
import ipaddress
import bencode
import tools

class NodeDatabase:
    def __init__(self):
        self.peers = []
        self.database = []
        self.neighbours = []

    def get_list(self):
        return [] # TODO

    def get_neighbours(self):
        return neighbours # TODO remove unnecessary shit

    def get_neighbour_address(self, ip):
        for n in self.neighbours:
            if n["ip"] = ip:
                return (ip, n["port"])
        return None

    def hello_peer(self, message):
        pass

    def remove_peer(self, username):
        pass

    def update_neighbour(self, message):
        pass
    
    def remove_neighbour(self, ip, port):
        pass

class TimerThread(threading.Thread):
    def __init__(self, node_db):
        super(TimerThread, self).__init__()

    def run(self):
        pass

class ListenThread(tools.ListenThread):
    def __init__(self, socket, packet_queue, node_db):
        super(ListenThread, self).__init__(socket, packet_queue)
        self.node_db = node_db

    def run(self):
        while True:
            message = self.recieve()
            if message == "stop":
                break
            if message is False:
                continue

            if message["type"] == "hello":
                self.node_db.hello_peer(message)
            elif message["type"] == "getlist":
                ack = tools.create_packet("ack")
                ack["txid"] = message["txid"]
                self.packet_queue.queue_message(ack, message["address"])
                self.packet_queue.queue_message(tools.create_packet("list", peers = self.node_db.get_list()), message["address"])
            elif message["type"] == "update":
                self.process_update(message)
            elif message["type"] == "disconnect":
                self.node_db.remove_neighbour(message["address"][0], message["address"][1])
            elif message["type"] == "ack":
                self.packet_queue.pop_ack(message["txid"])
            else:
                tools.err_print("Error: Unexpected packet of type '{}'".format(message["type"]))

    def process_update(self, message):
        pass # TODO

class NodeDaemon:
    def __init__(self, info):
        self.info = info
        self.node_db = NodeDatabase()

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((str(self.info.reg_ipv4), self.info.ref_port))
        self.packet_queue = tools.PacketQueue()
        
        self.listen_thread = ListenThread(self.socket, self.packet_queue, self.node_db)
        self.timeout_thread = None

    def get_database(self):
        return self.node_db.get_list()

    def get_neighbour_list(self):
        return self.node_db.get_neighbours()

    def connect_to_node(self, ip, port):
        # TODO add update packet to queue
        return True

    def disconnect_from_node(self, ip):
        packet = tools.create_packet("disconnect")
        address = self.node_db.get_neighbour_address(ip)
        if address == None:
            tools.err_print("Error: No neighbour with ip {}. Can't disconnect.".format())
            return False
        self.packet_queue.queue_message(packet, address)
        return True
        
    def synchronise_with_node(self, ip):
        # TODO add update packet to queue
        return True

    def finish(self):
        self.socket.sendto(bytes("stop", "utf-8"), (str(self.info.reg_ipv4), self.info.reg_port))
        self.listen_thread.join()

def main():
    parser = argparse.ArgumentParser(description="Node Daemon for PDS18 P2P Chat")
    parser.add_argument("-i", "--id", type = tools.id_check, required = True, metavar = "<id>",
        help = "unique id of the node")
    parser.add_argument("-ri", "--reg-ipv4", type = tools.ip_check, required = True, metavar = "<ip addr>",
        help = "IP address of the node")
    parser.add_argument("-rp", "--reg-port", type = tools.port_check, required = True, metavar = "<port>",
        help = "port on which the node should listen")
    args = parser.parse_args()
    try:
        daemon = NodeDaemon(args)
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