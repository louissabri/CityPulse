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
        console.log("Received response:", data);
        
        // Remove typing indicator
        clearInterval(typingIndicator.interval);
        typingIndicator.element.remove();
        
        // Add assistant response to chat
        if (data.places && data.places.length > 0) {
            console.log("Search results received, formatting for display");
            
            // Format place data into a nice HTML display
            let placesHTML = `
                <div class="search-summary">
                    <p>${data.summary}</p>
                </div>
            `;
            
            // Add highlights if available
            if (data.highlights) {
                placesHTML += `
                    <div class="highlights">
                        <h4>Highlights</h4>
                        <p>${data.highlights}</p>
                    </div>
                `;
            }
            
            // Start the grid for place cards
            placesHTML += `<div class="places-grid">`;
            
            // Add individual place cards
            data.places.forEach(place => {
                const rating = place.rating && typeof place.rating === 'number' ? 
                               '★'.repeat(Math.round(place.rating)) + '☆'.repeat(5 - Math.round(place.rating)) :
                               'Rating N/A';
                placesHTML += `
                    <div class="place-card">
                        <h4>${place.name}</h4>
                        <p class="address">${place.address}</p>
                        <p class="rating">${rating} ${place.total_ratings ? `(${place.total_ratings} reviews)` : ''}</p>
                        ${place.website ? `<p><a href="${place.website}" target="_blank">Website</a></p>` : ''}
                    </div>
                `;
            });
            
            // Close the grid
            placesHTML += `</div>`;
            
            // Add additional info sections if available
            if (data.social_proof || data.considerations) {
                placesHTML += `<div class="additional-info">`;
                
                if (data.social_proof) {
                    placesHTML += `
                        <div class="social-proof">
                            <h4>What others say</h4>
                            <p>${data.social_proof}</p>
                        </div>
                    `;
                }
                
                if (data.considerations) {
                    placesHTML += `
                        <div class="considerations">
                            <h4>Things to consider</h4>
                            <p>${data.considerations}</p>
                        </div>
                    `;
                }
                
                placesHTML += `</div>`;
            }
            
            // Add the formatted places display to chat
            addMessageToChat('assistant', placesHTML);
            
            // Clear previous markers
            if (markers.length > 0) {
                markers.forEach(marker => marker.setMap(null));
                markers = [];
            }
            
            // Add markers to the map and prepare list view data
            const listViewContainer = document.getElementById('list-view');
            if (listViewContainer) {
                listViewContainer.innerHTML = '';
            }
            
            // Create bounds object to auto-zoom the map
            const bounds = new google.maps.LatLngBounds();
            
            // Add markers for each place
            data.places.forEach((place, index) => {
                if (place.location && place.location.lat && place.location.lng) {
                    const position = new google.maps.LatLng(place.location.lat, place.location.lng);
                    
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
                            <h4>${place.name}</h4>
                            <p>${place.address}</p>
                            <p>Rating: ${place.rating}★ (${place.total_ratings} reviews)</p>
                            ${place.website ? `<p><a href="${place.website}" target="_blank">Website</a></p>` : ''}
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
                    if (listViewContainer) {
                        const listItem = document.createElement('div');
                        listItem.className = 'list-item';
                        listItem.innerHTML = `
                            <div class="list-marker">${index + 1}</div>
                            <div class="list-content">
                                <h4>${place.name}</h4>
                                <p class="address">${place.address}</p>
                                <p class="rating">${'★'.repeat(Math.round(place.rating))}${'☆'.repeat(5 - Math.round(place.rating))} (${place.total_ratings})</p>
                                ${place.website ? `<p><a href="${place.website}" target="_blank">Website</a></p>` : ''}
                            </div>
                        `;
                        
                        // Add click event to list item
                        listItem.addEventListener('click', () => {
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
                            
                            // Switch to map view if in list view
                            showMapView();
                        });
                        
                        listViewContainer.appendChild(listItem);
                    }
                }
            });
            
            // Fit map to bounds if we have markers
            if (markers.length > 0) {
                map.fitBounds(bounds);
                
                // Add a small padding to bounds
                const listener = google.maps.event.addListenerOnce(map, 'bounds_changed', () => {
                    if (map.getZoom() > 16) {
                        map.setZoom(16);
                    }
                });
            }
            
            // Add view toggle functionality
            setupViewToggle();
            
            // Scroll to bottom and update search history
            scrollToBottom();
            
            // Update search history
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
        } else {
            // Regular message (not search results)
            addMessageToChat('assistant', data.response);
        }
        
        // Scroll to bottom of chat
        scrollToBottom();
    } catch (error) {
        console.error('Error sending message:', error);
        clearInterval(typingIndicator.interval);
        typingIndicator.element.remove();
        addMessageToChat('assistant', 'Sorry, there was an error processing your request. Please try again.');
    }
}

// Function to add a message to the chat UI
function addMessageToChat(role, content) {
    const chatMessages = document.querySelector('.chat-messages');
    const messageElement = document.createElement('div');
    messageElement.className = `message ${role}`;
    
    // Ensure content is a string
    const contentStr = typeof content === 'string' ? content : String(content || '');
    
    // Convert any links in the content to clickable links
    const linkedContent = contentStr.replace(
        /(https?:\/\/[^\s]+)/g, 
        '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>'
    );
    
    // Check if content contains special formatting for search results
    if (contentStr.includes('<div class="places-grid">')) {
        messageElement.innerHTML = contentStr;
    } else {
        messageElement.innerHTML = linkedContent;
    }
    
    chatMessages.appendChild(messageElement);
    scrollToBottom();
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
    
    // Scroll to show the typing indicator
    scrollToBottom();
    
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
            <button class="query-pill" onclick="useExample(this)">Best coffee in Surry Hills</button>
            <button class="query-pill" onclick="useExample(this)">Hidden bars in Darlinghurst</button>
            <button class="query-pill" onclick="useExample(this)">Family-friendly restaurants in Bondi</button>
        </div>
    `;
    chatMessages.appendChild(welcomeMessage);
}

// Add event listener for Enter key
document.getElementById('query').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        sendMessage();
    }
});

// Handle example query clicks
function useExample(button) {
    const input = document.getElementById('query');
    input.value = button.textContent;
    sendMessage();
}

// Initialize the application
document.addEventListener('DOMContentLoaded', async () => {
    // Initialize session
    await initializeSession();
    
    // The initial welcome message is already in the HTML, no need to add it again
});

// Add a shuffle function to the script
function shuffleArray(array) {
    for (let i = array.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [array[i], array[j]] = [array[j], array[i]]; // Swap elements
    }
    return array;
}

// Add this function after scrollToBottom()
function setupViewToggle() {
    // Add event listeners to view toggle buttons if they don't already have them
    const mapViewBtn = document.querySelector('button[data-view="map"]');
    const listViewBtn = document.querySelector('button[data-view="list"]');
    
    if (mapViewBtn && !mapViewBtn._hasListener) {
        mapViewBtn.addEventListener('click', showMapView);
        mapViewBtn._hasListener = true;
    }
    
    if (listViewBtn && !listViewBtn._hasListener) {
        listViewBtn.addEventListener('click', showListView);
        listViewBtn._hasListener = true;
    }
}

function showMapView() {
    const mapElement = document.getElementById('map');
    const listViewElement = document.getElementById('list-view');
    const mapViewBtn = document.querySelector('button[data-view="map"]');
    const listViewBtn = document.querySelector('button[data-view="list"]');
    
    if (mapElement && listViewElement) {
        // Show map, hide list
        mapElement.classList.remove('hidden');
        listViewElement.classList.add('hidden');
        
        // Update buttons
        mapViewBtn.classList.add('active');
        listViewBtn.classList.remove('active');
        
        // Refresh map
        if (window.google && map) {
            google.maps.event.trigger(map, 'resize');
        }
    }
}

function showListView() {
    const mapElement = document.getElementById('map');
    const listViewElement = document.getElementById('list-view');
    const mapViewBtn = document.querySelector('button[data-view="map"]');
    const listViewBtn = document.querySelector('button[data-view="list"]');
    
    if (mapElement && listViewElement) {
        // Show list, hide map
        mapElement.classList.add('hidden');
        listViewElement.classList.remove('hidden');
        
        // Update buttons
        mapViewBtn.classList.remove('active');
        listViewBtn.classList.add('active');
    }
}
