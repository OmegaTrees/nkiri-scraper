import requests
from bs4 import BeautifulSoup
import time
import os
import re
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
API_ID = 25
API_HASH = "8"
BOT_TOKEN = ""

DOWNLOAD_PATH = "./downloads/"
THUMBNAIL_PATH = "./thumbnails/"
MONITOR_FILE = "./monitor_data.json"

# ============================================================================
# Drama Scraper Class
# ============================================================================
class DramaEpisodeScraper:
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
        """Search for drama on the website"""
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
        """Scrape episodes from the selected drama page"""
        try:
            response = self.session.get(drama_url, verify=False)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            seasons = self.parse_elementor_episodes_by_season(soup)

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
        """Parse episodes with proper season detection"""
        seasons = {}
        current_season = None
        detected_season_numbers = []
        
        containers = soup.find_all('div', class_='elementor-container elementor-column-gap-default')
        
        for container in containers:
            headings = container.find_all('h2', class_='elementor-heading-title')
            
            for heading in headings:
                heading_text = heading.get_text(strip=True)
                
                season_match = re.search(r'season\s+(\d+)', heading_text, re.IGNORECASE)
                if season_match:
                    season_num = int(season_match.group(1))
                    current_season = heading_text
                    detected_season_numbers.append(season_num)
                    
                    if current_season not in seasons:
                        seasons[current_season] = []
                
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
        """Infer what the current season should be"""
        if not detected_season_numbers:
            return "Season 1"
        min_season = min(detected_season_numbers)
        return f"Season {min_season}"
    
    def is_direct_video_file(self, url):
        """Check if URL points to an actual video file by checking Content-Type"""
        try:
            print(f"Checking if direct video: {url}")
            
            video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v']
            url_lower = url.lower()
            
            has_video_extension = any(ext in url_lower for ext in video_extensions)
            
            if not has_video_extension:
                print(f"No video extension in URL")
                return False
            
            head_response = self.session.head(url, verify=False, timeout=10, allow_redirects=True)
            content_type = head_response.headers.get('Content-Type', '').lower()
            content_length = head_response.headers.get('Content-Length', '0')
            
            print(f"Content-Type: {content_type}")
            print(f"Content-Length: {content_length}")
            
            is_video = any(vid_type in content_type for vid_type in ['video/', 'application/octet-stream'])
            is_large = int(content_length) > 1000000
            
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
        """Download video file directly from URL with retry mechanism"""
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                if progress_callback:
                    if attempt > 0:
                        progress_callback(f"📥 Retry attempt {attempt + 1}...")
                    else:
                        progress_callback("📥 Direct video download...")
                
                filename = url.split('/')[-1].split('?')[0]
                if not filename or '.' not in filename:
                    filename = f"video_{int(time.time())}.mkv"
                
                filename = re.sub(r'[^\w\-_\.]', '_', filename)
                
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
                
                file_size = os.path.getsize(filepath) / (1024 * 1024)
                
                print(f"✅ Direct download successful: {filename} ({file_size:.2f} MB)")
                
                return {
                    'success': True,
                    'filepath': filepath,
                    'filename': filename,
                    'size_mb': file_size
                }
                
            except Exception as e:
                print(f"Download attempt {attempt + 1} failed: {e}")
                
                if 'filepath' in locals() and os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                    except:
                        pass
                
                if attempt < max_retries - 1:
                    time.sleep(3 * (attempt + 1))
                    continue
                
                return {
                    'success': False,
                    'error': str(e),
                    'attempts': max_retries
                }
        
        return None
    
    def extract_and_download(self, page_url, progress_callback=None):
        """Smart download handler with proper video detection"""
        
        print(f"\n{'='*60}")
        print(f"Processing URL: {page_url}")
        print(f"{'='*60}")
        
        if self.is_direct_video_file(page_url):
            print("✅ Direct video file detected - downloading...")
            return self.download_direct_video(page_url, progress_callback)
        
        print("📄 File host page detected - extracting download link...")
        
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
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
                
                form_data = {
                    'op': 'download2',
                    'id': file_id,
                    'rand': '',
                    'referer': '',
                    'method_free': 'Free Download',
                    'method_premium': ''
                }
                
                for input_field in form.find_all('input'):
                    input_type = input_field.get('type', '').lower()
                    name = input_field.get('name')
                    value = input_field.get('value', '')
                    
                    if name and input_type in ['hidden', 'submit']:
                        form_data[name] = value
                
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
                
                if wait_time == 0:
                    wait_time = 10
                
                if progress_callback:
                    progress_callback(f"⏳ Waiting {wait_time} seconds (required by site)...")
                
                print(f"Waiting {wait_time} seconds...")
                time.sleep(wait_time + 2)
                
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
                
                if post_response.status_code == 302:
                    download_url = post_response.headers.get('Location')
                    print(f"Redirect found: {download_url}")
                
                elif post_response.status_code == 200:
                    response_soup = BeautifulSoup(post_response.content, 'html.parser')
                    
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
                    
                    if not download_url:
                        scripts = response_soup.find_all('script')
                        for script in scripts:
                            script_text = script.get_text()
                            
                            js_urls = re.findall(r'["\']https?://[^"\']*\.(mp4|mkv|avi|mov|wmv)[^"\']*["\']', script_text, re.I)
                            if js_urls:
                                download_url = js_urls[0].strip('"\'')
                                break
                            
                            server_urls = re.findall(r'["\']https?://[^"\']*(?:nkiserv|cdn|storage|files)[^"\']*["\']', script_text, re.I)
                            if server_urls:
                                download_url = server_urls[0].strip('"\'')
                                break
                            
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
                
                if not download_url.startswith('http'):
                    if download_url.startswith('//'):
                        download_url = 'https:' + download_url
                    elif download_url.startswith('/'):
                        download_url = 'https://downloadwella.com' + download_url
                    else:
                        download_url = 'https://downloadwella.com/' + download_url
                
                print(f"Extracted download URL: {download_url}")
                
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
    """Extract a random frame from video as thumbnail using ffmpeg"""
    try:
        if output_path is None:
            output_path = os.path.join(THUMBNAIL_PATH, f"thumb_{int(time.time())}.jpg")
        
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
        
        random_time = random.uniform(duration * 0.1, duration * 0.9)
        
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
    """Load monitoring data from file"""
    global monitor_data
    try:
        if os.path.exists(MONITOR_FILE):
            with open(MONITOR_FILE, 'r') as f:
                monitor_data = json.load(f)
                monitor_data = {int(k): v for k, v in monitor_data.items()}
    except Exception as e:
        print(f"Error loading monitor data: {e}")
        monitor_data = {}

def save_monitor_data():
    """Save monitoring data to file"""
    try:
        with open(MONITOR_FILE, 'w') as f:
            json.dump(monitor_data, f, indent=2)
    except Exception as e:
        print(f"Error saving monitor data: {e}")

def get_user_settings(user_id):
    if user_id not in user_settings:
        user_settings[user_id] = {
            'upload_as': 'video',
            'use_thumbnail': True,
            'thumbnail_type': 'auto',
            'custom_thumbnail_path': None,
            'monitor_auto_upload': False
        }
    return user_settings[user_id]

scraper = DramaEpisodeScraper()

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    await message.reply_text(
        "🎬 **Welcome to Drama Downloader Bot!**\n\n"
        "I can help you search and download drama episodes.\n\n"
        "**Commands:**\n"
        "📺 /search <drama name> - Search for dramas\n"
        "👁️ /monitor - View monitored dramas\n"
        "⚙️ /settings - Configure upload preferences\n"
        "📸 /setthumbnail - Set custom thumbnail\n"
        "❓ /help - Show detailed help\n\n"
        "**Quick Start:**\n"
        "`/search squid game`"
    )

@app.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    settings = get_user_settings(message.from_user.id)
    
    await message.reply_text(
        "🎬 **Drama Downloader Bot Help**\n\n"
        "**How to use:**\n"
        "1. Search for drama: `/search <name>`\n"
        "2. Select drama from results\n"
        "3. Choose to download or monitor\n"
        "4. Wait for download and upload\n\n"
        "**Commands:**\n"
        "📺 /search <name> - Search dramas\n"
        "👁️ /monitor - View & manage monitored dramas\n"
        "⚙️ /settings - Upload settings\n"
        "📸 /setthumbnail - Set custom thumbnail\n"
        "🗑️ /clearthumbnail - Remove custom thumbnail\n"
        "❌ /cancel - Cancel operation\n\n"
        f"**Current Settings:**\n"
        f"Upload as: {settings['upload_as'].title()}\n"
        f"Thumbnail: {settings['thumbnail_type'].title()}\n"
        f"Monitor Auto-Upload: {'✅ Enabled' if settings['monitor_auto_upload'] else '❌ Disabled'}\n\n"
        "**Monitoring:**\n"
        "Click 'Monitor' button when viewing episodes to track new releases.\n"
        "Bot checks every hour for new episodes."
    )

@app.on_message(filters.command("settings"))
async def settings_command(client: Client, message: Message):
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

@app.on_message(filters.command("setthumbnail"))
async def set_thumbnail_command(client: Client, message: Message):
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
    settings = get_user_settings(message.from_user.id)
    
    if settings['custom_thumbnail_path'] and os.path.exists(settings['custom_thumbnail_path']):
        os.remove(settings['custom_thumbnail_path'])
    
    settings['custom_thumbnail_path'] = None
    settings['thumbnail_type'] = 'auto'
    
    await message.reply_text("✅ Custom thumbnail cleared! Switched to auto thumbnail mode.")

@app.on_message(filters.photo)
async def handle_thumbnail_photo(client: Client, message: Message):
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

@app.on_callback_query(filters.regex(r"^set_"))
async def handle_settings(client: Client, callback_query):
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

@app.on_message(filters.command("cancel"))
async def cancel_command(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id in user_sessions:
        del user_sessions[user_id]
        await message.reply_text("✅ Operation cancelled.")
    else:
        await message.reply_text("❌ No active operation to cancel.")

@app.on_message(filters.command("monitor"))
async def monitor_command(client: Client, message: Message):
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
    for result in results[:10]:
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

@app.on_callback_query(filters.regex(r"^drama_\d+$"))
async def drama_selected(client: Client, callback_query):
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
        await callback_query.answer("❌ Drama not found.", show_alert=True)
        return
    
    await callback_query.message.edit_text(f"⏳ Loading episodes for **{selected_drama['title']}**...")
    
    seasons = scraper.scrape_episodes(selected_drama['url'])
    
    if not seasons:
        await callback_query.message.edit_text("❌ No episodes found.")
        return
    
    all_episodes = []
    episode_number = 1
    
    for season_name in sorted(seasons.keys()):
        for episode in seasons[season_name]:
            episode['global_number'] = episode_number
            episode['display_title'] = f"{season_name} - {episode['title']}"
            all_episodes.append(episode)
            episode_number += 1
    
    user_sessions[user_id]['episodes'] = all_episodes
    user_sessions[user_id]['drama_title'] = selected_drama['title']
    user_sessions[user_id]['drama_url'] = selected_drama['url']
    
    keyboard = [[
        InlineKeyboardButton("📥 Download All Episodes", callback_data="download_all")
    ], [
        InlineKeyboardButton("👁️ Monitor for New Episodes", callback_data="add_monitor")
    ]]
    
    for i in range(0, min(len(all_episodes), 50), 5):
        row = []
        for episode in all_episodes[i:i+5]:
            row.append(
                InlineKeyboardButton(
                    f"Ep {episode['global_number']}",
                    callback_data=f"ep_{episode['global_number']}"
                )
            )
        keyboard.append(row)
    
    episode_list = "\n".join([
        f"{ep['global_number']}. {ep['display_title']}"
        for ep in all_episodes[:15]
    ])
    
    if len(all_episodes) > 15:
        episode_list += f"\n... and {len(all_episodes) - 15} more"
    
    await callback_query.message.edit_text(
        f"📺 **{selected_drama['title']}**\n\n"
        f"Found {len(all_episodes)} episodes:\n\n"
        f"{episode_list}\n\n"
        f"📥 Download all, monitor for new episodes, or select individual episode:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@app.on_callback_query(filters.regex(r"^add_monitor$"))
async def add_to_monitor(client: Client, callback_query):
    user_id = callback_query.from_user.id
    
    if user_id not in user_sessions or 'episodes' not in user_sessions[user_id]:
        await callback_query.answer("❌ Session expired. Please search again.", show_alert=True)
        return
    
    drama_title = user_sessions[user_id].get('drama_title', 'Unknown')
    drama_url = user_sessions[user_id].get('drama_url', '')
    episode_count = len(user_sessions[user_id]['episodes'])
    
    if user_id not in monitor_data:
        monitor_data[user_id] = []
    
    for drama in monitor_data[user_id]:
        if drama['url'] == drama_url:
            await callback_query.answer("⚠️ Already monitoring this drama!", show_alert=True)
            return
    
    monitor_data[user_id].append({
        'title': drama_title,
        'url': drama_url,
        'episode_count': episode_count,
        'added_time': datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    
    save_monitor_data()
    
    await callback_query.answer("✅ Drama added to monitoring!")
    await callback_query.message.reply_text(
        f"✅ **Monitoring Added**\n\n"
        f"**Drama:** {drama_title}\n"
        f"**Current Episodes:** {episode_count}\n\n"
        f"I'll check for new episodes every hour and notify you.\n"
        f"Use /monitor to manage your monitored dramas."
    )

@app.on_callback_query(filters.regex(r"^remove_monitor_\d+$"))
async def remove_from_monitor(client: Client, callback_query):
    user_id = callback_query.from_user.id
    
    if user_id not in monitor_data or not monitor_data[user_id]:
        await callback_query.answer("❌ No monitored dramas found.", show_alert=True)
        return
    
    idx = int(callback_query.data.split("_")[2])
    
    if idx >= len(monitor_data[user_id]):
        await callback_query.answer("❌ Drama not found.", show_alert=True)
        return
    
    removed_drama = monitor_data[user_id].pop(idx)
    save_monitor_data()
    
    await callback_query.answer(f"✅ Removed {removed_drama['title']}")
    
    if not monitor_data[user_id]:
        await callback_query.message.edit_text(
            "👁️ **No Monitored Dramas**\n\n"
            "You're not monitoring any dramas.\n\n"
            "Use /search to find and monitor new dramas."
        )
    else:
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
        text += "Use /settings to toggle auto-upload."
        
        await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

@app.on_callback_query(filters.regex(r"^download_all$"))
async def download_all_episodes(client: Client, callback_query):
    user_id = callback_query.from_user.id
    
    if user_id not in user_sessions or 'episodes' not in user_sessions[user_id]:
        await callback_query.answer("❌ Session expired. Please search again.", show_alert=True)
        return
    
    episodes = user_sessions[user_id]['episodes']
    drama_title = user_sessions[user_id].get('drama_title', 'Drama')
    
    await callback_query.answer("⏳ Starting batch download...")
    
    status_msg = await callback_query.message.edit_text(
        f"📥 **Downloading All Episodes**\n\n"
        f"**Drama:** {drama_title}\n"
        f"**Total Episodes:** {len(episodes)}\n"
        f"**Progress:** 0/{len(episodes)}\n\n"
        f"⏳ Starting..."
    )
    
    settings = get_user_settings(user_id)
    successful = 0
    failed = 0
    skipped = 0
    
    for idx, episode in enumerate(episodes, 1):
        try:
            await status_msg.edit_text(
                f"📥 **Downloading All Episodes**\n\n"
                f"**Drama:** {drama_title}\n"
                f"**Total Episodes:** {len(episodes)}\n"
                f"**Progress:** {idx}/{len(episodes)}\n"
                f"**✅ Success:** {successful} | **❌ Failed:** {failed} | **⏭️ Skipped:** {skipped}\n\n"
                f"⏳ Current: {episode['display_title']}"
            )
            
            result = scraper.extract_and_download(episode['download_link'])
            
            if not result or not result.get('success'):
                retry_keyboard = [
                    [InlineKeyboardButton("🔄 Retry", callback_data=f"retry_{idx}")],
                    [InlineKeyboardButton("⏭️ Skip", callback_data=f"skip_{idx}")],
                    [InlineKeyboardButton("❌ Cancel All", callback_data="cancel_batch")]
                ]
                
                error_msg = result.get('error', 'Unknown error') if result else 'Download failed'
                
                await status_msg.edit_text(
                    f"❌ **Download Failed**\n\n"
                    f"**Episode:** {episode['display_title']}\n"
                    f"**Error:** {error_msg}\n\n"
                    f"**Progress:** {idx}/{len(episodes)}\n"
                    f"**✅ Success:** {successful} | **❌ Failed:** {failed} | **⏭️ Skipped:** {skipped}\n\n"
                    f"What would you like to do?",
                    reply_markup=InlineKeyboardMarkup(retry_keyboard)
                )
                
                user_sessions[user_id]['batch_state'] = {
                    'current_idx': idx,
                    'episode': episode,
                    'successful': successful,
                    'failed': failed,
                    'skipped': skipped,
                    'total': len(episodes),
                    'drama_title': drama_title
                }
                
                return
            
            thumbnail_path = None
            
            if settings['upload_as'] == 'video' and settings['thumbnail_type'] != 'none':
                if settings['thumbnail_type'] == 'custom' and settings['custom_thumbnail_path']:
                    thumbnail_path = settings['custom_thumbnail_path']
                elif settings['thumbnail_type'] == 'auto':
                    thumbnail_path = extract_thumbnail_from_video(result['filepath'])
            
            if settings['upload_as'] == 'video':
                await client.send_video(
                    chat_id=callback_query.message.chat.id,
                    video=result['filepath'],
                    caption=f"🎬 {episode['display_title']}\n📦 {result['size_mb']:.2f} MB | @kdramahype",
                    thumb=thumbnail_path,
                    supports_streaming=True
                )
            else:
                await client.send_document(
                    chat_id=callback_query.message.chat.id,
                    document=result['filepath'],
                    caption=f"🎬 {episode['display_title']}\n📦 {result['size_mb']:.2f} MB | @kdramahype"
                )
            
            successful += 1
            
            if os.path.exists(result['filepath']):
                os.remove(result['filepath'])
            if thumbnail_path and thumbnail_path != settings['custom_thumbnail_path']:
                if os.path.exists(thumbnail_path):
                    os.remove(thumbnail_path)
            
            await asyncio.sleep(2)
            
        except Exception as e:
            print(f"Error processing episode {idx}: {e}")
            failed += 1
            continue
    
    await status_msg.edit_text(
        f"✅ **Batch Download Complete!**\n\n"
        f"**Drama:** {drama_title}\n"
        f"**Total Episodes:** {len(episodes)}\n"
        f"**✅ Successful:** {successful}\n"
        f"**❌ Failed:** {failed}\n"
        f"**⏭️ Skipped:** {skipped}"
    )

@app.on_callback_query(filters.regex(r"^(retry|skip)_\d+$"))
async def handle_batch_retry_skip(client: Client, callback_query):
    user_id = callback_query.from_user.id
    
    if user_id not in user_sessions or 'batch_state' not in user_sessions[user_id]:
        await callback_query.answer("❌ Session expired.", show_alert=True)
        return
    
    action, _ = callback_query.data.split('_', 1)
    batch_state = user_sessions[user_id]['batch_state']
    
    if action == "retry":
        await callback_query.answer("🔄 Retrying download...")
        
        result = scraper.extract_and_download(batch_state['episode']['download_link'])
        
        if result and result.get('success'):
            settings = get_user_settings(user_id)
            
            thumbnail_path = None
            if settings['upload_as'] == 'video' and settings['thumbnail_type'] != 'none':
                if settings['thumbnail_type'] == 'custom' and settings['custom_thumbnail_path']:
                    thumbnail_path = settings['custom_thumbnail_path']
                elif settings['thumbnail_type'] == 'auto':
                    thumbnail_path = extract_thumbnail_from_video(result['filepath'])
            
            if settings['upload_as'] == 'video':
                await client.send_video(
                    chat_id=callback_query.message.chat.id,
                    video=result['filepath'],
                    caption=f"🎬 {batch_state['episode']['display_title']}\n📦 {result['size_mb']:.2f} MB | @kdramahype",
                    thumb=thumbnail_path,
                    supports_streaming=True
                )
            else:
                await client.send_document(
                    chat_id=callback_query.message.chat.id,
                    document=result['filepath'],
                    caption=f"🎬 {batch_state['episode']['display_title']}\n📦 {result['size_mb']:.2f} MB | @kdramahype"
                )
            
            batch_state['successful'] += 1
            
            if os.path.exists(result['filepath']):
                os.remove(result['filepath'])
            if thumbnail_path and thumbnail_path != settings['custom_thumbnail_path']:
                if os.path.exists(thumbnail_path):
                    os.remove(thumbnail_path)
        else:
            batch_state['failed'] += 1
    
    elif action == "skip":
        await callback_query.answer("⏭️ Skipping episode...")
        batch_state['skipped'] += 1
    
    await continue_batch_download(client, callback_query, user_id)

@app.on_callback_query(filters.regex(r"^cancel_batch$"))
async def cancel_batch_download(client: Client, callback_query):
    user_id = callback_query.from_user.id
    
    if user_id in user_sessions and 'batch_state' in user_sessions[user_id]:
        batch_state = user_sessions[user_id]['batch_state']
        
        await callback_query.message.edit_text(
            f"❌ **Batch Download Cancelled**\n\n"
            f"**Drama:** {batch_state['drama_title']}\n"
            f"**Progress:** {batch_state['current_idx']}/{batch_state['total']}\n"
            f"**✅ Successful:** {batch_state['successful']}\n"
            f"**❌ Failed:** {batch_state['failed']}\n"
            f"**⏭️ Skipped:** {batch_state['skipped']}"
        )
        
        del user_sessions[user_id]['batch_state']
    
    await callback_query.answer("❌ Batch download cancelled.")

async def continue_batch_download(client: Client, callback_query, user_id):
    """Continue batch download from where it left off"""
    if user_id not in user_sessions or 'batch_state' not in user_sessions[user_id]:
        return
    
    batch_state = user_sessions[user_id]['batch_state']
    episodes = user_sessions[user_id]['episodes']
    settings = get_user_settings(user_id)
    
    for idx in range(batch_state['current_idx'], len(episodes)):
        episode = episodes[idx]
        
        try:
            await callback_query.message.edit_text(
                f"📥 **Downloading All Episodes**\n\n"
                f"**Drama:** {batch_state['drama_title']}\n"
                f"**Total Episodes:** {batch_state['total']}\n"
                f"**Progress:** {idx + 1}/{batch_state['total']}\n"
                f"**✅ Success:** {batch_state['successful']} | **❌ Failed:** {batch_state['failed']} | **⏭️ Skipped:** {batch_state['skipped']}\n\n"
                f"⏳ Current: {episode['display_title']}"
            )
            
            result = scraper.extract_and_download(episode['download_link'])
            
            if not result or not result.get('success'):
                retry_keyboard = [
                    [InlineKeyboardButton("🔄 Retry", callback_data=f"retry_{idx + 1}")],
                    [InlineKeyboardButton("⏭️ Skip", callback_data=f"skip_{idx + 1}")],
                    [InlineKeyboardButton("❌ Cancel All", callback_data="cancel_batch")]
                ]
                
                error_msg = result.get('error', 'Unknown error') if result else 'Download failed'
                
                await callback_query.message.edit_text(
                    f"❌ **Download Failed Again**\n\n"
                    f"**Episode:** {episode['display_title']}\n"
                    f"**Error:** {error_msg}\n\n"
                    f"**Progress:** {idx + 1}/{batch_state['total']}\n"
                    f"**✅ Success:** {batch_state['successful']} | **❌ Failed:** {batch_state['failed']} | **⏭️ Skipped:** {batch_state['skipped']}\n\n"
                    f"What would you like to do?",
                    reply_markup=InlineKeyboardMarkup(retry_keyboard)
                )
                
                batch_state['current_idx'] = idx + 1
                batch_state['episode'] = episode
                return
            
            thumbnail_path = None
            
            if settings['upload_as'] == 'video' and settings['thumbnail_type'] != 'none':
                if settings['thumbnail_type'] == 'custom' and settings['custom_thumbnail_path']:
                    thumbnail_path = settings['custom_thumbnail_path']
                elif settings['thumbnail_type'] == 'auto':
                    thumbnail_path = extract_thumbnail_from_video(result['filepath'])
            
            if settings['upload_as'] == 'video':
                await client.send_video(
                    chat_id=callback_query.message.chat.id,
                    video=result['filepath'],
                    caption=f"🎬 {episode['display_title']}\n📦 {result['size_mb']:.2f} MB | @kdramahype",
                    thumb=thumbnail_path,
                    supports_streaming=True
                )
            else:
                await client.send_document(
                    chat_id=callback_query.message.chat.id,
                    document=result['filepath'],
                    caption=f"🎬 {episode['display_title']}\n📦 {result['size_mb']:.2f} MB | @kdramahype"
                )
            
            batch_state['successful'] += 1
            
            if os.path.exists(result['filepath']):
                os.remove(result['filepath'])
            if thumbnail_path and thumbnail_path != settings['custom_thumbnail_path']:
                if os.path.exists(thumbnail_path):
                    os.remove(thumbnail_path)
            
            await asyncio.sleep(2)
            
        except Exception as e:
            print(f"Error processing episode {idx + 1}: {e}")
            batch_state['failed'] += 1
            continue
    
    await callback_query.message.edit_text(
        f"✅ **Batch Download Complete!**\n\n"
        f"**Drama:** {batch_state['drama_title']}\n"
        f"**Total Episodes:** {batch_state['total']}\n"
        f"**✅ Successful:** {batch_state['successful']}\n"
        f"**❌ Failed:** {batch_state['failed']}\n"
        f"**⏭️ Skipped:** {batch_state['skipped']}"
    )
    
    if 'batch_state' in user_sessions[user_id]:
        del user_sessions[user_id]['batch_state']

@app.on_callback_query(filters.regex(r"^ep_\d+$"))
async def download_single_episode(client: Client, callback_query):
    user_id = callback_query.from_user.id
    
    if user_id not in user_sessions or 'episodes' not in user_sessions[user_id]:
        await callback_query.answer("❌ Session expired. Please search again.", show_alert=True)
        return
    
    episode_number = int(callback_query.data.split("_")[1])
    episodes = user_sessions[user_id]['episodes']
    
    selected_episode = None
    for episode in episodes:
        if episode['global_number'] == episode_number:
            selected_episode = episode
            break
    
    if not selected_episode:
        await callback_query.answer("❌ Episode not found.", show_alert=True)
        return
    
    await callback_query.answer("⏳ Starting download...")
    
    status_msg = await callback_query.message.edit_text(
        f"📥 **Downloading Episode**\n\n"
        f"**Episode:** {selected_episode['display_title']}\n"
        f"⏳ Extracting download link..."
    )
    
    async def progress_callback(message):
        try:
            await status_msg.edit_text(
                f"📥 **Downloading Episode**\n\n"
                f"**Episode:** {selected_episode['display_title']}\n"
                f"{message}"
            )
        except:
            pass
    
    max_retries = 3
    attempt = 0
    
    while attempt < max_retries:
        result = scraper.extract_and_download(selected_episode['download_link'], progress_callback)
        
        if result and result.get('success'):
            break
        
        attempt += 1
        
        if attempt < max_retries:
            retry_keyboard = [
                [InlineKeyboardButton("🔄 Retry", callback_data=f"retry_single_{episode_number}")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_single")]
            ]
            
            error_msg = result.get('error', 'Unknown error') if result else 'Download failed'
            
            await status_msg.edit_text(
                f"❌ **Download Failed (Attempt {attempt}/{max_retries})**\n\n"
                f"**Episode:** {selected_episode['display_title']}\n"
                f"**Error:** {error_msg}\n\n"
                f"Would you like to retry?",
                reply_markup=InlineKeyboardMarkup(retry_keyboard)
            )
            return
    
    if not result or not result.get('success'):
        await status_msg.edit_text(
            f"❌ **Download Failed**\n\n"
            f"**Episode:** {selected_episode['display_title']}\n"
            f"**Error:** {result.get('error', 'Unknown error') if result else 'All attempts failed'}\n\n"
            f"Please try again later or report this issue."
        )
        return
    
    await status_msg.edit_text(
        f"📤 **Uploading Episode**\n\n"
        f"**Episode:** {selected_episode['display_title']}\n"
        f"**Size:** {result['size_mb']:.2f} MB\n"
        f"⏳ Uploading to Telegram..."
    )
    
    settings = get_user_settings(user_id)
    thumbnail_path = None
    
    if settings['upload_as'] == 'video' and settings['thumbnail_type'] != 'none':
        if settings['thumbnail_type'] == 'custom' and settings['custom_thumbnail_path']:
            thumbnail_path = settings['custom_thumbnail_path']
        elif settings['thumbnail_type'] == 'auto':
            thumbnail_path = extract_thumbnail_from_video(result['filepath'])
    
    try:
        if settings['upload_as'] == 'video':
            await client.send_video(
                chat_id=callback_query.message.chat.id,
                video=result['filepath'],
                caption=f"🎬 {selected_episode['display_title']}\n📦 {result['size_mb']:.2f} MB | @kdramahype",
                thumb=thumbnail_path,
                supports_streaming=True
            )
        else:
            await client.send_document(
                chat_id=callback_query.message.chat.id,
                document=result['filepath'],
                caption=f"🎬 {selected_episode['display_title']}\n📦 {result['size_mb']:.2f} MB | @kdramahype"
            )
        
        await status_msg.edit_text(
            f"✅ **Upload Complete!**\n\n"
            f"**Episode:** {selected_episode['display_title']}\n"
            f"**Size:** {result['size_mb']:.2f} MB | @kdramahype"
        )
    
    except Exception as e:
        await status_msg.edit_text(
            f"❌ **Upload Failed**\n\n"
            f"**Episode:** {selected_episode['display_title']}\n"
            f"**Error:** {str(e)}"
        )
    
    finally:
        if os.path.exists(result['filepath']):
            os.remove(result['filepath'])
        if thumbnail_path and thumbnail_path != settings['custom_thumbnail_path']:
            if os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)

@app.on_callback_query(filters.regex(r"^retry_single_\d+$"))
async def retry_single_episode(client: Client, callback_query):
    episode_number = int(callback_query.data.split("_")[2])
    
    callback_query.data = f"ep_{episode_number}"
    await download_single_episode(client, callback_query)

@app.on_callback_query(filters.regex(r"^cancel_single$"))
async def cancel_single_download(client: Client, callback_query):
    await callback_query.message.edit_text("❌ **Download Cancelled**")
    await callback_query.answer("❌ Download cancelled.")

# ============================================================================
# Background Monitoring Task
# ============================================================================
async def start_monitoring_task():
    """Start the monitoring task after bot initialization"""
    await asyncio.sleep(5)
    asyncio.create_task(check_monitored_dramas())

async def check_monitored_dramas():
    """Background task that checks for new episodes every hour"""
    await asyncio.sleep(60)
    
    while True:
        try:
            print("🔍 Checking monitored dramas for new episodes...")
            
            for user_id, dramas in list(monitor_data.items()):
                for drama in dramas:
                    try:
                        seasons = scraper.scrape_episodes(drama['url'])
                        
                        if not seasons:
                            continue
                        
                        current_count = sum(len(episodes) for episodes in seasons.values())
                        old_count = drama['episode_count']
                        
                        if current_count > old_count:
                            new_episodes = current_count - old_count
                            
                            print(f"🆕 New episodes found for {drama['title']}: {new_episodes} new episode(s)")
                            
                            notification_text = (
                                f"🆕 **New Episodes Available!**\n\n"
                                f"**Drama:** {drama['title']}\n"
                                f"**Previous Episodes:** {old_count}\n"
                                f"**Current Episodes:** {current_count}\n"
                                f"**New Episodes:** {new_episodes}\n\n"
                            )
                            
                            settings = get_user_settings(user_id)
                            
                            if settings['monitor_auto_upload']:
                                notification_text += "⏳ Auto-uploading new episodes..."
                                await app.send_message(user_id, notification_text)
                                
                                all_episodes = []
                                for season_name in sorted(seasons.keys()):
                                    for episode in seasons[season_name]:
                                        all_episodes.append(episode)
                                
                                new_episode_list = all_episodes[-new_episodes:]
                                
                                for episode in new_episode_list:
                                    try:
                                        result = scraper.extract_and_download(episode['download_link'])
                                        
                                        if result and result.get('success'):
                                            thumbnail_path = None
                                            
                                            if settings['upload_as'] == 'video' and settings['thumbnail_type'] != 'none':
                                                if settings['thumbnail_type'] == 'custom' and settings['custom_thumbnail_path']:
                                                    thumbnail_path = settings['custom_thumbnail_path']
                                                elif settings['thumbnail_type'] == 'auto':
                                                    thumbnail_path = extract_thumbnail_from_video(result['filepath'])
                                            
                                            if settings['upload_as'] == 'video':
                                                await app.send_video(
                                                    chat_id=user_id,
                                                    video=result['filepath'],
                                                    caption=f"🎬 {drama['title']} - {episode['title']}\n📦 {result['size_mb']:.2f} MB | @kdramahype",
                                                    thumb=thumbnail_path,
                                                    supports_streaming=True
                                                )
                                            else:
                                                await app.send_document(
                                                    chat_id=user_id,
                                                    document=result['filepath'],
                                                    caption=f"🎬 {drama['title']} - {episode['title']}\n📦 {result['size_mb']:.2f} MB | @kdramahype"
                                                )
                                            
                                            if os.path.exists(result['filepath']):
                                                os.remove(result['filepath'])
                                            if thumbnail_path and thumbnail_path != settings['custom_thumbnail_path']:
                                                if os.path.exists(thumbnail_path):
                                                    os.remove(thumbnail_path)
                                            
                                            await asyncio.sleep(2)
                                    
                                    except Exception as e:
                                        print(f"Error auto-uploading episode: {e}")
                                        continue
                            
                            else:
                                notification_text += (
                                    "Use /search to download the new episodes.\n\n"
                                    "💡 Tip: Enable 'Monitor Auto-Upload' in /settings to automatically upload new episodes."
                                )
                                await app.send_message(user_id, notification_text)
                            
                            drama['episode_count'] = current_count
                            save_monitor_data()
                    
                    except Exception as e:
                        print(f"Error checking drama {drama.get('title', 'Unknown')}: {e}")
                        continue
                    
                    await asyncio.sleep(5)
            
            print("✅ Monitor check complete. Sleeping for 1 hour...")
            
        except Exception as e:
            print(f"Error in monitoring task: {e}")
        
        await asyncio.sleep(3600)

if __name__ == "__main__":
    print("🎬 Drama Downloader Bot Starting...")
    load_monitor_data()
    print(f"📊 Loaded {sum(len(dramas) for dramas in monitor_data.values())} monitored dramas")
    
    app.loop.create_task(start_monitoring_task())
    
    print("🚀 Starting bot and monitoring service...")
    app.run()
