from flask import Flask, jsonify, request
import logging
import re
import json
import googleapiclient
import requests
from bs4 import BeautifulSoup
import yt_dlp
import urllib.parse
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os
import google.auth
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

# Use the API key directly
API_KEY = 'AIzaSyCS0pKbLr2CmaxsQmHBerQnfkD8f8hZ8w4'
# Build the YouTube client
youtube = build('youtube', 'v3', developerKey=API_KEY)

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    return response

def extract_playlist_id(url):
    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.hostname in ('youtube.com', 'www.youtube.com', 'music.youtube.com'):
        query = urllib.parse.parse_qs(parsed_url.query)
        return query.get('list', [None])[0]
    return None

# Function to extract playlist info
def get_playlist_info(playlist_url):
    ydl_opts = {
        'quiet': True,  # Suppress all logs
        'extract_flat': True,  # Only extract playlist info (without downloading)
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Extract playlist info
            playlist_info = ydl.extract_info(playlist_url, download=False)

            if 'entries' in playlist_info:
                # Extract details for each song in the playlist
                song_info = [
                    {
                        'title': entry['title'], 
                        'writer': entry.get('uploader') or entry.get('artist') or entry.get('creator', 'Unknown'),
                        'url': f"https://www.youtube.com/watch?v={entry['id']}",
                        'image_url': entry.get('thumbnails', [{}])[-1].get('url', ''),  # Get highest resolution thumbnail URL
                        'playlistUrl': playlist_url  # Add the playlist URL to each song
                    } for entry in playlist_info['entries']
                ]
                song_count = len(song_info)  # Total count of songs
                
                return {'songCount': song_count, 'songInfo': song_info}
            else:
                return {'error': 'No entries found in the playlist'}
    except Exception as e:
        return {'error': str(e)}

# Route for the playlist endpoint
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
        result = get_playlist_info(playlist_url)
        if isinstance(result, dict) and 'songInfo' in result:
            all_songs_info.extend(result['songInfo'])
        elif 'error' in result:
            logging.error(f"Error processing playlist {playlist_url}: {result['error']}")

    return jsonify({
        'songCount': len(all_songs_info),
        'songInfo': all_songs_info
    })

YOUTUBE_API_KEY = 'AIzaSyC5ypUn4Wg8kZ_9Q2k6PTa2FBKq6aChZcc'
# Initialize the YouTube Data API client
youtube = googleapiclient.discovery.build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

def extract_video_id(video_url):
    parsed_url = urlparse(video_url)
    if "youtube.com" in video_url:
        return parse_qs(parsed_url.query).get("v", [None])[0]
    elif "youtu.be" in video_url:
        return parsed_url.path.lstrip("/")
    return None

def fetch_video_metadata(video_id):
    try:
        response = youtube.videos().list(part="snippet,contentDetails,status", id=video_id).execute()
        if not response.get('items'):
            return None
        item = response['items'][0]
        return {
            'title': item['snippet']['title'],
            'uploader': item['snippet']['channelTitle'],
            'duration': item['contentDetails']['duration'],
            'is_embeddable': item['status'].get('embeddable', True),
            'availability': item['status']['uploadStatus'],
            'privacyStatus': item['status'].get('privacyStatus', 'public'),
        }
    except Exception as e:
        print(f"YouTube API error: {e}")
        return None

def extract_audio_stream(video_url):
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)
        audio_url = next((f['url'] for f in info['formats'] if f['ext'] in ['m4a', 'mp3', 'webm']), None)
        if not audio_url:
            raise ValueError("No audio stream found")
        return {
            'audioUrl': audio_url,
            'title': info.get('title', 'Unknown Title'),
            'uploader': info.get('uploader', 'Unknown Uploader'),
            'duration': info.get('duration', 0),
        }

@app.route('/get-audio', methods=['GET'])
def get_audio():
    video_url = request.args.get('url')
    if not video_url:
        return jsonify({'error': 'Missing video URL parameter'}), 400
    
    video_id = extract_video_id(video_url)
    if not video_id:
        return jsonify({'error': 'Invalid YouTube URL'}), 400
    
    metadata = fetch_video_metadata(video_id)
    if not metadata or metadata.get('privacyStatus') != 'public':
        return jsonify({'error': 'Video is unavailable or restricted'}), 400
    
    try:
        audio_info = extract_audio_stream(video_url)
        return jsonify(audio_info)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
