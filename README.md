# P2P Chat
Project made as a part of the course Data Communications, Computer Networks and Protocols at Brno University of Technology. The task was to create a hybrid P2P chat network.

## How to use
1. Clone this repo using `git clone https://github.com/photohunter9/PDS.git`
2. Run registration node using `python3 node.py -i <id> -ri <ip addr> -rp <port>` or `python3 node.py -h` to get help
3. Run at least 2 chat peers and connect them to the registration node using `python3 peer.py -i <id> -u <username> -ci <ip addr> -cp <port> -ri <ip addr> -rp <port>` or `python3 peer.py -h` to get help
4. Send RPC commands to them using `python3 rpc.py -i <id> (-p | -n) -c {message,getlist,peers,reconnect,database,neighbors,connect,disconnect,sync} [-f <username>] [-t <username>] [-m <message>] [-ri <ip addr>] [-rp <port>]` or `python3 rpc.py -h` to get help
5. ???
6. Profit!