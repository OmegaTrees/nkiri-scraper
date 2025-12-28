import requests
from bs4 import BeautifulSoup
import time
import os
import re
from pyrogram import utils
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
import asyncio
from typing import Dict, List
import random
import subprocess
import urllib3
import json
from datetime import datetime

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================================================
# CONFIGURATION
# ============================================================================
API_ID = 22
API_HASH = "82a"
BOT_TOKEN = "79XM"

DOWNLOAD_PATH = "./downloads/"
THUMBNAIL_PATH = "./thumbnails/"
MONITOR_FILE = "./monitor_data.json"

   
def get_peer_type_new(peer_id: int) -> str:
    peer_id_str = str(peer_id)
    if not peer_id_str.startswith("-"):
        return "user"
    elif peer_id_str.startswith("-100"):
        return "channel"
    else:
        return "chat"

utils.get_peer_type = get_peer_type_new

# ============================================================================
# Drama Scraper Class
# ============================================================================
class DramaEpisodeScraper:
    """
    Scrapes drama episodes from thenkiri.com website.
    Handles search, episode extraction, and video file downloads.
    """
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:145.0) Gecko/20100101 Firefox/145.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        })
        self.session.verify = False
        self.base_url = "https://thenkiri.com"
        os.makedirs(DOWNLOAD_PATH, exist_ok=True)
        os.makedirs(THUMBNAIL_PATH, exist_ok=True)
        
    def search_drama(self, search_term):
        """
        Search for drama on the website.
        
        Args:
            search_term (str): Drama name to search for
            
        Returns:
            list: List of search results with title and URL
        """
        try:
            search_url = f"{self.base_url}/?s={search_term}"
            response = self.session.get(search_url, verify=False)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                return self.extract_search_results(soup)
            return []
        except Exception as e:
            print(f"Error searching: {e}")
            return []
    
    def extract_search_results(self, soup):
        """Extract search results from the page"""
        results = []
        selectors = ['article', '.post', '.search-result', '.movie-item', '.drama-item', 'h2 a', 'h3 a']
        
        for selector in selectors:
            items = soup.select(selector)
            if items:
                for i, item in enumerate(items, 1):
                    link_element = item if item.name == 'a' else item.find('a')
                    if link_element and link_element.get('href'):
                        title_element = item.find(['h1', 'h2', 'h3', 'h4']) or link_element
                        title = title_element.get_text(strip=True) if title_element else "Unknown Title"
                        
                        results.append({
                            'number': i,
                            'title': title,
                            'url': link_element.get('href')
                        })
                break
        return results
    
    def scrape_episodes(self, drama_url):
        """
        Scrape episodes from the selected drama page.
        
        Args:
            drama_url (str): URL of the drama page
            
        Returns:
            dict: Dictionary organized by season containing episode lists
        """
        try:
            response = self.session.get(drama_url, verify=False)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            seasons = self.parse_elementor_episodes_by_season(soup)

            # Fallback to movie if no episodes found
            if not seasons or all(len(eps) == 0 for eps in seasons.values()):
                movie = self.extract_movie_download(soup)
                if movie:
                    return {"Movie": [movie]}
            return seasons
        except Exception as e:
            print(f"Error scraping episodes: {e}")
            return {}

    def extract_movie_download(self, soup):
        """Fallback: detect single movie download button."""
        btn = soup.find('a', class_='elementor-button')
        if not btn or not btn.get('href'):
            return None
        
        return {
            'number': 1,
            'title': "Movie Download",
            'download_link': btn.get('href'),
            'season': "Movie"
        }
    
    def parse_elementor_episodes_by_season(self, soup):
        """
        Parse episodes with proper season detection from Elementor containers.
        
        Returns:
            dict: Seasons with their episodes
        """
        seasons = {}
        current_season = None
        detected_season_numbers = []
        
        containers = soup.find_all('div', class_='elementor-container elementor-column-gap-default')
        
        for container in containers:
            headings = container.find_all('h2', class_='elementor-heading-title')
            
            for heading in headings:
                heading_text = heading.get_text(strip=True)
                
                # Check if this is a season heading
                season_match = re.search(r'season\s+(\d+)', heading_text, re.IGNORECASE)
                if season_match:
                    season_num = int(season_match.group(1))
                    current_season = heading_text
                    detected_season_numbers.append(season_num)
                    
                    if current_season not in seasons:
                        seasons[current_season] = []
                
                # Check if this is an episode heading
                elif re.search(r'episode\s+\d+', heading_text, re.IGNORECASE):
                    if current_season is None:
                        current_season = self.infer_current_season(detected_season_numbers)
                    
                    if current_season not in seasons:
                        seasons[current_season] = []
                    
                    download_button = container.find('a', class_='elementor-button')
                    if download_button and download_button.get('href'):
                        episode_number = len(seasons[current_season]) + 1
                        
                        seasons[current_season].append({
                            'number': episode_number,
                            'title': heading_text,
                            'download_link': download_button.get('href'),
                            'season': current_season
                        })
        
        return seasons
    
    def infer_current_season(self, detected_season_numbers):
        """Infer what the current season should be based on detected seasons"""
        if not detected_season_numbers:
            return "Season 1"
        min_season = min(detected_season_numbers)
        return f"Season {min_season}"
    
    def is_direct_video_file(self, url):
        """
        Check if URL points to an actual video file by checking Content-Type.
        
        Args:
            url (str): URL to check
            
        Returns:
            bool: True if URL is a direct video file
        """
        try:
            print(f"Checking if direct video: {url}")
            
            video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v']
            url_lower = url.lower()
            
            has_video_extension = any(ext in url_lower for ext in video_extensions)
            
            if not has_video_extension:
                print(f"No video extension in URL")
                return False
            
            # Check Content-Type header
            head_response = self.session.head(url, verify=False, timeout=10, allow_redirects=True)
            content_type = head_response.headers.get('Content-Type', '').lower()
            content_length = head_response.headers.get('Content-Length', '0')
            
            print(f"Content-Type: {content_type}")
            print(f"Content-Length: {content_length}")
            
            is_video = any(vid_type in content_type for vid_type in ['video/', 'application/octet-stream'])
            is_large = int(content_length) > 1000000  # > 1MB
            
            if is_video and is_large:
                print(f"✅ Confirmed direct video file")
                return True
            else:
                print(f"❌ Not a video file (probably HTML page)")
                return False
                
        except Exception as e:
            print(f"Error checking video file: {e}")
            return False
    
    def download_direct_video(self, url, progress_callback=None):
        """
        Download video file directly from URL with retry mechanism.
        
        Args:
            url (str): Direct video file URL
            progress_callback (callable): Function to call with progress updates
            
        Returns:
            dict: Download result with success status, filepath, and file info
        """
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                if progress_callback:
                    if attempt > 0:
                        progress_callback(f"📥 Retry attempt {attempt + 1}...")
                    else:
                        progress_callback("📥 Direct video download...")
                
                # Extract filename from URL
                filename = url.split('/')[-1].split('?')[0]
                if not filename or '.' not in filename:
                    filename = f"video_{int(time.time())}.mkv"
                
                filename = re.sub(r'[^\w\-_\.]', '_', filename)
                
                # Handle duplicate filenames
                base_name, ext = os.path.splitext(filename)
                counter = 1
                while os.path.exists(os.path.join(DOWNLOAD_PATH, filename)):
                    filename = f"{base_name}_{counter}{ext}"
                    counter += 1
                
                filepath = os.path.join(DOWNLOAD_PATH, filename)
                
                if progress_callback:
                    progress_callback(f"📥 Downloading: {filename}")
                
                print(f"Downloading direct video (attempt {attempt + 1}): {url}")
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': '*/*',
                    'Connection': 'keep-alive',
                }
                
                response = self.session.get(url, headers=headers, stream=True, verify=False, timeout=60)
                response.raise_for_status()
                
                total_size = int(response.headers.get('Content-Length', 0))
                
                # Download with progress tracking
                with open(filepath, 'wb') as f:
                    downloaded = 0
                    last_progress = 0
                    
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            if total_size > 0 and progress_callback:
                                progress = (downloaded / total_size) * 100
                                if int(progress) // 10 > last_progress // 10:
                                    progress_callback(f"📥 Progress: {progress:.1f}%")
                                    last_progress = progress
                
                file_size = os.path.getsize(filepath) / (1024 * 1024)  # MB
                
                print(f"✅ Direct download successful: {filename} ({file_size:.2f} MB)")
                
                return {
                    'success': True,
                    'filepath': filepath,
                    'filename': filename,
                    'size_mb': file_size
                }
                
            except Exception as e:
                print(f"Download attempt {attempt + 1} failed: {e}")
                
                # Clean up partial download
                if 'filepath' in locals() and os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                    except:
                        pass
                
                if attempt < max_retries - 1:
                    time.sleep(3 * (attempt + 1))  # Exponential backoff
                    continue
                
                return {
                    'success': False,
                    'error': str(e),
                    'attempts': max_retries
                }
        
        return None
    
    def extract_and_download(self, page_url, progress_callback=None):
        """
        Smart download handler that detects if URL is direct video or file host page.
        Extracts download link from file host if needed, then downloads the video.
        
        Args:
            page_url (str): URL to download from
            progress_callback (callable): Function for progress updates
            
        Returns:
            dict: Download result with success status and file info
        """
        
        print(f"\n{'='*60}")
        print(f"Processing URL: {page_url}")
        print(f"{'='*60}")
        
        # Check if it's a direct video file
        if self.is_direct_video_file(page_url):
            print("✅ Direct video file detected - downloading...")
            return self.download_direct_video(page_url, progress_callback)
        
        print("📄 File host page detected - extracting download link...")
        
        max_retries = 30
        
        for attempt in range(max_retries):
            try:
                # Extract file ID from URL
                try:
                    url_parts = page_url.split('/')
                    file_id = url_parts[4] if len(url_parts) > 4 else url_parts[3]
                except IndexError:
                    print(f"Failed to extract file ID from URL: {page_url}")
                    return None
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }
                
                # Get the initial page
                try:
                    response = self.session.get(page_url, headers=headers, timeout=30, verify=False)
                    if response.status_code != 200:
                        print(f"Initial page request failed: {response.status_code}")
                        if attempt < max_retries - 1:
                            time.sleep(2 ** attempt)
                            continue
                        return None
                except requests.exceptions.RequestException as e:
                    print(f"Network error on attempt {attempt + 1}: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    return None
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Find the download form
                form = (soup.find('form', {'name': 'F1'}) or 
                       soup.find('form', {'id': 'downloadform'}) or 
                       soup.find('form', action=re.compile(r'downloadwella|dl')) or
                       soup.find('form'))
                
                if not form:
                    print("Download form not found")
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue
                    return None
                
                # Build form data
                form_data = {
                    'op': 'download2',
                    'id': file_id,
                    'rand': '',
                    'referer': '',
                    'method_free': 'Free Download',
                    'method_premium': ''
                }
                
                # Extract hidden form fields
                for input_field in form.find_all('input'):
                    input_type = input_field.get('type', '').lower()
                    name = input_field.get('name')
                    value = input_field.get('value', '')
                    
                    if name and input_type in ['hidden', 'submit']:
                        form_data[name] = value
                
                # Find countdown timer
                countdown_selectors = ['span.seconds', '#countdown', '.countdown', 'span[id*="count"]', 'div[id*="wait"]', '.timer']
                
                wait_time = 0
                for selector in countdown_selectors:
                    countdown = soup.select_one(selector)
                    if countdown:
                        try:
                            countdown_text = countdown.get_text()
                            numbers = re.findall(r'\d+', countdown_text)
                            if numbers:
                                wait_time = int(numbers[0])
                                break
                        except (AttributeError, ValueError):
                            continue
                
                # Fallback: check JavaScript for timer
                if wait_time == 0:
                    scripts = soup.find_all('script')
                    for script in scripts:
                        script_text = script.get_text()
                        if 'countdown' in script_text.lower() or 'timer' in script_text.lower():
                            numbers = re.findall(r'\b(\d+)\b', script_text)
                            for num in numbers:
                                if 5 <= int(num) <= 60:
                                    wait_time = int(num)
                                    break
                            if wait_time > 0:
                                break
                
                # Default wait time if none found
                if wait_time == 0:
                    wait_time = 10
                
                if progress_callback:
                    progress_callback(f"⏳ Waiting {wait_time} seconds (required by site)...")
                
                print(f"Waiting {wait_time} seconds...")
                time.sleep(wait_time + 2)
                
                # Submit the form
                post_headers = {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Origin': 'https://downloadwella.com',
                    'Referer': page_url,
                    'User-Agent': headers['User-Agent'],
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Cache-Control': 'no-cache',
                }
                
                try:
                    post_response = self.session.post(
                        page_url,
                        data=form_data,
                        headers=post_headers,
                        allow_redirects=False,
                        timeout=30,
                        verify=False
                    )
                except requests.exceptions.RequestException as e:
                    print(f"Form submission error: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    return None
                
                download_url = None
                
                # Check for redirect
                if post_response.status_code == 302:
                    download_url = post_response.headers.get('Location')
                    print(f"Redirect found: {download_url}")
                
                # Parse response for download link
                elif post_response.status_code == 200:
                    response_soup = BeautifulSoup(post_response.content, 'html.parser')
                    
                    # Try multiple patterns to find download link
                    download_patterns = [
                        response_soup.find('a', {'id': re.compile(r'download', re.I)}),
                        response_soup.find('a', {'class': re.compile(r'download', re.I)}),
                        response_soup.find('a', string=re.compile(r'download', re.I)),
                        response_soup.find('a', href=re.compile(r'\.(mp4|mkv|avi|mov|wmv|flv|webm)', re.I)),
                        response_soup.find('a', href=re.compile(r'nkiserv\.com|cdn\.|storage\.|files/', re.I)),
                        response_soup.find('a', href=re.compile(r'/d/|/download/|/file/', re.I)),
                        response_soup.find('button', {'onclick': re.compile(r'download|location', re.I)}),
                    ]
                    
                    for pattern in download_patterns:
                        if pattern:
                            if pattern.name == 'button' and pattern.get('onclick'):
                                onclick = pattern.get('onclick')
                                url_match = re.search(r"['\"](https?://[^'\"]+)['\"]", onclick)
                                if url_match:
                                    download_url = url_match.group(1)
                                    break
                            elif pattern.get('href'):
                                download_url = pattern.get('href')
                                break
                    
                    # Fallback: search JavaScript code
                    if not download_url:
                        scripts = response_soup.find_all('script')
                        for script in scripts:
                            script_text = script.get_text()
                            
                            # Look for video file URLs
                            js_urls = re.findall(r'["\']https?://[^"\']*\.(mp4|mkv|avi|mov|wmv)[^"\']*["\']', script_text, re.I)
                            if js_urls:
                                download_url = js_urls[0].strip('"\'')
                                break
                            
                            # Look for CDN/server URLs
                            server_urls = re.findall(r'["\']https?://[^"\']*(?:nkiserv|cdn|storage|files)[^"\']*["\']', script_text, re.I)
                            if server_urls:
                                download_url = server_urls[0].strip('"\'')
                                break
                            
                            # Look for redirect URLs
                            redirect_urls = re.findall(r'location\.(?:href|replace)\s*[=\(]\s*["\']([^"\']+)["\']', script_text)
                            if redirect_urls:
                                download_url = redirect_urls[0]
                                break
                
                else:
                    print(f"Unexpected response status: {post_response.status_code}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    return None
                
                if not download_url:
                    print("No download link found")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    return None
                
                # Normalize URL
                if not download_url.startswith('http'):
                    if download_url.startswith('//'):
                        download_url = 'https:' + download_url
                    elif download_url.startswith('/'):
                        download_url = 'https://downloadwella.com' + download_url
                    else:
                        download_url = 'https://downloadwella.com/' + download_url
                
                print(f"Extracted download URL: {download_url}")
                
                # Verify it's actually a video file
                if not self.is_direct_video_file(download_url):
                    print(f"❌ WARNING: Extracted URL is NOT a video file!")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    return None
                
                return self.download_direct_video(download_url, progress_callback)
                
            except Exception as e:
                print(f"Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return None
        
        print(f"All {max_retries} attempts failed")
        return None

# ============================================================================
# Thumbnail Generator
# ============================================================================
def extract_thumbnail_from_video(video_path, output_path=None):
    """
    Extract a random frame from video as thumbnail using ffmpeg.
    
    Args:
        video_path (str): Path to the video file
        output_path (str, optional): Where to save thumbnail
        
    Returns:
        str: Path to generated thumbnail, or None if failed
    """
    try:
        if output_path is None:
            output_path = os.path.join(THUMBNAIL_PATH, f"thumb_{int(time.time())}.jpg")
        
        # Get video duration
        duration_cmd = [
            'ffprobe', '-v', 'error', '-show_entries',
            'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1',
            video_path
        ]
        
        result = subprocess.run(duration_cmd, capture_output=True, text=True)
        try:
            duration = float(result.stdout.strip())
        except ValueError:
            duration = 60
        
        # Pick random time between 10% and 90% of video
        random_time = random.uniform(duration * 0.1, duration * 0.9)
        
        # Extract frame
        extract_cmd = [
            'ffmpeg', '-ss', str(random_time), '-i', video_path,
            '-vframes', '1', '-q:v', '2', '-y', output_path
        ]
        
        subprocess.run(extract_cmd, capture_output=True, check=True)
        
        if os.path.exists(output_path):
            return output_path
        return None
        
    except Exception as e:
        print(f"Thumbnail extraction failed: {e}")
        return None

# ============================================================================
# Pyrogram Bot
# ============================================================================
app = Client(
    "drama_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

user_sessions: Dict[int, Dict] = {}
user_settings: Dict[int, Dict] = {}
monitor_data: Dict[int, List] = {}

def load_monitor_data():
    """Load monitoring data from JSON file"""
    global monitor_data
    try:
        if os.path.exists(MONITOR_FILE):
            with open(MONITOR_FILE, 'r') as f:
                monitor_data = json.load(f)
                # Convert string keys back to integers
                monitor_data = {int(k): v for k, v in monitor_data.items()}
    except Exception as e:
        print(f"Error loading monitor data: {e}")
        monitor_data = {}

def save_monitor_data():
    """Save monitoring data to JSON file"""
    try:
        with open(MONITOR_FILE, 'w') as f:
            json.dump(monitor_data, f, indent=2)
    except Exception as e:
        print(f"Error saving monitor data: {e}")

def get_user_settings(user_id):
    """
    Get or create user settings with default values.
    Includes upload preferences, thumbnail settings, and channel management.
    
    Args:
        user_id (int): Telegram user ID
        
    Returns:
        dict: User settings dictionary
    """
    if user_id not in user_settings:
        user_settings[user_id] = {
            'upload_as': 'video',
            'use_thumbnail': True,
            'thumbnail_type': 'auto',
            'custom_thumbnail_path': None,
            'monitor_auto_upload': False,
            'saved_channels': [],  # Store channel IDs/usernames
            'default_upload_destination': 'bot'  # 'bot', 'channel', or specific channel
        }
    return user_settings[user_id]

async def get_upload_chat_id(user_id):
    """
    Helper function to get the correct chat ID for uploads.
    Returns either user ID (for bot DM) or channel ID.
    
    Args:
        user_id (int): Telegram user ID
        
    Returns:
        int: Chat ID to upload to
    """
    if user_id in user_sessions and 'upload_destination' in user_sessions[user_id]:
        return user_sessions[user_id]['upload_destination']['id']
    return user_id

scraper = DramaEpisodeScraper()

# ============================================================================
# Bot Commands
# ============================================================================

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """Welcome message with bot overview"""
    await message.reply_text(
        "🎬 **Welcome to Drama Downloader Bot!**\n\n"
        "I can help you search and download drama episodes.\n\n"
        "**Commands:**\n"
        "📺 /search <drama name> - Search for dramas\n"
        "👁️ /monitor - View monitored dramas\n"
        "📺 /channels - Manage upload channels\n"
        "⚙️ /settings - Configure upload preferences\n"
        "📸 /setthumbnail - Set custom thumbnail\n"
        "❓ /help - Show detailed help\n\n"
        "**Quick Start:**\n"
        "`/search squid game`"
    )

@app.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    """Detailed help and current settings"""
    settings = get_user_settings(message.from_user.id)
    
    await message.reply_text(
        "🎬 **Drama Downloader Bot Help**\n\n"
        "**How to use:**\n"
        "1. Search for drama: `/search <name>`\n"
        "2. Select drama from results\n"
        "3. Choose upload destination\n"
        "4. Download or monitor episodes\n"
        "5. Wait for download and upload\n\n"
        "**Commands:**\n"
        "📺 /search <name> - Search dramas\n"
        "👁️ /monitor - View & manage monitored dramas\n"
        "📺 /channels - Manage upload channels\n"
        "⚙️ /settings - Upload settings\n"
        "📸 /setthumbnail - Set custom thumbnail\n"
        "🗑️ /clearthumbnail - Remove custom thumbnail\n"
        "❌ /cancel - Cancel operation\n\n"
        f"**Current Settings:**\n"
        f"Upload as: {settings['upload_as'].title()}\n"
        f"Thumbnail: {settings['thumbnail_type'].title()}\n"
        f"Monitor Auto-Upload: {'✅ Enabled' if settings['monitor_auto_upload'] else '❌ Disabled'}\n"
        f"Saved Channels: {len(settings['saved_channels'])}\n\n"
        "**Monitoring:**\n"
        "Click 'Monitor' button when viewing episodes to track new releases.\n"
        "Bot checks every hour for new episodes.\n\n"
        "**Channel Uploads:**\n"
        "Add channels via /channels to upload directly to them.\n"
        "Make sure the bot is admin in the channel!"
    )

@app.on_message(filters.command("settings"))
async def settings_command(client: Client, message: Message):
    """Upload settings configuration menu"""
    settings = get_user_settings(message.from_user.id)
    
    keyboard = [
        [InlineKeyboardButton(
            f"{'✅' if settings['upload_as'] == 'video' else '☑'} Upload as Video",
            callback_data="set_upload_video"
        )],
        [InlineKeyboardButton(
            f"{'✅' if settings['upload_as'] == 'document' else '☑'} Upload as Document",
            callback_data="set_upload_document"
        )],
        [InlineKeyboardButton(
            f"{'✅' if settings['thumbnail_type'] == 'auto' else '☑'} Auto Thumbnail",
            callback_data="set_thumb_auto"
        )],
        [InlineKeyboardButton(
            f"{'✅' if settings['thumbnail_type'] == 'custom' else '☑'} Custom Thumbnail",
            callback_data="set_thumb_custom"
        )],
        [InlineKeyboardButton(
            f"{'✅' if settings['thumbnail_type'] == 'none' else '☑'} No Thumbnail",
            callback_data="set_thumb_none"
        )],
        [InlineKeyboardButton(
            f"{'✅' if settings['monitor_auto_upload'] else '☑'} Monitor Auto-Upload",
            callback_data="set_monitor_auto"
        )]
    ]
    
    thumb_status = "Not set"
    if settings['thumbnail_type'] == 'custom' and settings['custom_thumbnail_path']:
        thumb_status = "✅ Custom thumbnail set"
    
    await message.reply_text(
        "⚙️ **Upload Settings**\n\n"
        f"**Upload Type:** {settings['upload_as'].title()}\n"
        f"**Thumbnail Mode:** {settings['thumbnail_type'].title()}\n"
        f"**Custom Thumbnail:** {thumb_status}\n"
        f"**Monitor Auto-Upload:** {'✅ Enabled' if settings['monitor_auto_upload'] else '❌ Disabled'}\n\n"
        "Select an option to change:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@app.on_message(filters.command("channels"))
async def manage_channels_command(client: Client, message: Message):
    """Manage saved upload channels"""
    user_id = message.from_user.id
    settings = get_user_settings(user_id)
    
    keyboard = [[InlineKeyboardButton("➕ Add New Channel", callback_data="add_channel")]]
    
    text = "📺 **Saved Channels**\n\n"
    
    if settings['saved_channels']:
        for idx, channel in enumerate(settings['saved_channels']):
            text += f"{idx + 1}. {channel['name']} (`{channel['id']}`)\n"
            keyboard.append([
                InlineKeyboardButton(f"🗑️ Remove: {channel['name']}", callback_data=f"remove_channel_{idx}")
            ])
    else:
        text += "No saved channels yet.\n\n"
    
    text += "\nAdd channels to upload episodes directly to them.\n"
    text += "⚠️ Make sure I'm an admin in the channel!"
    
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

@app.on_message(filters.command("setthumbnail"))
async def set_thumbnail_command(client: Client, message: Message):
    """Initiate custom thumbnail setup"""
    await message.reply_text(
        "📸 **Set Custom Thumbnail**\n\n"
        "Please send me an image (photo) to use as thumbnail.\n\n"
        "The image will be used for all video uploads until you change it."
    )
    
    user_id = message.from_user.id
    if user_id not in user_sessions:
        user_sessions[user_id] = {}
    user_sessions[user_id]['waiting_for_thumbnail'] = True

@app.on_message(filters.command("clearthumbnail"))
async def clear_thumbnail_command(client: Client, message: Message):
    """Remove custom thumbnail and revert to auto mode"""
    settings = get_user_settings(message.from_user.id)
    
    if settings['custom_thumbnail_path'] and os.path.exists(settings['custom_thumbnail_path']):
        os.remove(settings['custom_thumbnail_path'])
    
    settings['custom_thumbnail_path'] = None
    settings['thumbnail_type'] = 'auto'
    
    await message.reply_text("✅ Custom thumbnail cleared! Switched to auto thumbnail mode.")

@app.on_message(filters.command("cancel"))
async def cancel_command(client: Client, message: Message):
    """Cancel current operation"""
    user_id = message.from_user.id
    if user_id in user_sessions:
        del user_sessions[user_id]
        await message.reply_text("✅ Operation cancelled.")
    else:
        await message.reply_text("❌ No active operation to cancel.")

@app.on_message(filters.command("monitor"))
async def monitor_command(client: Client, message: Message):
    """View and manage monitored dramas"""
    user_id = message.from_user.id
    
    if user_id not in monitor_data or not monitor_data[user_id]:
        await message.reply_text(
            "👁️ **No Monitored Dramas**\n\n"
            "You're not monitoring any dramas yet.\n\n"
            "To monitor a drama:\n"
            "1. Use /search to find a drama\n"
            "2. Select it and click 'Monitor' button"
        )
        return
    
    keyboard = []
    text = "👁️ **Monitored Dramas**\n\n"
    
    for idx, drama in enumerate(monitor_data[user_id], 1):
        text += f"{idx}. **{drama['title']}**\n"
        text += f"   Episodes: {drama['episode_count']}\n"
        text += f"   Added: {drama['added_time']}\n\n"
        
        keyboard.append([
            InlineKeyboardButton(
                f"🗑️ Remove: {drama['title'][:30]}",
                callback_data=f"remove_monitor_{idx-1}"
            )
        ])
    
    settings = get_user_settings(user_id)
    text += f"\n**Auto-Upload:** {'✅ Enabled' if settings['monitor_auto_upload'] else '❌ Disabled'}\n"
    text += "Use /settings to toggle auto-upload for new episodes."
    
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

@app.on_message(filters.command("search"))
async def search_command(client: Client, message: Message):
    """
    Search for dramas.
    Usage: /search <drama name>
    """
    user_id = message.from_user.id
    
    command_parts = message.text.split(maxsplit=1)
    if len(command_parts) < 2:
        await message.reply_text("❌ Please provide a drama name.\n\nExample: `/search squid game`")
        return
    
    search_term = command_parts[1].strip()
    
    status_msg = await message.reply_text(f"🔍 Searching for **{search_term}**...")
    
    results = scraper.search_drama(search_term)
    
    if not results:
        await status_msg.edit_text("❌ No results found. Try a different name.")
        return
    
    user_sessions[user_id] = {
        'results': results,
        'search_term': search_term
    }
    
    keyboard = []
    for result in results[:10]:  # Limit to 10 results
        keyboard.append([
            InlineKeyboardButton(
                result['title'][:60],
                callback_data=f"drama_{result['number']}"
            )
        ])
    
    await status_msg.edit_text(
        f"📋 **Search Results for:** {search_term}\n\n"
        f"Found {len(results)} results. Select one:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================================================
# Test Functions
# ============================================================================

@app.on_message(filters.command("testmonitor"))
async def test_monitor_command(client: Client, message: Message):
    """
    Test the monitoring function immediately without waiting.
    Useful for debugging the auto-upload feature.
    """
    user_id = message.from_user.id
    
    if user_id not in monitor_data or not monitor_data[user_id]:
        await message.reply_text("❌ You're not monitoring any dramas. Use /monitor to see your list.")
        return
    
    status_msg = await message.reply_text(
        "🧪 **Testing Monitor Function**\n\n"
        "Checking all monitored dramas now..."
    )
    
    settings = get_user_settings(user_id)
    results = []
    
    for idx, drama in enumerate(monitor_data[user_id], 1):
        try:
            await status_msg.edit_text(
                f"🧪 **Testing Monitor**\n\n"
                f"Checking: {drama['title']}\n"
                f"Progress: {idx}/{len(monitor_data[user_id])}"
            )
            
            # Scrape current episodes
            current_episodes = scraper.scrape_episodes(drama['url'])
            current_total = sum(len(eps) for eps in current_episodes.values())
            
            old_count = drama['episode_count']
            new_count = current_total - old_count
            
            result_text = f"📺 **{drama['title']}**\n"
            result_text += f"   Previous: {old_count} episodes\n"
            result_text += f"   Current: {current_total} episodes\n"
            
            if new_count > 0:
                result_text += f"   🆕 New: {new_count} episodes!\n"
                
                # Auto-upload if enabled
                if settings['monitor_auto_upload']:
                    result_text += f"   📤 Auto-uploading...\n"
                    
                    # Set upload destination
                    if user_id not in user_sessions:
                        user_sessions[user_id] = {}
                    user_sessions[user_id]['upload_destination'] = drama['upload_destination']
                    
                    # Get new episodes
                    all_current = []
                    for season_eps in current_episodes.values():
                        all_current.extend(season_eps)
                    
                    new_episodes = all_current[old_count:]
                    
                    upload_success = 0
                    for episode in new_episodes:
                        success = await download_and_upload_episode(
                            client,
                            message,
                            user_id,
                            episode,
                            silent=True,
                            drama_title=drama['title']
                        )
                        if success:
                            upload_success += 1
                    
                    result_text += f"   ✅ Uploaded: {upload_success}/{new_count}\n"
                    
                    # Update count
                    drama['episode_count'] = current_total
                    save_monitor_data()
                else:
                    result_text += f"   ⚠️ Auto-upload disabled\n"
            else:
                result_text += f"   ✅ No new episodes\n"
            
            results.append(result_text)
            
        except Exception as e:
            results.append(f"❌ **{drama['title']}**\n   Error: {str(e)}\n")
            print(f"Test monitor error for {drama['title']}: {e}")
    
    # Final report
    report = "🧪 **Monitor Test Complete**\n\n"
    report += "\n".join(results)
    report += f"\n\n**Settings:**\n"
    report += f"Auto-Upload: {'✅ Enabled' if settings['monitor_auto_upload'] else '❌ Disabled'}"
    
    await status_msg.edit_text(report)


@app.on_message(filters.command("forcemonitor"))
async def force_monitor_command(client: Client, message: Message):
    """
    Force download the latest episode from each monitored drama.
    Useful for testing if the drama name appears correctly.
    """
    user_id = message.from_user.id
    
    if user_id not in monitor_data or not monitor_data[user_id]:
        await message.reply_text("❌ You're not monitoring any dramas.")
        return
    
    # Show selection menu
    keyboard = []
    for idx, drama in enumerate(monitor_data[user_id]):
        keyboard.append([
            InlineKeyboardButton(
                f"Test: {drama['title'][:40]}",
                callback_data=f"force_test_{idx}"
            )
        ])
    
    await message.reply_text(
        "🧪 **Force Monitor Test**\n\n"
        "Select a drama to test download with correct name:\n"
        "(Will download the latest episode)",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


@app.on_callback_query(filters.regex(r"^force_test_\d+$"))
async def force_test_callback(client: Client, callback_query):
    """Handle force test selection"""
    user_id = callback_query.from_user.id
    idx = int(callback_query.data.split("_")[2])
    
    if user_id not in monitor_data or idx >= len(monitor_data[user_id]):
        await callback_query.answer("❌ Drama not found", show_alert=True)
        return
    
    drama = monitor_data[user_id][idx]
    
    await callback_query.answer()
    status_msg = await callback_query.message.reply_text(
        f"🧪 **Testing with {drama['title']}**\n\n"
        "Fetching latest episode..."
    )
    
    try:
        # Scrape episodes
        episodes = scraper.scrape_episodes(drama['url'])
        
        # Get the last episode
        all_episodes = []
        for season_eps in episodes.values():
            all_episodes.extend(season_eps)
        
        if not all_episodes:
            await status_msg.edit_text("❌ No episodes found")
            return
        
        latest_episode = all_episodes[-1]
        
        await status_msg.edit_text(
            f"🧪 **Testing Download**\n\n"
            f"Drama: {drama['title']}\n"
            f"Episode: {latest_episode['title']}\n\n"
            f"This should show the CORRECT drama name in caption!"
        )
        
        # Set upload destination
        if user_id not in user_sessions:
            user_sessions[user_id] = {}
        user_sessions[user_id]['upload_destination'] = drama['upload_destination']
        
        # Download with drama title
        success = await download_and_upload_episode(
            client,
            callback_query.message,
            user_id,
            latest_episode,
            silent=False,
            drama_title=drama['title']  # This is the key - passing the correct name!
        )
        
        if success:
            await status_msg.edit_text(
                f"✅ **Test Complete!**\n\n"
                f"Check the uploaded video caption.\n"
                f"It should show: **{drama['title']}**"
            )
        else:
            await status_msg.edit_text("❌ Test failed - check error messages above")
            
    except Exception as e:
        await status_msg.edit_text(f"❌ Test error: {str(e)}")
        print(f"Force test error: {e}")


@app.on_message(filters.command("debugsession"))
async def debug_session_command(client: Client, message: Message):
    """
    Debug command to see what's in the user session.
    Shows what drama name would be used for uploads.
    """
    user_id = message.from_user.id
    
    debug_info = "🔍 **Debug Info**\n\n"
    
    # Check user_sessions
    if user_id in user_sessions:
        session = user_sessions[user_id]
        debug_info += "**User Session:**\n"
        if 'drama' in session:
            debug_info += f"Drama: {session['drama']['title']}\n"
        else:
            debug_info += "Drama: Not set\n"
        
        if 'upload_destination' in session:
            debug_info += f"Upload to: {session['upload_destination']['name']}\n"
        else:
            debug_info += "Upload to: Not set\n"
    else:
        debug_info += "**User Session:** Empty\n"
    
    debug_info += "\n**Monitored Dramas:**\n"
    if user_id in monitor_data and monitor_data[user_id]:
        for drama in monitor_data[user_id]:
            debug_info += f"• {drama['title']} ({drama['episode_count']} eps)\n"
    else:
        debug_info += "None\n"
    
    debug_info += "\n**Note:** When auto-uploading, the drama name should come from monitor_data, NOT user_sessions!"
    
    await message.reply_text(debug_info)

# ============================================================================



# ============================================================================
# Photo Handler for Custom Thumbnail
# ============================================================================

@app.on_message(filters.photo)
async def handle_thumbnail_photo(client: Client, message: Message):
    """Handle photo sent for custom thumbnail"""
    user_id = message.from_user.id
    
    if user_id in user_sessions and user_sessions[user_id].get('waiting_for_thumbnail'):
        status = await message.reply_text("⏳ Saving thumbnail...")
        
        photo_path = os.path.join(THUMBNAIL_PATH, f"custom_thumb_{user_id}.jpg")
        await message.download(file_name=photo_path)
        
        settings = get_user_settings(user_id)
        settings['custom_thumbnail_path'] = photo_path
        settings['thumbnail_type'] = 'custom'
        
        user_sessions[user_id]['waiting_for_thumbnail'] = False
        
        await status.edit_text(
            "✅ **Thumbnail saved successfully!**\n\n"
            "This thumbnail will be used for all video uploads.\n"
            "You can change it anytime with /setthumbnail"
        )

# ============================================================================
# Text Handler for Channel Input
# ============================================================================

@app.on_message(filters.text & ~filters.command(["start", "help", "search", "settings", "monitor", "setthumbnail", "clearthumbnail", "cancel", "channels"]))
async def handle_channel_input(client: Client, message: Message):
    """Handle text input for channel username/ID"""
    if not message.from_user:
        return
    user_id = message.from_user.id
    
    if user_id not in user_sessions or not user_sessions[user_id].get('waiting_for_channel'):
        return
    
    channel_input = message.text.strip()
    
    try:
        # Verify channel exists and bot has access
        chat = await client.get_chat(channel_input)
        
        settings = get_user_settings(user_id)
        
        channel_data = {
            'id': chat.id,
            'name': chat.title or channel_input
        }
        
        action = user_sessions[user_id].get('channel_action')
        
        if action:
            # Channel added for immediate use
            user_sessions[user_id]['upload_destination'] = {
                'type': 'channel',
                'id': channel_data['id'],
                'name': channel_data['name']
            }
            user_sessions[user_id]['waiting_for_channel'] = False
            
            await message.reply_text(f"✅ Will upload to: {channel_data['name']}")
            
            # Continue with the action (download_all or monitor)
            if action == "all":
                callback_query = type('obj', (object,), {
                    'message': message,
                    'from_user': message.from_user
                })()
                await download_all_episodes(client, callback_query)
            else:
                callback_query = type('obj', (object,), {
                    'message': message,
                    'from_user': message.from_user,
                    'answer': lambda *args, **kwargs: None
                })()
                await add_to_monitor(client, callback_query)
        else:
            # Channel added to saved list
            if not any(ch['id'] == channel_data['id'] for ch in settings['saved_channels']):
                settings['saved_channels'].append(channel_data)
                await message.reply_text(f"✅ Channel added: {channel_data['name']}")
            else:
                await message.reply_text(f"⚠️ Channel already saved: {channel_data['name']}")
            
            user_sessions[user_id]['waiting_for_channel'] = False
    
    except Exception as e:
        await message.reply_text(
            f"❌ **Error accessing channel**\n\n"
            f"Error: {str(e)}\n\n"
            f"Make sure:\n"
            f"• The channel exists\n"
            f"• I'm added as admin\n"
            f"• The ID/username is correct"
        )

# ============================================================================
# Callback Query Handlers
# ============================================================================

@app.on_callback_query(filters.regex(r"^set_"))
async def handle_settings(client: Client, callback_query):
    """Handle settings toggle buttons"""
    user_id = callback_query.from_user.id
    settings = get_user_settings(user_id)
    action = callback_query.data
    
    if action == "set_upload_video":
        settings['upload_as'] = 'video'
    elif action == "set_upload_document":
        settings['upload_as'] = 'document'
    elif action == "set_thumb_auto":
        settings['thumbnail_type'] = 'auto'
    elif action == "set_thumb_custom":
        if not settings['custom_thumbnail_path']:
            await callback_query.answer("❌ No custom thumbnail set. Use /setthumbnail first.", show_alert=True)
            return
        settings['thumbnail_type'] = 'custom'
    elif action == "set_thumb_none":
        settings['thumbnail_type'] = 'none'
    elif action == "set_monitor_auto":
        settings['monitor_auto_upload'] = not settings['monitor_auto_upload']
    
    await callback_query.answer("✅ Setting updated!")
    
    # Rebuild keyboard with updated checkmarks
    keyboard = [
        [InlineKeyboardButton(
            f"{'✅' if settings['upload_as'] == 'video' else '☑'} Upload as Video",
            callback_data="set_upload_video"
        )],
        [InlineKeyboardButton(
            f"{'✅' if settings['upload_as'] == 'document' else '☑'} Upload as Document",
            callback_data="set_upload_document"
        )],
        [InlineKeyboardButton(
            f"{'✅' if settings['thumbnail_type'] == 'auto' else '☑'} Auto Thumbnail",
            callback_data="set_thumb_auto"
        )],
        [InlineKeyboardButton(
            f"{'✅' if settings['thumbnail_type'] == 'custom' else '☑'} Custom Thumbnail",
            callback_data="set_thumb_custom"
        )],
        [InlineKeyboardButton(
            f"{'✅' if settings['thumbnail_type'] == 'none' else '☑'} No Thumbnail",
            callback_data="set_thumb_none"
        )],
        [InlineKeyboardButton(
            f"{'✅' if settings['monitor_auto_upload'] else '☑'} Monitor Auto-Upload",
            callback_data="set_monitor_auto"
        )]
    ]
    
    thumb_status = "Not set"
    if settings['thumbnail_type'] == 'custom' and settings['custom_thumbnail_path']:
        thumb_status = "✅ Custom thumbnail set"
    
    await callback_query.message.edit_text(
        "⚙️ **Upload Settings**\n\n"
        f"**Upload Type:** {settings['upload_as'].title()}\n"
        f"**Thumbnail Mode:** {settings['thumbnail_type'].title()}\n"
        f"**Custom Thumbnail:** {thumb_status}\n"
        f"**Monitor Auto-Upload:** {'✅ Enabled' if settings['monitor_auto_upload'] else '❌ Disabled'}\n\n"
        "Select an option to change:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@app.on_callback_query(filters.regex(r"^add_channel$"))
async def add_channel_callback(client: Client, callback_query):
    """Initiate channel addition process"""
    user_id = callback_query.from_user.id
    
    if user_id not in user_sessions:
        user_sessions[user_id] = {}
    user_sessions[user_id]['waiting_for_channel'] = True
    
    await callback_query.message.edit_text(
        "📺 **Add Channel**\n\n"
        "Please send the channel username or ID.\n\n"
        "Format:\n"
        "• `@channelname`\n"
        "• `-1001234567890`\n\n"
        "Make sure to add me as admin to the channel first!"
    )
    await callback_query.answer()

@app.on_callback_query(filters.regex(r"^remove_channel_\d+$"))
async def remove_channel_callback(client: Client, callback_query):
    """Remove a saved channel"""
    user_id = callback_query.from_user.id
    settings = get_user_settings(user_id)
    
    idx = int(callback_query.data.split("_")[2])
    
    if idx < len(settings['saved_channels']):
        removed = settings['saved_channels'].pop(idx)
        await callback_query.answer(f"✅ Removed {removed['name']}")
        
        # Rebuild channel list
        keyboard = [[InlineKeyboardButton("➕ Add New Channel", callback_data="add_channel")]]
        
        text = "📺 **Saved Channels**\n\n"
        
        if settings['saved_channels']:
            for idx, channel in enumerate(settings['saved_channels']):
                text += f"{idx + 1}. {channel['name']} (`{channel['id']}`)\n"
                keyboard.append([
                    InlineKeyboardButton(f"🗑️ Remove: {channel['name']}", callback_data=f"remove_channel_{idx}")
                ])
        else:
            text += "No saved channels yet.\n\n"
        
        text += "\nAdd channels to upload episodes directly to them."
        
        await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

@app.on_callback_query(filters.regex(r"^drama_\d+$"))
async def drama_selected(client: Client, callback_query):
    """Handle drama selection from search results"""
    user_id = callback_query.from_user.id
    
    if user_id not in user_sessions or 'results' not in user_sessions[user_id]:
        await callback_query.answer("❌ Session expired. Please search again.", show_alert=True)
        return
    
    drama_number = int(callback_query.data.split("_")[1])
    results = user_sessions[user_id]['results']
    
    selected_drama = None
    for result in results:
        if result['number'] == drama_number:
            selected_drama = result
            break
    
    if not selected_drama:
        await callback_query.answer("❌ Invalid selection.", show_alert=True)
        return
    
    await callback_query.message.edit_text("⏳ Loading episodes...")
    
    episodes = scraper.scrape_episodes(selected_drama['url'])
    
    if not episodes:
        await callback_query.message.edit_text("❌ No episodes found for this drama.")
        return
    
    user_sessions[user_id]['drama'] = selected_drama
    user_sessions[user_id]['episodes'] = episodes
    
    # Ask user where to upload
    keyboard = [
        [InlineKeyboardButton("📤 Upload to Bot (DM)", callback_data="upload_dest_bot")],
        [InlineKeyboardButton("📺 Select Channel", callback_data="upload_dest_channel")],
    ]
    
    settings = get_user_settings(user_id)
    if settings['saved_channels']:
        keyboard.append([InlineKeyboardButton("📺 Use Saved Channel", callback_data="upload_dest_saved")])
    
    await callback_query.message.edit_text(
        f"📺 **{selected_drama['title']}**\n\n"
        f"Found {sum(len(eps) for eps in episodes.values())} episodes\n\n"
        "**Where do you want to upload?**",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    await callback_query.answer()

@app.on_callback_query(filters.regex(r"^upload_dest_"))
async def upload_destination(client: Client, callback_query):
    """Handle upload destination selection"""
    user_id = callback_query.from_user.id
    action = callback_query.data.replace("upload_dest_", "")
    
    if action == "bot":
        user_sessions[user_id]['upload_destination'] = {
            'type': 'bot',
            'id': user_id,
            'name': 'Bot DM'
        }
        await show_episode_menu(client, callback_query)
    
    elif action == "channel":
        await callback_query.message.edit_text(
            "📺 **Enter Channel**\n\n"
            "Send the channel username or ID:\n\n"
            "Format:\n"
            "• `@channelname`\n"
            "• `-1001234567890`\n\n"
            "Make sure I'm an admin in the channel!"
        )
        user_sessions[user_id]['waiting_for_channel'] = True
        user_sessions[user_id]['channel_action'] = None
    
    elif action == "saved":
        settings = get_user_settings(user_id)
        keyboard = []
        
        for idx, channel in enumerate(settings['saved_channels']):
            keyboard.append([
                InlineKeyboardButton(
                    channel['name'],
                    callback_data=f"use_saved_channel_{idx}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("« Back", callback_data="back_to_dest")])
        
        await callback_query.message.edit_text(
            "📺 **Select Channel**\n\nChoose from your saved channels:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    await callback_query.answer()

@app.on_callback_query(filters.regex(r"^use_saved_channel_\d+$"))
async def use_saved_channel(client: Client, callback_query):
    """Use a saved channel as upload destination"""
    user_id = callback_query.from_user.id
    settings = get_user_settings(user_id)
    
    idx = int(callback_query.data.split("_")[-1])
    
    if idx < len(settings['saved_channels']):
        channel = settings['saved_channels'][idx]
        user_sessions[user_id]['upload_destination'] = {
            'type': 'channel',
            'id': channel['id'],
            'name': channel['name']
        }
        await show_episode_menu(client, callback_query)
    
    await callback_query.answer()

async def show_episode_menu(client: Client, callback_query):
    """Display episode selection menu with seasons"""
    user_id = callback_query.from_user.id
    episodes = user_sessions[user_id]['episodes']
    drama = user_sessions[user_id]['drama']
    dest = user_sessions[user_id]['upload_destination']
    
    keyboard = []
    
    # Add season buttons
    for season_name in sorted(episodes.keys()):
        ep_count = len(episodes[season_name])
        keyboard.append([
            InlineKeyboardButton(
                f"{season_name} ({ep_count} episodes)",
                callback_data=f"season_{list(episodes.keys()).index(season_name)}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("📥 Download All Episodes", callback_data="download_all")])
    keyboard.append([InlineKeyboardButton("👁️ Monitor for New Episodes", callback_data="monitor_drama")])
    
    await callback_query.message.edit_text(
        f"📺 **{drama['title']}**\n"
        f"📤 Uploading to: **{dest['name']}**\n\n"
        f"Total Episodes: {sum(len(eps) for eps in episodes.values())}\n\n"
        "Select a season or action:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    await callback_query.answer()

@app.on_callback_query(filters.regex(r"^season_\d+$"))
async def season_selected(client: Client, callback_query):
    """Show episodes for selected season"""
    user_id = callback_query.from_user.id
    season_idx = int(callback_query.data.split("_")[1])
    
    episodes = user_sessions[user_id]['episodes']
    season_name = list(episodes.keys())[season_idx]
    season_episodes = episodes[season_name]
    
    keyboard = []
    
    # Show first 10 episodes
    for ep in season_episodes[:10]:
        keyboard.append([
            InlineKeyboardButton(
                f"Episode {ep['number']}: {ep['title'][:40]}",
                callback_data=f"episode_{season_name}_{ep['number']}"
            )
        ])
    
    if len(season_episodes) > 10:
        keyboard.append([InlineKeyboardButton("➡️ More Episodes", callback_data=f"season_page_{season_idx}_1")])
    
    keyboard.append([InlineKeyboardButton(f"📥 Download All ({len(season_episodes)} eps)", callback_data=f"download_season_{season_idx}")])
    keyboard.append([InlineKeyboardButton("« Back", callback_data="back_to_seasons")])
    
    await callback_query.message.edit_text(
        f"📺 **{season_name}**\n\n"
        f"Episodes: {len(season_episodes)}\n\n"
        "Select an episode:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    await callback_query.answer()

@app.on_callback_query(filters.regex(r"^episode_"))
async def episode_selected(client: Client, callback_query):
    """Download selected episode"""
    user_id = callback_query.from_user.id
    
    parts = callback_query.data.split("_")
    season_name = "_".join(parts[1:-1])
    episode_num = int(parts[-1])
    
    episodes = user_sessions[user_id]['episodes']
    episode = None
    
    for ep in episodes[season_name]:
        if ep['number'] == episode_num:
            episode = ep
            break
    
    if not episode:
        await callback_query.answer("❌ Episode not found", show_alert=True)
        return
    
    await callback_query.answer()
    await download_and_upload_episode(client, callback_query.message, user_id, episode)

@app.on_callback_query(filters.regex(r"^download_all$"))
async def download_all_callback(client: Client, callback_query):
    """Download all episodes"""
    await callback_query.answer()
    await download_all_episodes(client, callback_query)

@app.on_callback_query(filters.regex(r"^download_season_\d+$"))
async def download_season_callback(client: Client, callback_query):
    """Download all episodes from selected season"""
    user_id = callback_query.from_user.id
    season_idx = int(callback_query.data.split("_")[2])
    
    episodes = user_sessions[user_id]['episodes']
    season_name = list(episodes.keys())[season_idx]
    season_episodes = episodes[season_name]
    
    await callback_query.answer()
    
    status_msg = await callback_query.message.reply_text(
        f"📥 **Starting Download**\n\n"
        f"Season: {season_name}\n"
        f"Episodes: {len(season_episodes)}\n\n"
        f"Progress: 0/{len(season_episodes)}"
    )
    
    for idx, episode in enumerate(season_episodes, 1):
        await status_msg.edit_text(
            f"📥 **Downloading**\n\n"
            f"Season: {season_name}\n"
            f"Progress: {idx}/{len(season_episodes)}\n\n"
            f"Current: Episode {episode['number']}"
        )
        
        await download_and_upload_episode(client, callback_query.message, user_id, episode, silent=True)
    
    await status_msg.edit_text(
        f"✅ **Download Complete!**\n\n"
        f"Season: {season_name}\n"
        f"Downloaded: {len(season_episodes)} episodes"
    )

@app.on_callback_query(filters.regex(r"^monitor_drama$"))
async def monitor_drama_callback(client: Client, callback_query):
    """Add drama to monitoring"""
    await callback_query.answer()
    await add_to_monitor(client, callback_query)

@app.on_callback_query(filters.regex(r"^remove_monitor_\d+$"))
async def remove_monitor_callback(client: Client, callback_query):
    """Remove drama from monitoring"""
    user_id = callback_query.from_user.id
    idx = int(callback_query.data.split("_")[2])
    
    if user_id in monitor_data and idx < len(monitor_data[user_id]):
        removed = monitor_data[user_id].pop(idx)
        save_monitor_data()
        
        await callback_query.answer(f"✅ Removed: {removed['title']}")
        
        # Refresh monitor list
        if not monitor_data[user_id]:
            await callback_query.message.edit_text(
                "👁️ **No Monitored Dramas**\n\n"
                "You're not monitoring any dramas."
            )
        else:
            keyboard = []
            text = "👁️ **Monitored Dramas**\n\n"
            
            for idx, drama in enumerate(monitor_data[user_id], 1):
                text += f"{idx}. **{drama['title']}**\n"
                text += f"   Episodes: {drama['episode_count']}\n\n"
                
                keyboard.append([
                    InlineKeyboardButton(
                        f"🗑️ Remove: {drama['title'][:30]}",
                        callback_data=f"remove_monitor_{idx-1}"
                    )
                ])
            
            await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

@app.on_callback_query(filters.regex(r"^back_to_"))
async def back_navigation(client: Client, callback_query):
    """Handle back button navigation"""
    action = callback_query.data.replace("back_to_", "")
    
    if action == "seasons":
        await show_episode_menu(client, callback_query)
    elif action == "dest":
        await drama_selected(client, callback_query)
    
    await callback_query.answer()

# ============================================================================
# Download & Upload Functions
# ============================================================================

async def download_and_upload_episode(client: Client, message: Message, user_id: int, episode: dict, silent: bool = False, drama_title: str = None):
    """
    Download episode and upload to Telegram.
    
    Args:
        client: Pyrogram client
        message: Message object to reply to
        user_id: Telegram user ID
        episode: Episode dict with download link
        silent: If True, suppress individual status messages
        drama_title: Optional drama title override (for auto-uploads)
        
    Returns:
        bool: True if successful, False otherwise
    """
    
    settings = get_user_settings(user_id)
    chat_id = await get_upload_chat_id(user_id)
    
    if not silent:
        status_msg = await message.reply_text(f"📥 Starting download: {episode['title']}")
    
    progress_updates = []
    
    def progress_callback(update):
        progress_updates.append(update)
    
    # Download the video
    result = scraper.extract_and_download(episode['download_link'], progress_callback)
    
    if not result or not result.get('success'):
        error_msg = f"❌ Download failed: {episode['title']}"
        if not silent:
            await status_msg.edit_text(error_msg)
        else:
            await message.reply_text(error_msg)
        return False
    
    filepath = result['filepath']
    filename = result['filename']
    
    if not silent:
        await status_msg.edit_text(f"✅ Downloaded!\n📤 Uploading to Telegram...")
    
    # Get thumbnail
    thumb_path = None
    if settings['thumbnail_type'] == 'auto':
        thumb_path = extract_thumbnail_from_video(filepath)
    elif settings['thumbnail_type'] == 'custom':
        thumb_path = settings['custom_thumbnail_path']
    
    # Upload to Telegram
    try:
        caption = f"**{episode['title']}**\n\n"
        
        # Use provided drama_title (for auto-uploads) or session data (for manual downloads)
        if drama_title:
            caption += f"Drama: {drama_title}\n"
        elif user_id in user_sessions and 'drama' in user_sessions[user_id]:
            caption += f"Drama: {user_sessions[user_id]['drama']['title']}\n"
        
        caption += f"\n"
        if 'season' in episode:
            caption += f"Season: {episode['season']}\n"
        caption += f"Episode: {episode['number']}\n"
        caption += f"Size: {result['size_mb']:.2f} MB | @kdramahype"
        
        if settings['upload_as'] == 'video':
            await client.send_video(
                chat_id=chat_id,
                video=filepath,
                caption=caption,
                thumb=thumb_path,
                supports_streaming=True
            )
        else:
            await client.send_document(
                chat_id=chat_id,
                document=filepath,
                caption=caption,
                thumb=thumb_path
            )
        
        if not silent:
            await status_msg.edit_text(f"✅ Upload complete: {episode['title']}")
        
        # Cleanup
        if os.path.exists(filepath):
            os.remove(filepath)
        if thumb_path and settings['thumbnail_type'] == 'auto' and os.path.exists(thumb_path):
            os.remove(thumb_path)
        
        return True
        
    except Exception as e:
        error_msg = f"❌ Upload failed: {str(e)}"
        if not silent:
            await status_msg.edit_text(error_msg)
        else:
            await message.reply_text(error_msg)
        
        # Cleanup
        if os.path.exists(filepath):
            os.remove(filepath)
        
        return False




async def download_all_episodes(client: Client, callback_query):
    """Download all episodes from all seasons"""
    user_id = callback_query.from_user.id
    episodes = user_sessions[user_id]['episodes']
    drama = user_sessions[user_id]['drama']
    
    all_episodes = []
    for season_episodes in episodes.values():
        all_episodes.extend(season_episodes)
    
    total = len(all_episodes)
    
    status_msg = await callback_query.message.reply_text(
        f"📥 **Downloading All Episodes**\n\n"
        f"Drama: {drama['title']}\n"
        f"Total: {total} episodes\n\n"
        f"Progress: 0/{total}"
    )
    
    success_count = 0
    
    for idx, episode in enumerate(all_episodes, 1):
        await status_msg.edit_text(
            f"📥 **Downloading**\n\n"
            f"Drama: {drama['title']}\n"
            f"Progress: {idx}/{total}\n"
            f"Success: {success_count}/{idx-1}\n\n"
            f"Current: {episode['title']}"
        )
        
        success = await download_and_upload_episode(
            client, 
            callback_query.message, 
            user_id, 
            episode, 
            silent=True
        )
        
        if success:
            success_count += 1
    
    await status_msg.edit_text(
        f"✅ **Download Complete!**\n\n"
        f"Drama: {drama['title']}\n"
        f"Total: {total} episodes\n"
        f"Successful: {success_count}\n"
        f"Failed: {total - success_count}"
    )

async def add_to_monitor(client: Client, callback_query):
    """Add drama to monitoring list"""
    user_id = callback_query.from_user.id
    drama = user_sessions[user_id]['drama']
    episodes = user_sessions[user_id]['episodes']
    dest = user_sessions[user_id]['upload_destination']
    
    # Initialize monitor data for user
    if user_id not in monitor_data:
        monitor_data[user_id] = []
    
    # Check if already monitoring
    for monitored in monitor_data[user_id]:
        if monitored['url'] == drama['url']:
            await callback_query.message.reply_text("⚠️ You're already monitoring this drama!")
            return
    
    total_episodes = sum(len(eps) for eps in episodes.values())
    
    monitor_entry = {
        'title': drama['title'],
        'url': drama['url'],
        'episode_count': total_episodes,
        'upload_destination': dest,
        'added_time': datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    
    monitor_data[user_id].append(monitor_entry)
    save_monitor_data()
    
    await callback_query.message.reply_text(
        f"✅ **Monitoring Added**\n\n"
        f"Drama: {drama['title']}\n"
        f"Current Episodes: {total_episodes}\n"
        f"Upload to: {dest['name']}\n\n"
        f"I'll check for new episodes every hour."
    )

# ============================================================================
# Background Monitoring Task
# ============================================================================

async def check_monitored_dramas():
    """Background task to check for new episodes in monitored dramas"""
    while True:
        try:
            await asyncio.sleep(3600)  # Check every hour
            
            for user_id, dramas in monitor_data.items():
                settings = get_user_settings(user_id)
                
                for drama in dramas:
                    try:
                        # Scrape current episodes
                        current_episodes = scraper.scrape_episodes(drama['url'])
                        current_total = sum(len(eps) for eps in current_episodes.values())
                        
                        # Check if new episodes found
                        if current_total > drama['episode_count']:
                            new_count = current_total - drama['episode_count']
                            
                            await app.send_message(
                                user_id,
                                f"🆕 **New Episodes Detected!**\n\n"
                                f"Drama: {drama['title']}\n"
                                f"New Episodes: {new_count}\n"
                                f"Total Now: {current_total}"
                            )
                            
                            # Auto-download if enabled
                            if settings['monitor_auto_upload']:
                                # Temporarily set upload destination from monitor data
                                if user_id not in user_sessions:
                                    user_sessions[user_id] = {}
                                user_sessions[user_id]['upload_destination'] = drama['upload_destination']
                                
                                # Get new episodes
                                all_current = []
                                for season_eps in current_episodes.values():
                                    all_current.extend(season_eps)
                                
                                new_episodes = all_current[drama['episode_count']:]
                                
                                for episode in new_episodes:
                                    await download_and_upload_episode(
                                        app,
                                        await app.send_message(user_id, "Processing..."),
                                        user_id,
                                        episode,
                                        silent=True,
                                        drama_title=drama['title']  # Pass the correct drama title!
                                    )
                            
                            # Update count
                            drama['episode_count'] = current_total
                            save_monitor_data()
                    
                    except Exception as e:
                        print(f"Error checking drama {drama['title']}: {e}")
                        continue
        
        except Exception as e:
            print(f"Monitor task error: {e}")
            await asyncio.sleep(300)  # Wait 5 minutes on error

# ============================================================================
# Bot Startup & Shutdown
# ============================================================================

@app.on_disconnect()
async def on_disconnect(client):
    """Save data on disconnect"""
    save_monitor_data()
    print("Bot disconnected - data saved")

if __name__ == "__main__":
    print("🎬 Drama Downloader Bot Starting...")
    print(f"Download Path: {DOWNLOAD_PATH}")
    print(f"Thumbnail Path: {THUMBNAIL_PATH}")
    
    # Load saved monitoring data
    load_monitor_data()
    print(f"Loaded {sum(len(dramas) for dramas in monitor_data.values())} monitored dramas")
    
    # Start monitoring background task
    asyncio.get_event_loop().create_task(check_monitored_dramas())
    
    print("✅ Bot is running!\n")
    app.run()
