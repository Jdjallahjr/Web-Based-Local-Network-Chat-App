from flask import Flask, render_template, request
from flask_socketio import SocketIO, send, emit, join_room, leave_room
import socket
import threading
import time
import netifaces
import ipaddress
import subprocess
import re
import platform

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
socketio = SocketIO(app, cors_allowed_origins="*")

users = {} 
discovered_devices = {}  
chat_history = {
    "public": []  
}

def get_local_ip():
    """Get the local IP address of this machine"""
    try:
        interfaces = netifaces.interfaces()
        for interface in interfaces:
            if interface.startswith('lo'):
                continue
            
            addresses = netifaces.ifaddresses(interface)
            if netifaces.AF_INET in addresses:
                for address_info in addresses[netifaces.AF_INET]:
                    ip = address_info['addr']
                    if ip.startswith('192.168.') or ip.startswith('10.') or ip.startswith('172.'):
                        return ip
        return socket.gethostbyname(socket.gethostname())
    except:
        return "127.0.0.1"

def get_network_devices():
    """Get all devices on the network using platform-specific commands"""
    local_ip = get_local_ip()
    
    if not local_ip or local_ip == "127.0.0.1":
        return
    
    # Get the subnet to scan
    network = '.'.join(local_ip.split('.')[0:3]) + '.'
    
    # Different approaches based on OS
    if platform.system() == "Windows":
        try:
            # Use ARP to find devices on Windows
            result = subprocess.run(['arp', '-a'], capture_output=True, text=True)
            output = result.stdout
            
            # Parse ARP output
            ip_pattern = re.compile(r'(\d+\.\d+\.\d+\.\d+)')
            for line in output.split('\n'):
                if network in line:  # Only devices in subnet
                    ip_match = ip_pattern.search(line)
                    if ip_match:
                        ip = ip_match.group(1)
                        try:
                            hostname = socket.getfqdn(ip)
                            if hostname == ip:  # If hostname resolution failed
                                hostname = f"Device-{ip.split('.')[-1]}"
                        except:
                            hostname = f"Device-{ip.split('.')[-1]}"
                            
                        discovered_devices[ip] = {
                            "name": hostname,
                            "last_seen": time.time(),
                            "active": False  # Assume not running the app initially
                        }
        except:
            pass
    else:
        try:
            # Use ping scan on Linux/Mac
            for i in range(1, 255):
                ip = network + str(i)
                if ip == local_ip:
                    continue
                    
                # Check if the device responds to ping
                ping_param = '-n' if platform.system() == "Windows" else '-c'
                result = subprocess.run(['ping', ping_param, '1', '-W', '1', ip], 
                                       stdout=subprocess.DEVNULL, 
                                       stderr=subprocess.DEVNULL)
                if result.returncode == 0:
                    try:
                        hostname = socket.getfqdn(ip)
                        if hostname == ip:  # If hostname resolution failed
                            hostname = f"Device-{i}"
                    except:
                        hostname = f"Device-{i}"
                        
                    discovered_devices[ip] = {
                        "name": hostname,
                        "last_seen": time.time(),
                        "active": False  # Assume not running the app initially
                    }
        except:
            pass

def check_active_devices():
    """Check which discovered devices are running the chat app"""
    for ip in discovered_devices:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex((ip, 5000))  # Check if port 5000 is open
            
            if result == 0:
                discovered_devices[ip]["active"] = True
            else:
                discovered_devices[ip]["active"] = False
                
            sock.close()
        except:
            discovered_devices[ip]["active"] = False

def discover_devices():
    """Scan the local network for devices"""
    while True:
        get_network_devices()
        check_active_devices()
        
        # Clean up devices that haven't been seen in 10 minutes
        current_time = time.time()
        to_remove = []
        for ip, info in discovered_devices.items():
            if current_time - info["last_seen"] > 600:  # 10 minutes
                to_remove.append(ip)
        
        for ip in to_remove:
            del discovered_devices[ip]
        
        # Broadcast discovered devices to all connected clients
        socketio.emit("update_discovered_devices", discovered_devices)
        
        time.sleep(30)  # Scan every 30 seconds

def get_chat_id(user1, user2):
    """Generate a unique chat ID for two users"""
    # Sort the IDs to ensure the same chat ID regardless of order
    sorted_ids = sorted([user1, user2])
    return f"{sorted_ids[0]}:{sorted_ids[1]}"

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    client_ip = request.remote_addr  # Get user's IP
    session_id = request.sid  # Unique session ID
    
    try:
        client_name = socket.gethostbyaddr(client_ip)[0]
    except:
        client_name = f"User-{session_id[:4]}"
    
    users[session_id] = {
        "ip": client_ip,
        "name": client_name
    }

    # Mark the device as active in discovered_devices
    if client_ip in discovered_devices:
        discovered_devices[client_ip]["active"] = True
        discovered_devices[client_ip]["last_seen"] = time.time()
    else:
        discovered_devices[client_ip] = {
            "name": client_name,
            "last_seen": time.time(),
            "active": True
        }

    join_room("public")

    # Send the chat history to the new user
    emit("chat_history", {"room": "public", "history": chat_history["public"]})
    
    emit("update_users", users, broadcast=True)  # Update users list
    emit("update_discovered_devices", discovered_devices)  # Send discovered devices
    
    # Broadcast new user notification
    message_data = {
        "sender_id": "system",
        "sender_name": "System",
        "sender_ip": "",
        "message": f"{client_name} has joined the chat",
        "timestamp": time.time(),
        "system": True
    }
    emit("message", message_data, room="public")
    
    print(f"User connected: {client_name} ({client_ip}, Session: {session_id})")

@socketio.on('register_name')
def register_name(data):
    session_id = request.sid
    if session_id in users:
        old_name = users[session_id]["name"]
        users[session_id]["name"] = data["name"]
        
        # Update device name in discovered devices
        client_ip = users[session_id]["ip"]
        if client_ip in discovered_devices:
            discovered_devices[client_ip]["name"] = data["name"]
        
        emit("update_users", users, broadcast=True)
        emit("update_discovered_devices", discovered_devices, broadcast=True)
        
        # Broadcast name change notification
        message_data = {
            "sender_id": "system",
            "sender_name": "System",
            "sender_ip": "",
            "message": f"{old_name} changed their name to {data['name']}",
            "timestamp": time.time(),
            "system": True
        }
        emit("message", message_data, room="public")
        
        print(f"User renamed: {users[session_id]['name']} ({users[session_id]['ip']})")

@socketio.on('disconnect')
def handle_disconnect():
    session_id = request.sid
    if session_id in users:
        client_name = users[session_id]["name"]
        client_ip = users[session_id]["ip"]
        
        # Mark the device as inactive in discovered_devices
        if client_ip in discovered_devices:
            discovered_devices[client_ip]["active"] = False
        
        # Leave all rooms
        leave_room("public")
        
        # Broadcast user left notification
        message_data = {
            "sender_id": "system",
            "sender_name": "System",
            "sender_ip": "",
            "message": f"{client_name} has left the chat",
            "timestamp": time.time(),
            "system": True
        }
        emit("message", message_data, room="public")
        
        # Remove user
        del users[session_id]
        emit("update_users", users, broadcast=True)
        emit("update_discovered_devices", discovered_devices, broadcast=True)
        
        print(f"User disconnected: {client_name} ({client_ip})")

@socketio.on('join_private_chat')
def join_private_chat(data):
    sender_id = request.sid
    recipient_id = data['recipient_id']
    
    if sender_id in users and recipient_id in users:
        # Create a unique chat room ID
        chat_id = get_chat_id(sender_id, recipient_id)
        
        # Join the room
        join_room(chat_id)
        
        # Initialize chat history if it doesn't exist
        if chat_id not in chat_history:
            chat_history[chat_id] = []
        
        # Send chat history to the user
        emit("chat_history", {"room": chat_id, "history": chat_history[chat_id]})
        
        print(f"User {users[sender_id]['name']} joined private chat with {users[recipient_id]['name']}")

@socketio.on('leave_private_chat')
def leave_private_chat(data):
    sender_id = request.sid
    recipient_id = data['recipient_id']
    
    if sender_id in users and recipient_id in users:
        # Get the chat room ID
        chat_id = get_chat_id(sender_id, recipient_id)
        
        # Leave the room
        leave_room(chat_id)
        
        # Send public chat history to the user
        emit("chat_history", {"room": "public", "history": chat_history["public"]})
        
        print(f"User {users[sender_id]['name']} left private chat with {users[recipient_id]['name']}")

@socketio.on('message')
def handle_message(msg):
    sender_id = request.sid
    if sender_id in users:
        sender_info = users[sender_id]
        
        # Create message data
        message_data = {
            "sender_id": sender_id,
            "sender_name": sender_info["name"],
            "sender_ip": sender_info["ip"],
            "message": msg,
            "timestamp": time.time()
        }
        
        # Add to public chat history
        chat_history["public"].append(message_data)
        
        # Keep chat history at a reasonable size
        if len(chat_history["public"]) > 100:
            chat_history["public"] = chat_history["public"][-100:]
        
        # Broadcast the message to all users in public chat
        emit("message", message_data, room="public")

@socketio.on('private_message')
def handle_private_message(data):
    sender_id = request.sid
    recipient_id = data['recipient']
    message = data['message']

    if sender_id in users and recipient_id in users:
        sender_info = users[sender_id]
        recipient_info = users[recipient_id]
        
        # Create a unique chat room ID
        chat_id = get_chat_id(sender_id, recipient_id)
        
        # Create message data
        message_data = {
            "sender_id": sender_id,
            "sender_name": sender_info["name"],
            "sender_ip": sender_info["ip"],
            "message": message,
            "timestamp": time.time(),
            "private": True
        }
        
        # Add to private chat history
        if chat_id not in chat_history:
            chat_history[chat_id] = []
        
        chat_history[chat_id].append(message_data)
        
        # Keep chat history at a reasonable size
        if len(chat_history[chat_id]) > 100:
            chat_history[chat_id] = chat_history[chat_id][-100:]
        
        # Send to both users in the private chat
        emit("message", message_data, room=chat_id)
        
        print(f"Private message from {sender_info['name']} to {recipient_info['name']}: {message}")

if __name__ == '__main__':
    # Start device discovery in a separate thread
    discovery_thread = threading.Thread(target=discover_devices, daemon=True)
    discovery_thread.start()
    
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)