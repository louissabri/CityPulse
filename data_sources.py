import os
import asyncpraw
import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Optional
import asyncio
import aiohttp
from datetime import datetime, timedelta
import logging
import urllib.parse

# Set up logging with more detail
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Trusted domains for web scraping
TRUSTED_DOMAINS = {
    'broadsheet.com.au': {
        'base_url': 'https://www.broadsheet.com.au',
        'search_path': '/sydney/search?q=',
        'selectors': {
            'article': '.search-results article',
            'title': '.article-title',
            'content': '.article-summary',
            'date': '.article-date'
        }
    },
    'concreteplayground.com': {
        'base_url': 'https://concreteplayground.com',
        'search_path': '/sydney/search/',
        'selectors': {
            'article': '.grid-item',
            'title': '.title',
            'content': '.excerpt',
            'date': '.meta time'
        }
    },
    'timeout.com': {
        'base_url': 'https://www.timeout.com',
        'search_path': '/sydney/search?q=',
        'selectors': {
            'article': '.card--search',
            'title': '.card-title',
            'content': '.card-description',
            'date': '.published-date'
        }
    }
}

class DataSourceManager:
    def __init__(self):
        # Initialize Reddit API client with better error handling and validation
        self.reddit = None
        self.session = None
        self._reddit_session = None  # Add private session for Reddit
        
        # Validate Reddit credentials
        client_id = os.getenv('REDDIT_CLIENT_ID')
        client_secret = os.getenv('REDDIT_CLIENT_SECRET')
        
        if not client_id or not client_secret:
            logger.error("Missing Reddit API credentials")
            return
            
        try:
            logger.info("Initializing Reddit API client...")
            self.reddit = asyncpraw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent="AmenityFinderBot/1.0"
            )
            logger.info("Reddit API client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Reddit API client: {str(e)}")
            self.reddit = None

    async def get_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    async def get_reddit_session(self):
        """Get a dedicated session for Reddit API calls."""
        if self._reddit_session is None:
            self._reddit_session = aiohttp.ClientSession()
            # Attach the session to the Reddit instance
            self.reddit._core._requestor._http = self._reddit_session
        return self._reddit_session

    async def close(self):
        """Properly close all sessions."""
        if self.session:
            await self.session.close()
            self.session = None
        if self._reddit_session:
            await self._reddit_session.close()
            self._reddit_session = None
        if self.reddit:
            await self.reddit.close()

    async def scrape_trusted_site(self, domain: str, search_term: str) -> List[Dict]:
        """Scrape content from a trusted domain."""
        if domain not in TRUSTED_DOMAINS:
            return []

        config = TRUSTED_DOMAINS[domain]
        # URL encode the search term properly
        encoded_term = urllib.parse.quote(search_term)
        url = f"{config['base_url']}{config['search_path']}{encoded_term}"
        
        logger.info(f"Scraping {domain} for term: {search_term}")
        logger.info(f"Full URL: {url}")
        
        session = await self.get_session()
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    logger.warning(f"Failed to fetch from {domain}. Status: {response.status}")
                    return []
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html5lib')
                
                # Debug selector matches
                article_elements = soup.select(config['selectors']['article'])
                logger.info(f"Found {len(article_elements)} article elements using selector: {config['selectors']['article']}")
                
                # Debug full HTML if no articles found
                if len(article_elements) == 0:
                    logger.debug(f"HTML content preview: {html[:500]}...")
                
                articles = []
                for article in article_elements[:5]:  # Limit to 5 results
                    try:
                        # Debug each selector
                        title_elem = article.select_one(config['selectors']['title'])
                        content_elem = article.select_one(config['selectors']['content'])
                        date_elem = article.select_one(config['selectors']['date'])
                        
                        logger.debug(f"Title selector '{config['selectors']['title']}' found: {title_elem is not None}")
                        logger.debug(f"Content selector '{config['selectors']['content']}' found: {content_elem is not None}")
                        logger.debug(f"Date selector '{config['selectors']['date']}' found: {date_elem is not None}")
                        
                        if title_elem and content_elem:
                            title_text = title_elem.text.strip()
                            content_text = content_elem.text.strip()
                            date_text = date_elem.text.strip() if date_elem else None
                            url_elem = article.find('a')
                            
                            # Debug extracted content
                            logger.debug(f"Extracted title: {title_text[:50]}...")
                            logger.debug(f"Extracted content length: {len(content_text)}")
                            
                            articles.append({
                                'source': domain,
                                'title': title_text,
                                'content': content_text,
                                'date': date_text,
                                'url': config['base_url'] + url_elem['href'] if url_elem and 'href' in url_elem.attrs else None
                            })
                            logger.info(f"Successfully processed article: {title_text[:50]}...")
                    except Exception as e:
                        logger.error(f"Error processing article from {domain}: {str(e)}")
                        continue
                
                logger.info(f"Found {len(articles)} valid articles from {domain}")
                return articles
        except Exception as e:
            logger.error(f"Error scraping {domain}: {str(e)}")
            return []

    async def get_reddit_content(self, subreddit_name: str, search_query: str) -> List[Dict]:
        """Get relevant content from Reddit with retry logic."""
        if not self.reddit:
            logger.error("Reddit API client not initialized")
            return []

        # Ensure Reddit session is active
        await self.get_reddit_session()

        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                logger.info(f"Searching Reddit r/{subreddit_name} for: {search_query} (Attempt {retry_count + 1})")
                subreddit = await self.reddit.subreddit(subreddit_name)
                posts = []
                
                # Search for relevant posts from the past month
                async for post in subreddit.search(search_query, time_filter='month', limit=10):
                    try:
                        # Only include posts with comments
                        if post.num_comments > 0:
                            logger.info(f"Processing post: {post.title[:50]}...")
                            
                            # Get top 5 comments
                            await post.load()
                            post.comments.replace_more(limit=0)
                            comments = []
                            comment_count = 0
                            
                            async for comment in post.comments.list():
                                if comment_count >= 5:
                                    break
                                    
                                comment_text = comment.body.strip()
                                if len(comment_text) > 20:  # Filter out very short comments
                                    comments.append({
                                        'text': comment_text,
                                        'score': comment.score,
                                        'created_utc': datetime.fromtimestamp(comment.created_utc).strftime('%Y-%m-%d')
                                    })
                                    comment_count += 1
                                    logger.debug(f"Added comment with score {comment.score}")
                            
                            if comments:  # Only include posts with valid comments
                                posts.append({
                                    'title': post.title,
                                    'url': f"https://reddit.com{post.permalink}",
                                    'score': post.score,
                                    'num_comments': post.num_comments,
                                    'created_utc': datetime.fromtimestamp(post.created_utc).strftime('%Y-%m-%d'),
                                    'comments': comments
                                })
                                logger.info(f"Added post with {len(comments)} comments")
                    except Exception as e:
                        logger.error(f"Error processing Reddit post: {str(e)}")
                        continue
                
                logger.info(f"Found {len(posts)} relevant Reddit posts")
                return posts
                
            except Exception as e:
                retry_count += 1
                logger.error(f"Error fetching Reddit content (Attempt {retry_count}): {str(e)}")
                if retry_count < max_retries:
                    await asyncio.sleep(1)  # Wait 1 second before retrying
                else:
                    logger.error("Max retries reached for Reddit content fetch")
                    return []
        
        return []

    async def gather_additional_data(self, place_name: str, location: str) -> Dict:
        """Gather additional data from all sources for a specific place."""
        search_term = f"{place_name} {location}"
        logger.info(f"\n{'='*50}\nGathering data for: {search_term}\n{'='*50}")
        
        # Gather data from all sources concurrently
        scraping_tasks = []
        for domain in TRUSTED_DOMAINS.keys():
            logger.info(f"Setting up scraping task for {domain}")
            scraping_tasks.append(self.scrape_trusted_site(domain, search_term))
        
        # Add Reddit search task
        if self.reddit:
            logger.info("Setting up Reddit search task")
            reddit_task = self.get_reddit_content('sydney', search_term)
        else:
            logger.error("Reddit client not initialized - skipping Reddit search")
            reddit_task = None
        
        # Gather all results
        try:
            if reddit_task:
                results = await asyncio.gather(*scraping_tasks, reddit_task, return_exceptions=True)
            else:
                results = await asyncio.gather(*scraping_tasks, return_exceptions=True)
            
            # Process results
            additional_data = {
                'articles': [],
                'reddit_posts': []
            }
            
            # Process web scraping results
            for i, result in enumerate(results[:-1] if reddit_task else results):
                domain = list(TRUSTED_DOMAINS.keys())[i]
                if isinstance(result, Exception):
                    logger.error(f"Error from {domain}: {str(result)}")
                elif isinstance(result, list):
                    logger.info(f"Got {len(result)} articles from {domain}")
                    additional_data['articles'].extend(result)
                else:
                    logger.warning(f"Unexpected result type from {domain}: {type(result)}")
            
            # Process Reddit results
            if reddit_task:
                reddit_result = results[-1]
                if isinstance(reddit_result, Exception):
                    logger.error(f"Error from Reddit: {str(reddit_result)}")
                elif isinstance(reddit_result, list):
                    logger.info(f"Got {len(reddit_result)} Reddit posts")
                    additional_data['reddit_posts'] = reddit_result
                else:
                    logger.warning(f"Unexpected result type from Reddit: {type(reddit_result)}")
            
            logger.info(f"Final data count - Articles: {len(additional_data['articles'])}, Reddit posts: {len(additional_data['reddit_posts'])}")
            return additional_data
            
        except Exception as e:
            logger.error(f"Error gathering additional data: {str(e)}")
            return {'articles': [], 'reddit_posts': []}

    def extract_relevant_insights(self, data: Dict, user_query: str) -> Dict:
        """Extract relevant insights from the additional data."""
        insights = {
            'recent_mentions': [],
            'popular_opinions': [],
            'relevant_discussions': []
        }
        
        # Process articles
        for article in data.get('articles', []):
            if article['date']:  # Add recent mentions
                insights['recent_mentions'].append({
                    'source': article['source'],
                    'title': article['title'],
                    'excerpt': article['content'][:200] + '...',
                    'date': article['date'],
                    'url': article['url']
                })
        
        # Process Reddit posts
        for post in data.get('reddit_posts', []):
            # Add popular discussions
            if post['score'] > 5:  # Only include posts with positive score
                discussion = {
                    'title': post['title'],
                    'url': post['url'],
                    'date': post['created_utc'],
                    'relevant_comments': []
                }
                
                # Add relevant comments
                for comment in post['comments']:
                    if comment['score'] > 1:  # Only include positively scored comments
                        discussion['relevant_comments'].append({
                            'text': comment['text'][:200] + '...' if len(comment['text']) > 200 else comment['text'],
                            'score': comment['score'],
                            'date': comment['created_utc']
                        })
                
                if discussion['relevant_comments']:
                    insights['relevant_discussions'].append(discussion)
        
        return insights 