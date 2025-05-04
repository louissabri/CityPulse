let map;
let markers = [];
let searchHistory = [];
let sessionId = null;

// Map styles for light and dark themes
window.lightMapStyle = [
    {
        "featureType": "all",
        "elementType": "geometry.fill",
        "stylers": [{"weight": "2.00"}]
    },
    {
        "featureType": "all",
        "elementType": "geometry.stroke",
        "stylers": [{"color": "#9c9c9c"}]
    },
    {
        "featureType": "all",
        "elementType": "labels.text",
        "stylers": [{"visibility": "on"}]
    },
    {
        "featureType": "landscape",
        "elementType": "all",
        "stylers": [{"color": "#f2f2f2"}]
    },
    {
        "featureType": "landscape",
        "elementType": "geometry.fill",
        "stylers": [{"color": "#ffffff"}]
    },
    {
        "featureType": "landscape.man_made",
        "elementType": "geometry.fill",
        "stylers": [{"color": "#ffffff"}]
    },
    {
        "featureType": "poi",
        "elementType": "all",
        "stylers": [{"visibility": "off"}]
    },
    {
        "featureType": "road",
        "elementType": "all",
        "stylers": [{"saturation": -100}, {"lightness": 45}]
    },
    {
        "featureType": "road",
        "elementType": "geometry.fill",
        "stylers": [{"color": "#eeeeee"}]
    },
    {
        "featureType": "road",
        "elementType": "labels.text.fill",
        "stylers": [{"color": "#7b7b7b"}]
    },
    {
        "featureType": "road",
        "elementType": "labels.text.stroke",
        "stylers": [{"color": "#ffffff"}]
    },
    {
        "featureType": "road.highway",
        "elementType": "all",
        "stylers": [{"visibility": "simplified"}]
    },
    {
        "featureType": "water",
        "elementType": "all",
        "stylers": [{"color": "#46bcec"}, {"visibility": "on"}]
    },
    {
        "featureType": "water",
        "elementType": "geometry.fill",
        "stylers": [{"color": "#c8d7d4"}]
    },
    {
        "featureType": "water",
        "elementType": "labels.text.fill",
        "stylers": [{"color": "#070707"}]
    },
    {
        "featureType": "water",
                "elementType": "labels.text.stroke",
        "stylers": [{"color": "#ffffff"}]
    }
];

window.darkMapStyle = [
    {
        "elementType": "geometry",
        "stylers": [{"color": "#242f3e"}]
            },
            {
                "elementType": "labels.text.fill",
                "stylers": [{"color": "#746855"}]
            },
    {
        "elementType": "labels.text.stroke",
        "stylers": [{"color": "#242f3e"}]
    },
            {
                "featureType": "administrative.locality",
                "elementType": "labels.text.fill",
                "stylers": [{"color": "#d59563"}]
            },
            {
                "featureType": "poi",
                "elementType": "labels.text.fill",
                "stylers": [{"color": "#d59563"}]
            },
            {
                "featureType": "poi.park",
                "elementType": "geometry",
                "stylers": [{"color": "#263c3f"}]
            },
            {
                "featureType": "poi.park",
                "elementType": "labels.text.fill",
                "stylers": [{"color": "#6b9a76"}]
            },
            {
                "featureType": "road",
                "elementType": "geometry",
                "stylers": [{"color": "#38414e"}]
            },
            {
                "featureType": "road",
                "elementType": "geometry.stroke",
                "stylers": [{"color": "#212a37"}]
            },
            {
                "featureType": "road",
                "elementType": "labels.text.fill",
                "stylers": [{"color": "#9ca5b3"}]
            },
            {
                "featureType": "road.highway",
                "elementType": "geometry",
                "stylers": [{"color": "#746855"}]
            },
            {
                "featureType": "road.highway",
                "elementType": "geometry.stroke",
                "stylers": [{"color": "#1f2835"}]
            },
            {
                "featureType": "road.highway",
                "elementType": "labels.text.fill",
                "stylers": [{"color": "#f3d19c"}]
            },
    {
        "featureType": "transit",
        "elementType": "geometry",
        "stylers": [{"color": "#2f3948"}]
    },
    {
        "featureType": "transit.station",
        "elementType": "labels.text.fill",
        "stylers": [{"color": "#d59563"}]
    },
            {
                "featureType": "water",
                "elementType": "geometry",
                "stylers": [{"color": "#17263c"}]
            },
            {
                "featureType": "water",
                "elementType": "labels.text.fill",
                "stylers": [{"color": "#515c6d"}]
            },
            {
                "featureType": "water",
                "elementType": "labels.text.stroke",
                "stylers": [{"color": "#17263c"}]
            }
];

// Initialize session on page load
async function initializeSession() {
    try {
        // Try to get session ID from localStorage
        sessionId = localStorage.getItem('citypulse_session_id');
        
        // If no session ID exists, request a new one
        if (!sessionId) {
            try {
                const response = await fetch('/generate_session_id', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    }
                });
                
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                
                const data = await response.json();
                sessionId = data.session_id;
            } catch (error) {
                console.warn('Failed to get session ID from server, using fallback:', error);
                sessionId = generateFallbackSessionId();
            }
            
            // Store session ID in localStorage
            localStorage.setItem('citypulse_session_id', sessionId);
        }
        
        console.log('Using session ID:', sessionId);
        return sessionId;
    } catch (error) {
        console.error('Session initialization error:', error);
        sessionId = generateFallbackSessionId();
        localStorage.setItem('citypulse_session_id', sessionId);
        return sessionId;
    }
}

// Function to generate a fallback session ID when server-side generation fails
function generateFallbackSessionId() {
    const timestamp = new Date().getTime();
    const random = Math.floor(Math.random() * 1000000);
    return `local-${timestamp}-${random}`;
}

// Initialize the map with light theme
function initMap() {
    const sydney = { lat: -33.8688, lng: 151.2093 };
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
    
    map = new google.maps.Map(document.getElementById('map'), {
        center: sydney,
        zoom: 13,
        styles: currentTheme === 'dark' ? window.darkMapStyle : window.lightMapStyle,
        mapTypeControl: false,
        streetViewControl: false,
        fullscreenControl: false
    });
    
    // Initialize markers array
    markers = [];

    // Make map globally accessible
    window.map = map;
}

// Function to update map style
function updateMapStyle(theme) {
    if (window.google && window.map && window.map instanceof google.maps.Map) {
        window.map.setOptions({
            styles: theme === 'dark' ? window.darkMapStyle : window.lightMapStyle
        });
    }
}

// Export the updateMapStyle function globally
window.updateMapStyle = updateMapStyle;

// Send message to the backend with conversation history
async function sendMessage() {
    const query = document.getElementById('query').value.trim();
    if (!query) return;
    
    console.log("Sending message:", query);
    console.log("Current session ID:", sessionId);
    
    // Remove the initial welcome message if it exists
    const initialMessage = document.querySelector('.message.system.initial');
    if (initialMessage) {
        initialMessage.remove();
    }
    
    // Add user message to chat
    addMessageToChat('user', query);
    document.getElementById('query').value = '';
    
    // Display typing indicator with loading messages
    const typingIndicator = displayTypingIndicator();
    
    try {
        // Ensure we have a session ID
        if (!sessionId) {
            await initializeSession();
            console.log("Session initialized with ID:", sessionId);
        }
        
        // Check if this is likely a follow-up query
        const isLikelyFollowUp = /what about|how about|any in|similar in/.test(query.toLowerCase());
        if (isLikelyFollowUp) {
            console.log("Detected likely follow-up query:", query);
        }
        
        // Log request details
        console.log("Sending request to /chat with data:", {
            message: query,
            session_id: sessionId
        });
        
        // Send message to backend with session ID
        const response = await fetch('/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message: query,
                session_id: sessionId
            }),
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Enhanced debugging for follow-up query issue
        console.log("Received response:", data);
        console.log("Response contains places array:", data.places ? `Yes (${data.places.length} places)` : "No");
        if (data.places) {
            console.log("First place:", data.places[0] ? data.places[0].name : "None");
        }
        
        // Remove typing indicator
        clearInterval(typingIndicator.interval);
        typingIndicator.element.remove();
        
        // Process the response based on type
        if (data.places && data.places.length > 0) {
            console.log("Search results received, formatting for display");
            
            // Track if this is likely a follow-up query based on the message
            const isFollowUpQuery = /what about|how about|any in|similar in/.test(query.toLowerCase());
            if (isFollowUpQuery) {
                console.log("Processing follow-up search results");
            }
            
            // Add assistant response to chat (without auto-scrolling - handled in addMessageToChat)
            addMessageToChat('assistant', data.response);
            
            // ALWAYS clear previous markers for ANY search results, including follow-ups
            console.log(`Clearing ${markers.length} existing markers`);
            markers.forEach(marker => marker.setMap(null));
            markers = [];
            
            // ALWAYS clear the list view for ANY search results, including follow-ups
            const listViewContainer = document.getElementById('list-view');
            if (listViewContainer) {
                console.log("Clearing existing list view");
                listViewContainer.innerHTML = '';
            }
            
            // Create bounds object to auto-zoom the map
            const bounds = new google.maps.LatLngBounds();
            
            // Add markers for each place
            console.log(`Adding ${data.places.length} new markers and list items`);
            let markersAdded = 0;
            
            data.places.forEach((place, index) => {
                // Extract location from geometry
                if (place.geometry && place.geometry.location) {
                    markersAdded++;
                    const position = new google.maps.LatLng(
                        place.geometry.location.lat,
                        place.geometry.location.lng
                    );
                    
                    // Create marker
                    const marker = new google.maps.Marker({
                        position: position,
                        map: map,
                        title: place.name,
                        label: {
                            text: (index + 1).toString(),
                            color: '#FFFFFF'
                        },
                        animation: google.maps.Animation.DROP
                    });
                    
                    // Create info window
                    const infoContent = `
                        <div class="info-window">
                            <h4>${place.name || 'Unknown'}</h4>
                            <p>${place.formatted_address || 'Address unavailable'}</p>
                        </div>
                    `;
                    
                    const infoWindow = new google.maps.InfoWindow({
                        content: infoContent
                    });
                    
                    // Add click event to marker
                    marker.addListener('click', () => {
                        // Close any open info windows
                        markers.forEach(m => {
                            if (m.infoWindow && m.infoWindow.getMap()) {
                                m.infoWindow.close();
                            }
                        });
                        
                        // Open this info window
                        infoWindow.open(map, marker);
                    });
                    
                    // Store info window with marker
                    marker.infoWindow = infoWindow;
                    
                    // Add to markers array
                    markers.push(marker);
                    
                    // Add to bounds
                    bounds.extend(position);
                    
                    // Add to list view
                    const listViewContainer = document.getElementById('list-view');
                    if (listViewContainer) {
                        // Create list item with expandable details
                        const listItem = document.createElement('div');
                        listItem.className = 'list-item';
                        
                        // Store data on the element using dataset
                        if (place.opening_hours && place.opening_hours.weekday_text) {
                            // Store as a JSON string because dataset values are strings
                            listItem.dataset.openingHours = JSON.stringify(place.opening_hours.weekday_text);
                        } else {
                            listItem.dataset.openingHours = JSON.stringify(["Opening hours not available."]);
                        }
                        listItem.dataset.aiDescription = place.ai_description || "Description not available.";
                        
                        // Create base structure for list item with only name and rating, plus hidden details
                        listItem.innerHTML = `
                            <div class="list-marker">${index + 1}</div>
                            <div class="list-content">
                                <h4>${place.name || 'Unknown'}</h4>
                                <p class="rating">${'★'.repeat(Math.round(place.rating || 0))}${'☆'.repeat(5 - Math.round(place.rating || 0))}</p>
                                
                                <!-- Hidden details section -->
                                <div class="list-item-details"> 
                                    <div class="ai-description">
                                        <!-- AI description will be loaded here on click -->
                                    </div>
                                </div>
                            </div>
                        `;
                        
                        // Add click event to list item to toggle details and interact with map
                        listItem.addEventListener('click', () => {
                            // Find the details container within this specific listItem
                            const detailsContainer = listItem.querySelector('.list-item-details');
                            const descriptionElement = detailsContainer.querySelector('.ai-description');
                            
                            // Close all other expanded items first
                            const allListItems = document.querySelectorAll('.list-item');
                            allListItems.forEach(item => {
                                if (item !== listItem && item.classList.contains('expanded')) {
                                    item.classList.remove('expanded');
                                }
                            });
                            
                            // Check if it's currently expanded
                            const isExpanded = listItem.classList.contains('expanded');
                            
                            if (!isExpanded) {
                                // Populate the details
                                
                                // Populate Description
                                descriptionElement.textContent = listItem.dataset.aiDescription;
                                
                                // Add the 'expanded' class to trigger CSS
                                listItem.classList.add('expanded');
                            } else {
                                // Remove the 'expanded' class to hide via CSS
                                listItem.classList.remove('expanded');
                            }
                            
                            // Center map on this marker
                            map.setCenter(position);
                            map.setZoom(16);
                            
                            // Close any open info windows
                            markers.forEach(m => {
                                if (m.infoWindow && m.infoWindow.getMap()) {
                                    m.infoWindow.close();
                                }
                            });
                            
                            // Open this info window
                            infoWindow.open(map, marker);
                        });
                        
                        listViewContainer.appendChild(listItem);
                    }
                }
            });
            
            // Fit map to bounds if we have markers
            if (markers.length > 0) {
                console.log(`Successfully added ${markersAdded} markers to map`);
                map.fitBounds(bounds);
                
                // Add a small padding to bounds
                const listener = google.maps.event.addListenerOnce(map, 'bounds_changed', () => {
                    if (map.getZoom() > 16) {
                        map.setZoom(16);
                    }
                });
            } else {
                console.warn("No markers were added to the map");
            }
            
            // Update search history but don't scroll
            const historyItem = {
                query: query,
                timestamp: new Date().toISOString()
            };
            searchHistory.unshift(historyItem);
            
            // Limit history to 10 items
            if (searchHistory.length > 10) {
                searchHistory.pop();
            }
            
            // Update history UI
            updateSearchHistory();
        } else if (data.places && data.places.length === 0) {
            // Handle empty places array (search with no results)
            console.log("Search returned empty places array - no results found");
            
            // Add assistant response to chat
            addMessageToChat('assistant', data.response);
            
            // Clear previous markers
            console.log("Clearing existing markers due to empty results");
            markers.forEach(marker => marker.setMap(null));
            markers = [];
            
            // Clear list view
            const listViewContainer = document.getElementById('list-view');
            if (listViewContainer) {
                console.log("Clearing existing list view due to empty results");
                listViewContainer.innerHTML = '';
            }
        } else if (data.response) {
            // Regular chat message (not search results)
            addMessageToChat('assistant', data.response);
        } else if (data.error) {
            addMessageToChat('assistant', `Sorry, I encountered an error: ${data.error}`);
        } else {
            addMessageToChat('assistant', "Something went wrong. Please try again.");
        }
    } catch (error) {
        console.error('Error sending message:', error);
        clearInterval(typingIndicator.interval);
        typingIndicator.element.remove();
        addMessageToChat('assistant', 'Sorry, there was an error processing your request. Please try again.');
    }
}

/**
 * Properly format message content with robust handling of Markdown and HTML
 * @param {string} content - The message content to format
 * @returns {string} - The formatted HTML content
 */
function formatMessageContent(content) {
    if (!content) return '';
    
    // Check if content is already HTML
    if (/<\/?[a-z][\s\S]*>/i.test(content)) {
        return content; // Return as-is if it contains HTML tags
    }
    
    // Step 1: Escape HTML to prevent injection
    let formatted = content
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    
    // Step 2: Process Markdown-style formatting in a specific order
    
    // Handle bold text - capture text between double asterisks non-greedily
    formatted = formatted.replace(/\*\*([^*]+?)\*\*/g, '<strong>$1</strong>');
    
    // Handle section titles with special formatting (Amenities, Good to know, etc.)
    formatted = formatted.replace(/\n([A-Za-z ]+):/g, '\n<span class="section-title">$1:</span>');
    
    // Handle links - very simple link detection
    formatted = formatted.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');
    
    // Step 3: Handle paragraph breaks properly
    let paragraphs = formatted.split('\n\n');
    formatted = paragraphs.map(p => {
        if (p.trim()) {
            // Replace single newlines with <br>
            return '<p>' + p.replace(/\n/g, '<br>') + '</p>';
        }
        return '';
    }).join('');
    
    return formatted;
}

// Function to add a message to the chat UI
function addMessageToChat(role, content) {
    const chatMessages = document.querySelector('.chat-messages');
    const messageElement = document.createElement('div');
    messageElement.className = `message ${role}`;
    
    // Ensure content is a string
    const contentStr = typeof content === 'string' ? content : String(content || '');
    
    // Apply special class for search queries to ensure proper styling
    if (role === 'user' && (
        contentStr.toLowerCase().includes('find') || 
        contentStr.toLowerCase().includes('where') ||
        contentStr.toLowerCase().includes('show me') ||
        contentStr.toLowerCase().match(/\w+ in \w+/)
    )) {
        messageElement.classList.add('search-query');
    }
    
    // Format the message content with our robust formatter
    const formattedContent = formatMessageContent(contentStr);
    
    // Set the formatted content to the message element
    messageElement.innerHTML = formattedContent;
    
    // Add the message to the chat container
    chatMessages.appendChild(messageElement);
    
    // Only scroll to bottom for user messages
    if (role === 'user') {
        scrollToBottom();
    }
}

// Function to display typing indicator with cycling quirky messages
function displayTypingIndicator() {
    const chatMessages = document.querySelector('.chat-messages');
    const typingElement = document.createElement('div');
    typingElement.className = 'message assistant typing';
    
    // Create a container for better centering
    const typingContainer = document.createElement('div');
    typingContainer.className = 'typing-container';
    
    // Create message element for the loading dots
    const loadingDotsElement = document.createElement('div');
    loadingDotsElement.className = 'typing-dots';
    loadingDotsElement.innerHTML = '<span></span><span></span><span></span>';
    
    // Create element for the quirky message
    const quirkyMessageElement = document.createElement('div');
    quirkyMessageElement.className = 'quirky-message';
    
    // Array of quirky messages (expanded to 30 messages)
    const quirkyMessages = [
        "Checking Sydney's hidden gems...",
        "Asking the locals for recommendations...",
        "Scouring the latest reviews...",
        "Finding the perfect spot for you...",
        "Consulting my Sydney guidebook...",
        "Analyzing thousands of reviews...",
        "Checking with my foodie friends...",
        "Searching high and low in Sydney...",
        "Looking for local hotspots...",
        "Digging through Sydney's best kept secrets...",
        "Checking Instagram for trendy spots...",
        "Speaking with Sydney baristas...",
        "Reading through food blogs...",
        "Contacting Sydney tour guides...",
        "Analyzing satellite imagery of Sydney...",
        "Checking today's weather for outdoor spots...",
        "Filtering for places with the best ambiance...",
        "Finding places the locals don't want you to know about...",
        "Checking what's open right now...",
        "Browsing through Sydney's event calendar...",
        "Searching for hidden restaurant menus...",
        "Consulting my network of Sydney foodies...",
        "Finding places with the best views...",
        "Checking which places are trending this week...",
        "Finding spots with the shortest wait times...",
        "Searching for places with unique experiences...",
        "Checking which places are kid-friendly...",
        "Finding venues with outdoor seating...",
        "Analyzing parking availability nearby...",
        "Searching for hidden street art nearby..."
    ];
    
    // Create a shuffled copy of the messages array
    let shuffledMessages = [...quirkyMessages];
    shuffleArray(shuffledMessages);
    
    let previousMessageIndex = -1; // Track the previously shown message
    
    // Randomly select initial quirky message (ensuring no consecutive repeats)
    let initialMessageIndex = Math.floor(Math.random() * shuffledMessages.length);
    quirkyMessageElement.textContent = shuffledMessages[initialMessageIndex];
    previousMessageIndex = initialMessageIndex;
    
    // Add elements to the container
    typingContainer.appendChild(loadingDotsElement);
    typingContainer.appendChild(quirkyMessageElement);
    
    // Add container to typing element
    typingElement.appendChild(typingContainer);
    chatMessages.appendChild(typingElement);
    
    // Don't auto-scroll for typing indicator
    // The typing indicator is from the assistant, so we don't want to scroll
    
    // Cycle through quirky messages with random selection but no repeats
    const interval = setInterval(() => {
        // Generate a new random index that's different from the previous one
        let newIndex;
        do {
            newIndex = Math.floor(Math.random() * shuffledMessages.length);
        } while (newIndex === previousMessageIndex);
        
        // Update the previous index
        previousMessageIndex = newIndex;
        
        // Fade out the current message
        quirkyMessageElement.style.opacity = 0;
        
        // Change message content and fade in after a short delay
        setTimeout(() => {
            quirkyMessageElement.textContent = shuffledMessages[newIndex];
            quirkyMessageElement.style.opacity = 1;
        }, 200);
        
        // Reshuffle the array occasionally to maintain randomness
        if (Math.random() < 0.2) { // 20% chance to reshuffle
            shuffleArray(shuffledMessages);
        }
    }, 4000);
    
    return {
        element: typingElement,
        interval: interval
    };
}

// Function to scroll to the bottom of the chat
function scrollToBottom() {
    const chatMessages = document.querySelector('.chat-messages');
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Update search history UI
function updateSearchHistory() {
    const historyContainer = document.getElementById('search-history');
    if (historyContainer) {
        historyContainer.innerHTML = '';
        
        searchHistory.forEach(item => {
            const historyItem = document.createElement('div');
            historyItem.className = 'history-item';
            historyItem.textContent = item.query;
            historyItem.addEventListener('click', () => {
                document.getElementById('query').value = item.query;
                sendMessage();
            });
            historyContainer.appendChild(historyItem);
        });
    }
}

// Function to clear conversation and start fresh
function clearConversation() {
    // Clear chat UI
    const chatMessages = document.querySelector('.chat-messages');
    chatMessages.innerHTML = '';
    
    // Generate a new session ID
    sessionId = generateFallbackSessionId();
    localStorage.setItem('citypulse_session_id', sessionId);
    
    // Re-add the initial welcome message with example buttons
    const welcomeMessage = document.createElement('div');
    welcomeMessage.className = 'message system initial';
    welcomeMessage.innerHTML = `
        <h2>Welcome to CityPulse</h2>
        <p>Ask me about places in Sydney and I'll help you discover the best spots!</p>
        <div class="example-queries">
            <button class="query-pill" onclick="useExample(this)">Dog friendly beer gardens in Newtown</button>
            <button class="query-pill" onclick="useExample(this)">Hidden bars in Darlinghurst</button>
            <button class="query-pill" onclick="useExample(this)">Family-friendly restaurants in Bondi</button>
        </div>
    `;
    chatMessages.appendChild(welcomeMessage);
    
    // Scroll to bottom to show the welcome message (user-initiated action)
    scrollToBottom();
}

// Add event listener for Enter key
document.getElementById('query').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        sendMessage();
    }
});

// Handle example query clicks
function useExample(button) {
    // This is a user-initiated action (clicking an example), so we'll treat it like a user message
    const input = document.getElementById('query');
    input.value = button.textContent;
    sendMessage();
}

// Initialize the application
document.addEventListener('DOMContentLoaded', async () => {
    // Initialize map
    initMap();
    
    // Check for pending query from How It Works page
    const pendingQuery = localStorage.getItem('pendingQuery');
    if (pendingQuery) {
        // Clear it immediately to prevent reuse
        localStorage.removeItem('pendingQuery');
        
        // Wait a moment for everything to initialize
        setTimeout(() => {
            const chatInput = document.getElementById('chat-input');
            if (chatInput) {
                chatInput.value = pendingQuery;
                // Trigger send if auto-send is desired
                // Alternatively, just let the user review the query before sending
                // document.querySelector('.send-button').click();
            }
        }, 1000);
    }
    
    // Initialize session
    await initializeSession();
    
    // Add Enter key listener for query input
    const queryInput = document.getElementById('query');
    if (queryInput) {
        queryInput.addEventListener('keydown', function(event) {
            if (event.key === 'Enter') {
                sendMessage();
            }
        });
    }
    
    // Add window resize event listener to ensure chat container fits on screen
    window.addEventListener('resize', adjustChatContainerPosition);
});

// Function to adjust chat container position when window is resized
function adjustChatContainerPosition() {
    const chatContainer = document.getElementById('chat-container');
    if (!chatContainer || chatContainer.classList.contains('hidden')) return;
    
    const containerRect = chatContainer.getBoundingClientRect();
    const viewportHeight = window.innerHeight;
    
    if (containerRect.bottom > viewportHeight) {
        // Adjust top position to fit in viewport
        const newTop = Math.max(60, viewportHeight - containerRect.height - 20);
        chatContainer.style.top = newTop + 'px';
    }
}

// Add a shuffle function to the script
function shuffleArray(array) {
    for (let i = array.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [array[i], array[j]] = [array[j], array[i]]; // Swap elements
    }
    return array;
}

// Function to handle chat toggle
function toggleChat() {
    const chatContainer = document.getElementById('chat-container');
    const chatToggleBtn = document.getElementById('chat-toggle-btn');
    const icon = chatToggleBtn.querySelector('i');
    
    chatContainer.classList.toggle('hidden');
    
    // Update button icon
    if (chatContainer.classList.contains('hidden')) {
        icon.classList.remove('fa-times');
        icon.classList.add('fa-comments');
    } else {
        icon.classList.remove('fa-comments');
        icon.classList.add('fa-times');
        
        // Check if chat container is partially off-screen and adjust if needed
        const containerRect = chatContainer.getBoundingClientRect();
        const viewportHeight = window.innerHeight;
        
        if (containerRect.bottom > viewportHeight) {
            // Adjust top position to fit in viewport
            const newTop = Math.max(60, viewportHeight - containerRect.height - 20);
            chatContainer.style.top = newTop + 'px';
        }
        
        // Focus the input field when chat is opened
        setTimeout(() => {
            const queryInput = document.getElementById('query');
            if (queryInput) queryInput.focus();
        }, 300);
        
        // Don't automatically scroll to the bottom when opening the chat
        // This allows users to see the conversation history
    }
}
