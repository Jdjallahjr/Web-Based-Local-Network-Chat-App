document.addEventListener("DOMContentLoaded", () => {
    const socket = io();
    const chatBox = document.getElementById("chat-box");
    const messageInput = document.getElementById("message");
    const nameInput = document.getElementById("username");
    let selectedUser = null;
    let mySessionId = null;

    // Set user's name
    window.setUsername = function() {
        const username = nameInput.value.trim();
        if (username !== "") {
            socket.emit("register_name", { name: username });
            document.getElementById("username-form").classList.add("d-none");
            document.getElementById("chat-interface").classList.remove("d-none");
            
            // Save username to localStorage
            localStorage.setItem("chatUsername", username);
        }
    };

    // Check if username exists in localStorage
    const savedUsername = localStorage.getItem("chatUsername");
    if (savedUsername) {
        nameInput.value = savedUsername;
    }

    // Handle incoming messages
    socket.on("message", (data) => {
        const isCurrentUser = data.sender_id === mySessionId;
        const messageElement = document.createElement("div");
        
        // Set message alignment based on sender
        messageElement.classList.add("message", isCurrentUser ? "message-sent" : "message-received");
        
        // For private messages
        if (data.private) {
            messageElement.classList.add("private-message");
        }
        
        // Create message content
        const messageContent = document.createElement("div");
        messageContent.classList.add("message-content");
        
        // Add sender name for received messages
        if (!isCurrentUser) {
            const senderName = document.createElement("div");
            senderName.classList.add("sender-name");
            senderName.textContent = `${data.sender_name} (${data.sender_ip})`;
            messageContent.appendChild(senderName);
        }
        
        // Add message text
        const messageText = document.createElement("div");
        messageText.classList.add("message-text");
        messageText.textContent = data.message;
        messageContent.appendChild(messageText);
        
        // Add timestamp
        const timestamp = document.createElement("div");
        timestamp.classList.add("message-time");
        const date = new Date(data.timestamp * 1000);
        timestamp.textContent = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        messageContent.appendChild(timestamp);
        
        messageElement.appendChild(messageContent);
        chatBox.appendChild(messageElement);
        chatBox.scrollTop = chatBox.scrollHeight;
    });

    // Get current user's session ID
    socket.on("connect", () => {
        mySessionId = socket.id;

        // If there's a saved username, automatically register it
        if (savedUsername) {
            socket.emit("register_name", { name: savedUsername });
            document.getElementById("username-form").classList.add("d-none");
            document.getElementById("chat-interface").classList.remove("d-none");
        }
    });

    // Send message (private if a user is selected)
    window.sendMessage = function() {
        const message = messageInput.value.trim();
        if (message !== "") {
            if (selectedUser) {
                socket.emit("private_message", { recipient: selectedUser, message: message });
            } else {
                socket.send(message);
            }
            messageInput.value = "";
        }
    };

    messageInput.addEventListener("keypress", (event) => {
        if (event.key === "Enter") {
            sendMessage();
        }
    });
    
    nameInput.addEventListener("keypress", (event) => {
        if (event.key === "Enter") {
            setUsername();
        }
    });

    // Track users
    let users = {};

    // Update user list when users change
    socket.on("update_users", (updatedUsers) => {
        users = updatedUsers;
        updateUserList();
    });
    
    // Handle discovered devices
    socket.on("update_discovered_devices", (devices) => {
        discoveredDevices = devices;
        updateUserList();
    });
    
    let discoveredDevices = {};
    
    // Update the user list in the sidebar
    function updateUserList() {
        const userList = document.getElementById("userList");
        userList.innerHTML = "";
        
        // First add connected users
        const connectedHeader = document.createElement("div");
        connectedHeader.classList.add("sidebar-section-header");
        connectedHeader.textContent = "Connected Users";
        userList.appendChild(connectedHeader);
        
        for (const [sessionId, info] of Object.entries(users)) {
            const listItem = document.createElement("li");
            listItem.innerHTML = `<span class="user-name">${info.name}</span><span class="user-ip">${info.ip}</span>`;
            listItem.dataset.sessionId = sessionId;
            
            // Highlight current user
            if (sessionId === mySessionId) {
                listItem.classList.add("current-user");
                listItem.innerHTML += '<span class="badge bg-success">You</span>';
            } else {
                // Only add click listener for other users
                listItem.addEventListener("click", () => {
                    // Toggle selection
                    if (selectedUser === sessionId) {
                        selectedUser = null;
                        document.querySelectorAll("#userList li").forEach(li => li.classList.remove("selected"));
                        document.getElementById("private-indicator").textContent = "Public Chat";
                        socket.emit("leave_private_chat", { recipient_id: sessionId });
                    } else {
                        selectedUser = sessionId;
                        document.querySelectorAll("#userList li").forEach(li => li.classList.remove("selected"));
                        listItem.classList.add("selected");
                        document.getElementById("private-indicator").textContent = `Private: ${info.name}`;
                        socket.emit("join_private_chat", { recipient_id: sessionId });
                    }
                });
            }
            
            userList.appendChild(listItem);
        }
        
        // Then add discovered devices
        if (Object.keys(discoveredDevices).length > 0) {
            const discoveredHeader = document.createElement("div");
            discoveredHeader.classList.add("sidebar-section-header");
            discoveredHeader.textContent = "Discovered Devices";
            userList.appendChild(discoveredHeader);
            
            for (const [ip, info] of Object.entries(discoveredDevices)) {
                // Check if this device is already in the connected users list
                let alreadyConnected = false;
                for (const userInfo of Object.values(users)) {
                    if (userInfo.ip === ip) {
                        alreadyConnected = true;
                        break;
                    }
                }
                
                // Skip if already connected
                if (alreadyConnected) {
                    continue;
                }
                
                const listItem = document.createElement("li");
                listItem.classList.add("discovered-device");
                listItem.innerHTML = `<span class="user-name">${info.name}</span><span class="user-ip">${ip}</span>`;
                userList.appendChild(listItem);
            }
        }
    }

    // Sidebar toggle
    window.toggleSidebar = function() {
        const sidebar = document.getElementById("userSidebar");
        const wrapper = document.querySelector(".container-wrapper");
        sidebar.classList.toggle("collapsed");
        wrapper.classList.toggle("sidebar-collapsed");
    };

    // Handle device orientation changes and resize events
    window.addEventListener('resize', adjustLayoutForScreen);
    
    function adjustLayoutForScreen() {
        const sidebar = document.getElementById("userSidebar");
        const wrapper = document.querySelector(".container-wrapper");
        
        if (window.innerWidth < 768) {
            sidebar.classList.add("collapsed");
            wrapper.classList.add("sidebar-collapsed");
        } else {
            sidebar.classList.remove("collapsed");
            wrapper.classList.remove("sidebar-collapsed");
        }
    }
    
    // Initial layout adjustment
    adjustLayoutForScreen();
});