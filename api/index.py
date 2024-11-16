from flask import Flask, jsonify, request
import logging
import re
import json
import requests
from bs4 import BeautifulSoup
import yt_dlp
import urllib.parse
from pydub import AudioSegment
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

# Use the API key directly
API_KEY = 'AIzaSyAAgsgw39IjWMRIRFvJZpFj0oQF3_Yb5sw'
# Build the YouTube client
youtube = build('youtube', 'v3', developerKey=API_KEY)

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    return response

def get_playlist_info(playlist_id):
    try:
        playlist_items = []
        next_page_token = None

        while True:
            playlist_response = youtube.playlistItems().list(
                part='snippet',
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page_token
            ).execute()

            playlist_items.extend(playlist_response['items'])
            next_page_token = playlist_response.get('nextPageToken')

            if not next_page_token:
                break

        song_info = []
        for item in playlist_items:
            video = item['snippet']
            song_info.append({
                'title': video['title'],
                'writer': video['videoOwnerChannelTitle'],
                'url': f"https://www.youtube.com/watch?v={video['resourceId']['videoId']}",
                'image_url': video['thumbnails']['high']['url'],
            })

        return {
            'songCount': len(song_info),
            'songInfo': song_info
        }
    except HttpError as e:
        logging.error(f"YouTube API error: {str(e)}")
        return {'error': f'YouTube API error: {str(e)}'}

def extract_playlist_id(url):
    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.hostname in ('youtube.com', 'www.youtube.com', 'music.youtube.com'):
        query = urllib.parse.parse_qs(parsed_url.query)
        return query.get('list', [None])[0]
    return None

@app.route('/playlist', methods=['GET'])
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
        playlist_id = extract_playlist_id(playlist_url)
        if playlist_id:
            result = get_playlist_info(playlist_id)
            if isinstance(result, dict) and 'songInfo' in result:
                all_songs_info.extend(result['songInfo'])
            elif 'error' in result:
                logging.error(f"Error processing playlist {playlist_url}: {result['error']}")
        else:
            logging.error(f"Invalid playlist URL: {playlist_url}")

    return jsonify({
        'songCount': len(all_songs_info),
        'songInfo': all_songs_info
    })
    

# Your YouTube API key
YOUTUBE_API_KEY = "AIzaSyAAgsgw39IjWMRIRFvJZpFj0oQF3_Yb5sw"

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
    writer = writer.replace(" ", "-").capitalize()  # Format writer
    title = title.replace(" ", "-")  # Format title
    search_url = f"https://genius.com/{writer}-{title}-lyrics"

    try:
        response = requests.get(search_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        lyrics_div = soup.find('div', class_='Lyrics__Container-sc-1ynbvzw-1 kUgSbL')
        if lyrics_div:
            lyrics = BeautifulSoup(str(lyrics_div), 'html.parser').get_text("\n", strip=True)
            lyrics = re.sub(r'\[.*?\]', '', lyrics)  # Remove text inside brackets
            return lyrics
        else:
            return 'Lyrics not found in the expected location.'
    except requests.exceptions.HTTPError as http_err:
        if response.status_code == 404:
            return f"Lyrics not found for {writer} - {title} (404 Error)"
        return f"HTTP error occurred: {http_err}"
    except Exception as e:
        return f"Error fetching lyrics: {str(e)}"

def fetch_video_metadata(video_url):
    """Fetch video metadata using the YouTube Data API."""
    video_id = video_url.split("v=")[-1] if "v=" in video_url else video_url.split("/")[-1]
    api_url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet&id={video_id}&key={YOUTUBE_API_KEY}"

    try:
        response = requests.get(api_url)
        response.raise_for_status()
        video_data = response.json()

        if "items" in video_data and len(video_data["items"]) > 0:
            snippet = video_data["items"][0]["snippet"]
            title = snippet.get("title", "Unknown Title")
            uploader = snippet.get("channelTitle", "Unknown Uploader")
            return {"title": title, "uploader": uploader}
        else:
            return {"error": "Video not found"}
    except Exception as e:
        return {"error": str(e)}

def fetch_audio_stream(video_url):
    """Fetch the audio stream URL using yt-dlp."""
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
    }
    try:
        # Extracting info using yt-dlp
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(video_url, download=False)
            if 'url' in info_dict:
                audio_url = info_dict['url']
                return audio_url
            else:
                raise ValueError("Audio stream URL not found")
    except Exception as e:
        print(f"Error fetching audio stream: {e}")  # Log the error for debugging
        return None

@app.route('/get-audio', methods=['GET'])
def get_audio():
    video_url = request.args.get('url')
    if not video_url:
        return jsonify({'error': 'Missing video URL parameter'}), 400

    # Fetch video metadata
    video_metadata = fetch_video_metadata(video_url)
    if "error" in video_metadata:
        return jsonify({'error': video_metadata['error']}), 500

    # Clean and process the video title
    title = remove_parentheses(video_metadata["title"])
    writer = remove_parentheses(video_metadata["uploader"])
    title = remove_text_before_dash(title)
    title = remove_writer_from_title(title, writer)
    title = remove_symbols(title)

    # Fetch lyrics from Genius
    lyrics = get_lyrics_from_genius(writer, title)

    # Fetch audio stream URL
    audio_stream_url = fetch_audio_stream(video_url)

    if not audio_stream_url:
        return jsonify({'error': 'Failed to fetch audio stream'}), 500

    # Return response with the required data
    return jsonify({
        "title": title,
        "writer": writer,
        "lyrics": lyrics,
        "audioUrl": audio_stream_url
    })
    
if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)