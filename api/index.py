import sys
import yt_dlp
import json
import re
import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, make_response, request
import logging

app = Flask(__name__)

# Setting up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    return response

# Function to check if the URL belongs to YouTube or music.youtube
def is_youtube_url(url):
    # Check if the URL contains 'youtube' or 'music.youtube'
    return 'youtube.com' in url or 'music.youtube.com' in url

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

    # Filter out YouTube or music.youtube URLs
    playlist_urls = [url for url in playlist_urls if not is_youtube_url(url)]

    if not playlist_urls:
        return jsonify({'error': 'No valid playlist URLs found'}), 400

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

@app.route('/get-audio', methods=['GET'])
def get_audio():
    video_url = request.args.get('url')  # Get the video URL from the query parameter

    if not video_url:
        return jsonify({'error': 'Missing video URL parameter'}), 400

    result = download_audio(video_url)

    return jsonify(json.loads(result))


def download_audio(video_url):
    # Create a RequestsCookieJar instance to store cookies
    cookie_jar = requests.cookies.RequestsCookieJar()

    # Example: Set cookies from the extracted cookie data (using the cookie data you provided)
    cookies = [
        {"name": "PREF", "value": "f6=40000000&tz=Asia.Shanghai&f5=30000", "domain": ".youtube.com", "path": "/"},
        {"name": "wide", "value": "1", "domain": ".youtube.com", "path": "/"},
        {"name": "GPS", "value": "1", "domain": ".youtube.com", "path": "/"},
        {"name": "SID", "value": "g.a000qQhH17Hcx4NF8qxGHDbVgSvhQ06pejIv_nBeiRuT4bOL8mLtQKuD1EO54z0U-hsiYrC9KgACgYKAXMSARYSFQHGX2Miqe26lPmqBtxp-WkkFfZPrxoVAUF8yKqYuYfI_uVqdSgbj7Jsn6vI0076", "domain": ".youtube.com", "path": "/"},
        {"name": "HSID", "value": "Alagvt9Klvs5GNRko", "domain": ".youtube.com", "path": "/"},
        # Add all other cookies in a similar way...
    ]

    # Add the cookies to the cookie jar
    for cookie in cookies:
        cookie_jar.set(cookie['name'], cookie['value'], domain=cookie['domain'], path=cookie['path'])

    # Additional headers to mimic a real browser session (You can extract these from your browser)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        # Add any other headers you find in your browser session
    }

    # Pass cookie_jar and headers to yt-dlp
    ydl_opts = {
        'format': 'bestaudio/best',  # Download best available audio
        'outtmpl': '/tmp/audio.%(ext)s',  # Temporary file path
        'cookiejar': cookie_jar,  # Use the cookies we created
        'headers': headers,  # Use custom headers
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            result = ydl.extract_info(video_url, download=True)
            audio_file = ydl.prepare_filename(result)  # Get the file path of the downloaded audio
            return json.dumps({'audio_url': audio_file})
        except yt_dlp.DownloadError as e:
            return json.dumps({'error': f"Download error: {str(e)}"})
        except Exception as e:
            return json.dumps({'error': f"Error occurred: {str(e)}"})

if __name__ == '__main__':
    fetch_playlists_on_start()  # Fetch playlists when the app starts
    app.run(debug=True)
