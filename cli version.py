import requests
from bs4 import BeautifulSoup
import time
import json
import os
from urllib.parse import urljoin, urlparse
from datetime import datetime
import re

class DramaEpisodeScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:145.0) Gecko/20100101 Firefox/145.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        })
        self.base_url = "https://thenkiri.com"
        self.download_path = "/root/Downloads/"
        
        # Create download directory if it doesn't exist
        os.makedirs(self.download_path, exist_ok=True)
        
    def search_drama(self, search_term):
        """Search for drama on the website"""
        try:
            search_url = f"{self.base_url}/?s={search_term}"
            
            print(f"Searching for: {search_term}")
            response = self.session.get(search_url)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                results = self.extract_search_results(soup)
                return results
                        
            return []
            
        except Exception as e:
            print(f"Error searching: {e}")
            return []
    
    def extract_search_results(self, soup):
        """Extract search results from the page"""
        results = []
        
        selectors = [
            'article',
            '.post',
            '.search-result',
            '.movie-item',
            '.drama-item',
            'h2 a',
            'h3 a'
        ]
        
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
    
    def display_search_results(self, results):
        """Display search results for user selection"""
        if not results:
            print("No results found!")
            return None
            
        print("\nSearch Results:")
        print("-" * 80)
        
        for result in results:
            print(f"{result['number']}. {result['title']}")
        
        print("-" * 80)
        return results
    
    def get_user_choice(self, results):
        """Get user's choice from search results"""
        try:
            choice = int(input(f"Enter number (1-{len(results)}): "))
            if 1 <= choice <= len(results):
                return results[choice - 1]
            else:
                print("Invalid choice!")
                return None
        except ValueError:
            print("Please enter a valid number!")
            return None
    
    def scrape_episodes(self, drama_url):
        """Scrape episodes from the selected drama page"""
        try:
            print(f"Scraping episodes from: {drama_url}")
            response = self.session.get(drama_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            seasons = self.parse_elementor_episodes_by_season(soup)
            
            return seasons
            
        except Exception as e:
            print(f"Error scraping episodes: {e}")
            return {}
    
    def parse_elementor_episodes_by_season(self, soup):
        """Parse episodes with proper season detection or smart inference"""
        seasons = {}
        current_season = None
        detected_season_numbers = []
        
        # Find all Elementor containers in order
        containers = soup.find_all('div', class_='elementor-container elementor-column-gap-default')
        
        print(f"DEBUG: Processing {len(containers)} containers")
        
        for i, container in enumerate(containers):
            headings = container.find_all('h2', class_='elementor-heading-title')
            
            for heading in headings:
                heading_text = heading.get_text(strip=True)
                print(f"DEBUG: Container {i}, Heading: '{heading_text}'")
                
                # Check if it's a season title
                season_match = re.search(r'season\s+(\d+)', heading_text, re.IGNORECASE)
                if season_match:
                    season_num = int(season_match.group(1))
                    current_season = heading_text
                    detected_season_numbers.append(season_num)
                    
                    print(f"DEBUG: Found season: {current_season} (number: {season_num})")
                    
                    if current_season not in seasons:
                        seasons[current_season] = []
                
                # Check if it's an episode title
                elif re.search(r'episode\s+\d+', heading_text, re.IGNORECASE):
                    print(f"DEBUG: Found episode: {heading_text}")
                    
                    # If no explicit season found yet, use smart inference
                    if current_season is None:
                        current_season = self.infer_current_season(detected_season_numbers)
                        print(f"DEBUG: Inferred season: {current_season}")
                    
                    # Ensure current season exists in dict
                    if current_season not in seasons:
                        seasons[current_season] = []
                    
                    # Look for download button in the same container
                    download_button = container.find('a', class_='elementor-button')
                    if download_button and download_button.get('href'):
                        download_link = download_button.get('href')
                        
                        episode_number = len(seasons[current_season]) + 1
                        
                        seasons[current_season].append({
                            'number': episode_number,
                            'title': heading_text,
                            'download_link': download_link,
                            'season': current_season
                        })
                        print(f"DEBUG: Added episode {episode_number} to {current_season}")
        
        print(f"DEBUG: Detected season numbers: {sorted(set(detected_season_numbers))}")
        print(f"DEBUG: Final seasons: {list(seasons.keys())}")
        
        # Apply your smart inference if we have gaps
        if detected_season_numbers:
            seasons = self.apply_smart_inference(seasons, detected_season_numbers)
        
        return seasons
    
    def infer_current_season(self, detected_season_numbers):
        """Infer what the current season should be"""
        if not detected_season_numbers:
            return "Season 1"
        
        # Use the first detected season as starting point
        min_season = min(detected_season_numbers)
        return f"Season {min_season}"
    
    def apply_smart_inference(self, seasons, detected_season_numbers):
        """Apply your smart minus approach to fix missing seasons"""
        if not detected_season_numbers:
            return seasons
        
        sorted_detected = sorted(set(detected_season_numbers))
        print(f"DEBUG: Applying smart inference for seasons: {sorted_detected}")
        
        # Check if we have gaps in the sequence
        expected_seasons = list(range(sorted_detected[0], sorted_detected[-1] + 1))
        missing_seasons = [s for s in expected_seasons if s not in sorted_detected]
        
        if missing_seasons:
            print(f"DEBUG: Missing seasons detected: {missing_seasons}")
            
            # If we have episodes assigned to wrong seasons, try to redistribute
            new_seasons = {}
            
            # Collect all episodes in order they were found
            all_episodes = []
            for season_name in seasons:
                all_episodes.extend(seasons[season_name])
            
            # Redistribute to expected seasons
            episodes_assigned = 0
            for season_num in expected_seasons:
                season_name = f"Season {season_num}"
                new_seasons[season_name] = []
                
                # Find how many episodes this season should have
                # (We don't assume, we just assign what we found)
                if season_num in sorted_detected:
                    original_season_name = f"Season {season_num}"
                    if original_season_name in seasons:
                        new_seasons[season_name] = seasons[original_season_name]
                        episodes_assigned += len(seasons[original_season_name])
            
            return new_seasons
        
        return seasons
    
    def display_seasons_and_episodes(self, seasons):
        """Display seasons and episodes for user selection"""
        if not seasons:
            print("No episodes found!")
            return None
        
        print(f"\nFound {len(seasons)} season(s):")
        print("=" * 80)
        
        # Create a flat list for numbering
        all_episodes = []
        episode_number = 1
        
        # Sort seasons by season number for proper display
        sorted_seasons = self.sort_seasons(seasons)
        
        for season_name, episodes in sorted_seasons:
            if episodes:  # Only show seasons that have episodes
                print(f"\n📺 {season_name}")
                print("-" * 40)
                
                for episode in episodes:
                    print(f"  {episode_number}. {episode['title']}")
                    episode['global_number'] = episode_number
                    all_episodes.append(episode)
                    episode_number += 1
        
        print("=" * 80)
        return all_episodes
    
    def sort_seasons(self, seasons):
        """Sort seasons by their number"""
        def extract_season_number(season_name):
            # Extract number from season name like "Season 3" -> 3
            match = re.search(r'season\s+(\d+)', season_name, re.IGNORECASE)
            if match:
                return int(match.group(1))
            return 999  # Put unrecognized seasons at the end
        
        # Sort seasons by their number
        sorted_items = sorted(seasons.items(), key=lambda x: extract_season_number(x[0]))
        return sorted_items
    
    def get_episode_choice(self, all_episodes):
        """Get user's choice of episode from all seasons"""
        try:
            choice_input = input(f"Enter episode number (1-{len(all_episodes)}): ").strip()
            
            choice = int(choice_input)
            if 1 <= choice <= len(all_episodes):
                # Find the episode with the matching global number
                for episode in all_episodes:
                    if episode['global_number'] == choice:
                        return episode
                return None
            else:
                print("Invalid choice!")
                return None
        except ValueError:
            print("Please enter a valid number!")
            return None

    def extract_and_download(self, page_url):
        """Extract download link and download the file"""
        print("="*70)
        print("DOWNLOAD LINK EXTRACTOR")
        print("="*70)
        print(f"\n📥 URL: {page_url}\n")
        
        # Extract file ID from URL
        try:
            file_id = page_url.split('/')[3]
            print(f"✓ File ID: {file_id}")
        except IndexError:
            print("❌ Invalid URL format")
            return None
        
        # Step 1: GET initial page
        print("\n" + "-"*70)
        print("STEP 1: Fetching initial page")
        print("-"*70)
        
        try:
            response = self.session.get(page_url, timeout=30)
            print(f"Status Code: {response.status_code}")
            
            if response.status_code != 200:
                print(f"❌ Failed to load page: {response.status_code}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
            return None
        
        # Parse HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Step 2: Extract form data
        print("\n" + "-"*70)
        print("STEP 2: Extracting form data")
        print("-"*70)
        
        form = soup.find('form', {'name': 'F1'}) or soup.find('form')
        
        if not form:
            print("❌ No form found on page")
            return None
        
        form_data = {
            'op': 'download2',
            'id': file_id,
            'rand': '',
            'referer': '',
            'method_free': '',
            'method_premium': ''
        }
        
        # Extract hidden fields
        for input_field in form.find_all('input', {'type': 'hidden'}):
            name = input_field.get('name')
            value = input_field.get('value', '')
            if name:
                form_data[name] = value
        
        print("Form fields extracted successfully")
        
        # Step 3: Check for countdown
        print("\n" + "-"*70)
        print("STEP 3: Checking countdown timer")
        print("-"*70)
        
        countdown = soup.find('span', class_='seconds')
        wait_time = 0
        
        if countdown:
            try:
                wait_time = int(countdown.get_text().strip())
                print(f"⏱️  Countdown detected: {wait_time} seconds")
                print(f"⏳ Waiting", end="", flush=True)
                for i in range(wait_time + 1):
                    time.sleep(1)
                    print(".", end="", flush=True)
                print(" Done!")
            except ValueError:
                print("⚠️  Countdown element found but couldn't parse value")
                print("   Waiting 5 seconds as safety buffer...")
                time.sleep(5)
        else:
            print("✓ No countdown required")
        
        # Step 4: Submit POST request
        print("\n" + "-"*70)
        print("STEP 4: Submitting download request")
        print("-"*70)
        
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
                timeout=30
            )
            
            print(f"Status Code: {post_response.status_code}")
            
        except requests.exceptions.RequestException as e:
            print(f"❌ POST request failed: {e}")
            return None
        
        # Step 5: Process response
        print("\n" + "-"*70)
        print("STEP 5: Processing response")
        print("-"*70)
        
        download_url = None
        
        # Check for 302 redirect
        if post_response.status_code == 302:
            download_url = post_response.headers.get('Location')
            
            if download_url:
                print("✅ Redirect detected (302)")
                print(f"📍 Location: {download_url}")
            else:
                print("❌ 302 redirect but no Location header")
                return None
        
        # Check for 200 with download link in HTML
        elif post_response.status_code == 200:
            print("📄 Got HTML response (200), parsing for download links...")
            
            response_soup = BeautifulSoup(post_response.content, 'html.parser')
            
            # Look for direct download links
            download_patterns = [
                response_soup.find('a', {'id': re.compile(r'download', re.I)}),
                response_soup.find('a', {'class': re.compile(r'download', re.I)}),
                response_soup.find('a', href=re.compile(r'\.mp4|\.mkv|\.avi|/d/', re.I))
            ]
            
            for link in download_patterns:
                if link and link.get('href'):
                    download_url = link.get('href')
                    print(f"✅ Found download link in HTML")
                    break
            
            if not download_url:
                print("❌ No download link found in response")
                return None
        
        else:
            print(f"❌ Unexpected status code: {post_response.status_code}")
            return None
        
        # Make sure it's a full URL
        if not download_url.startswith('http'):
            download_url = 'https://downloadwella.com' + download_url
        
        # Step 6: Download the file
        print("\n" + "-"*70)
        print("STEP 6: Downloading file")
        print("-"*70)
        
        try:
            # Get filename from URL or use a default
            filename = download_url.split('/')[-1]
            if not filename or '.' not in filename:
                filename = f"{file_id}.mkv"
            
            filepath = os.path.join(self.download_path, filename)
            
            print(f"📁 Downloading to: {filepath}")
            
            # Start download
            download_response = self.session.get(download_url, stream=True)
            download_response.raise_for_status()
            
            # Get file size for progress
            total_size = int(download_response.headers.get('Content-Length', 0))
            
            with open(filepath, 'wb') as f:
                downloaded = 0
                for chunk in download_response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if total_size > 0:
                            progress = (downloaded / total_size) * 100
                            print(f"\r📥 Progress: {progress:.1f}% ({downloaded}/{total_size} bytes)", end="", flush=True)
            
            print(f"\n✅ SUCCESS! File downloaded to: {filepath}")
            
            # Get file size
            file_size = os.path.getsize(filepath) / (1024 * 1024)  # MB
            print(f"📦 File size: {file_size:.2f} MB")
            
            return {
                'success': True,
                'filepath': filepath,
                'filename': filename,
                'size_mb': file_size
            }
            
        except Exception as e:
            print(f"❌ Download failed: {e}")
            return None

def main():
    scraper = DramaEpisodeScraper()
    
    # Get drama name to search
    search_term = input("Enter drama name to search: ").strip()
    
    # Step 1: Search for drama
    print(f"\n🔍 Searching for '{search_term}'...")
    results = scraper.search_drama(search_term)
    
    if not results:
        print("❌ No search results found. Please try a different drama name.")
        return
    
    # Step 2: Display results and get user choice
    print("\n📋 Select drama from results...")
    scraper.display_search_results(results)
    chosen_drama = scraper.get_user_choice(results)
    
    if not chosen_drama:
        return
    
    print(f"\n✅ Selected: {chosen_drama['title']}")
    
    # Step 3: Scrape episodes by season
    print("\n🎬 Scraping episodes...")
    seasons = scraper.scrape_episodes(chosen_drama['url'])
    
    if not seasons:
        print("❌ No episodes found on the selected page.")
        return
    
    # Step 4: Display seasons and episodes
    print("\n📺 Available seasons and episodes...")
    all_episodes = scraper.display_seasons_and_episodes(seasons)
    
    if not all_episodes:
        print("❌ No episodes available.")
        return
    
    chosen_episode = scraper.get_episode_choice(all_episodes)
    
    if not chosen_episode:
        return
    
    print(f"\n✅ Selected: {chosen_episode['season']} - {chosen_episode['title']}")
    
    # Step 5: Extract and download
    print(f"\n💾 Processing download link...")
    result = scraper.extract_and_download(chosen_episode['download_link'])
    
    if result and result.get('success'):
        print(f"\n🎉 DOWNLOAD COMPLETE!")
        print(f"📁 Location: {result['filepath']}")
        print(f"📦 Size: {result['size_mb']:.2f} MB")
        print(f"\n✅ File saved to /root/Downloads/{result['filename']}")
    else:
        print("❌ Download failed!")

if __name__ == "__main__":
    main()
