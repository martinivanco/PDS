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

    def get_database(self):
        full_db = []
        full_db.extend(self.peers) # TODO remove timestamp and shit
        full_db.extend(self.database)
        return full_db

    def get_neighbours(self):
        return neighbours # TODO remove unnecessary shit

    def get_neighbour_address(self, ip):
        for n in self.neighbours:
            if n["ip"] = ip:
                return (ip, n["port"])
        return None

    def add_peer(self):
        pass

    def remove_peer(self):
        pass

    def add_neighbour(self):
        pass
    
    def remove_neighbour(self):
        pass

class TimerThread(threading.Thread):
    def __init__(self, node_db):
        super(TimerThread, self).__init__()

    def run(self):
        pass

class ListenThread(threading.Thread):
    def __init__(self, socket, packet_queue, node_db):
        super(ListenThread, self).__init__()
        self.socket = socket
        self.packet_queue = packet_queue
        self.node_db = node_db

    def run(self):
        pass

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
        return self.node_db.get_database()

    def get_neighbour_list(self):
        return self.node_db.get_neighbours()

    def connect_to_node(self, ip, port):
        # TODO add update packet to queue
        return True

    def disconnect_from_node(self, ip):
        packet = NodeDaemon.create_packet("disconnect")
        address = self.node_db.get_neighbour_address(ip)
        if address == None:
            tools.err_print("Error: No neighbour with ip {}. Can't disconnect.".format())
            return False
        self.packet_queue.queue_message(packet, address)
        return True
        
    def synchronise_with_node(self, ip):
        # TODO add update packet to queue
        return True

    @staticmethod
    def create_packet(ptype, peers = None, db = None, verbose = None):
        packet = {"type": ptype, "txid": tools.generate_txid()}
        if not peers == None:
            packet["peers"] = peers
        if not db == None:
            packet["db"] = db
        if not verbose == None:
            packet["verbose"] = verbose
        return packet

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