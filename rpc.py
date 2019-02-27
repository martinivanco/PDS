import sys
import argparse
import tools

def main():
    parser = argparse.ArgumentParser(description="RPC Client for PDS18 P2P Chat")
    parser.add_argument("-i", "--id", type = tools.id_check, required = True, metavar = "<id>",
        help = "id of node or peer to send command to")

    np_group = parser.add_mutually_exclusive_group(required = True)
    np_group.add_argument("-p", "--peer", action = "store_true",
        help = "send command to a peer daemon")
    np_group.add_argument("-n", "--node", action = "store_true",
        help = "send command to a registration node daemon")

    if any(a in ("-n", "--node") for a in sys.argv):
        parser.add_argument("-c", "--command", required = True,
            choices = ["database", "neighbors", "connect", "disconnect", "sync"],
            help = "task to perform at given peer or node")
    elif any(a in ("-p", "--peer") for a in sys.argv):
        parser.add_argument("-c", "--command", required = True,
            choices = ["message", "getlist", "peers", "reconnect"],
            help = "task to perform at given peer or node")
    elif any(a in ("-h", "--help") for a in sys.argv):
        parser.add_argument("-c", "--command", required = True,
            choices = ["message", "getlist", "peers", "reconnect", "database", "neighbors", "connect", "disconnect", "sync"],
            help = "task to perform at given peer or node")

    if any(a in ("message", "-h", "--help") for a in sys.argv):
        parser.add_argument("-f", "--from", required = "message" in sys.argv, metavar = "<username>",
            help = "sender")
        parser.add_argument("-t", "--to", required = "message" in sys.argv, metavar = "<username>",
            help = "recipient")
        parser.add_argument("-m", "--message", required = "message" in sys.argv, metavar = "<message>",
            help = "message content")
    if any(a in ("connect", "disconnect", "reconnect", "sync", "-h", "--help") for a in sys.argv):
        parser.add_argument("-ri", "--reg-ipv4", required = any(a in ("connect", "disconnect", "reconnect", "sync") for a in sys.argv),
            metavar = "<ip addr>", type = tools.ip_check, help = "nodes IP address")
        parser.add_argument("-rp", "--reg-port", required = any(a in ("connect", "reconnect") for a in sys.argv),
            metavar = "<port>", type = tools.port_check, help = "nodes operating port")

    args = parser.parse_args()
    s = tools.get_stub(args.id % 19991 + 10000)

    if args.command == 'message':
        s.send_message(vars(args)["from"], args.to, args.message)
    elif args.command == 'getlist':
        s.update_peer_list()
    elif args.command == 'peers':
        print(s.get_peer_list())
    elif args.command == 'reconnect':
        s.change_reg_node(str(args.reg_ipv4), args.reg_port)
    elif args.command == 'database':
        print(s.get_database())
    elif args.command == 'neighbors':
        print(s.get_neighbour_list())
    elif args.command == 'connect':
        s.connect_to_node(str(args.reg_ipv4), args.reg_port)
    elif args.command == 'disconnect':
        s.disconnect_from_node(str(args.reg_ipv4), args.reg_port)
    elif args.command == 'sync':
        s.synchronise_with_node(str(args.reg_ipv4), args.reg_port)
    else:
        parser.error("unknown command '" + args.command + "'")

if __name__ == "__main__":
    main()
