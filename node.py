import sys
import time
import argparse
import threading
import socket
import ipaddress
import bencode
import tools

class NodeDatabase:
    def __init__(self, address_key, packet_queue):
        self.address_key = address_key
        self.packet_queue = packet_queue
        self.peers = []
        self.database = {}
        self.neighbours = []
        self.peer_lock = threading.Lock()
        self.neighbour_lock = threading.Lock()

    def get_list(self):
        peerlist = {}
        for i in range(len(self.peers)):
            peerlist[str(i)] = {"username": self.peers[i]["username"], "ipv4": self.peers[i]["ipv4"], "port": self.peers[i]["port"]}
        
        offset = len(self.peers)
        for r in self.database.values():
            for p in r.values():
                peerlist[str(offset)] = p
                offset += 1

        return peerlist

    def get_neighbours(self):
        neighbour_list = []
        for n in self.neighbours:
            neighbour_list.append({"ipv4": n["ipv4"], "port": n["port"]})
        return neighbour_list

    def get_database(self):
        db = self.database.copy()
        mydb = {}
        for i in range(len(self.peers)):
            mydb[str(i)] = {"username": self.peers[i]["username"], "ipv4": self.peers[i]["ipv4"], "port": self.peers[i]["port"]}
        db[self.address_key] = mydb
        return db

    def hello_peer(self, username, ipv4, port):
        for p in self.peers:
            if p["username"] == username:
                if ipv4 == "0.0.0.0" and port == 0:
                    self.remove_peer(p)
                else:
                    self.peer_lock.acquire()
                    p["timestamp"] = time.time()
                    self.peer_lock.release()
                return
                
        self.peer_lock.acquire()
        self.peers.append({"username": username, "ipv4": ipv4, "port": port, "timestamp": time.time()})
        self.peer_lock.release()
        self.force_update()
        tools.dbg_print("Added new peer: {}\n- - - - - - - - - -".format(username))

    def remove_peer(self, peer):
        self.peer_lock.acquire()
        self.peers.remove(peer)
        self.peer_lock.release()
        self.force_update()
        tools.dbg_print("Removed peer: {}\n- - - - - - - - - -".format(peer["username"]))

    def clean_peers(self):
        current_time = time.time()
        bye_time = current_time - 30
        oldest_peer = current_time
        for p in self.peers:
            if p["timestamp"] < bye_time:
                tools.dbg_print("Peer timed out: {}\n- - - - - - - - - -".format(p["username"]))
                self.remove_peer(p)
            elif p["timestamp"] < oldest_peer:
                oldest_peer = p["timestamp"]
        return oldest_peer

    def check_peer(self, address):
        for p in self.peers:
            if p["ipv4"] == address[0] and p["port"] == address[1]:
                return True
        return False

    def update_neighbour(self, ipv4, port, his_peers):
        for n in self.neighbours:
            if n["ipv4"] == ipv4 and n["port"] == port:
                self.neighbour_lock.acquire()
                n["timestamp"] = time.time()
                self.database["{ip},{po}".format(ip = ipv4, po = port)] = his_peers
                self.neighbour_lock.release()
                return
        
        self.neighbour_lock.acquire()
        self.neighbours.append({"ipv4": ipv4, "port": port, "timestamp": time.time()})
        self.database["{ip},{po}".format(ip = ipv4, po = port)] = his_peers
        self.neighbour_lock.release()
        tools.dbg_print("Added new neighbour: {ip}:{po}\n- - - - - - - - - -".format(ip = ipv4, po = port))
    
    def remove_neighbour(self, ipv4, port):
        neighbour = None
        for n in self.neighbours:
            if n["ipv4"] == ipv4  and n["port"] == port:
                neighbour = n
                break
        if neighbour == None:
            return False
        self.neighbour_lock.acquire()
        self.neighbours.remove(neighbour)
        self.database.pop("{ip},{po}".format(ip = ipv4, po = port))
        self.neighbour_lock.release()
        tools.dbg_print("Removed neighbour: {ip}:{po}\n- - - - - - - - - -".format(ip = ipv4, po = port))

    def clean_neighbours(self):
        current_time = time.time()
        bye_time = current_time - 30
        oldest_neighbour = current_time
        for n in self.neighbours:
            if n["timestamp"] < bye_time:
                self.remove_neighbour(n["ipv4"], n["port"])
            elif n["timestamp"] < oldest_neighbour:
                oldest_neighbour = n["timestamp"]
        return oldest_neighbour

    def force_update(self):
        for n in self.neighbours:
            self.packet_queue.queue_message(tools.create_packet("update", db = self.get_database()), (n["ipv4"], n["port"]))

class TimerThread(threading.Thread):
    def __init__(self, node_db):
        super(TimerThread, self).__init__()
        self.node_db = node_db
        self.stop_event = threading.Event()

    def run(self):
        while not self.stop_event:
            next_peer = self.node_db.clean_peers() + 30
            next_neighbour = self.node_db.clean_neighbours() + 12
            if next_peer > next_neighbour:
                wait_time = next_neighbour - time.time()
            else:
                wait_time = next_peer - time.time()
            self.stop_event.wait(wait_time)

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
                self.node_db.remove_neighbour(message["address"][0], message["address"][1])
            elif message["type"] == "ack":
                self.packet_queue.pop_ack(message["txid"])
            else:
                tools.err_print("Error: Unexpected packet of type '{}'".format(message["type"]))

    def process_hello(self, message):
        if not all(f in message for f in ("username", "ipv4", "port")):
            self.send_error(message["txid"], "Missing fields in packet of type 'hello'. Expected 'username', 'ipv4' and 'port'.", message["address"])
            return False
        if type(message["username"]) is not str or type(message["port"]) is not int:
            self.send_error(message["txid"], "The username must be a string and the port must be a number.", message["address"])
            return False
        try:
            tools.ip_check(message["ipv4"])
            tools.port_check(message["port"])
        except argparse.ArgumentTypeError:
            self.send_error(message["txid"], "Invalid IPv4 address or port.", message["address"])
            return False
        self.node_db.hello_peer(message["username"], message["ipv4"], message["port"])

    def process_getlist(self, message):
        if not self.node_db.check_peer(message["address"]):
            self.send_error(message["txid"], "Can't answer to unregistered peers.", message["address"])
            return False
        ack = tools.create_packet("ack")
        ack["txid"] = message["txid"]
        self.packet_queue.queue_message(ack, message["address"])
        self.packet_queue.queue_message(tools.create_packet("list", peers = self.node_db.get_list()), message["address"], 2, 2)

    def process_update(self, message):
        if "db" not in message:
            self.send_error(message["txid"], "Missing field in packet of type 'update'. Expected 'db'.", message["address"])
            return False
        if type(message["db"]) is not dict:
            self.send_error(message["txid"], "Invalid contents of field 'db'.", message["address"])
            return False

        for n in message["db"]:
            n_split = n.split(",")
            if len(n_split) != 2 or not self.check_node(n_split):
                self.send_error(message["txid"], "Invalid contents of field 'db'.", message["address"])
                return False

        key = "{ip},{po}".format(ip = message["address"][0], po = message["address"][1])
        if key in message["db"] and not self.check_db_record(message["db"][key]):
            self.send_error(message["txid"], "Invalid contents of field 'db'.", message["address"])
            return False
        
        self.node_db.update_neighbour(message["address"][0], message["address"][1], message["db"][key])
    
    def check_node(self, address):
        try:
            n_ip = tools.ip_check(address[0])
            n_port = tools.port_check(address[1])
        except argparse.ArgumentTypeError:
            return False
        
        if (str(n_ip), n_port) not in self.node_db.neighbours:
            self.packet_queue.queue_message(tools.create_packet("update", db = self.node_db.get_database()), (str(n_ip), n_port))
        return True

    def check_db_record(self, record):
        for p in record.values():
            if not all(f in p for f in ("username", "ipv4", "port")):
                return False
            if type(p["username"]) is not str or type(p["port"]) is not int:
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
        self.packet_queue = tools.PacketQueue()
        self.node_db = NodeDatabase("{ip},{po}".format(ip = self.info.reg_ipv4, po = self.info.reg_port), self.packet_queue)

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((str(self.info.reg_ipv4), self.info.reg_port))
        
        self.listen_thread = ListenThread(self.socket, self.packet_queue, self.node_db)
        self.send_thread = tools.SendThread(self.socket, self.packet_queue)
        self.timer_thread = TimerThread(self.node_db)
        self.listen_thread.start()
        self.send_thread.start()
        self.timer_thread.start()

    def get_database(self):
        return self.node_db.get_database()

    def get_neighbour_list(self):
        return self.node_db.get_neighbours()

    def connect_to_node(self, ip, port):
        self.packet_queue.queue_message(tools.create_packet("update", db = self.node_db.get_database()), (ip, port))
        return True

    def disconnect_from_node(self, ip, port):
        self.packet_queue.queue_message(tools.create_packet("disconnect"), (ip, port))
        return True
        
    def synchronise_with_node(self, ip, port):
        self.packet_queue.queue_message(tools.create_packet("update", db = self.node_db.get_database()), (ip, port))
        return True

    def finish(self):
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