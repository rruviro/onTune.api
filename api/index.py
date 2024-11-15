import sys
import yt_dlp
import json
import re
import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, make_response, request
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

app = Flask(__name__)

# Setting up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    return response

# Playlist info function
def get_playlist_info(playlist_url):
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            playlist_info = ydl.extract_info(playlist_url, download=False)
            if 'entries' in playlist_info:
                song_info = [
                    {
                        'title': entry['title'],
                        'writer': entry.get('uploader') or entry.get('artist') or entry.get('creator', 'Unknown'),
                        'url': f"https://www.youtube.com/watch?v={entry['id']}",
                        'image_url': entry.get('thumbnails', [{}])[-1].get('url', ''),
                        'playlistUrl': playlist_url
                    } for entry in playlist_info['entries']
                ]
                
                return {
                    'songCount': len(song_info),
                    'songInfo': song_info
                }
            else:
                return {'error': 'No entries found in the playlist'}
        except yt_dlp.utils.DownloadError as e:
            logging.error(f"DownloadError: {str(e)}")
            return {'error': f"DownloadError: {str(e)}"}
        except Exception as e:
            logging.error(f"Error fetching playlist info: {str(e)}")
            return {'error': f"Error: {str(e)}"}

@app.route('/get_playlist_info', methods=['GET'])
def playlist_info_endpoint():
    try:
        with open('api/links.txt', 'r') as file:
            playlist_urls = [line.strip() for line in file.readlines()]
    except Exception as e:
        logging.error(f"Failed to read api/links.txt: {str(e)}")
        return jsonify({'error': f'Failed to read api/links.txt: {str(e)}'}), 500

    if not playlist_urls:
        return jsonify({'error': 'No playlist URLs found in api/links.txt'}), 400

    all_songs_info = []
    for playlist_url in playlist_urls:
        result = get_playlist_info(playlist_url)
        if isinstance(result, dict) and 'songInfo' in result:
            all_songs_info.extend(result['songInfo'])

    return jsonify({
        'songCount': len(all_songs_info),
        'songInfo': all_songs_info
    })

def fetch_playlists_on_start():
    try:
        with open('api/links.txt', 'r') as file:
            playlist_urls = [line.strip() for line in file.readlines()]
    except Exception as e:
        logging.error(f"Failed to read api/links.txt: {str(e)}")
        return

    if not playlist_urls:
        logging.error("No playlist URLs found in api/links.txt")
        return

    all_songs_info = []
    for playlist_url in playlist_urls:
        result = get_playlist_info(playlist_url)
        if isinstance(result, dict) and 'songInfo' in result:
            all_songs_info.extend(result['songInfo'])

    logging.info(f"Fetched {len(all_songs_info)} songs.")
    for song in all_songs_info:
        logging.info(json.dumps(song))

# Helper functions for cleaning and fetching data
def remove_parentheses(text):
    """Removes any text within parentheses from a string."""
    return re.sub(r'\s*\(.*?\)\s*', '', text).strip()

def remove_symbols(text):
    """Removes most symbols, retaining only alphanumeric characters and spaces."""
    return re.sub(r'[^A-Za-z0-9 ]', '', text).strip()

def remove_text_before_dash(text):
    """Removes any text before the first dash, including the dash, and removes any space after the dash."""
    return text.split("-", 1)[-1].lstrip() if "-" in text else text

def remove_writer_from_title(title, writer):
    """Removes the writer's name from the title if it appears within it."""
    writer_escaped = re.escape(writer)
    return re.sub(r'\b' + writer_escaped + r'\b', '', title).strip()

def get_lyrics_from_genius(writer, title):
    """Fetch lyrics from Genius based on song title and artist."""
    writer = writer.replace(" ", "-").capitalize()
    title = title.replace(" ", "-")

    search_url = f"https://genius.com/{writer}-{title}-lyrics"

    try:
        response = requests.get(search_url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        
        lyrics_div = soup.find('div', class_='Lyrics__Container-sc-1ynbvzw-1 kUgSbL')
        if lyrics_div:
            lyrics = str(lyrics_div)
            lyrics = BeautifulSoup(lyrics, 'html.parser').get_text("\n", strip=True)
            lyrics = lyrics.replace('<br>', '\n')
            lyrics = re.sub(r'\[.*?\]', '', lyrics)
            lyrics = lyrics.replace('"', '"\n')

            return lyrics
        else:
            return 'Lyrics not found in the expected location.'
    except requests.exceptions.HTTPError as http_err:
        if response.status_code == 404:
            return f"Lyrics not found for {writer} - {title} (404 Error)"
        return f"HTTP error occurred: {http_err}"
    except Exception as e:
        return f"Error fetching lyrics: {str(e)}"

class YoutubeDLPWrapper:
    def __init__(self):
        self.ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': '%(id)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': 'in_playlist',
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'logtostderr': False,
            'no_color': True,
        }

    def extract_info(self, url):
        with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                return info
            except Exception as e:
                return {'error': str(e)}

def get_audio_url(video_url):
    ydl_wrapper = YoutubeDLPWrapper()
    
    # Add a random delay to mimic human behavior
    time.sleep(random.uniform(1, 3))
    
    info = ydl_wrapper.extract_info(video_url)
    
    if 'error' in info:
        return json.dumps({'error': info['error']})
    
    if 'formats' not in info:
        return json.dumps({'error': 'No formats found for this video.'})
    
    # Find the best audio format
    audio_formats = [f for f in info['formats'] if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
    if not audio_formats:
        return json.dumps({'error': 'No suitable audio format found.'})
    
    best_audio = max(audio_formats, key=lambda f: f.get('abr', 0))
    
    return json.dumps({
        'audioUrl': best_audio['url'],
        'title': info.get('title', 'Unknown Title'),
        'artist': info.get('artist', info.get('uploader', 'Unknown Artist')),
    })

@app.route('/get-audio', methods=['GET'])
def get_audio():
    video_url = request.args.get('url')

    if not video_url:
        return jsonify({'error': 'Missing video URL parameter'}), 400

    result = get_audio_url(video_url)

    return jsonify(json.loads(result))
if __name__ == "__main__":
    fetch_playlists_on_start()
    app.run(debug=True, host='0.0.0.0', port=5000)