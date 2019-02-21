import sys
import argparse
import uuid
import ipaddress
from xmlrpc.server import SimpleXMLRPCServer
from xmlrpc.server import SimpleXMLRPCRequestHandler
from xmlrpc.client import ServerProxy

ERR_FATAL = 4
ERR_RECOVER = 1
OK = 2

class RequestHandler(SimpleXMLRPCRequestHandler):
    rpc_paths = ('/RPC2',)

def run_server(daemon, port):
    with SimpleXMLRPCServer(('localhost', port), requestHandler = RequestHandler) as server:
        server.register_instance(daemon)
        server.serve_forever()

def get_stub(port):
    return ServerProxy('http://localhost:' + str(port))

def id_check(value):
    msg = "%r is not a valid id - must be a positive integer" % value
    try:
        id_val = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(msg)
    if id_val <= 0:
        raise argparse.ArgumentTypeError(msg)
    return id_val

def ip_check(value):
    msg = "%r is not a valid IPv4 address" % value
    try:
        ip_val = ipaddress.ip_address(value)
    except ValueError:
        raise argparse.ArgumentTypeError(msg)
    if ip_val.version != 4:
        raise argparse.ArgumentTypeError(msg)
    return ip_val

def port_check(value):
    msg = "%r is not a valid port" % value
    try:
        port_val = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(msg)
    if port_val < 0 or port_val > (2**16 - 1):
        raise argparse.ArgumentTypeError(msg)
    return port_val

def generate_txid():
    return uuid.uuid4().int & 0xffff

def err_print(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)