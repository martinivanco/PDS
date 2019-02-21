import sys
import time
import argparse
import threading
import socket
import ipaddress
import bencode
import tools

class NodeDaemon:
    def __init__(self, info):
        self.info = info
        self.listen_thread = None
        self.timeout_thread = None

    def get_database(self):
        return True

    def get_neighbour_list(self):
        return True

    def connect_to_node(self, ip, port):
        return True

    def disconnect_from_node(self, ip):
        return True
        
    def synchronise_with_node(self, ip):
        return True

    def finish(self):
        pass

def main():
    parser = argparse.ArgumentParser(description="Node Daemon for PDS18 P2P Chat")
    parser.add_argument("-i", "--id", type = tools.id_check, required = True, metavar = "<id>",
        help = "unique id of the node")
    parser.add_argument("-ri", "--reg-ipv4", type = tools.ip_check, required = True, metavar = "<ip addr>",
        help = "IP address of the node")
    parser.add_argument("-rp", "--reg-port", type = tools.port_check, required = True, metavar = "<port>",
        help = "port on which the node should listen")
    args = parser.parse_args()
    daemon = NodeDaemon(args)
    try:
        tools.run_server(daemon, args.id % 19991 + 10000)
    except KeyboardInterrupt:
        tools.err_print("\nStopping daemon...")
        daemon.finish()
        tools.err_print("Bye.")

if __name__ == "__main__":
    main()