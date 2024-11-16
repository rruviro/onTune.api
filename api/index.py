from flask import Flask, Response, jsonify, request
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
from os import BytesIO

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
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

def validate_youtube_url(video_url):
    """Validates the YouTube video URL using the YouTube Data API."""
    try:
        parsed_url = urllib.parse.urlparse(video_url)
        video_id = urllib.parse.parse_qs(parsed_url.query).get("v")
        if not video_id:
            return None, "Invalid video URL"

        video_id = video_id[0]

        # Use the YouTube Data API
        youtube = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, developerKey=YOUTUBE_API_KEY)
        response = youtube.videos().list(part="id,snippet", id=video_id).execute()

        if "items" not in response or len(response["items"]) == 0:
            return None, "Video not found"

        return video_id, None
    except HttpError as e:
        return None, f"HTTP error occurred: {e}"
    except Exception as e:
        return None, f"Error validating URL: {e}"


def fetch_audio_stream(video_url):
    """Fetches the audio stream URL using yt-dlp."""
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(video_url, download=False)
            audio_url = info_dict.get("url", None)
            return audio_url, None
    except Exception as e:
        return None, str(e)


def stream_audio(audio_url):
    """Streams audio from a URL and converts it to a playable format."""
    try:
        audio_response = requests.get(audio_url, stream=True)
        audio = AudioSegment.from_file(BytesIO(audio_response.content))
        buffer = BytesIO()
        audio.export(buffer, format="mp3")
        buffer.seek(0)
        return buffer, None
    except Exception as e:
        return None, str(e)


@app.route('/get-audio', methods=['GET'])
def get_audio():
    video_url = request.args.get('url')
    if not video_url:
        return jsonify({'error': 'Missing video URL parameter'}), 400

    # Step 1: Validate the URL with YouTube Data API
    video_id, error = validate_youtube_url(video_url)
    if error:
        return jsonify({'error': error}), 400

    # Step 2: Fetch the audio stream
    audio_url, error = fetch_audio_stream(video_url)
    if error:
        return jsonify({'error': f"Failed to fetch audio stream: {error}"}), 500

    # Step 3: Stream and convert the audio
    audio_buffer, error = stream_audio(audio_url)
    if error:
        return jsonify({'error': f"Failed to process audio: {error}"}), 500

    # Step 4: Serve the audio as a stream
    return Response(audio_buffer, mimetype="audio/mp3")
    
if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
