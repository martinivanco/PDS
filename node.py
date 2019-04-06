import sys
import time
import argparse
import threading
import socket
import ipaddress
import bencode
import tools

class NodeDatabase:
    def __init__(self, node_address):
        self.node_address = node_address
        self.peers = []
        self.nodes = []
        self.blocked = []
        self.database = {}
        self.peer_lock = threading.Lock()
        self.node_lock = threading.Lock()
        self.update_event = threading.Event()

    def get_oldest_hello(self):
        current_time = time.time()
        bye_time = current_time - 30
        oldest_peer = current_time
        with self.peer_lock:
            for p in self.peers:
                if p["hello"] <= bye_time:
                    tools.dbg_print("Peer timed out: {}\n- - - - - - - - - -".format(p["username"]))
                    self.remove_peer(p)
                elif p["hello"] < oldest_peer:
                    oldest_peer = p["hello"]
        return oldest_peer

    def hello_peer(self, username, ipv4, port):
        with self.peer_lock:
            for p in self.peers:
                if p["username"] == username:
                    if ipv4 == "0.0.0.0" and port == 0:
                        self.remove_peer(p)
                    else:
                        p["hello"] = time.time()
                    return

            if ipv4 != "0.0.0.0" and port != 0:
                self.add_peer({"username": username, "ipv4": ipv4, "port": port, "hello": time.time()})        

    def getlist_peer(self, address):
        found = False
        with self.peer_lock:
            for p in self.peers:
                if p["ipv4"] == address[0] and p["port"] == address[1]:
                    found = True
        if not found:
            return None

        peerlist = {}
        with self.peer_lock:
            for i in range(len(self.peers)):
                peerlist[str(i)] = {"username": self.peers[i]["username"], "ipv4": self.peers[i]["ipv4"], "port": self.peers[i]["port"]}
            offset = len(self.peers)
        
        with self.node_lock:
            for r in self.database.values():
                for p in r.values():
                    peerlist[str(offset)] = p
                    offset += 1

        return peerlist

    def add_peer(self, peer):
        self.peers.append(peer)
        self.update_event.set()
        self.update_event.clear()
        tools.dbg_print("Added new peer: {}\n- - - - - - - - - -".format(peer["username"]))

    def remove_peer(self, peer):
        self.peers.remove(peer)
        self.update_event.set()
        self.update_event.clear()
        tools.dbg_print("Removed peer: {}\n- - - - - - - - - -".format(peer["username"]))

    def get_oldest_echo(self):
        current_time = time.time()
        bye_time = current_time - 12
        oldest_node = current_time
        with self.node_lock:
            for n in self.nodes:
                if n["echo"] <= bye_time:
                    tools.dbg_print("Node timed out: {ip}:{po}\n- - - - - - - - - -".format(ip = n["ipv4"], po = n["port"]))
                    self.remove_node(n)
                elif n["echo"] < oldest_node:
                    oldest_node = n["echo"]
        return oldest_node

    def get_oldest_update(self, to_update):
        current_time = time.time()
        update_time = current_time - 4
        oldest_node = current_time
        with self.node_lock:
            for n in self.nodes:
                if n["update"] <= update_time:
                    to_update.append((n["ipv4"], n["port"]))
                    n["update"] = current_time
                elif n["update"] < oldest_node:
                    oldest_node = n["update"]
        return oldest_node

    def update_node(self, ipv4, port, db):
        with self.node_lock:
            for b in self.blocked:
                if n["ipv4"] == ipv4 and n["port"] == port:
                    return False

            for n in self.nodes:
                if n["ipv4"] == ipv4 and n["port"] == port:
                    n["echo"] = time.time()
                    self.database["{ip},{po}".format(ip = ipv4, po = port)] = db
                    return True
            
            self.add_node({"ipv4": ipv4, "port": port, "echo": time.time(), "update": time.time()}, db)
            return False

    def disconnect_node(self, ipv4, port):
        with self.node_lock:
            for n in self.nodes:
                if n["ipv4"] == ipv4  and n["port"] == port:
                    self.remove_node(n)
                    return

    def disconnect_all(self):
        with self.node_lock:
            for n in self.nodes:
                self.remove_node(n, True)

    def add_node(self, node, db):
        self.nodes.append(node)
        self.database["{ip},{po}".format(ip = node["ipv4"], po = node["port"])] = db
        tools.dbg_print("Added new node: {ip}:{po}\n- - - - - - - - - -".format(ip = node["ipv4"], po = node["port"]))

    def remove_node(self, node, block_updates = False):
        if block_updates:
            self.blocked.append(node)
        self.nodes.remove(node)
        self.database.pop("{ip},{po}".format(ip = node["ipv4"], po = node["port"]))
        tools.dbg_print("Removed node: {ip}:{po}\n- - - - - - - - - -".format(ip = node["ipv4"], po = node["port"]))

    def get_database(self):
        with self.node_lock:
            db = self.database.copy()

        mydb = {}
        with self.peer_lock:
            for i in range(len(self.peers)):
                mydb[str(i)] = {"username": self.peers[i]["username"], "ipv4": self.peers[i]["ipv4"], "port": self.peers[i]["port"]}

        db[self.node_address] = mydb
        return db

    def get_nodes(self):
        node_list = []
        with self.node_lock:
            for n in self.nodes:
                node_list.append({"ipv4": n["ipv4"], "port": n["port"]})
        return node_list

    def remove_known_nodes(self, node_list):
        with self.peer_lock:
            for n in self.nodes:
                if (n["ipv4"], n["port"]) in node_list:
                    node_list.remove((n["ipv4"], n["port"]))
        my_addr = self.node_address.split(",")
        if (my_addr[0], int(my_addr[1])) in node_list:
            node_list.remove((my_addr[0], int(my_addr[1])))

class TimerThread(threading.Thread):
    def __init__(self, node_db, packet_queue):
        super(TimerThread, self).__init__()
        self.node_db = node_db
        self.packet_queue = packet_queue
        self.stop_event = threading.Event()

    def run(self):
        while not self.stop_event.is_set():
            next_hello = self.node_db.get_oldest_hello() + 30
            next_echo = self.node_db.get_oldest_echo() + 12
            nodes_to_update = []
            next_update = self.node_db.get_oldest_update(nodes_to_update) + 4

            if len(nodes_to_update) > 0:
                update_db = self.node_db.get_database()
                for address in nodes_to_update:
                    self.packet_queue.queue_message(tools.create_packet("update", db = update_db), address)

            self.stop_event.wait(min(next_hello, next_echo, next_update) - time.time())

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
                self.process_hello(message)
            elif message["type"] == "getlist":
                self.process_getlist(message)
            elif message["type"] == "update":
                self.process_update(message)
            elif message["type"] == "disconnect":
                self.node_db.disconnect_node(message["address"][0], message["address"][1])
                ack = tools.create_packet("ack")
                ack["txid"] = message["txid"]
                self.packet_queue.queue_message(ack, message["address"])
            elif message["type"] == "ack":
                self.packet_queue.pop_ack(message["txid"])
            else:
                self.send_error(message["txid"], "Error: Unexpected packet of type '{}'".format(message["type"]), message["address"])

    def process_hello(self, message):
        if not all(f in message for f in ("username", "ipv4", "port")):
            self.send_error(message["txid"], "Missing fields in packet of type 'hello'. Expected 'username', 'ipv4' and 'port'.", message["address"])
            return False
        if not (type(message["username"]) is str and type(message["ipv4"]) is str and type(message["port"]) is int):
            self.send_error(message["txid"], "The username and ip must be strings and the port must be a number.", message["address"])
            return False
        try:
            tools.ip_check(message["ipv4"])
            tools.port_check(message["port"])
        except argparse.ArgumentTypeError:
            self.send_error(message["txid"], "Invalid IPv4 address or port.", message["address"])
            return False
        self.node_db.hello_peer(message["username"], message["ipv4"], message["port"])

    def process_getlist(self, message):
        peerlist = self.node_db.getlist_peer(message["address"])
        if peerlist == None:
            self.send_error(message["txid"], "Can't answer to unregistered peers.", message["address"])
            return False
            
        ack = tools.create_packet("ack")
        ack["txid"] = message["txid"]
        self.packet_queue.queue_message(ack, message["address"])
        self.packet_queue.queue_message(tools.create_packet("list", peers = peerlist), message["address"], 2, 2)

    def process_update(self, message):
        if "db" not in message:
            self.send_error(message["txid"], "Missing field in packet of type 'update'. Expected 'db'.", message["address"])
            return False
        if type(message["db"]) is not dict:
            self.send_error(message["txid"], "Invalid contents of field 'db'.", message["address"])
            return False

        node_list = []
        for na in message["db"]:
            address = self.check_node_address(na)
            if address is False:
                self.send_error(message["txid"], "Invalid index of DB_RECORD.", message["address"])
                return False
            node_list.append(address)
            
        node_key = "{ip},{po}".format(ip = message["address"][0], po = message["address"][1])
        if node_key in message["db"] and not self.check_node_db(message["db"][node_key]):
            self.send_error(message["txid"], "Invalid contents of DB_RECORD.", message["address"])
            return False
        if not self.node_db.update_node(message["address"][0], message["address"][1], message["db"][node_key]):
            self.packet_queue.queue_message(tools.create_packet("update", db = self.node_db.get_database()), message["address"])

        self.node_db.remove_known_nodes(node_list)
        for na in node_list:
            self.packet_queue.queue_message(tools.create_packet("update", db = self.node_db.get_database()), na)
    
    def check_node_address(self, node_key):
        if type(node_key) != str:
            return False
        address = node_key.split(",")
        if len(address) != 2:
            return False
        try:
            tools.ip_check(address[0])
            tools.port_check(address[1])
        except argparse.ArgumentTypeError:
            return False
        return (address[0], int(address[1]))

    def check_node_db(self, database):
        for p in database.values():
            if not (all(f in p for f in ("username", "ipv4", "port")) and type(p["username"]) is str and type(p["ipv4"]) is str and type(p["port"]) is int):
                return False
            try:
                tools.ip_check(p["ipv4"])
                tools.port_check(p["port"])
            except argparse.ArgumentTypeError:
                return False
        return True        

class NodeDaemon:
    def __init__(self, info):
        self.info = info
        self.node_db = NodeDatabase("{ip},{po}".format(ip = self.info.reg_ipv4, po = self.info.reg_port))

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((str(self.info.reg_ipv4), self.info.reg_port))
        self.packet_queue = tools.PacketQueue()
        
        self.listen_thread = ListenThread(self.socket, self.packet_queue, self.node_db)
        self.send_thread = tools.SendThread(self.socket, self.packet_queue)
        self.timer_thread = TimerThread(self.node_db, self.packet_queue)
        self.listen_thread.start()
        self.send_thread.start()
        self.timer_thread.start()

    def get_database(self):
        print(self.node_db.get_database())
        return True

    def get_neighbour_list(self):
        print(self.node_db.get_nodes())
        return True

    def connect_to_node(self, ip, port):
        self.packet_queue.queue_message(tools.create_packet("update", db = self.node_db.get_database()), (ip, port))
        return True
   
    def disconnect_from_nodes(self):
        nodes = self.node_db.get_nodes()
        for n in nodes:
            self.packet_queue.queue_message(tools.create_packet("disconnect"), (n["ipv4"], n["port"]), 2, 2, 3)
        self.node_db.disconnect_all()
        return True

    def synchronise_with_nodes(self):
        nodes = self.node_db.get_nodes()
        for n in nodes:
            self.packet_queue.queue_message(tools.create_packet("update", db = self.node_db.get_database()), (n["ipv4"], n["port"]))
        return True

    def finish(self):
        self.disconnect_from_nodes()
        self.timer_thread.stop_event.set()
        self.socket.sendto(bytes("stop", "utf-8"), (str(self.info.reg_ipv4), self.info.reg_port))
        self.send_thread.stop_event.set()
        self.packet_queue.queue_event.set()
        self.timer_thread.join()
        self.send_thread.join()
        self.listen_thread.join()
        self.socket.close()

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