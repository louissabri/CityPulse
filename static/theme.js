// Map styles
const lightMapStyle = [
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

const darkMapStyle = [
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

// Theme handling
function initTheme() {
    // Check for saved theme preference, default to light
    const savedTheme = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
    
    // Update toggle switch state
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        themeToggle.checked = savedTheme === 'dark';
    }

    // Only update map style if Google Maps is loaded and map is initialized
    if (window.google && window.map && typeof window.updateMapStyle === 'function') {
        window.updateMapStyle(savedTheme);
    }
}

function toggleTheme(event) {
    const newTheme = event.target.checked ? 'dark' : 'light';
    
    // Update theme
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);

    // Only update map style if Google Maps is loaded and map is initialized
    if (window.google && window.map && typeof window.updateMapStyle === 'function') {
        window.updateMapStyle(newTheme);
    }
}

// Initialize theme
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    
    // Add change handler to theme toggle
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        themeToggle.addEventListener('change', toggleTheme);
    }
}); 