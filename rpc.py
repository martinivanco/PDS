import sys
import argparse
import ipaddress
import tools

def ipCheck(value):
    msg = "%r is not a valid IPv4 address" % value
    try:
        ip_val = ipaddress.ip_address(value)
    except ValueError:
        raise argparse.ArgumentTypeError(msg)
    if ip_val.version != 4:
        raise argparse.ArgumentTypeError(msg)
    return ip_val

def portCheck(value):
    msg = "%r is not a valid port" % value
    try:
        port_val = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(msg)
    if port_val < 0 or port_val > (2**16 - 1):
        raise argparse.ArgumentTypeError(msg)
    return port_val

parser = argparse.ArgumentParser(description="RPC Client for PDS18 P2P Chat")
parser.add_argument("-i", "--id", type = int, required = True, metavar = "<id>",
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
    parser.add_argument("--from", required = "message" in sys.argv, metavar = "<username>",
        help = "sender")
    parser.add_argument("--to", required = "message" in sys.argv, metavar = "<username>",
        help = "recipient")
    parser.add_argument("--message", required = "message" in sys.argv, metavar = "<message>",
        help = "message content")
if any(a in ("connect", "disconnect", "reconnect", "sync", "-h", "--help") for a in sys.argv):
    parser.add_argument("--reg-ipv4", required = any(a in ("connect", "disconnect", "reconnect", "sync") for a in sys.argv),
        metavar = "<ip addr>", type = ipCheck, help = "nodes IP address")
if any(a in ("connect", "reconnect", "-h", "--help") for a in sys.argv):
    parser.add_argument("--reg-port", required = any(a in ("connect", "reconnect") for a in sys.argv),
        metavar = "<port>", type = portCheck, help = "nodes operating port")

args = parser.parse_args()
s = tools.get_stub()

if args.command == 'message':
    s.send_message(vars(args)["from"], args.to, args.message)
elif args.command == 'getlist':
    s.update_peer_list()
elif args.command == 'peers':
    print(s.get_peer_list())
elif args.command == 'reconnect':
    s.change_reg_node(str(args.reg_ipv4), args.reg_port)
elif args.command == 'database':
    pass
elif args.command == 'neighbors':
    pass
elif args.command == 'connect':
    pass
elif args.command == 'disconnect':
    pass
elif args.command == 'sync':
    pass
else:
    parser.error("unknown command '" + args.command + "'")
