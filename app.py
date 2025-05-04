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

# Load environment variables using an absolute path
# Replace 'YourUsername' with your actual PythonAnywhere username
project_home = Path('/home/CityPulse/citypulse')
env_path = project_home / '.env'
load_dotenv(dotenv_path=env_path, override=True) # Use dotenv_path argument

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

# Create a simple memory cache for search context
search_context_cache = {}

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

@app.route('/how_it_works')
def how_it_works():
    return render_template('how_it_works.html')

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
        
        # Also check for follow-up questions about locations
        if not is_search_query:
            # Check for patterns like "what about in [location]" or "any in [location]"
            follow_up_location_patterns = [
                r'what about in \w+',
                r'how about in \w+', 
                r'any in \w+',
                r'what about \w+',
                r'similar in \w+'
            ]
            
            for pattern in follow_up_location_patterns:
                if re.search(pattern, user_message.lower()):
                    is_search_query = True
                    logger.info(f"Detected location follow-up query pattern: '{user_message}'")
                    break
        
        # Use NLP to detect search intent instead of keyword matching
        # This approach classifies the query based on its overall meaning rather than specific keywords
        try:
            # First check for direct signs of search intent in the message
            search_indicators = {
                'location': r'\b(in|near|around)\s+([A-Z][a-z]+|\w+\s+\w+)',  # "in Sydney", "near Newtown"
                'place_type': r'\b(restaurant|cafe|bar|pub|garden|shop|store|venue|place)s?\b',  # Types of places
                'amenity': r'\b(dog|pet|family|kid|child|outdoor|friendly|beer|wine|food)\b',  # Common amenities
                'action': r'\b(find|look|search|where|show|recommend|suggest)\b'  # Search actions
            }

            # Check for location patterns, place types, and amenities
            matches = []
            for indicator_type, pattern in search_indicators.items():
                if re.search(pattern, user_message.lower()):
                    matches.append(indicator_type)
                    logger.info(f"Detected search indicator: {indicator_type} in '{user_message}'")

            # If we have multiple indicators or specific combinations, treat as search query
            is_search_query = (len(matches) >= 2 or  # Multiple indicators suggest search intent
                              'location' in matches or  # Explicit location is strong signal
                              ('place_type' in matches and 'amenity' in matches) or  # Place + amenity
                              'action' in matches)  # Explicit search action

            # For more complex cases, use OpenAI to analyze search intent
            if not is_search_query and len(user_message.split()) > 3:  # Only for non-trivial messages
                logger.info(f"Using OpenAI to classify search intent for: '{user_message}'")

                intent_query = f"""Determine if this is a location/place search query: "{user_message}"

                Examples of search queries:
                - "Dog friendly beer gardens in Newtown"
                - "Where can I find good coffee shops with wifi?"
                - "Italian restaurants in Sydney CBD"
                - "Pubs with outdoor seating"

                Is this a query looking for places, venues, or locations? Respond with ONLY 'yes' or 'no'."""

                try:
                    intent_response = openai.ChatCompletion.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": "You are a system that determines if a message is asking about places or locations. Only respond with 'yes' or 'no'."},
                            {"role": "user", "content": intent_query}
                        ],
                        max_tokens=5,  # Very short response needed
                        temperature=0.1  # Low temperature for consistency
                    )

                    intent_result = intent_response['choices'][0]['message']['content'].strip().lower()
                    is_search_query = 'yes' in intent_result
                    logger.info(f"OpenAI classified as search query: {is_search_query}")

                except Exception as e:
                    logger.error(f"Error using OpenAI for intent classification: {str(e)}")
                    # Fall back to simple heuristic - longer queries about places are likely searches
                    if any(term in user_message.lower() for term in ['in', 'at', 'near', 'around']):
                        is_search_query = True
                        logger.info("Fallback location heuristic detected search query")

            logger.info(f"Final search intent classification: {is_search_query}")

        except Exception as e:
            logger.error(f"Error in search intent detection: {str(e)}")
            # If error in detection, fall back to original method
            is_search_query = any(keyword in user_message.lower() for keyword in
                            ['find', 'where', 'location', 'place', 'nearby', 'restaurant', 'cafe', 'bar'])
            logger.info(f"Fallback search detection: {is_search_query}")

        logger.info(f"Message identified as search query: {is_search_query}")

        # Flag to determine whether to call search function
        call_search_function = False
        
        # If initially classified as a search query, do additional classification
        if is_search_query:
            logger.info(f"Initial classification as search query. Now checking if this is a 'more info' follow-up")
            
            # Check if this is a 'tell me more about X' type of follow-up
            more_info_patterns = [
                r'tell me more about',
                r'more details on',
                r'more information about',
                r'more about',
                r'details for',
                r'what can you tell me about',
                r'what do you know about'
            ]
            
            # Initial check for common "more info" patterns
            potentially_more_info = any(re.search(pattern, user_message.lower()) for pattern in more_info_patterns)
            
            if potentially_more_info:
                logger.info(f"Detected potential 'more info' follow-up: '{user_message}'")
                
                try:
                    # Get recent conversation to provide context
                    conversation_history = conversation_manager.get_conversation(session_id)
                    
                    # Only consider a reasonable number of recent messages
                    history_snippet = conversation_history[-6:] if len(conversation_history) >= 6 else conversation_history
                    
                    # Create formatted history for the prompt (excluding current user message)
                    formatted_history = ""
                    for msg in history_snippet:
                        if msg['role'] == 'user' and msg['content'] == user_message:
                            continue
                        formatted_history += f"{msg['role'].title()}: {msg['content']}\n\n"
                    
                    # Craft a classification prompt
                    classification_prompt = f"""You are an assistant that classifies user follow-up questions about local places based on conversation history.

Recent Conversation History:
{formatted_history}
User: {user_message}

Based on the User's message and the history, classify the User's intent:
A) Requesting a NEW SEARCH for different places/locations/criteria.
B) Requesting MORE INFORMATION about a SPECIFIC place already mentioned.

Respond with ONLY the letter A or B."""

                    # Call OpenAI for classification
                    logger.info("Calling OpenAI to classify follow-up intent")
                    classification_response = openai.ChatCompletion.create(
                        model="gpt-4o-mini",  # Using the same model as other calls
                        messages=[
                            {"role": "system", "content": "Classify user intent: A=New Search, B=More Info."},
                            {"role": "user", "content": classification_prompt}
                        ],
                        max_tokens=2,
                        temperature=0.1  # Low temperature for consistency
                    )
                    
                    follow_up_type = classification_response['choices'][0]['message']['content'].strip().upper()
                    logger.info(f"Follow-up classification result: {follow_up_type}")
                    
                    if follow_up_type == 'A':
                        call_search_function = True
                        logger.info("Classified as a NEW SEARCH request")
                    elif follow_up_type == 'B':
                        call_search_function = False
                        logger.info("Classified as a MORE INFO request about a specific place")
                    else:
                        # Unexpected response, default to safer option (general chat)
                        call_search_function = False
                        logger.warning(f"Unexpected classification result: {follow_up_type}. Defaulting to general chat.")
                
                except Exception as e:
                    logger.error(f"Error during follow-up classification: {str(e)}", exc_info=True)
                    # Default to general chat on error (safer than incorrect search)
                    call_search_function = False
            else:
                # Not a "more info" query but still a search query
                call_search_function = True
                logger.info("No 'more info' patterns detected. Proceeding with search.")
        else:
            # Not initially classified as a search query
            call_search_function = False
            logger.info("Not classified as a search query. Handling as general chat.")
        
        # Add user message to conversation history
        conversation_manager.add_message(session_id, 'user', user_message)
        logger.info(f"Added user message to conversation history for session {session_id}")
        
        # If this looks like a search query, redirect it to the search endpoint
        if call_search_function:
            logger.info(f"Handling as NEW SEARCH query: '{user_message}'")
            # Create a new request to the search endpoint
            search_result = await search(user_message, session_id)
            logger.info(f"Search complete, returning result type: {type(search_result)}")
            return search_result
        
        # Get conversation history (trimmed to avoid token limits)
        conversation = conversation_manager.trim_conversation(session_id)
        logger.info(f"Got trimmed conversation with {len(conversation)} messages")
        
        try:
            logger.info("Calling OpenAI API for general chat")
            
            # Check if this is a "more info" request to enhance the system message
            is_more_info_request = any(re.search(pattern, user_message.lower()) for pattern in [
                r'tell me more about',
                r'more details on',
                r'more information about',
                r'more about',
                r'details for',
                r'what can you tell me about',
                r'what do you know about'
            ])
            
            # Customize system message if it exists
            if is_more_info_request and conversation and conversation[0]['role'] == 'system':
                logger.info("Enhanced system message for 'more info' request about a specific place")
                conversation[0]['content'] = """You are CityPulse, a helpful assistant for finding local information about places in Sydney.
When users ask for more information about a specific place you've previously mentioned:
1. Provide rich, detailed information about that specific place
2. Include details about atmosphere, specialties, what makes it unique
3. Mention practical information such as best times to visit, what to expect
4. Be conversational and helpful, as if giving advice to a friend

If the user is asking about a place you haven't mentioned before or don't have information about, 
politely explain that you don't have specific details about that place."""
            
            # Use the older openai API style
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",  # Upgraded to GPT-4o mini for better conversation
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

        This is part of a conversation about places in Sydney. The user may be asking about specific types of venues or establishments.

        Pay special attention to the EXACT type of place being requested. For example:
        - "beer garden" should be extracted as the exact amenity, not just "restaurant" or "bar"
        - "dog friendly cafe" should extract "cafe" as the amenity and "dog-friendly" as the requirement
        - "family restaurant in Newtown" should extract "restaurant" as the amenity and "family-friendly" as the requirement

        Format your response EXACTLY like this:
        amenity: [the EXACT type of place being sought. Examples: "beer garden", "cafe", "restaurant", "pub", etc. Be as specific as possible and match the user's words exactly. If not clearly specified, write 'not specified']
        requirements: [specific requirements or criteria mentioned, e.g., 'dog-friendly', 'outdoor seating', 'wifi'. If not mentioned, write 'not specified']
        location: [the specific suburb, area, or 'Sydney' if general. Use 'default' ONLY if absolutely no location mentioned.]
        follow_up: [yes/no - indicate if this is a follow-up question that references a previous query]
        """

        logger.info(f"[Search] Using OpenAI FIRST to extract search terms from query: '{user_query}'")

        try:
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",  # Upgraded to GPT-4o mini for better context understanding
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that extracts search criteria (amenity, requirements, location) from user queries about finding places. You're especially good at recognizing follow-up questions that reference previous search contexts."},
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
                    if value_cleaned == 'none' or value_cleaned == '[none]' or value_cleaned == '[]' or value_cleaned == 'not specified':
                        value = ''
                    else:
                        value = value.strip().strip('[]') # Keep original case unless empty
                    extracted[key.strip()] = value

            initial_search_terms = extracted.get('amenity', '')
            initial_requirements = extracted.get('requirements', '')
            initial_location_query = extracted.get('location', 'default') # Default if not found
            is_follow_up = extracted.get('follow_up', '').lower() == 'yes'

            logger.info(f"[Search] OpenAI Extracted Amenity: '{initial_search_terms}'")
            logger.info(f"[Search] OpenAI Extracted Requirements: '{initial_requirements}'")
            logger.info(f"[Search] OpenAI Extracted Location: '{initial_location_query}'")
            logger.info(f"[Search] OpenAI Detected Follow-up: {is_follow_up}")

            # Direct follow-up pattern detection
            if not is_follow_up and not initial_search_terms:
                # Check for common follow-up patterns that might have been missed by OpenAI
                follow_up_patterns = [
                    r'what about',
                    r'how about',
                    r'any in',
                    r'what\'s in',
                    r'similar in'
                ]

                for pattern in follow_up_patterns:
                    if re.search(pattern, user_query.lower()):
                        is_follow_up = True
                        logger.info(f"[Search] Manual pattern detection identified follow-up: '{pattern}' in '{user_query}'")
                        break

            # If this appears to be a follow-up question or is missing search terms but has location
            if (is_follow_up or (not initial_search_terms or initial_search_terms == 'not specified')) and session_id:
                logger.info(f"[Search] Detected likely follow-up question. Looking for context in conversation history.")

                # Initialize variables for context tracking
                previous_search_terms = None
                previous_requirements = None
                use_conversation_history = True

                # First check the search context cache for this session
                if session_id in search_context_cache:
                    cached_context = search_context_cache[session_id]
                    # Only use cache if it's relatively recent (within last 30 minutes)
                    if datetime.now().timestamp() - cached_context['timestamp'] < 1800:
                        logger.info(f"[Search] Found recent search context in cache for session {session_id}")
                        if not initial_search_terms or initial_search_terms == 'not specified':
                            initial_search_terms = cached_context['search_terms']
                            logger.info(f"[Search] Using cached search terms: '{initial_search_terms}'")

                        if not initial_requirements or initial_requirements == 'not specified':
                            initial_requirements = cached_context['requirements']
                            logger.info(f"[Search] Using cached requirements: '{initial_requirements}'")

                        # No need to continue with conversation history search
                        use_conversation_history = False
                    else:
                        logger.info(f"[Search] Found cached context but it's too old, searching conversation history instead")

                # If we don't have cached context or it's too old, check conversation history
                if use_conversation_history:
                    try:
                        # Get conversation history
                        conversation = conversation_manager.get_conversation(session_id)

                        # Find the most recent user and assistant interaction with search context
                        for msg in reversed(conversation):
                            # Skip this current message
                            if msg['role'] == 'user' and msg['content'] == user_query:
                                continue

                            if msg['role'] == 'assistant' and 'I found some places matching your search' in msg['content']:
                                # Found an assistant response with search results
                                logger.info(f"[Search] Found previous assistant response with search results")

                                # Look for the previous user query to get the context
                                prev_user_query = None
                                for prev_msg in reversed(conversation):
                                    if prev_msg['role'] == 'user' and prev_msg['content'] != user_query:
                                        prev_user_query = prev_msg['content'].lower()
                                        logger.info(f"[Search] Found previous user query: '{prev_user_query}'")
                                        break

                                # Extract search terms from previous user query
                                if prev_user_query:
                                    # Look for specific search terms in the OpenAI response to that query
                                    # Go through conversation to find the OpenAI extracted terms for that query
                                    last_query_amenity = None
                                    last_query_requirements = None

                                    for prev_log in logger.handlers[0].baseFilename:
                                        if f"[Search] OpenAI Extracted Amenity: '{last_query_amenity}'" in prev_log and prev_user_query in prev_log:
                                            # Found the OpenAI extraction for the previous query
                                            try:
                                                last_query_amenity = re.search(r"OpenAI Extracted Amenity: '([^']+)'", prev_log).group(1)
                                                last_query_requirements = re.search(r"OpenAI Extracted Requirements: '([^']+)'", prev_log).group(1)
                                                logger.info(f"[Search] Found previous query context from logs: amenity='{last_query_amenity}', requirements='{last_query_requirements}'")
                                                break
                                            except:
                                                pass

                                    # Use the found terms or fallback to pattern matching if needed
                                    if last_query_amenity and last_query_amenity != 'not specified':
                                        previous_search_terms = last_query_amenity
                                        logger.info(f"[Search] Using previous search term from logs: '{previous_search_terms}'")
                                    else:
                                        # Fallback to pattern detection
                                        if 'burger' in prev_user_query:
                                            previous_search_terms = 'burger place'
                                        elif 'beer garden' in prev_user_query or 'pub' in prev_user_query:
                                            previous_search_terms = 'beer garden'
                                        elif 'cafe' in prev_user_query or 'coffee' in prev_user_query:
                                            previous_search_terms = 'cafe'
                                        elif 'restaurant' in prev_user_query or 'food' in prev_user_query:
                                            previous_search_terms = 'restaurant'
                                        elif 'bar' in prev_user_query:
                                            previous_search_terms = 'bar'
                                        else:
                                            # Check for other common amenities
                                            amenity_patterns = [
                                                (r'park', 'park'),
                                                (r'gym', 'gym'),
                                                (r'shop', 'shopping'),
                                                (r'store', 'store'),
                                                (r'market', 'market'),
                                                (r'library', 'library'),
                                                (r'pizza', 'pizza place'),
                                                (r'sushi', 'sushi restaurant'),
                                                (r'thai', 'thai restaurant'),
                                                (r'italian', 'italian restaurant'),
                                                (r'chinese', 'chinese restaurant'),
                                                (r'indian', 'indian restaurant')
                                            ]

                                            for pattern, term in amenity_patterns:
                                                if re.search(pattern, prev_user_query):
                                                    previous_search_terms = term
                                                    break

                                    # Do the same for requirements
                                    if last_query_requirements and last_query_requirements != 'not specified':
                                        previous_requirements = last_query_requirements
                                        logger.info(f"[Search] Using previous requirements from logs: '{previous_requirements}'")
                                    else:
                                        # Check for specific requirements
                                        if 'dog' in prev_user_query or 'pet' in prev_user_query:
                                            previous_requirements = 'dog-friendly'
                                        elif 'family' in prev_user_query or 'kid' in prev_user_query or 'child' in prev_user_query:
                                            previous_requirements = 'family-friendly'
                                        elif 'wifi' in prev_user_query or 'internet' in prev_user_query:
                                            previous_requirements = 'wifi'

                                # If we couldn't determine specifics, set a default
                                if not previous_search_terms:
                                    previous_search_terms = 'places'

                                logger.info(f"[Search] Extracted search context from previous conversation: '{previous_search_terms}'")
                                break

                        # Apply previous context if found
                        if previous_search_terms:
                            if not initial_search_terms or initial_search_terms == 'not specified':
                                initial_search_terms = previous_search_terms
                                logger.info(f"[Search] Using previous search term from conversation: '{initial_search_terms}'")

                            if (not initial_requirements or initial_requirements == 'not specified') and previous_requirements:
                                initial_requirements = previous_requirements
                                logger.info(f"[Search] Using previous requirements from conversation: '{initial_requirements}'")

                    except Exception as e:
                        logger.error(f"[Search] Error retrieving conversation context: {str(e)}")

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
        if not search_terms or search_terms == '-':
            # For follow-up questions or vague queries, default to a broad search term
            # Try to preserve context from previous queries if available
            if 'cafe' in user_query_lower or 'coffee' in user_query_lower:
                search_terms = "cafe"
            elif 'restaurant' in user_query_lower or 'food' in user_query_lower or 'eat' in user_query_lower:
                search_terms = "restaurant"
            elif 'bar' in user_query_lower or 'pub' in user_query_lower or 'drink' in user_query_lower or 'beer' in user_query_lower:
                search_terms = "bar"
            elif 'what about' in user_query_lower or 'how about' in user_query_lower or 'any in' in user_query_lower or 'similar' in user_query_lower:
                # Strong indicator of a follow-up question - look for the most recent search in history
                if session_id:
                    try:
                        logger.info("[Search] Detected follow-up based on phrasing. Checking history for context.")
                        conversation = conversation_manager.get_conversation(session_id)

                        # Find the most recent search query
                        for msg in reversed(conversation):
                            if msg['role'] == 'user' and msg['content'] != user_query:
                                last_query = msg['content'].lower()
                                logger.info(f"[Search] Found previous user query: '{last_query}'")

                                # Extract context from the last question
                                if 'beer garden' in last_query or 'pub' in last_query:
                                    search_terms = "beer garden"
                                    if 'dog' in last_query:
                                        if not requirements:
                                            requirements = "dog-friendly"
                                    break
                                elif 'cafe' in last_query or 'coffee' in last_query:
                                    search_terms = "cafe"
                                    if 'wifi' in last_query:
                                        if not requirements:
                                            requirements = "wifi"
                                    break
                                elif 'restaurant' in last_query or 'food' in last_query or 'eat' in last_query:
                                    search_terms = "restaurant"
                                    break
                                elif 'bar' in last_query:
                                    search_terms = "bar"
                                    break
                    except Exception as e:
                        logger.error(f"[Search] Error finding previous context: {str(e)}")
            elif session_id:
                # Look at conversation history for context
                try:
                    conversation = conversation_manager.get_conversation(session_id)
                    for msg in reversed(conversation):
                        if msg['role'] == 'user' and any(term in msg['content'].lower() for term in
                                                    ['cafe', 'restaurant', 'bar', 'coffee', 'food', 'beer garden']):
                            # Extract search context from previous questions
                            last_query = msg['content'].lower()
                            if 'beer garden' in last_query or 'pub' in last_query:
                                search_terms = "beer garden"
                                break
                            elif 'cafe' in last_query or 'coffee' in last_query:
                                search_terms = "cafe"
                                break
                            elif 'restaurant' in last_query or 'food' in last_query:
                                search_terms = "restaurant"
                                break
                            elif 'bar' in last_query:
                                search_terms = "bar"
                                break
                except Exception as e:
                    logger.error(f"[Search] Error getting conversation context: {str(e)}")

            # If still no search term, default to places
            if not search_terms or search_terms == '-':
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
                        # More focused radius for specific suburbs
                        if location_query.lower() in ['newtown', 'surry hills', 'marrickville', 'enmore', 'erskineville']:
                            search_radius = 800  # Smaller radius for dense inner-city suburbs
                            logger.info(f"[Search] Using smaller radius for dense inner-city suburb: {location_query}")
                        else:
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
            # Construct better search terms by ensuring we include the requirements
            search_query = search_terms

            # Special handling for specific venue types
            if search_terms.lower() == 'beer garden':
                # Beer gardens are often in pubs, so include both terms
                search_query = "pub beer garden"
                logger.info(f"[Search] Enhanced search query for beer garden: '{search_query}'")
            elif search_terms.lower() == 'pub':
                # When looking for pubs, prioritize those with beer gardens
                if 'beer garden' in user_query_lower or 'outdoor' in user_query_lower:
                    search_query = "pub beer garden"
                    logger.info(f"[Search] Enhanced pub search to focus on beer gardens: '{search_query}'")

            # Make sure dog-friendly requirement is included in search terms
            if requirements == 'dog-friendly' and 'dog' not in search_query.lower():
                search_query = f"{search_query} dog friendly"
                logger.info(f"[Search] Added dog-friendly requirement to search query: '{search_query}'")

            # Fetch places from Google Places API
            logger.info(f"[Search] Fetching places from Google Maps API: {search_query}")
            google_places = await _fetch_google_nearby(location, search_radius, search_query)

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
                            # Generate AI description for this place
                            place_name = place_details.get('name', 'This place')
                            place_types = place_details.get('type', [])
                            place_address = place_details.get('formatted_address', '')

                            # Construct a prompt for OpenAI
                            description_prompt = f"""
                            Generate a very concise, friendly, one-sentence description (max 20 words)
                            for the amenity '{place_name}' located at '{place_address}'.
                            It is known for being types: {', '.join(place_types) if isinstance(place_types, list) else str(place_types)}.
                            Focus on its main purpose or vibe, and link it to the user's requirement '{requirements}'.
                            """

                            try:
                                # Use OpenAI to generate a short description
                                description_response = openai.ChatCompletion.create(
                                    model="gpt-4o-mini",  # Or your preferred model
                                    messages=[
                                        {"role": "system", "content": "You provide concise, appealing one-sentence descriptions for amenities."},
                                        {"role": "user", "content": description_prompt}
                                    ],
                                    max_tokens=40,  # Limit response length
                                    temperature=0.6  # Slightly creative but concise
                                )
                                short_description = description_response['choices'][0]['message']['content'].strip()
                                logger.info(f"[Search] Generated description for {place_name}: {short_description}")

                                # Add the description to the place_details dictionary
                                place_details['ai_description'] = short_description

                            except Exception as desc_error:
                                logger.error(f"[Search] Failed to generate description for {place_name}: {str(desc_error)}")
                                # Add a fallback description
                                place_details['ai_description'] = f"A notable place in the area."  # Fallback

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
                type_list = place.get('type', [])
                types = ', '.join(type_list if isinstance(type_list, list) else [str(type_list)])

                # Add details to prompt
                analysis_prompt += f"""
{i+1}. {name}
   Address: {address}
   Rating: {rating}/5
   Types: {types}
   """

                # Add reviews if available
                review_list = place.get('review', [])
                if review_list:
                    analysis_prompt += "   Recent reviews:\n"
                    for j, review in enumerate(review_list[:3]):  # Only include up to 3 reviews
                        review_text = review.get('text', '').replace('\n', ' ')[:100]  # Truncate long reviews
                        review_rating = review.get('rating', 0)
                        analysis_prompt += f"   - {review_text}... (Rating: {review_rating}/5)\n"

            # Add instructions for analysis - more conversational approach
            analysis_prompt += f"""
Based on the user's query: "{user_query}", provide:
1. A friendly, conversational summary of the best options - imagine you're telling a friend about these places
2. Specific highlights of each place that make it special, particularly focusing on {requirements if requirements else 'what makes them great'}
3. Casual comparisons between options to help the user decide
4. Information about the various amenities available at each place (where applicable), such as:
   - Outdoor seating/beer gardens
   - Pet-friendly policies and accommodations
   - Family-friendly features
   - Accessibility options
   - Special events or promotions
   - Unique features that distinguish this place
5. Practical information like best times to visit, what to expect for crowds or wait times

The user is looking for: "{search_terms}"{' that are ' + requirements if requirements else ''}.
Only include places that actually match what they're looking for.

Format your response as JSON with these fields:
{{
  "summary": "A friendly, conversational summary of the best places - write as if chatting with a friend",
  "highlights": [
    {{"place_name": "Name of Place 1", "key_features": ["A specific standout feature described conversationally", "Another great thing about this place"]}},
    {{"place_name": "Name of Place 2", "key_features": ["What makes this place special", "Another noteworthy aspect"]}}
  ],
  "comparisons": ["A casual comparison between places, like 'If you prefer a relaxed vibe, X is better than Y'", "Another helpful comparison"],
  "amenities": [
    {{"place_name": "Name of Place 1", "amenities": ["Notable amenity 1", "Notable amenity 2"]}},
    {{"place_name": "Name of Place 2", "amenities": ["Notable amenity 1", "Notable amenity 2"]}}
  ],
  "practical_info": [
    {{"place_name": "Name of Place 1", "info": ["Best time to visit", "What to expect"]}},
    {{"place_name": "Name of Place 2", "info": ["Best time to visit", "What to expect"]}}
  ]
}}
"""

            # Get analysis from OpenAI
            try:
                logger.info("[Search] Calling OpenAI for place analysis")

                # Enhanced system message with the specific search context
                system_message = "You are a friendly, conversational assistant that analyzes places for users in a helpful and personable way. Write as if you're talking to a friend rather than presenting a formal analysis."
                if requirements:
                    system_message += f" Pay special attention to the '{requirements}' requirement and highlight venues that truly excel at this."
                if search_terms != "places":
                    system_message += f" Focus specifically on whether these places are excellent {search_terms}s, sharing what makes them special."
                system_message += " While your response will be structured as JSON, the content should be warm, helpful and engaging."

                analysis_response = openai.ChatCompletion.create(
                    model="gpt-4o-mini",  # Upgraded to GPT-4o mini for better analysis
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": analysis_prompt}
                    ],
                    temperature=0.7
                )

                # Extract the assistant's response
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
                        "comparisons": [],
                        "amenities": [],
                        "practical_info": []
                    }

                # Save the search context to the cache for future reference
                if session_id:
                    search_context_cache[session_id] = {
                        'timestamp': datetime.now().timestamp(),
                        'search_terms': search_terms,
                        'requirements': requirements,
                        'original_query': user_query
                    }
                    logger.info(f"[Search] Saved search context to cache for session {session_id}")

                # Add analysis to conversation history if session provided
                if session_id:
                    # Create a more conversational response style
                    conversational_response = _create_conversational_response(analysis_data, places_with_details, search_terms, requirements, location_query)

                    # Add the conversational response to conversation history
                    conversation_manager.add_message(session_id, 'assistant', conversational_response)
                    
                    # Log the number of places being returned and query details
                    logger.info(f"[Search] Returning {len(places_with_details)} places for follow-up query: '{user_query}' (search_terms: '{search_terms}', location: '{location_query}')")
                    logger.info(f"[Search] First place in results: {places_with_details[0].get('name') if places_with_details else 'None'}")
                    
                    # Return the conversational response to match the chat style
                    request_duration = (datetime.now() - request_start_time).total_seconds()
                    logger.info(f"=== Search End === Total Duration: {request_duration:.2f}s")
                    
                    # For the response, return the conversational format
                    return jsonify({'response': conversational_response, 
                                  'places': places_with_details,
                                  'analysis': analysis_data})

                # Prepare final response (non-conversational, for direct API use)
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
                fields=['name', 'formatted_address', 'rating', 'type', 'review',
                        'photo', 'website', 'price_level', 'opening_hours',
                        'formatted_phone_number', 'geometry']
            )
        )
        result = details_result.get('result', {})

        # Ensure geometry.location is properly structured for the frontend
        if 'geometry' in result and 'location' in result['geometry']:
            # Leave geometry.location as is for the frontend to access
            pass
        else:
            # Add a default location if none exists
            logger.warning(f"[Search] Place {result.get('name', 'Unknown')} has no geometry data. Using default.")
            result['geometry'] = {
                'location': {'lat': -33.8978149, 'lng': 151.1785003}  # Default to Newtown
            }

        logger.info(f"[Search] Successfully fetched details for: {result.get('name', 'Unknown')}")
        return result
    except Exception as e:
        logger.error(f"[Search] Error fetching place details: {e}", exc_info=True)
        return None

@app.teardown_appcontext
async def teardown_session(exception=None):
    await data_manager.close()

def _create_conversational_response(analysis_data, places, search_terms, requirements, location):
    """Create a friendly, conversational response like you're talking to a friend."""

    # Get data from analysis
    summary = analysis_data.get('summary', '')
    highlights = analysis_data.get('highlights', [])
    comparisons = analysis_data.get('comparisons', [])
    amenities = analysis_data.get('amenities', [])
    practical_info = analysis_data.get('practical_info', [])

    # Create a friendly, casual intro
    if location and location != 'default':
        if requirements:
            intro = f"Here are some {requirements} {search_terms} in {location.title()}: "
        else:
            intro = f"I found some great {search_terms} in {location.title()} for you: "
    else:
        if requirements:
            intro = f"Here are some {requirements} {search_terms} for you: "
        else:
            intro = f"I found some great {search_terms} spots for you: "

    # Start building the casual, conversational response
    response = intro

    # Only add the summary if it's a good one
    if summary and len(summary) < 150:
        response = summary + "\n\n"

    # Add top recommendations in a conversational, personable way
    if places and len(places) > 0:
        top_places = places[:4]  # Limit to top 4 for conversation

        for i, place in enumerate(top_places):
            name = place.get('name', 'Unknown')
            address = place.get('formatted_address', '').split(',')[0]  # Just the street address
            rating = place.get('rating', 'No rating')

            # Find highlights for this place
            place_highlight = next((h for h in highlights if h.get('place_name') == name), None)
            features = place_highlight.get('key_features', []) if place_highlight else []

            # Find amenities for this place
            place_amenities = next((a for a in amenities if a.get('place_name') == name), None)
            amenity_list = place_amenities.get('amenities', []) if place_amenities else []

            # Find practical info for this place
            place_practical = next((p for p in practical_info if p.get('place_name') == name), None)
            practical_list = place_practical.get('info', []) if place_practical else []

            # Ensure name is properly formatted with bold markup
            # Use single backticks for names to prevent nesting issues
            response += f"**{name}** - "

            # Add a casual description based on features
            if features:
                # Convert feature lists to casual speaking
                if len(features) >= 2:
                    response += f"{features[0]} and {features[1].lower()}. "
                elif len(features) == 1:
                    response += f"{features[0]}. "

                # Add a casual comment about the place based on rating
                if rating and float(rating) >= 4.5:
                    response += f"People absolutely love this place! "
                elif rating and float(rating) >= 4.0:
                    response += f"It's really well-rated. "

            else:
                # Generic comment if no features
                if rating:
                    if float(rating) >= 4.5:
                        response += f"This place is highly rated at {rating}/5! "
                    elif float(rating) >= 4.0:
                        response += f"Good spot with {rating}/5 stars. "
                    else:
                        response += f"Located at {address}. "

            # Add location in a casual way
            if "Road" in address or "Street" in address or "Lane" in address:
                response += f"You'll find it on {address}. "
            else:
                response += f"It's at {address}. "

            # Add amenities if available - using proper formatting for section titles
            if amenity_list:
                response += "\nAmenities: "
                response += f"{', '.join(amenity_list[:3])}. "

            # Add practical info if available
            if practical_list:
                response += "\nGood to know: "
                response += f"{', '.join(practical_list[:2])}. "

            response += "\n\n"

    # Add one comparison if available, in a conversational way
    if comparisons and len(comparisons) > 0:
        comparison = comparisons[0]
        # Make the comparison more conversational if it's not already
        if not any(casual_word in comparison.lower() for casual_word in ["if you're", "perfect for", "better if", "great for"]):
            response += f"Just so you know, {comparison.lower()}\n\n"
        else:
            response += f"{comparison}\n\n"

    # Add a casual closing that invites further questions
    closings = [
        "Let me know if you want to know more about any of these places!",
        "Hope that helps! Any of these catch your eye?",
        "Do any of these sound good to you?",
        "Would you like more details about any of these spots?",
        "Have you been to any of these before?"
    ]

    import random
    response += random.choice(closings)

    return response

if __name__ == '__main__':
    print("Starting app on http://localhost:8080")
    app.run(host='127.0.0.1', port=8080, debug=True)