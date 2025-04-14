from flask import Flask, render_template, request, jsonify, send_from_directory
import os
import openai
import googlemaps
from dotenv import load_dotenv
from pathlib import Path
from data_sources import DataSourceManager
import asyncio
import logging
from conversation_manager import ConversationManager
from datetime import datetime
import re
import json
from typing import List, Dict, Optional, Set

# Constants
MAX_PLACES_TO_ANALYZE = 7  # Number of top places to analyze in depth
DEFAULT_LOCATION_COORDS = {'lat': -33.8688, 'lng': 151.2093}  # Sydney CBD

# Load environment variables
env_path = Path('.') / '.env'
load_dotenv(env_path, override=True)

maps_api_key = os.getenv('MAPS_API_KEY')
if not maps_api_key:
    print("WARNING: No Maps API key found!")

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', os.urandom(24).hex())

# Set up enhanced logging
logging.basicConfig(
    level=logging.INFO,  # Changed back to INFO for production
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.setLevel(logging.INFO)

# Initialize API clients
openai_api_key = os.getenv('OPENAI_API_KEY')
openai.api_key = openai_api_key
try:
    gmaps = googlemaps.Client(key=maps_api_key)
    test_result = gmaps.geocode('Sydney, Australia')
    if not test_result:
        print("Google Maps API key validation failed - no results returned")
except Exception as e:
    print(f"Error initializing Google Maps client: {str(e)}")
    gmaps = None

# Initialize data source manager
data_manager = DataSourceManager()

# Initialize conversation manager
conversation_manager = ConversationManager()

# Cleaning up old sessions every day
CLEANUP_INTERVAL = 60 * 60 * 24  # Once per day
last_cleanup_time = 0

def maybe_cleanup():
    """Occasionally clean up old sessions."""
    global last_cleanup_time
    current_time = int(datetime.now().timestamp())
    if current_time - last_cleanup_time > CLEANUP_INTERVAL:
        deleted = conversation_manager.cleanup_old_sessions(days=7)
        logger.info(f"Cleaned up {deleted} old conversation sessions")
        last_cleanup_time = current_time

@app.route('/')
def home():
    return render_template('index.html', maps_api_key=maps_api_key)

@app.route('/api')
def api_docs():
    return render_template('api.html')

@app.route('/generate_session_id', methods=['POST'])
def generate_session_id():
    """Generate a new session ID for the client."""
    user_ip = request.remote_addr
    user_agent = request.headers.get('User-Agent', '')
    
    session_id = conversation_manager.generate_session_id(user_ip, user_agent)
    return jsonify({'session_id': session_id})

@app.route('/static/<path:filename>')
def custom_static(filename):
    """Explicit route for serving static files with additional error handling."""
    try:
        logger.debug(f"Serving static file: {filename}")
        return send_from_directory('static', filename)
    except Exception as e:
        logger.error(f"Error serving static file {filename}: {str(e)}")
        return f"Error serving file: {str(e)}", 500

@app.route('/chat', methods=['POST'])
async def chat():
    """Handle incoming chat messages."""
    try:
        data = request.json
        user_message = data.get('message', '').strip()
        session_id = data.get('session_id')
        
        logger.info(f"Received chat request - Message: '{user_message}', Session ID: {session_id}")
        
        if not user_message:
            logger.warning("Empty message received")
            return jsonify({'response': "I didn't receive a message. How can I help you?"})
        
        if not session_id:
            logger.warning("No session ID provided")
            return jsonify({'error': 'No session ID provided'}), 400

        # Check if this might be a search query
        is_search_query = any(keyword in user_message.lower() for keyword in 
                             ['find', 'where', 'location', 'place', 'nearby', 'restaurant', 'cafe', 'bar'])
        
        logger.info(f"Message identified as search query: {is_search_query}")
        
        # Add user message to conversation history
        conversation_manager.add_message(session_id, 'user', user_message)
        logger.info(f"Added user message to conversation history for session {session_id}")
        
        # If this looks like a search query, redirect it to the search endpoint
        if is_search_query:
            logger.info(f"Handling as search query: '{user_message}'")
            # Create a new request to the search endpoint
            search_result = await search(user_message, session_id)
            logger.info(f"Search complete, returning result type: {type(search_result)}")
            return search_result
        
        # Get conversation history (trimmed to avoid token limits)
        conversation = conversation_manager.trim_conversation(session_id)
        logger.info(f"Got trimmed conversation with {len(conversation)} messages")
        
        try:
            logger.info("Calling OpenAI API for general chat")
            # Use the older openai API style
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",  # or gpt-4 if available
                messages=conversation,
                max_tokens=1000,
                temperature=0.7
            )
            
            # Extract the assistant's response
            assistant_message = response['choices'][0]['message']['content'].strip()
            logger.info(f"Received response from OpenAI: '{assistant_message[:50]}...'")
            
            # Add assistant's response to conversation history
            conversation_manager.add_message(session_id, 'assistant', assistant_message)
            
            # Maybe cleanup old sessions
            maybe_cleanup()
            
            logger.info("Returning successful response to client")
            return jsonify({'response': assistant_message})
            
        except Exception as e:
            logger.error(f"OpenAI API error: {str(e)}", exc_info=True)
            return jsonify({'response': "I'm sorry, I encountered an error processing your request. Please try again."})
    
    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}", exc_info=True)
        return jsonify({'response': "I'm sorry, something went wrong with the chat service. Please try again."})

# Simplify the search function to use only Google Maps Places API
async def search(query=None, session_id=None):
    """Search for places based on user query using Google Maps API only."""
    request_start_time = datetime.now()
    logger.info(f"=== Search Start === Received Query Parameter: '{query}', Session: {session_id}")
    
    if query:
        user_query = query 
        logger.info(f"[Search] Using passed query parameter: '{user_query}'")
    elif request.method == 'POST' and request.json:
        user_query = request.json.get('query')
        logger.info(f"[Search] Using POST request JSON query: '{user_query}'")
    else:
        user_query = ""
        logger.warning("[Search] No valid query source found.")
        
    if not user_query:
        logger.error("[Search] CRITICAL: user_query is empty after assignment attempt.")
        return jsonify({'error': 'Internal error processing search query'}), 500
        
    logger.info(f"[Search] Assigned User Query for processing: {user_query}")
    
    try:
        # --- Extraction using OpenAI First --- 
        initial_search_terms = None
        initial_location_query = None
        initial_requirements = None
        
        # Always try OpenAI first for structured extraction
        prompt = f"""Extract search information from this query: "{user_query}"
        Format your response EXACTLY like this, with ONLY these three lines:
        amenity: [the specific type of place or business being sought, e.g., 'cafe', 'restaurant', 'park']
        requirements: [specific requirements, preferences, or criteria mentioned, e.g., 'dog-friendly', 'outdoor seating', 'cheap']
        location: [the specific suburb, area, or 'Sydney' if general. Use 'default' ONLY if absolutely no location mentioned.]
        """
        
        logger.info(f"[Search] Using OpenAI FIRST to extract search terms from query: '{user_query}'")
        
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that extracts search criteria (amenity, requirements, location) from user queries about finding places."},
                    {"role": "user", "content": prompt}
                ]
            )
            response_text = response['choices'][0]['message']['content'].strip()
            logger.info(f"[Search] OpenAI extraction response: {response_text}")
            response_lines = response_text.split('\n')
            
            extracted = {}
            for line in response_lines:
                if ': ' in line:
                    key, value = line.split(': ', 1)
                    # Convert string 'None' or empty brackets to empty string
                    value_cleaned = value.strip().lower()
                    if value_cleaned == 'none' or value_cleaned == '[none]' or value_cleaned == '[]':
                        value = ''
                    else:
                        value = value.strip().strip('[]') # Keep original case unless empty
                    extracted[key.strip()] = value
            
            initial_search_terms = extracted.get('amenity', '')
            initial_requirements = extracted.get('requirements', '')
            initial_location_query = extracted.get('location', 'default') # Default if not found
            
            logger.info(f"[Search] OpenAI Extracted Amenity: '{initial_search_terms}'")
            logger.info(f"[Search] OpenAI Extracted Requirements: '{initial_requirements}'")
            logger.info(f"[Search] OpenAI Extracted Location: '{initial_location_query}'")

        except Exception as openai_error:
            logger.error(f"[Search] OpenAI extraction failed: {openai_error}", exc_info=True)
            # Fallback values if OpenAI fails
            initial_search_terms = "places"
            initial_requirements = ""
            initial_location_query = "default"

        # --- Refine Search Terms & Requirements --- 
        search_terms = initial_search_terms
        requirements = initial_requirements
        location_query = initial_location_query.lower().strip() # Use lowercase for matching
        
        # Simple Keyword check for requirements if OpenAI missed them
        user_query_lower = user_query.lower()
        if not requirements:
            if 'dog friendly' in user_query_lower or 'dog-friendly' in user_query_lower:
                requirements = "dog-friendly"
                logger.info("[Search] Found 'dog-friendly' requirement via keyword.")
            elif 'family' in user_query_lower or 'family-friendly' in user_query_lower or 'kid' in user_query_lower:
                requirements = "family-friendly"
                logger.info("[Search] Found 'family-friendly' requirement via keyword.")
        
        # Ensure requirements are added to search terms for Google
        if requirements == "dog-friendly" and 'dog' not in search_terms.lower():
            search_terms = f"{search_terms} dog friendly" if search_terms else "dog friendly"
        elif requirements == "family-friendly" and 'family' not in search_terms.lower():
             search_terms = f"{search_terms} family friendly" if search_terms else "family friendly"
             
        # Final fallback for search terms
        if not search_terms:
            search_terms = "places"
            logger.info(f"[Search] Using final fallback search term: '{search_terms}'")

        logger.info(f"[Search] Final Search Terms for Google: '{search_terms}'")
        logger.info(f"[Search] Final Requirements: '{requirements}'")
        logger.info(f"[Search] Final Location Query: '{location_query}'")
        
        # --- Location Resolution & Dynamic Radius (Geocoding Only) --- 
        if not gmaps:
            return jsonify({
                'error': 'Google Maps API is not properly configured.'
            }), 503

        location = None
        search_radius = 5000  # Default large radius 
        location_specificity = "default"

        # Attempt Geocoding if a specific location query was extracted
        if location_query and location_query != 'default':
            try:
                logger.info(f"[Search] Geocoding location query: '{location_query} sydney australia'")
                geocode_result = gmaps.geocode(f"{location_query} sydney australia")
                if geocode_result:
                    location_data = geocode_result[0]['geometry']['location']
                    location = (location_data['lat'], location_data['lng'])
                    
                    # Determine specificity and radius based on result type
                    types = geocode_result[0].get('types', [])
                    if any(t in types for t in ['locality', 'sublocality', 'neighborhood']):  # Suburb level
                        search_radius = 1500 
                        location_specificity = "geocoded_suburb"
                    elif any(t in types for t in ['administrative_area_level_1', 'country']):  # Very broad
                        search_radius = 10000  # Use a larger radius for broad areas like 'Sydney'
                        location_specificity = "geocoded_broad_area"
                    else:  # Could be a street, PoI, etc. 
                        search_radius = 2000
                        location_specificity = "geocoded_specific"
                    logger.info(f"[Search] Using GEOCODED location: {location_query} -> {location}. Radius: {search_radius}m")
                else:
                    logger.warning(f"[Search] Geocoding failed for '{location_query}'. Falling back to default Sydney CBD.")
                    location_query = 'default'  # Mark as default if geocoding failed
            except Exception as e:
                logger.error(f"[Search] Geocoding error for '{location_query}': {str(e)}", exc_info=True)
                location_query = 'default'  # Mark as default on error
        else:
            logger.info(f"[Search] No specific location query ('{location_query}'), using default Sydney CBD.")
            location_query = 'default'  # Ensure it is marked default
        
        # Fallback to Default Sydney CBD if geocoding wasn't attempted or failed
        if not location:
            location = (DEFAULT_LOCATION_COORDS['lat'], DEFAULT_LOCATION_COORDS['lng'])
            search_radius = 5000  # Ensure default radius
            location_specificity = "default_cbd"
            logger.info(f"[Search] Using DEFAULT location (Sydney CBD) -> {location}. Radius: {search_radius}m")

        # --- Search using Google Places API only ---
        try:
            # Fetch places from Google Places API
            logger.info(f"[Search] Fetching places from Google Maps API: {search_terms}")
            google_places = await _fetch_google_nearby(location, search_radius, search_terms)
            
            if not google_places:
                logger.warning(f"[Search] No places found from Google Maps API.")
                return jsonify({
                    'error': 'No places found matching your query.',
                    'query': {
                        'original': user_query,
                        'amenity': search_terms,
                        'requirements': requirements,
                        'location': location_query
                    }
                }), 404
            
            logger.info(f"[Search] Found {len(google_places)} places from Google Maps API")
                
            # Get place details for top results
            top_places = google_places[:MAX_PLACES_TO_ANALYZE]
            logger.info(f"[Search] Getting details for top {len(top_places)} places")
            
            # Get details for each place
            places_with_details = []
            for place in top_places:
                place_id = place.get('place_id')
                if place_id:
                    try:
                        logger.info(f"[Search] Getting details for place: {place.get('name')}")
                        
                        # Get place details from Google Maps API
                        place_details = await _fetch_place_details(place_id)
                        if place_details:
                            places_with_details.append(place_details)
                        else:
                            logger.warning(f"[Search] No details found for place: {place.get('name')}")
                    except Exception as e:
                        logger.error(f"[Search] Error getting details for place {place.get('name')}: {str(e)}")
            
            # Analyze places using OpenAI
            analysis_prompt = f"""Analyze these places in Sydney based on the user's query: "{user_query}"

Places:
"""
            for i, place in enumerate(places_with_details):
                name = place.get('name', 'Unknown')
                address = place.get('formatted_address', 'Address unknown')
                rating = place.get('rating', 'No rating')
                types = ', '.join(place.get('types', ['Unknown']))
                
                # Add details to prompt
                analysis_prompt += f"""
{i+1}. {name}
   Address: {address}
   Rating: {rating}/5
   Types: {types}
   """
                
                # Add reviews if available
                reviews = place.get('reviews', [])
                if reviews:
                    analysis_prompt += "   Recent reviews:\n"
                    for j, review in enumerate(reviews[:3]):  # Only include up to 3 reviews
                        review_text = review.get('text', '').replace('\n', ' ')[:100]  # Truncate long reviews
                        review_rating = review.get('rating', 0)
                        analysis_prompt += f"   - {review_text}... (Rating: {review_rating}/5)\n"
                        
            # Add instructions for analysis
            analysis_prompt += """
Based on the user's query, provide:
1. A summary of the best options
2. Highlights of each place relevant to the query
3. Any notable comparisons between options

Format your response as JSON with these exact fields:
{
  "summary": "A concise summary of the best matches for the query",
  "highlights": [
    {"place_name": "Name of Place 1", "key_features": ["Feature 1", "Feature 2"]},
    {"place_name": "Name of Place 2", "key_features": ["Feature 1", "Feature 2"]}
  ],
  "comparisons": ["Comparison point 1", "Comparison point 2"]
}
"""
            
            # Get analysis from OpenAI
            try:
                logger.info("[Search] Calling OpenAI for place analysis")
                analysis_response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant that analyzes places based on user queries."},
                        {"role": "user", "content": analysis_prompt}
                    ],
                    temperature=0.7
                )
                
                analysis_text = analysis_response['choices'][0]['message']['content'].strip()
                logger.info(f"[Search] Received analysis from OpenAI")
                
                # Try to parse JSON
                analysis_data = {}
                try:
                    # Extract JSON from response
                    json_match = re.search(r'```json\s*(.*?)\s*```', analysis_text, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(1)
                    else:
                        json_str = analysis_text
                        
                    # Clean up the string and parse JSON
                    json_str = re.sub(r'```.*?```', '', json_str, flags=re.DOTALL)
                    analysis_data = json.loads(json_str)
                    logger.info("[Search] Successfully parsed analysis JSON")
                except Exception as json_error:
                    logger.error(f"[Search] Error parsing analysis JSON: {str(json_error)}")
                    # Fallback to text response
                    analysis_data = {
                        "summary": analysis_text[:500] + "...",
                        "highlights": [],
                        "comparisons": []
                    }
                    
                # Add analysis to conversation history if session provided
                if session_id:
                    conversation_manager.add_message(session_id, 'assistant', 
                                                   f"I found some places matching your search. {analysis_data.get('summary', '')}")
                
                # Prepare final response
                final_data = {
                    'places': places_with_details,
                    'analysis': analysis_data,
                    'query': {
                        'original': user_query,
                        'amenity': search_terms,
                        'requirements': requirements,
                        'location': location_query
                    }
                }
                
                request_duration = (datetime.now() - request_start_time).total_seconds()
                logger.info(f"=== Search End === Total Duration: {request_duration:.2f}s")
                return jsonify(final_data)
                
            except Exception as analysis_error:
                logger.error(f"[Search] OpenAI analysis error: {str(analysis_error)}")
                return jsonify({
                    'places': places_with_details,
                    'error': 'Error analyzing places',
                    'query': {
                        'original': user_query,
                        'amenity': search_terms,
                        'requirements': requirements,
                        'location': location_query
                    }
                })
                
        except Exception as search_error:
            logger.error(f"[Search] Error during Google Places search: {str(search_error)}")
            return jsonify({'error': 'Error searching for places.'}), 500

    except Exception as e:
        logger.error(f"[Search] Top-level Error in search function: {str(e)}", exc_info=True)
        return jsonify({'error': 'Error processing your request.'}), 500

async def _fetch_google_nearby(location, radius, keyword) -> List[Dict]:
    """Fetches Google Nearby results asynchronously."""
    if not gmaps:
        logger.error("[Search] Google Maps client not available for Nearby Search.")
        return []
    try:
        loop = asyncio.get_running_loop()
        logger.info(f"[Search] Starting Google Nearby Search - Keyword: '{keyword}'")
        places_result = await loop.run_in_executor(
            None, # Use default executor
            lambda: gmaps.places_nearby(location=location, radius=radius, keyword=keyword)
        )
        results = places_result.get('results', [])
        logger.info(f"[Search] Google Nearby Search finished. Found {len(results)} raw results.")
        return results # Return all results
    except Exception as e:
        logger.error(f"[Search] Error during Google Nearby Search API call: {e}", exc_info=True)
        return []

async def _fetch_place_details(place_id: str) -> Optional[Dict]:
    """Fetches details for a specific place using its ID."""
    if not gmaps:
        logger.error("[Search] Google Maps client not available for Place Details.")
        return None
    try:
        loop = asyncio.get_running_loop()
        logger.info(f"[Search] Fetching details for place ID: {place_id}")
        details_result = await loop.run_in_executor(
            None,
            lambda: gmaps.place(
                place_id=place_id,
                fields=['name', 'formatted_address', 'rating', 'types', 'reviews', 
                        'photos', 'website', 'price_level', 'opening_hours', 
                        'formatted_phone_number', 'geometry']
            )
        )
        result = details_result.get('result', {})
        logger.info(f"[Search] Successfully fetched details for: {result.get('name', 'Unknown')}")
        return result
    except Exception as e:
        logger.error(f"[Search] Error fetching place details: {e}", exc_info=True)
        return None

@app.teardown_appcontext
async def teardown_session(exception=None):
    await data_manager.close()

if __name__ == '__main__':
    print("Starting app on http://localhost:8080")
    app.run(host='0.0.0.0', port=8080, debug=True) 