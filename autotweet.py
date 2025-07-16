import os
import random
import tweepy
import requests
from bs4 import BeautifulSoup
import sys
import tempfile

# Konfigurasi
TWEETS_FILE = 'tweets_media.txt'
MAX_TWEET_LENGTH = 250  # Disisakan space untuk URL
TRENDING_LIMIT = 2
DEBUG_MODE = os.getenv('DEBUG_MODE', 'false').lower() == 'true'
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'

class TwitterBot:
    def __init__(self):
        self.client = self.authenticate()
        self.api_v1 = self.authenticate_v1()
        
    def authenticate(self):
        """Autentikasi dengan Twitter API v2"""
        try:
            return tweepy.Client(
                consumer_key=os.getenv('TWITTER_API_KEY'),
                consumer_secret=os.getenv('TWITTER_API_SECRET'),
                access_token=os.getenv('TWITTER_ACCESS_TOKEN'),
                access_token_secret=os.getenv('TWITTER_ACCESS_TOKEN_SECRET')
            )
        except Exception as e:
            print(f"❌ Auth error (v2): {str(e)}")
            sys.exit(1)
    
    def authenticate_v1(self):
        """Autentikasi dengan Twitter API v1.1 (untuk upload media)"""
        try:
            auth = tweepy.OAuthHandler(
                os.getenv('TWITTER_API_KEY'),
                os.getenv('TWITTER_API_SECRET')
            )
            auth.set_access_token(
                os.getenv('TWITTER_ACCESS_TOKEN'),
                os.getenv('TWITTER_ACCESS_TOKEN_SECRET')
            )
            return tweepy.API(auth)
        except Exception as e:
            print(f"❌ Auth error (v1.1): {str(e)}")
            return None

    def download_media(self, url):
        """Download media dari URL ke temporary file"""
        try:
            headers = {'User-Agent': USER_AGENT}
            response = requests.get(url, headers=headers, stream=True, timeout=15)
            response.raise_for_status()
            
            # Deteksi ekstensi file
            content_type = response.headers.get('content-type', '')
            ext = '.jpg'  # Default
            if 'png' in content_type:
                ext = '.png'
            elif 'gif' in content_type:
                ext = '.gif'
                
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp_file:
                for chunk in response.iter_content(chunk_size=8192):
                    tmp_file.write(chunk)
                return tmp_file.name
        except Exception as e:
            print(f"⚠️ Media download error: {str(e)}")
            return None

    def parse_tweets_file(self):
        """Baca file dan parse menjadi list dict (text, media, url)"""
        tweets = []
        try:
            with open(TWEETS_FILE, 'r', encoding='utf-8') as f:
                current_tweet = {}
                for line in f:
                    line = line.strip()
                    if line.startswith('text:'):
                        current_tweet['text'] = line[5:].strip()
                    elif line.startswith('media:'):
                        current_tweet['media'] = line[6:].strip().split(',')
                    elif line.startswith('url:'):
                        current_tweet['url'] = line[4:].strip()
                    elif line == '---':
                        if current_tweet:
                            tweets.append(current_tweet)
                        current_tweet = {}
                
                if current_tweet:
                    tweets.append(current_tweet)
                    
            if not tweets:
                raise ValueError("No valid tweets found")
            return tweets
        except Exception as e:
            print(f"❌ Error parsing tweets: {str(e)}")
            sys.exit(1)

    def get_twitter_trends(self):
        """Scraping trending topics dari Twitter Indonesia"""
        try:
            url = "https://trends24.in/indonesia/"
            headers = {'User-Agent': USER_AGENT}
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            trends = []
            
            for item in soup.select('.trend-card__list a'):
                text = item.get_text(strip=True)
                if text.startswith(('#', '@')):
                    trends.append(text)
            
            return trends[:5] if trends else ['#Indonesia', '@TwitterID']
        except Exception as e:
            print(f"⚠️ Trends error: {str(e)}")
            return ['#Trending', '@Twitter']

    def compose_tweet(self, base_text, media_links, target_url):
        """Buat tweet dengan text + trending + URL tujuan"""
        # Tambahkan trending hashtag/mention
        trends = self.get_twitter_trends()
        tweet_text = base_text
        
        if trends:
            available_space = MAX_TWEET_LENGTH - len(tweet_text) - len(target_url) - 2
            if available_space > 10:
                for tag in trends:
                    if len(tag) <= available_space:
                        tweet_text += f" {tag}"
                        available_space -= len(tag) + 1
        
        # Tambahkan URL di akhir tweet
        tweet_text += f" {target_url}"
        
        # Pilih media random jika ada
        media_id = None
        if media_links:
            random_media = random.choice(media_links)
            if media_path := self.download_media(random_media.strip()):
                media_id = self.upload_media(media_path)
        
        if DEBUG_MODE:
            print(f"✏️ Final text: {tweet_text}")
            print(f"📷 Media ID: {media_id}")
            print(f"🔗 Target URL: {target_url}")
        
        return tweet_text, media_id

    def upload_media(self, media_path):
        """Upload media ke Twitter"""
        if not self.api_v1:
            return None
            
        try:
            media = self.api_v1.media_upload(media_path)
            return media.media_id_string
        except Exception as e:
            print(f"⚠️ Media upload error: {str(e)}")
            return None
        finally:
            try:
                os.unlink(media_path)
            except:
                pass

    def post_tweet(self):
        """Posting tweet dengan gambar dan URL tujuan"""
        tweets = self.parse_tweets_file()
        selected_tweet = random.choice(tweets)
        
        base_text = selected_tweet.get('text', '')
        media_links = selected_tweet.get('media', [])
        target_url = selected_tweet.get('url', '')
        
        if not target_url:
            print("❌ No target URL specified")
            return False
            
        tweet_text, media_id = self.compose_tweet(base_text, media_links, target_url)
        
        try:
            if DEBUG_MODE:
                print("🔧 DEBUG MODE - Simulating tweet:")
                print(f"Text: {tweet_text}")
                print(f"Media: {'Yes' if media_id else 'No'}")
                print(f"URL: {target_url}")
                return True
                
            # Pastikan URL muncul di text tweet untuk memicu Twitter Card
            if target_url not in tweet_text:
                tweet_text += f" {target_url}"
                
            if media_id:
                response = self.client.create_tweet(
                    text=tweet_text,
                    media_ids=[media_id]
                )
            else:
                response = self.client.create_tweet(
                    text=tweet_text
                )
                
            print(f"✅ Tweet posted! ID: {response.data['id']}")
            return True
            
        except tweepy.errors.TweepyException as e:
            print(f"❌ Twitter error: {str(e)}")
            return False
        except Exception as e:
            print(f"❌ Unexpected error: {str(e)}")
            return False

if __name__ == "__main__":
    print("\n=== 🚀 Twitter Bot with Clickable Media ===")
    bot = TwitterBot()
    
    if bot.post_tweet():
        print("✅ Success")
        sys.exit(0)
    else:
        print("❌ Failed")
        sys.exit(1)
