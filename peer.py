import sys
import time
import argparse
import threading
import ipaddress
import tools

class HelloThread(threading.Thread):
    def __init__(self, packet, node):
        super(HelloThread, self).__init__()
        self.packet = packet
        self.node_ip = node[0]
        self.node_port = node[1]
        self.stop_f = False
        
    def run(self):
        while not self.stop_f:
            self.packet["txid"] = tools.generate_txid()
            # bencode and send it
            for i in range(10):
                if self.stop_f:
                    break
                time.sleep(1)
        self.packet["txid"] = tools.generate_txid()
        self.packet["ipv4"] = "0.0.0.0"
        self.packet["port"] = 0
        # bencode and send it
    
    def stop(self):
        self.stop_f = True

class PeerDaemon:
    def __init__(self, info):
        self.info = info
        self.hello_packet = {
            "type": "hello",
            "txid": 0,
            "username": info.username,
            "ipv4": str(info.chat_ipv4),
            "port": info.chat_port
        }
        self.peers = []
        self.hello_thread = HelloThread(self.hello_packet, (self.info.reg_ipv4, self.info.reg_port))
        self.hello_thread.start()

    def send_message(self, sender, recipient, message):
        print(recipient + ": " + message)
        return True

    def update_peer_list(self):
        # getlist
        # for any in response not in peers append
        # má rpc čakať?
        return True

    def get_peer_list(self):
        return self.peers
    
    def change_reg_node(self, ip_address, port):
        self.hello_thread.stop()
        self.info.reg_ipv4 = ipaddress.ip_address(ip_address)
        self.info.reg_port = port
        self.hello_thread.join()
        self.hello_thread = HelloThread(self.hello_packet, (self.info.reg_ipv4, self.info.reg_port))
        self.hello_thread.start()
        return True
    
    def finish(self):
        self.hello_thread.stop()
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

