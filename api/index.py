from flask import Flask, jsonify, request
import logging
import re
import json
import requests
from bs4 import BeautifulSoup
import yt_dlp

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    return response

# Helper functions for cleaning and fetching data
def remove_parentheses(text):
    return re.sub(r'\s*$$.*?$$\s*', '', text).strip()

def remove_symbols(text):
    return re.sub(r'[^A-Za-z0-9 ]', '', text).strip()

def remove_text_before_dash(text):
    return text.split("-", 1)[-1].lstrip() if "-" in text else text

def remove_writer_from_title(title, writer):
    writer_escaped = re.escape(writer)
    return re.sub(r'\b' + writer_escaped + r'\b', '', title).strip()

def get_lyrics_from_genius(writer, title):
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

def get_audio_info(video_url):
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'extract_flat': 'in_playlist',
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(video_url, download=False)
            if 'entries' in info:  # It's a playlist
                return get_playlist_info(info)
            else:  # It's a single video
                return get_single_video_info(info)
        except Exception as e:
            return {'error': str(e)}

def get_single_video_info(info):
    title = remove_parentheses(info.get("title", "Unknown Title"))
    writer = remove_parentheses(info.get("artist", info.get("uploader", "Unknown Writer")))
    title = remove_text_before_dash(title)
    title = remove_writer_from_title(title, writer)
    title = remove_symbols(title)
    lyrics = get_lyrics_from_genius(writer, title)

    return {
        'audioUrl': info.get('url'),
        'title': title,
        'writer': writer,
        'lyrics': lyrics
    }

def get_playlist_info(info):
    song_info = [
        {
            'title': entry['title'],
            'writer': entry.get('uploader') or entry.get('artist') or entry.get('creator', 'Unknown'),
            'url': f"https://www.youtube.com/watch?v={entry['id']}",
            'image_url': entry.get('thumbnails', [{}])[-1].get('url', ''),
        } for entry in info['entries'] if entry
    ]
    
    return {
        'songCount': len(song_info),
        'songInfo': song_info
    }

@app.route('/get-audio', methods=['GET'])
def get_audio():
    video_url = request.args.get('url')
    if not video_url:
        return jsonify({'error': 'Missing video URL parameter'}), 400

    result = get_audio_info(video_url)
    return jsonify(result)

@app.route('/get_playlist_info', methods=['GET'])
def playlist_info_endpoint():
    try:
        with open('links.txt', 'r') as file:
            playlist_urls = [line.strip() for line in file.readlines()]
    except Exception as e:
        return jsonify({'error': f'Failed to read links.txt: {str(e)}'}), 500

    if not playlist_urls:
        return jsonify({'error': 'No playlist URLs found in links.txt'}), 400

    all_songs_info = []
    for playlist_url in playlist_urls:
        result = get_audio_info(playlist_url)
        if isinstance(result, dict) and 'songInfo' in result:
            all_songs_info.extend(result['songInfo'])

    return jsonify({
        'songCount': len(all_songs_info),
        'songInfo': all_songs_info
    })

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)