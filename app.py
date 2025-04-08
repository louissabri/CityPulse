from flask import Flask, render_template, request, jsonify
import openai
import googlemaps
import os
from dotenv import load_dotenv
from pathlib import Path
from data_sources import DataSourceManager
import asyncio
import logging
from conversation_manager import ConversationManager
from datetime import datetime

# Load environment variables
env_path = Path('.') / '.env'
load_dotenv(env_path, override=True)

# Debug: Print loaded API key (first few characters)
maps_api_key = os.getenv('MAPS_API_KEY')
if maps_api_key:
    print(f"Loaded Maps API key starting with: {maps_api_key[:10]}...")
else:
    print("WARNING: No Maps API key found!")

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', os.urandom(24).hex())

# Initialize API clients
openai_api_key = os.getenv('OPENAI_API_KEY')
openai.api_key = openai_api_key
try:
    gmaps = googlemaps.Client(key=maps_api_key)
    # Test the API key with a simple geocoding request
    test_result = gmaps.geocode('Sydney, Australia')
    if test_result:
        print("Google Maps API key is working!")
    else:
        print("Google Maps API key validation failed - no results returned")
except Exception as e:
    print(f"Error initializing Google Maps client: {str(e)}")
    gmaps = None

# Initialize data source manager
data_manager = DataSourceManager()

# Initialize conversation manager
conversation_manager = ConversationManager()

# Define default coordinates (Sydney CBD)
DEFAULT_LOCATION_COORDS = {'lat': -33.8688, 'lng': 151.2093}

# Add after Flask app initialization
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

@app.route('/chat', methods=['POST'])
async def chat():
    """Conversational chat endpoint that maintains history."""
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
            logger.info("Calling OpenAI API")
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
            logger.error(f"OpenAI API error: {str(e)}")
            return jsonify({'response': "I'm sorry, I encountered an error processing your request. Please try again."})
    
    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}", exc_info=True)
        return jsonify({'response': "I'm sorry, something went wrong with the chat service. Please try again."})

# Modified search function to accept optional parameters from chat
async def search(query=None, session_id=None):
    """Search for places based on user query."""
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
        search_radius = 5000 # Default large radius 
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
                    if any(t in types for t in ['locality', 'sublocality', 'neighborhood']): # Suburb level
                        search_radius = 1500 
                        location_specificity = "geocoded_suburb"
                    elif any(t in types for t in ['administrative_area_level_1', 'country']): # Very broad (State/Country)
                        search_radius = 10000 # Use a larger radius for broad areas like 'Sydney'
                        location_specificity = "geocoded_broad_area"
                    else: # Could be a street, PoI, etc. 
                        search_radius = 2000
                        location_specificity = "geocoded_specific"
                    logger.info(f"[Search] Using GEOCODED location: {location_query} -> {location}. Specificity: {location_specificity}. Types: {types}. Radius: {search_radius}m")
                else:
                    logger.warning(f"[Search] Geocoding failed for '{location_query}'. Falling back to default Sydney CBD.")
                    location_query = 'default' # Mark as default if geocoding failed
            except Exception as e:
                logger.error(f"[Search] Geocoding error for '{location_query}': {str(e)}", exc_info=True)
                location_query = 'default' # Mark as default on error
        else:
            logger.info(f"[Search] No specific location query ('{location_query}'), using default Sydney CBD.")
            location_query = 'default' # Ensure it is marked default
        
        # Fallback to Default Sydney CBD if geocoding wasn't attempted or failed
        if not location:
            location = (DEFAULT_LOCATION_COORDS['lat'], DEFAULT_LOCATION_COORDS['lng'])
            search_radius = 5000 # Ensure default radius
            location_specificity = "default_cbd"
            logger.info(f"[Search] Using DEFAULT location (Sydney CBD) -> {location}. Radius: {search_radius}m")

        # --- Google Maps API Call --- 
        try:
            logger.info(f"[Search] Calling Google Maps API - Location: {location}, Radius: {search_radius}, Keyword: '{search_terms}'")
            gmaps_start_time = datetime.now()
            places_result = gmaps.places_nearby(
                location=location,
                radius=search_radius,
                keyword=search_terms
            )
            gmaps_duration = (datetime.now() - gmaps_start_time).total_seconds()
            logger.info(f"[Search] Google Maps API call took {gmaps_duration:.2f}s")
            logger.info(f"[Search] Raw Google Maps Result (first 500 chars): {str(places_result)[:500]}")

            places_to_analyze = places_result.get('results', [])[:5]

            logger.info(f"[Search] Number of places to analyze: {len(places_to_analyze)}")
            if not places_to_analyze:
                logger.warning("[Search] No places found by Google Maps.")
                return jsonify({
                    'places': [],
                    'search_terms': search_terms,
                    'message': f'I searched for {search_terms} within {search_radius/1000}km of {location_query if location_query != "default" else "Sydney"}, but couldn\'t find any matches. Try broadening your search or trying a different location.'
                })

            filtered_places = []
            details_fetch_start_time = datetime.now()
            for i, place in enumerate(places_to_analyze):
                logger.info(f"[Search] Processing Place {i+1}/{len(places_to_analyze)}: {place.get('name', 'Unknown')} (ID: {place.get('place_id', 'N/A')})")
                try:
                    logger.info(f"\n{'='*50}\nProcessing place: {place.get('name', 'Unknown')}\n{'='*50}")
                    
                    place_details = gmaps.place(place['place_id'])['result']
                    logger.info(f"Google Maps Reviews found: {len(place_details.get('reviews', []))}")
                    
                    logger.info(f"Fetching additional data for: {place_details.get('name', '')}")
                    additional_data = await data_manager.gather_additional_data(
                        place_details.get('name', ''),
                        location_query
                    )
                    
                    logger.info(f"Additional data gathered:")
                    logger.info(f"- Articles found: {len(additional_data.get('articles', []))}")
                    logger.info(f"- Reddit posts found: {len(additional_data.get('reddit_posts', []))}")
                    
                    insights = data_manager.extract_relevant_insights(additional_data, user_query)
                    logger.info(f"Insights extracted:")
                    logger.info(f"- Recent mentions: {len(insights['recent_mentions'])}")
                    logger.info(f"- Relevant discussions: {len(insights['relevant_discussions'])}")
                    
                    reviews = []
                    if 'reviews' in place_details:
                        for review in place_details['reviews']:
                            reviews.append({
                                'rating': review.get('rating', 'N/A'),
                                'text': review.get('text', ''),
                                'time': review.get('relative_time_description', ''),
                                'author': review.get('author_name', 'Anonymous')
                            })

                    debug_info = {
                        'data_sources': {
                            'google_reviews': len(reviews),
                            'articles': len(additional_data.get('articles', [])),
                            'reddit_posts': len(additional_data.get('reddit_posts', [])),
                            'recent_mentions': len(insights['recent_mentions']),
                            'relevant_discussions': len(insights['relevant_discussions'])
                        }
                    }

                    filtered_places.append({
                        'name': place_details.get('name', ''),
                        'location': {
                            'lat': place['geometry']['location']['lat'],
                            'lng': place['geometry']['location']['lng']
                        },
                        'address': place_details.get('formatted_address', ''),
                        'rating': place_details.get('rating', 'N/A'),
                        'total_ratings': place_details.get('user_ratings_total', 0),
                        'reviews': reviews,
                        'opening_hours': place_details.get('opening_hours', {}).get('weekday_text', []),
                        'website': place_details.get('website', ''),
                        'phone': place_details.get('formatted_phone_number', ''),
                        'price_level': place_details.get('price_level', 'N/A'),
                        'types': place.get('types', []),
                        'place_id': place.get('place_id', ''),
                        'additional_insights': {
                            'recent_mentions': insights['recent_mentions'],
                            'relevant_discussions': insights['relevant_discussions']
                        },
                        'debug_info': debug_info
                    })
                except Exception as e:
                    logger.error(f"[Search] Error processing place {place.get('name', 'Unknown')}: {str(e)}", exc_info=True)
                    filtered_places.append({
                        'name': place['name'],
                        'location': {
                            'lat': place['geometry']['location']['lat'],
                            'lng': place['geometry']['location']['lng']
                        },
                        'address': place.get('vicinity', ''),
                        'rating': place.get('rating', 'N/A'),
                        'total_ratings': place.get('user_ratings_total', 0),
                        'reviews': [],
                        'opening_hours': [],
                        'website': '',
                        'phone': '',
                        'price_level': 'N/A',
                        'types': place.get('types', []),
                        'place_id': place.get('place_id', '')
                    })
            details_fetch_duration = (datetime.now() - details_fetch_start_time).total_seconds()
            logger.info(f"[Search] Fetching details for {len(filtered_places)} places took {details_fetch_duration:.2f}s")
            logger.info(f"[Search] Filtered Places data (first place name): {filtered_places[0]['name'] if filtered_places else 'None'}")

            logger.info(f"\n{'='*50}\nStarting analysis phase\n{'='*50}")
            logger.info(f"Analyzing {len(filtered_places)} places for query: {user_query}")

            analysis_prompt = f"""As a local expert, analyze these places in response to: "{user_query}"

            The user is looking for: {search_terms}
            With these requirements: {requirements}
            In this location: {location_query}

            For each place below, focus on synthesizing information from ALL available sources (Google Reviews, Articles, and Reddit discussions) to provide a comprehensive analysis.
            
            Places to analyze:
            {'\n\n'.join([
                f"=== {place['name']} ===\n" +
                f"Rating: {place['rating']}★ ({place['total_ratings']} reviews)\n" +
                f"Location: {place['address']}\n" +
                f"Price: {'$' * place['price_level'] if place['price_level'] != 'N/A' else 'N/A'}\n\n" +
                f"Google Reviews:\n" +
                '\n'.join([
                    f"- {review['rating']}★: \"{review['text']}\""
                    for review in place['reviews'][:2]
                ]) +
                f"\n\nRecent Articles & News:\n" +
                '\n'.join([
                    f"- {mention['source']} ({mention['date']}): {mention['excerpt']}"
                    for mention in place['additional_insights']['recent_mentions'][:2]
                ]) +
                f"\n\nReddit Discussions:\n" +
                '\n'.join([
                    f"- {discussion['title']} ({discussion['date']}):\n  " +
                    '\n  '.join([
                        f"• {comment['text']}"
                        for comment in discussion['relevant_comments'][:1]
                    ])
                    for discussion in place['additional_insights']['relevant_discussions'][:2]
                ])
                for place in filtered_places
            ])}

            Provide a balanced analysis in this EXACT format:
            summary: [2-3 sentences directly answering the user's query, mentioning the best options and why they match the requirements. Include insights from different sources.]
            highlights: [3-5 bullet points of specific features that match the user's requirements, with place names. Mix insights from reviews, articles, and discussions.]
            social_proof: [2-3 specific quotes from different sources (reviews, articles, Reddit) that best support the recommendations]
            considerations: [1-2 important notes about availability, peak times, or other relevant factors from any source]

            Focus on answering these specific aspects of the query:
            1. Which places best match the specific requirements? (Use all sources)
            2. What recent developments or changes are mentioned in articles?
            3. What do locals on Reddit say about these places?
            4. What practical information would help the user decide?

            Keep all responses concise and focused on the user's needs."""

            logger.info(f"[Search] Analysis Prompt (first 500 chars): {analysis_prompt[:500]}")

            analysis_start_time = datetime.now()
            analysis_response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a knowledgeable local expert who provides clear, practical recommendations based on real experiences and reviews."},
                    {"role": "user", "content": analysis_prompt}
                ],
                temperature=0.7
            )
            analysis_duration = (datetime.now() - analysis_start_time).total_seconds()
            logger.info(f"[Search] OpenAI Analysis call took {analysis_duration:.2f}s")

            analysis_text = analysis_response['choices'][0]['message']['content'].strip()
            logger.info(f"[Search] Raw analysis response from OpenAI:\n------ START ANALYSIS -----\n{analysis_text}\n------ END ANALYSIS ------")

            analysis_data = {
                'summary': '',
                'highlights': '',
                'social_proof': '',
                'considerations': ''
            }
            current_key = None
            try:
                lines = analysis_text.strip().split('\n')
                for line in lines:
                    line_stripped = line.strip()
                    if not line_stripped:
                        continue
                    
                    found_key = False
                    for key in analysis_data.keys():
                        if line_stripped.lower().startswith(key + ':'):
                            current_key = key
                            value = line.split(':', 1)[1].strip().strip('[]')
                            analysis_data[current_key] = value
                            found_key = True
                            break
                        
                    if not found_key and current_key:
                        separator = '\n' if analysis_data[current_key] else ''
                        analysis_data[current_key] += separator + line_stripped
                        
            except Exception as parse_error:
                logger.error(f"[Search] Error parsing analysis response: {parse_error}", exc_info=True)
            
            for key in analysis_data:
                analysis_data[key] = analysis_data[key].strip()
            
            logger.info(f"[Search] Parsed analysis data: {analysis_data}")

            for place in filtered_places:
                sources = []
                
                for review in place['reviews']:
                    sources.append({
                        'type': 'review',
                        'source': 'Google Review',
                        'rating': review['rating'],
                        'content': review['text'],
                        'metadata': {
                            'author': review['author'],
                            'date': review['time']
                        }
                    })
                
                for mention in place['additional_insights']['recent_mentions']:
                    sources.append({
                        'type': 'article',
                        'source': mention['source'],
                        'title': mention['title'],
                        'content': mention['excerpt'],
                        'metadata': {
                            'date': mention['date'],
                            'url': mention['url']
                        }
                    })
                
                for discussion in place['additional_insights']['relevant_discussions']:
                    for comment in discussion['relevant_comments']:
                        sources.append({
                            'type': 'reddit',
                            'source': 'Reddit',
                            'title': discussion['title'],
                            'content': comment['text'],
                            'metadata': {
                                'score': comment['score'],
                                'date': comment['date'],
                                'url': discussion['url']
                            }
                        })
                
                place['sources'] = sources

            logger.info(f"\n{'='*50}\nAnalysis complete\n{'='*50}")
            logger.info(f"Summary length: {len(analysis_data.get('summary', ''))}")
            logger.info(f"Number of highlights: {len(analysis_data.get('highlights', '').split('•'))}")
            logger.info(f"Social proof quotes: {len(analysis_data.get('social_proof', '').split('•'))}")

            if session_id:
                summary_message = f"Based on your query, I found information about {search_terms} in {location_query if location_query != 'default' else 'Sydney'}. Here's what I found:"
                conversation_manager.add_message(session_id, 'assistant', summary_message)

            final_data = {
                'places': filtered_places,
                'search_terms': search_terms,
                'location': location_query if location_query != "default" else "Sydney",
                'summary': analysis_data.get('summary', ''),
                'highlights': analysis_data.get('highlights', ''),
                'social_proof': analysis_data.get('social_proof', ''),
                'considerations': analysis_data.get('considerations', '')
            }
            logger.info(f"[Search] Final JSON data being returned (keys): {list(final_data.keys())}")
            logger.info(f"[Search] Summary in final data: {final_data.get('summary', 'MISSING')[:100]}...")
            request_duration = (datetime.now() - request_start_time).total_seconds()
            logger.info(f"=== Search End === Total Duration: {request_duration:.2f}s")
            return jsonify(final_data)

        except Exception as e:
            error_message = str(e)
            if "REQUEST_DENIED" in error_message:
                return jsonify({
                    'error': 'The Google Maps API is not properly configured.'
                }), 503
            print(f"Google Maps API error: {error_message}")
            return jsonify({'error': 'Error fetching places from Google Maps'}), 500

    except Exception as e:
        print(f"OpenAI API error: {str(e)}")
        return jsonify({'error': 'Error processing your request'}), 500

@app.teardown_appcontext
async def teardown_session(exception=None):
    await data_manager.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True) 