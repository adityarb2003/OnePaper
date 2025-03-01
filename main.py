import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import schedule
import json
import feedparser
from flask import Flask, jsonify, make_response
from threading import Thread
import logging
import aiohttp
import asyncio
from email.utils import formataddr
import re
from cachetools import cached, TTLCache
import jwt
import os
from typing import Dict, List, Optional
from fastapi import HTTPException
from urllib.parse import quote
from datetime import datetime, timedelta
import pytz
import io
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('tech_news.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
cache = TTLCache(maxsize=100, ttl=3600)


SUBSCRIBERS_FILE = "subscribers.json"


class SubscriberManager:
    def __init__(self):
        self.secret_key = os.getenv('JWT_SECRET_KEY')
        if not self.secret_key:
            self.secret_key = ''

        self.logger = logging.getLogger(__name__)

    # def generate_token(self, email: str, action: str) -> str:
    #     """Generate a secure token for subscriber actions"""
    #     try:
    #         payload = {
    #             'email': email,
    #             'action': action,
    #             'exp': datetime.now(datetime.UTC) + timedelta(days=30),   # Token expires in 30 days
    #             'iat': datetime.now(datetime.UTC)   # Token creation time
    #         }
    #         token = jwt.encode(payload, self.secret_key, algorithm='HS256')
    #         self.logger.info(f"Generated token for {email} with action {action}")
    #         return token
    #     except Exception as e:
    #         self.logger.error(f"Error generating token: {e}")
    #         raise HTTPException(status_code=500, detail="Error generating token")
    def generate_token(self, email: str, action: str) -> str:
        """Generate a secure token for subscriber actions"""
        try:
            utc_now = datetime.now(pytz.UTC)
            payload = {
                'email': email,
                'action': action,
                'exp': utc_now + timedelta(days=30),  # Token expires in 30 days
                'iat': utc_now  # Token creation time
            }
            token = jwt.encode(payload, self.secret_key, algorithm='HS256')
            self.logger.info(f"Generated token for {email} with action {action}")
            return token
        except Exception as e:
            self.logger.error(f"Error generating token: {e}")
            raise HTTPException(status_code=500, detail="Error generating token")

    def verify_token(self, token: str) -> dict:
        """Verify and decode a subscriber token"""
        try:
            # Add logging to track token verification
            self.logger.info("Attempting to verify token")

            # Decode and verify the token
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])

            # Log successful verification
            self.logger.info(f"Token verified successfully for {payload.get('email')}")

            return payload

        except jwt.ExpiredSignatureError:
            self.logger.error("Token has expired")
            raise HTTPException(status_code=400, detail="Token has expired")
        except jwt.InvalidTokenError as e:
            self.logger.error(f"Invalid token: {str(e)}")
            raise HTTPException(status_code=400, detail="Invalid token")
        except Exception as e:
            self.logger.error(f"Unexpected error during token verification: {str(e)}")
            raise HTTPException(status_code=400, detail="Invalid token")

class TechNewsAggregator:
    def __init__(self):
        super().__init__()
        self.subscriber_manager = SubscriberManager()
        self.base_url = os.getenv('BASE_URL', 'http://localhost:5000')
        load_dotenv()
        self.subscribers = {}  # email: [preferences]
        self.email_sender = os.getenv('EMAIL_SENDER')
        self.email_password = os.getenv('EMAIL_PASSWORD')
        self.sender_name = os.getenv('SENDER_NAME', 'Tech News Digest')
        self.api_keys = {
            'newsapi': os.getenv('NEWSAPI_KEY'),
            'github': os.getenv('GITHUB_TOKEN')
        }
        self.load_subscribers()
        self.flask_app = Flask(__name__)
        self.add_health_endpoint()
        self.session = None

    def get_management_links(self, email: str) -> Dict[str, str]:
        """Generate secure links for subscription management"""
        unsubscribe_token = self.subscriber_manager.generate_token(email, 'unsubscribe')
        preferences_token = self.subscriber_manager.generate_token(email, 'preferences')

        return {
            'unsubscribe': f"{self.base_url}/unsubscribe?token={quote(unsubscribe_token)}",
            'preferences': f"{self.base_url}/preferences?token={quote(preferences_token)}"
        }

    async def initialize_session(self):
        """Initialize aiohttp session for async requests"""
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def close_session(self):
        """Close aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None

    def load_subscribers(self):
        """Load subscribers from JSON file if it exists."""
        try:
            with open('subscribers.json', 'r') as f:
                self.subscribers = json.load(f)
            logger.info(f"Loaded {len(self.subscribers)} subscribers")
        except FileNotFoundError:
            self.subscribers = {}
            logger.info("No existing subscribers file found")


    # def save_subscribers(self):
    #     """Save subscribers to JSON file."""
    #     try:
    #         with open('subscribers.json', 'w') as f:
    #             json.dump(self.subscribers, f)
    #         logger.info(f"Saved {len(self.subscribers)} subscribers")
    #     except Exception as e:
    #         logger.error(f"Error saving subscribers: {e}")
    def save_subscribers(self):
        """Save subscribers to JSON file."""
        try:
            with io.open('subscribers.json', 'w', encoding='utf-8') as f:
                f.write(json.dumps(self.subscribers, ensure_ascii=False, indent=4))
            logger.info(f"Saved {len(self.subscribers)} subscribers")
        except Exception as e:
            logger.error(f"Error saving subscribers: {e}")
    def add_health_endpoint(self):
        """Define the /health endpoint to check app status."""

        @self.flask_app.route('/health', methods=['GET'])
        def health():
            health_status = {
                "STATUS": "NORMAL",
                "SUBSCRIBERS": len(self.subscribers),
                "NEWS": bool(self.api_keys['newsapi']),
                "GITHUB": bool(self.api_keys['github']),
                "LAST_UPDATED": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            return make_response(jsonify(health_status), 200)

    def start_health_server(self, host='0.0.0.0', port=5001):
        """Start the Flask server in a separate thread."""
        thread = Thread(target=self.flask_app.run, kwargs={'host': host, 'port': port, 'use_reloader': False})
        thread.daemon = True
        thread.start()
        logger.info(f"Health server started on port {port}")

    @cached(cache) # Cache for 1 hour
    # async def fetch_github_trending(self) -> List[Dict]:
    #     """Fetch GitHub trending repositories"""
    #     try:
    #         headers = {'Authorization': f'token {self.api_keys["github"]}'}
    #         async with self.session.get(
    #                 'https://api.github.com/search/repositories?q=created:>2024-01-01&sort=stars&order=desc',
    #                 headers=headers
    #         ) as response:
    #             data = await response.json()
    #             repos = data['items'][:10]
    #             return [{
    #                 'title': f"{repo['full_name']} - {repo['description']}",
    #                 'url': repo['html_url'],
    #                 'source': 'GitHub Trending'
    #             } for repo in repos]
    #     except Exception as e:
    #         logger.error(f"Error fetching from GitHub: {e}")
    #         return []

    async def fetch_github_trending(self) -> List[Dict]:
        """
        Fetch trending GitHub repositories using a sophisticated trending detection approach.
        Considers star velocity and recent activity to identify truly trending repos.
        """
        try:
            # Calculate date ranges for different periods
            now = datetime.now()
            today = now.strftime('%Y-%m-%d')
            week_ago = (now - timedelta(days=7)).strftime('%Y-%m-%d')

            headers = {
                'Authorization': f'token {self.api_keys["github"]}',
                'Accept': 'application/vnd.github.v3+json'
            }


            query = f'created:>{week_ago} stars:>50 fork:false'
            url = f'https://api.github.com/search/repositories?q={query}&sort=stars&order=desc&per_page=50'

            async with self.session.get(url, headers=headers) as response:
                if response.status != 200:
                    logger.error(f"GitHub API returned status {response.status}")
                    return []

                data = await response.json()
                potential_trending = data.get('items', [])


                trending_repos = []
                for repo in potential_trending[:15]:
                    repo_name = repo['full_name']


                    activity_url = f'https://api.github.com/repos/{repo_name}/stargazers'
                    async with self.session.get(activity_url, headers={
                        **headers,
                        'Accept': 'application/vnd.github.star+json'
                    }) as activity_response:
                        if activity_response.status == 200:
                            activity_data = await activity_response.json()


                            recent_stars = len([s for s in activity_data if s.get('starred_at', '').startswith(today)])
                            weekly_stars = repo['stargazers_count']
                            star_velocity = recent_stars / 1 if recent_stars > 0 else weekly_stars / 7


                            commits_url = f'https://api.github.com/repos/{repo_name}/commits'
                            async with self.session.get(commits_url, headers=headers) as commits_response:
                                if commits_response.status == 200:
                                    commits_data = await commits_response.json()
                                    recent_commits = len(
                                        [c for c in commits_data if c['commit']['author']['date'].startswith(today)])


                                    score = (star_velocity * 3) + (recent_commits * 2) + (repo['forks_count'] * 0.5)

                                    trending_repos.append({
                                        'repo': repo,
                                        'score': score,
                                        'star_velocity': star_velocity,
                                        'recent_commits': recent_commits
                                    })

                trending_repos.sort(key=lambda x: x['score'], reverse=True)
                return [{
                    'title': (f"{repo['repo']['full_name']} ({repo['repo']['stargazers_count']}★ | "
                              f"+{round(repo['star_velocity'], 1)} stars/day | "
                              f"{repo['recent_commits']} commits today) - {repo['repo']['description']}"
                              if repo['repo']['description'] else
                              f"{repo['repo']['full_name']} ({repo['repo']['stargazers_count']}★)"),
                    'url': repo['repo']['html_url'],
                    'source': 'GitHub Trending',
                    'language': repo['repo']['language'],
                    'score': round(repo['score'], 2)
                } for repo in trending_repos[:5]]

        except Exception as e:
            logger.error(f"Error fetching from GitHub: {e}")
            return []

    async def fetch_hacker_news(self) -> List[Dict]:
        """Fetch top stories from Hacker News."""
        try:

            response = requests.get('https://hacker-news.firebaseio.com/v0/topstories.json')
            story_ids = response.json()[:5]

            stories = []
            for story_id in story_ids:
                story_response = requests.get(f'https://hacker-news.firebaseio.com/v0/item/{story_id}.json')
                story = story_response.json()
                stories.append({
                    'title': story.get('title'),
                    'url': story.get('url', f'https://news.ycombinator.com/item?id={story_id}'),
                    'description': story.get('text', '')[:200] + '...' if story.get(
                        'text') else 'Check out the article for more details.',
                    'source': 'Hacker News'
                })
            return stories
        except Exception as e:
            print(f"Error fetching from Hacker News: {e}")
            return []

    async def fetch_science_daily(self) -> List[Dict]:
        """Fetch technology news from Science Daily RSS feed"""
        try:
            async with self.session.get('https://www.sciencedaily.com/rss/computers_math/technology.xml') as response:
                content = await response.text()
                feed = feedparser.parse(content)
                return [{
                    'title': entry.title,
                    'url': entry.link,
                    'description': entry.summary[:200] + '...' if hasattr(entry,
                                                                          'summary') else 'No description available',
                    'source': 'Science Daily'
                } for entry in feed.entries[:5]]
        except Exception as e:
            logger.error(f"Error fetching from Science Daily: {e}")
            return []

    # async def fetch_newsapi_tech(self) -> List[Dict]:
    #     """Fetch from NewsAPI (TechCrunch, The Verge, Wired)"""
    #     try:
    #         sources = 'techcrunch,the-verge,wired'
    #         async with self.session.get(
    #                 f'https://newsapi.org/v2/top-headlines?sources={sources}&apiKey={self.api_keys["newsapi"]}'
    #         ) as response:
    #             data = await response.json()
    #             articles = data['articles']
    #             return [{
    #                 'title': article['title'],
    #                 'url': article['url'],
    #                 'source': article['source']['name']
    #             } for article in articles]
    #     except Exception as e:
    #         logger.error(f"Error fetching from NewsAPI: {e}")
    #         return []
    async def fetch_newsapi_tech(self) -> List[Dict]:
        """
        Fetch tech news from multiple sources with improved diversity and randomness
        """
        try:

            sources = [
                'techcrunch,the-verge,wired'
            ]


            async with self.session.get(
                    f'https://newsapi.org/v2/top-headlines?'
                    f'country=us&'
                    f'category=technology&'
                    f'sources={sources}&'
                    f'pageSize=10&'  
                    f'apiKey={self.api_keys["newsapi"]}'
            ) as response:
                data = await response.json()


                if data.get('status') != 'ok':
                    logger.error(f"NewsAPI error: {data.get('message', 'Unknown error')}")
                    return []

                articles = data.get('articles', [])


                unique_articles = []
                seen_titles = set()
                for article in articles:
                    if (article['title'] and article['title'] not in seen_titles and
                            len(article['title']) > 10 and
                            'placeholder' not in article['title'].lower()):
                        unique_articles.append({
                            'title': article['title'],
                            'url': article['url'],
                            'source': article['source']['name'],
                            'description': article.get('description', 'No description available')[:200] + '...'
                        })
                        seen_titles.add(article['title'])

                    if len(unique_articles) >= 5:
                        break

                return unique_articles

        except Exception as e:
            logger.error(f"Error fetching from NewsAPI: {e}")
            return []
    async def fetch_dev_to(self) -> List[Dict]:
        """Fetch top articles from Dev.to."""
        try:
            response = requests.get('https://dev.to/api/articles?top=1&per_page=10')
            articles = response.json()
            return [{
                'title': article['title'],
                'url': article['url'],
                'source': 'Dev.to'
            } for article in articles]
        except Exception as e:
            print(f"Error fetching from Dev.to: {e}")
            return []

    async def fetch_stack_exchange(self) -> List[Dict]:
        """Fetch hot questions from Stack Overflow."""
        try:
            response = requests.get(
                'https://api.stackexchange.com/2.3/questions',
                params={
                    'site': 'stackoverflow',
                    'sort': 'hot',
                    'pagesize': 10
                }
            )
            questions = response.json()['items']
            return [{
                'title': question['title'],
                'url': question['link'],
                'source': 'Stack Exchange'
            } for question in questions]
        except Exception as e:
            print(f"Error fetching from Stack Exchange: {e}")
            return []

    async def fetch_reddit(self) -> List[Dict]:
        """Fetch top posts from r/programming."""
        try:
            headers = {'User-Agent': 'TechNewsAggregator/1.0'}
            response = requests.get(
                'https://www.reddit.com/r/programming/top.json?limit=10',
                headers=headers
            )
            posts = response.json()['data']['children']
            return [{
                'title': post['data']['title'],
                'url': f"https://reddit.com{post['data']['permalink']}",
                'source': 'Reddit'
            } for post in posts]
        except Exception as e:
            print(f"Error fetching from Reddit: {e}")
            return []

    async def fetch_rss_feed_with_description(self, url: str, source_name: str) -> List[Dict]:
        """Fetch articles with descriptions from an RSS feed."""
        try:
            async with self.session.get(url) as response:
                content = await response.text()
                feed = feedparser.parse(content)
                return [
                    {
                        'title': entry.title,
                        'url': entry.link,
                        'description': (entry.summary[:200] + '...') if hasattr(entry,
                                                                                'summary') else 'No description available',
                        'source': source_name
                    }
                    for entry in feed.entries[:5]
                ]
        except Exception as e:
            logger.error(f"Error fetching RSS feed from {source_name}: {e}")
            return []

    # async def fetch_all_sources(self, preferences: List[str]) -> List[Dict]:
    #     """Fetch news from all selected sources concurrently"""
    #     tasks = []
    #
    #     source_mapping = {
    #         "Science Daily": self.fetch_science_daily,
    #         "Hacker News": self.fetch_hacker_news,
    #         "Reddit": self.fetch_reddit,
    #         "Dev.to": self.fetch_dev_to,
    #         "Stack Exchange": self.fetch_stack_exchange,
    #         "GitHub Trending": self.fetch_github_trending,
    #         "The Verge": self.fetch_newsapi_tech,
    #         "Wired": self.fetch_newsapi_tech,
    #         "Ars Technica": lambda: self.fetch_rss_feed_with_description('https://arstechnica.com/feed/',
    #                                                                      'Ars Technica'),
    #         "VentureBeat": lambda: self.fetch_rss_feed_with_description('https://venturebeat.com/feed/', 'VentureBeat'),
    #         "ZDNet": lambda: self.fetch_rss_feed_with_description('https://www.zdnet.com/news/rss.xml', 'ZDNet'),
    #         "TechRadar": lambda: self.fetch_rss_feed_with_description('https://www.techradar.com/rss', 'TechRadar'),
    #         "Hackernoon": lambda: self.fetch_rss_feed_with_description('https://hackernoon.com/feed', 'Hackernoon')
    #     }
    #
    #     for source in preferences:
    #         if source in source_mapping:
    #             tasks.append(source_mapping[source]())
    #
    #     results = await asyncio.gather(*tasks, return_exceptions=True)
    #
    #     all_news = []
    #     for result in results:
    #         if isinstance(result, list):  # Successful fetch
    #             all_news.extend(result)
    #         else:  # Exception occurred
    #             logger.error(f"Error fetching news: {result}")
    #
    #     return all_news

    async def fetch_all_sources(self, email: str) -> List[Dict]:
        """Fetch news based on the user's selected category or preferences from JSON file."""

        # Categories mapping
        category_mapping = {
            "Programming": ["Hacker News", "Reddit", "Dev.to", "Stack Exchange", "GitHub Trending"],
            "Tech & AI": ["The Verge", "Wired", "Ars Technica", "VentureBeat", "ZDNet", "TechRadar", "Hackernoon",
                          "Science Daily"]
        }

        user_preferences = self.subscribers.get(email, [])
        if not user_preferences:
            user_preferences = category_mapping["Tech & AI"]

        elif len(user_preferences) == 1 and user_preferences[0] in category_mapping:
            user_preferences = category_mapping[user_preferences[0]]

        source_mapping = {
            "Hacker News": self.fetch_hacker_news,
            "Reddit": self.fetch_reddit,
            "Dev.to": self.fetch_dev_to,
            "Stack Exchange": self.fetch_stack_exchange,
            "GitHub Trending": self.fetch_github_trending,
            "The Verge": self.fetch_newsapi_tech,
            "Wired": self.fetch_newsapi_tech,
            "Ars Technica": lambda: self.fetch_rss_feed_with_description('https://arstechnica.com/feed/',
                                                                         'Ars Technica'),
            "VentureBeat": lambda: self.fetch_rss_feed_with_description('https://venturebeat.com/feed/', 'VentureBeat'),
            "ZDNet": lambda: self.fetch_rss_feed_with_description('https://www.zdnet.com/news/rss.xml', 'ZDNet'),
            "TechRadar": lambda: self.fetch_rss_feed_with_description('https://www.techradar.com/rss', 'TechRadar'),
            "Hackernoon": lambda: self.fetch_rss_feed_with_description('https://hackernoon.com/feed', 'Hackernoon'),
            "Science Daily": self.fetch_science_daily
        }

        tasks = [source_mapping[source]() for source in user_preferences if source in source_mapping]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_news = []
        for result in results:
            if isinstance(result, list):
                all_news.extend(result)
            else:
                logger.error(f"Error fetching news: {result}")

        return all_news

    def validate_email(self, email: str) -> bool:
        """Validate email format"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    def add_subscriber(self, email: str, preferences: Optional[List[str]] = None):
        """Add a new subscriber with their preferences."""
        if not self.validate_email(email):
            logger.error(f"Invalid email format: {email}")
            raise ValueError("Invalid email format")

        if preferences is None:
            preferences = ['Hacker News', 'Reddit', 'Dev.to', 'Stack Exchange', 'GitHub Trending',
                           'The Verge', 'Wired', 'Ars Technica', 'VentureBeat', 'ZDNet',
                           'TechRadar', 'Hackernoon', 'Science Daily']

        self.subscribers[email] = preferences
        self.save_subscribers()
        logger.info(f"Added subscriber: {email} with {len(preferences)} preferences")

    def remove_subscriber(self, email: str):
        """Remove a subscriber."""
        if email in self.subscribers:
            del self.subscribers[email]
            self.save_subscribers()
            logger.info(f"Removed subscriber: {email}")
        else:
            logger.warning(f"Attempt to remove non-existent subscriber: {email}")

    # async def generate_newsletter(self, preferences: Optional[List[str]] = None) -> str:
    #     """Generate HTML newsletter content."""
    #     if preferences is None:
    #         preferences = ['Hacker News', 'Reddit', 'Dev.to', 'Stack Exchange', 'GitHub Trending',
    #                        'The Verge', 'Wired', 'Ars Technica', 'VentureBeat', 'ZDNet',
    #                        'TechRadar', 'Hackernoon', 'Science Daily']
    #
    #     all_news = await self.fetch_all_sources(preferences)
    #     html_content = await super().generate_newsletter(preferences)
    #
    #     # Group news by source
    #     news_by_source = {}
    #     for item in all_news:
    #         if item['source'] not in news_by_source:
    #             news_by_source[item['source']] = []
    #         news_by_source[item['source']].append(item)
    #
    #     # Generate HTML content with improved styling
    #     html = """
    #     <html>
    #     <head>
    #         <style>
    #             body {
    #                 font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
    #                 max-width: 800px;
    #                 margin: 0 auto;
    #                 padding: 20px;
    #                 line-height: 1.6;
    #                 color: #2d3748;
    #                 background-color: #f7fafc;
    #             }
    #             .header {
    #                 background-color: #2b6cb0;
    #                 color: white;
    #                 padding: 24px;
    #                 border-radius: 8px;
    #                 margin-bottom: 32px;
    #             }
    #             h1 {
    #                 font-size: 32px;
    #                 font-weight: bold;
    #                 margin: 0;
    #             }
    #             h2 {
    #                 font-size: 24px;
    #                 color: #2d3748;
    #                 border-bottom: 2px solid #e2e8f0;
    #                 padding-bottom: 8px;
    #                 margin-top: 32px;
    #             }
    #             .news-item {
    #                 background-color: white;
    #                 padding: 16px;
    #                 border-radius: 8px;
    #                 margin-bottom: 16px;
    #                 box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    #             }
    #             .news-title {
    #                 color: #2b6cb0;
    #                 text-decoration: none;
    #                 font-weight: 600;
    #                 font-size: 18px;
    #                 display: block;
    #                 margin-bottom: 8px;
    #             }
    #             .news-title:hover {
    #                 color: #2c5282;
    #             }
    #             .description {
    #                 color: #4a5568;
    #                 font-size: 16px;
    #                 margin: 8px 0;
    #             }
    #             .footer {
    #                 margin-top: 40px;
    #                 padding-top: 20px;
    #                 border-top: 1px solid #e2e8f0;
    #                 color: #718096;
    #                 font-size: 14px;
    #             }
    #             .unsubscribe {
    #                 color: #718096;
    #                 text-decoration: underline;
    #             }
    #         </style>
    #     </head>
    #     <body>
    #         <div class="header">
    #             <h1>ICYMI</h1>
    #             <p>Your daily roundup of the most important tech news</p>
    #         </div>
    #     """
    #
    #     for source, items in news_by_source.items():
    #         html += f"<h2>{source}</h2>"
    #         for item in items:
    #             description = item.get('description', 'Click to read more about this story.')
    #             html += f"""
    #                 <div class="news-item">
    #                     <a href="{item['url']}" class="news-title">{item['title']}</a>
    #                     <p class="description">{description}</p>
    #                 </div>
    #             """
    #
    #     html += """
    #         <div class="footer">
    #             <p>Thanks for reading!</p>
    #             <p>To unsubscribe, <a href="{{unsubscribe_link}}" class="unsubscribe">click here</a></p>
    #         </div>
    #     </body>
    #     </html>
    #     """
    #
    #     return html

    # async def generate_newsletter(self, preferences: Optional[List[str]] = None) -> str:
    #     """Generate HTML newsletter content with improved styling and management links."""
    #     if preferences is None:
    #         preferences = ['Hacker News', 'Reddit', 'Dev.to', 'Stack Exchange', 'GitHub Trending',
    #                        'The Verge', 'Wired', 'Ars Technica', 'VentureBeat', 'ZDNet',
    #                        'TechRadar', 'Hackernoon', 'Science Daily']
    #
    #     all_news = await self.fetch_all_sources(preferences)
    #
    #     # Group news by source
    #     news_by_source = {}
    #     for item in all_news:
    #         if item['source'] not in news_by_source:
    #             news_by_source[item['source']] = []
    #         news_by_source[item['source']].append(item)
    #
    #     # Generate HTML content with improved styling
    #     html = """
    #     <html>
    #     <head>
    #         <meta charset="UTF-8">
    #         <meta name="viewport" content="width=device-width, initial-scale=1.0">
    #         <style>
    #             body {
    #                 font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
    #                 max-width: 800px;
    #                 margin: 0 auto;
    #                 padding: 20px;
    #                 line-height: 1.6;
    #                 color: #2d3748;
    #                 background-color: #f7fafc;
    #             }
    #             .header {
    #                 background-color: #2b6cb0;
    #                 color: white;
    #                 padding: 24px;
    #                 border-radius: 8px;
    #                 margin-bottom: 32px;
    #                 text-align: center;
    #             }
    #             h1 {
    #                 font-size: 32px;
    #                 font-weight: bold;
    #                 margin: 0;
    #                 margin-bottom: 8px;
    #             }
    #             .header p {
    #                 margin: 0;
    #                 opacity: 0.9;
    #             }
    #             h2 {
    #                 font-size: 24px;
    #                 color: #2d3748;
    #                 border-bottom: 2px solid #e2e8f0;
    #                 padding-bottom: 8px;
    #                 margin-top: 32px;
    #             }
    #             .news-item {
    #                 background-color: white;
    #                 padding: 16px;
    #                 border-radius: 8px;
    #                 margin-bottom: 16px;
    #                 box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    #                 transition: transform 0.2s ease;
    #             }
    #             .news-item:hover {
    #                 transform: translateY(-2px);
    #             }
    #             .news-title {
    #                 color: #2b6cb0;
    #                 text-decoration: none;
    #                 font-weight: 600;
    #                 font-size: 18px;
    #                 display: block;
    #                 margin-bottom: 8px;
    #             }
    #             .news-title:hover {
    #                 color: #2c5282;
    #             }
    #             .description {
    #                 color: #4a5568;
    #                 font-size: 16px;
    #                 margin: 8px 0;
    #                 line-height: 1.6;
    #             }
    #             .footer {
    #                 margin-top: 40px;
    #                 padding: 20px;
    #                 border-top: 1px solid #e2e8f0;
    #                 color: #718096;
    #                 font-size: 14px;
    #                 text-align: center;
    #             }
    #             .footer p {
    #                 margin: 8px 0;
    #             }
    #             .management-links {
    #                 margin-top: 16px;
    #             }
    #             .management-link {
    #                 display: inline-block;
    #                 padding: 8px 16px;
    #                 margin: 0 8px;
    #                 color: #718096;
    #                 text-decoration: none;
    #                 border-radius: 4px;
    #                 border: 1px solid #e2e8f0;
    #                 transition: all 0.2s ease;
    #             }
    #             .management-link:hover {
    #                 background-color: #f7fafc;
    #                 color: #2b6cb0;
    #                 border-color: #2b6cb0;
    #             }
    #             .unsubscribe {
    #                 color: #ef4444;
    #             }
    #             .unsubscribe:hover {
    #                 background-color: #fef2f2;
    #                 color: #dc2626;
    #                 border-color: #dc2626;
    #             }
    #             .source-badge {
    #                 display: inline-block;
    #                 padding: 4px 8px;
    #                 font-size: 12px;
    #                 color: #718096;
    #                 background-color: #f7fafc;
    #                 border-radius: 4px;
    #                 margin-top: 8px;
    #             }
    #             @media (max-width: 600px) {
    #                 body {
    #                     padding: 12px;
    #                 }
    #                 .header {
    #                     padding: 16px;
    #                 }
    #                 h1 {
    #                     font-size: 24px;
    #                 }
    #                 .news-title {
    #                     font-size: 16px;
    #                 }
    #                 .description {
    #                     font-size: 14px;
    #                 }
    #             }
    #         </style>
    #     </head>
    #     <body>
    #         <div class="header">
    #             <h1>ICYMI</h1>
    #             <p>Your daily roundup of the most important tech news</p>
    #         </div>
    #     """
    #
    #     for source, items in news_by_source.items():
    #         html += f"<h2>{source}</h2>"
    #         for item in items:
    #             description = item.get('description', 'Click to read more about this story.')
    #             html += f"""
    #                 <div class="news-item">
    #                     <a href="{item['url']}" class="news-title">{item['title']}</a>
    #                     <p class="description">{description}</p>
    #                     <div class="source-badge">{item['source']}</div>
    #                 </div>
    #             """
    #
    #     html += """
    #         <div class="footer">
    #             <p>Thanks for reading!</p>
    #             <div class="management-links">
    #                 <a href="{{preferences_link}}" class="management-link">Manage Preferences</a>
    #                 <a href="{{unsubscribe_link}}" class="management-link unsubscribe">Unsubscribe</a>
    #             </div>
    #             <p style="margin-top: 16px; font-size: 12px;">This email was sent to {{subscriber_email}}</p>
    #         </div>
    #     </body>
    #     </html>
    #     """
    #
    #     return html

    # async def generate_newsletter(self, preferences: Optional[List[str]] = None) -> str:
    #     """Generate HTML newsletter content with compact, modern styling."""
    #     if preferences is None:
    #         preferences = ['Hacker News', 'Reddit', 'Dev.to', 'Stack Exchange', 'GitHub Trending',
    #                        'The Verge', 'Wired', 'Ars Technica', 'VentureBeat', 'ZDNet',
    #                        'TechRadar', 'Hackernoon', 'Science Daily']
    #
    #     all_news = await self.fetch_all_sources(preferences)
    #
    #     # Group news by source
    #     news_by_source = {}
    #     for item in all_news:
    #         if item['source'] not in news_by_source:
    #             news_by_source[item['source']] = []
    #         news_by_source[item['source']].append(item)
    #
    #     # Generate HTML content with compact styling
    #     html = """
    #     <html>
    #     <head>
    #         <meta charset="UTF-8">
    #         <meta name="viewport" content="width=device-width, initial-scale=1.0">
    #         <style>
    #             body {
    #                 font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
    #                 max-width: 650px;
    #                 margin: 0 auto;
    #                 padding: 20px;
    #                 line-height: 1.5;
    #                 color: #1a1a1a;
    #                 background-color: #ffffff;
    #             }
    #             .header {
    #                 text-align: center;
    #                 margin-bottom: 40px;
    #                 padding: 20px 0;
    #             }
    #             .header h1 {
    #                 font-size: 36px;
    #                 font-weight: 700;
    #                 margin: 0;
    #                 letter-spacing: -0.5px;
    #             }
    #             .header p {
    #                 font-size: 16px;
    #                 color: #666;
    #                 margin: 8px 0 0 0;
    #             }
    #             .section {
    #                 margin-bottom: 40px;
    #             }
    #             .section-title {
    #                 font-size: 24px;
    #                 font-weight: 700;
    #                 margin-bottom: 20px;
    #                 padding-bottom: 8px;
    #                 border-bottom: 1px solid #eee;
    #             }
    #             .article {
    #                 margin-bottom: 25px;
    #                 padding-bottom: 25px;
    #                 border-bottom: 1px solid #f0f0f0;
    #             }
    #             .article:last-child {
    #                 border-bottom: none;
    #             }
    #             .article-title {
    #                 font-size: 18px;
    #                 font-weight: 600;
    #                 color: #1a1a1a;
    #                 text-decoration: none;
    #                 line-height: 1.4;
    #                 margin-bottom: 8px;
    #                 display: block;
    #             }
    #             .article-title:hover {
    #                 color: #0066cc;
    #             }
    #             .article-description {
    #                 font-size: 16px;
    #                 color: #666;
    #                 margin: 8px 0;
    #                 line-height: 1.6;
    #             }
    #             .article-meta {
    #                 font-size: 14px;
    #                 color: #888;
    #                 margin-top: 8px;
    #             }
    #             .read-time {
    #                 display: inline-block;
    #                 margin-left: 8px;
    #                 color: #888;
    #             }
    #             .footer {
    #                 margin-top: 40px;
    #                 padding-top: 20px;
    #                 border-top: 1px solid #eee;
    #                 text-align: center;
    #                 color: #666;
    #                 font-size: 14px;
    #             }
    #             .management-links {
    #                 margin: 15px 0;
    #             }
    #             .management-link {
    #                 color: #666;
    #                 text-decoration: none;
    #                 margin: 0 10px;
    #             }
    #             .management-link:hover {
    #                 color: #0066cc;
    #                 text-decoration: underline;
    #             }
    #             @media (max-width: 600px) {
    #                 body {
    #                     padding: 15px;
    #                 }
    #                 .header h1 {
    #                     font-size: 28px;
    #                 }
    #                 .section-title {
    #                     font-size: 20px;
    #                 }
    #                 .article-title {
    #                     font-size: 16px;
    #                 }
    #             }
    #         </style>
    #     </head>
    #     <body>
    #         <div class="header">
    #             <h1>OnePaper</h1>
    #             <p>Your daily roundup of the most important tech news</p>
    #         </div>
    #     """
    #
    #     for source, items in news_by_source.items():
    #         html += f'<div class="section"><h2 class="section-title">{source}</h2>'
    #         for item in items:
    #             description = item.get('description', '')
    #             # Estimate read time based on word count (assuming 200 words per minute)
    #             word_count = len((item['title'] + ' ' + description).split())
    #             read_time = max(1, round(word_count / 200))
    #
    #             html += f"""
    #                 <div class="article">
    #                     <a href="{item['url']}" class="article-title">{item['title']}</a>
    #                     <div class="article-description">{description}</div>
    #                     <div class="article-meta">
    #                         {item['source']}
    #                         <span class="read-time">· {read_time} minute read</span>
    #                     </div>
    #                 </div>
    #             """
    #         html += '</div>'
    #
    #     html += """
    #         <div class="footer">
    #             <div class="management-links">
    #                 <a href="{{preferences_link}}" class="management-link">Preferences</a>
    #                 <a href="{{unsubscribe_link}}" class="management-link">Unsubscribe</a>
    #             </div>
    #             <p style="margin-top: 16px; font-size: 12px;">This email was sent to {{subscriber_email}}</p>
    #         </div>
    #     </body>
    #     </html>
    #     """
    #
    #     return html
    async def generate_newsletter(self, email: str) -> str:
        """Generate an HTML newsletter with categorized tech news."""

        news_articles = await self.fetch_all_sources(email)

        if not news_articles:
            return "<p>No news available today. Check back tomorrow!</p>"

        # Group news by source
        news_by_source = {}
        for article in news_articles:
            if article["source"] not in news_by_source:
                news_by_source[article["source"]] = []
            news_by_source[article["source"]].append(article)

        # Generate HTML content
        html = """
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body { font-family: Arial, sans-serif; max-width: 650px; margin: 0 auto; padding: 20px; color: #333; }
                .header { text-align: center; margin-bottom: 40px; }
                .header h1 { font-size: 36px; font-weight: bold; margin: 0; }
                .section { margin-bottom: 40px; }
                .section-title { font-size: 24px; font-weight: bold; margin-bottom: 10px; border-bottom: 2px solid #ddd; padding-bottom: 5px; }
                .article { margin-bottom: 20px; }
                .article-title { font-size: 18px; font-weight: bold; color: #0073e6; text-decoration: none; }
                .article-title:hover { text-decoration: underline; }
                .article-description { font-size: 16px; color: #666; margin: 8px 0; }
                .article-meta { font-size: 14px; color: #999; }
                .footer { text-align: center; font-size: 14px; color: #777; margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; }
                .unsubscribe { color: red; text-decoration: none; }
            </style>
        </head>
        <body>
            <div class="header">
                <h1>OnePaper</h1>
                <p>Your daily dose of programming & AI news</p>
            </div>
        """

        for source, articles in news_by_source.items():
            html += f'<div class="section"><h2 class="section-title">{source}</h2>'
            for article in articles:
                html += f"""
                    <div class="article">
                        <a href="{article['url']}" class="article-title">{article['title']}</a>
                        <p class="article-description">{article.get('description', '')}</p>
                        <p class="article-meta">Source: {article['source']}</p>
                    </div>
                """
            html += '</div>'

        links = self.get_management_links(email)
        html += f"""
            <div class="footer">
                <p>Enjoyed this newsletter? Share it with friends!</p>
                <p><a href="{links['preferences']}">Manage Preferences</a> | <a href="{links['unsubscribe']}" class="unsubscribe">Unsubscribe</a></p>
            </div>
        </body>
        </html>
        """

        return html

    # async def send_newsletter(self):
    #     """Send newsletter to all subscribers."""
    #     if not self.subscribers:
    #         logger.info("No subscribers to send newsletter to")
    #         return
    #
    #     try:
    #         server = smtplib.SMTP('smtp.gmail.com', 587)
    #         server.starttls()
    #         server.login(self.email_sender, self.email_password)
    #
    #         for email, preferences in self.subscribers.items():
    #             try:
    #                 newsletter_content = await self.generate_newsletter(preferences)
    #                 msg = MIMEMultipart('alternative')
    #                 msg['Subject'] = f"Tech News - {datetime.now().strftime('%Y-%m-%d')}"
    #                 msg['From'] = formataddr((self.sender_name, self.email_sender))
    #                 msg['To'] = email
    #
    #                 links = self.get_management_links(email)
    #
    #                 newsletter_content = newsletter_content.replace("{{unsubscribe_link}}", links['unsubscribe'])
    #                 newsletter_content = newsletter_content.replace("{{preferences_link}}", links['preferences'])
    #                 newsletter_content = newsletter_content.replace("{{subscriber_email}}", email)
    #
    #                 html_part = MIMEText(newsletter_content, 'html')
    #                 msg.attach(html_part)
    #
    #                 server.send_message(msg)
    #                 logger.info(f"Newsletter sent to {email}")
    #             except Exception as e:
    #                 logger.error(f"Error sending newsletter to {email}: {e}")
    #
    #         server.quit()
    #         logger.info("Completed sending newsletters")
    #
    #     except Exception as e:
    #         logger.error(f"Error in SMTP connection: {e}")
    async def send_newsletter(self):
        """Send newsletter to all subscribers."""
        if not self.subscribers:
            logger.info("No subscribers to send newsletter to")
            return

        try:
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(self.email_sender, self.email_password)

            for email, _ in self.subscribers.items():
                try:
                    newsletter_content = await self.generate_newsletter(email)
                    msg = MIMEMultipart('alternative')
                    msg['Subject'] = f"Tech News - {datetime.now().strftime('%Y-%m-%d')}"
                    msg['From'] = formataddr((self.sender_name, self.email_sender))
                    msg['To'] = email

                    links = self.get_management_links(email)

                    newsletter_content = newsletter_content.replace("{{unsubscribe_link}}", links['unsubscribe'])
                    newsletter_content = newsletter_content.replace("{{preferences_link}}", links['preferences'])
                    newsletter_content = newsletter_content.replace("{{subscriber_email}}", email)

                    html_part = MIMEText(newsletter_content, 'html')
                    msg.attach(html_part)

                    server.send_message(msg)
                    logger.info(f"Newsletter sent to {email}")
                except Exception as e:
                    logger.error(f"Error sending newsletter to {email}: {e}")

            server.quit()
            logger.info("Completed sending newsletters")

        except Exception as e:
            logger.error(f"Error in SMTP connection: {e}")
    async def start(self):
        """Initialize and start the aggregator."""
        try:
            # Initialize aiohttp session
            await self.initialize_session()

            # Start the health server
            self.start_health_server()

            # Schedule newsletter to be sent daily at specified time
            schedule_time = os.getenv('NEWSLETTER_TIME', '09:00')
            schedule.every().day.at(schedule_time).do(
                lambda: asyncio.create_task(self.send_newsletter())
            )

            logger.info(f"Newsletter scheduled for {schedule_time} daily")

            # Keep the script running and handle schedules
            while True:
                schedule.run_pending()
                await asyncio.sleep(60)

        except Exception as e:
            logger.error(f"Error in start: {e}")
        finally:
            await self.close_session()

async def main():
    try:

        aggregator = TechNewsAggregator()
        await aggregator.start()
        if not aggregator.subscribers:
            logger.info("No subscribers found.")
            return
        for email in aggregator.subscribers.keys():
            news = await aggregator.fetch_all_sources(email)
            print(f"News for {email}:")
            print(news)
    except Exception as e:
        logger.error(f"Error in main: {e}")


if __name__ == "__main__":
    asyncio.run(main())