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

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================================================
# CONFIGURATION
# ============================================================================
API_ID = 2522
API_HASH = "82a"
BOT_TOKEN = "796XM"

DOWNLOAD_PATH = "./downloads/"
THUMBNAIL_PATH = "./thumbnails/"

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
    
    def extract_and_download(self, page_url, progress_callback=None):
        """Extract download link and download the file"""
        try:
            file_id = page_url.split('/')[3]
        except IndexError:
            return None
        
        try:
            response = self.session.get(page_url, timeout=30, verify=False)
            if response.status_code != 200:
                return None
        except requests.exceptions.RequestException:
            return None
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        form = soup.find('form', {'name': 'F1'}) or soup.find('form')
        if not form:
            return None
        
        form_data = {
            'op': 'download2',
            'id': file_id,
            'rand': '',
            'referer': '',
            'method_free': '',
            'method_premium': ''
        }
        
        for input_field in form.find_all('input', {'type': 'hidden'}):
            name = input_field.get('name')
            value = input_field.get('value', '')
            if name:
                form_data[name] = value
        
        countdown = soup.find('span', class_='seconds')
        wait_time = 0
        
        if countdown:
            try:
                wait_time = int(countdown.get_text().strip())
                if progress_callback:
                    progress_callback(f"⏳ Waiting {wait_time} seconds...")
                time.sleep(wait_time + 1)
            except ValueError:
                time.sleep(5)
        
        post_headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://downloadwella.com',
            'Referer': page_url
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
        except requests.exceptions.RequestException:
            return None
        
        download_url = None
        
        if post_response.status_code == 302:
            download_url = post_response.headers.get('Location')
        elif post_response.status_code == 200:
            response_soup = BeautifulSoup(post_response.content, 'html.parser')
            download_patterns = [
                response_soup.find('a', {'id': re.compile(r'download', re.I)}),
                response_soup.find('a', {'class': re.compile(r'download', re.I)}),
                response_soup.find('a', href=re.compile(r'\.mp4|\.mkv|\.avi|/d/', re.I))
            ]
            
            for link in download_patterns:
                if link and link.get('href'):
                    download_url = link.get('href')
                    break
        
        if not download_url:
            return None
        
        if not download_url.startswith('http'):
            download_url = 'https://downloadwella.com' + download_url
        
        try:
            filename = download_url.split('/')[-1]
            if not filename or '.' not in filename:
                filename = f"{file_id}.mkv"
            
            filepath = os.path.join(DOWNLOAD_PATH, filename)
            
            if progress_callback:
                progress_callback(f"📥 Downloading: {filename}")
            
            download_response = self.session.get(download_url, stream=True, verify=False)
            download_response.raise_for_status()
            
            total_size = int(download_response.headers.get('Content-Length', 0))
            
            with open(filepath, 'wb') as f:
                downloaded = 0
                last_progress = 0
                for chunk in download_response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if total_size > 0 and progress_callback:
                            progress = (downloaded / total_size) * 100
                            if int(progress) // 10 > last_progress // 10:
                                progress_callback(f"📥 Progress: {progress:.1f}%")
                                last_progress = progress
            
            file_size = os.path.getsize(filepath) / (1024 * 1024)
            
            return {
                'success': True,
                'filepath': filepath,
                'filename': filename,
                'size_mb': file_size
            }
        except Exception as e:
            print(f"Download failed: {e}")
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

def get_user_settings(user_id):
    """Get user settings with defaults"""
    if user_id not in user_settings:
        user_settings[user_id] = {
            'upload_as': 'video',
            'use_thumbnail': True,
            'thumbnail_type': 'auto',
            'custom_thumbnail_path': None
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
        "3. Choose single episode or download all\n"
        "4. Wait for download and upload\n\n"
        "**Commands:**\n"
        "📺 /search <name> - Search dramas\n"
        "⚙️ /settings - Upload settings\n"
        "📸 /setthumbnail - Set custom thumbnail\n"
        "🗑️ /clearthumbnail - Remove custom thumbnail\n"
        "❌ /cancel - Cancel operation\n\n"
        f"**Current Settings:**\n"
        f"Upload as: {settings['upload_as'].title()}\n"
        f"Thumbnail: {settings['thumbnail_type'].title()}"
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
        )]
    ]
    
    thumb_status = "Not set"
    if settings['thumbnail_type'] == 'custom' and settings['custom_thumbnail_path']:
        thumb_status = "✅ Custom thumbnail set"
    
    await message.reply_text(
        "⚙️ **Upload Settings**\n\n"
        f"**Upload Type:** {settings['upload_as'].title()}\n"
        f"**Thumbnail Mode:** {settings['thumbnail_type'].title()}\n"
        f"**Custom Thumbnail:** {thumb_status}\n\n"
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
        )]
    ]
    
    thumb_status = "Not set"
    if settings['thumbnail_type'] == 'custom' and settings['custom_thumbnail_path']:
        thumb_status = "✅ Custom thumbnail set"
    
    await callback_query.message.edit_text(
        "⚙️ **Upload Settings**\n\n"
        f"**Upload Type:** {settings['upload_as'].title()}\n"
        f"**Thumbnail Mode:** {settings['thumbnail_type'].title()}\n"
        f"**Custom Thumbnail:** {thumb_status}\n\n"
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
    
    keyboard = [[
        InlineKeyboardButton("📥 Download All Episodes", callback_data="download_all")
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
        f"📥 Download all or select individual episode:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

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
    
    for idx, episode in enumerate(episodes, 1):
        try:
            await status_msg.edit_text(
                f"📥 **Downloading All Episodes**\n\n"
                f"**Drama:** {drama_title}\n"
                f"**Total Episodes:** {len(episodes)}\n"
                f"**Progress:** {idx}/{len(episodes)}\n"
                f"**Success:** {successful} | **Failed:** {failed}\n\n"
                f"⏳ Current: {episode['display_title']}"
            )
            
            result = scraper.extract_and_download(episode['download_link'])
            
            if not result or not result.get('success'):
                failed += 1
                continue
            
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
                    caption=f"🎬 {episode['display_title']}\n📦 {result['size_mb']:.2f} MB",
                    thumb=thumbnail_path,
                    supports_streaming=True
                )
            else:
                await client.send_document(
                    chat_id=callback_query.message.chat.id,
                    document=result['filepath'],
                    caption=f"🎬 {episode['display_title']}\n📦 {result['size_mb']:.2f} MB"
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
        f"**❌ Failed:** {failed}"
    )

@app.on_callback_query(filters.regex(r"^ep_\d+$"))
async def episode_selected(client: Client, callback_query):
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
        f"📥 **Downloading:**\n"
        f"{selected_episode['display_title']}\n\n"
        f"⏳ Please wait..."
    )
    
    result = scraper.extract_and_download(selected_episode['download_link'])
    
    if not result or not result.get('success'):
        await status_msg.edit_text("❌ Download failed. Please try again.")
        return
    
    settings = get_user_settings(user_id)
    
    await status_msg.edit_text(
        f"✅ **Download Complete!**\n\n"
        f"📦 Size: {result['size_mb']:.2f} MB\n"
        f"⬆️ Uploading to Telegram..."
    )
    
    try:
        thumbnail_path = None
        
        if settings['upload_as'] == 'video' and settings['thumbnail_type'] != 'none':
            if settings['thumbnail_type'] == 'custom' and settings['custom_thumbnail_path']:
                thumbnail_path = settings['custom_thumbnail_path']
            elif settings['thumbnail_type'] == 'auto':
                await status_msg.edit_text(
                    f"✅ **Download Complete!**\n\n"
                    f"📦 Size: {result['size_mb']:.2f} MB\n"
                    f"📸 Generating thumbnail...\n"
                    f"⬆️ Uploading to Telegram..."
                )
                thumbnail_path = extract_thumbnail_from_video(result['filepath'])
        
        async def progress(current, total):
            percent = (current / total) * 100
            if int(percent) % 10 == 0:
                try:
                    await status_msg.edit_text(
                        f"⬆️ **Uploading to Telegram**\n\n"
                        f"Progress: {percent:.1f}%\n"
                        f"Size: {result['size_mb']:.2f} MB"
                    )
                except:
                    pass
        
        if settings['upload_as'] == 'video':
            await client.send_video(
                chat_id=callback_query.message.chat.id,
                video=result['filepath'],
                caption=f"🎬 {selected_episode['display_title']}\n\n📦 Size: {result['size_mb']:.2f} MB",
                thumb=thumbnail_path,
                supports_streaming=True,
                progress=progress
            )
        else:
            await client.send_document(
                chat_id=callback_query.message.chat.id,
                document=result['filepath'],
                caption=f"🎬 {selected_episode['display_title']}\n\n📦 Size: {result['size_mb']:.2f} MB",
                progress=progress
            )
        
        await status_msg.edit_text("✅ **Upload Complete!**")
        
        try:
            os.remove(result['filepath'])
            if thumbnail_path and thumbnail_path != settings['custom_thumbnail_path']:
                if os.path.exists(thumbnail_path):
                    os.remove(thumbnail_path)
        except:
            pass
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Upload failed: {str(e)}")
        print(f"Upload error: {e}")

# ============================================================================
# Run Bot
# ============================================================================
if __name__ == "__main__":
    print("🤖 Starting Drama Downloader Bot...")
    print("Features: Search, Download All, Custom Thumbnails, Video/Doc Upload")
    app.run()