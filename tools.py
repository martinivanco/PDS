from xmlrpc.server import SimpleXMLRPCServer
from xmlrpc.server import SimpleXMLRPCRequestHandler
from xmlrpc.client import ServerProxy

class RequestHandler(SimpleXMLRPCRequestHandler):
    rpc_paths = ('/RPC2',)

def run_server(daemon):
    with SimpleXMLRPCServer(('localhost', 8000), requestHandler = RequestHandler) as server:
        server.register_instance(daemon)
        server.serve_forever()

def get_stub():
    return ServerProxy('http://localhost:8000')