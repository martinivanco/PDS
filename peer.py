import tools

class PeerDaemon:
    def __init__(self):
        pass

    def send_message(self, sender, recipient, message):
        print(recipient + ": " + message)
        return True

    def update_peer_list(self):
        print("getlist")
        return True

    def get_peer_list(self):
        print("peers")
        return "this will be a list of peers"
    
    def change_reg_node(self, ip_address, port):
        print("reconnect")
        return True


tools.run_server(PeerDaemon())