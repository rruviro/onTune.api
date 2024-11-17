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


YOUTUBE_API_KEY = 'AIzaSyCS0pKbLr2CmaxsQmHBerQnfkD8f8hZ8w4'
# Initialize the YouTube Data API client
youtube = googleapiclient.discovery.build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

@app.route('/get-audio', methods=['GET'])
def get_audio():
    video_url = request.args.get('url')
    if not video_url:
        return jsonify({'error': 'Missing video URL parameter'}), 400

    print(f"Received video URL: {video_url}")

    video_id = extract_video_id(video_url)
    if not video_id:
        return jsonify({'error': 'Invalid YouTube URL'}), 400

    try:
        # Fetch video metadata using the YouTube Data API
        metadata = fetch_video_metadata(video_id)
        if not metadata:
            return jsonify({'error': 'Unable to fetch video metadata or video is unavailable'}), 400
        
        print(f"Video Metadata: {metadata}")
        
        # Check if video is embeddable or restricted
        if not metadata.get('is_embeddable', False):
            print("Video is not embeddable, but audio extraction will continue.")
        
        # Check if video is available before attempting to extract audio
        if not is_video_available(metadata):
            return jsonify({'error': 'Video is unavailable or restricted'}), 400

        # Extract audio info using yt-dlp
        audio_info = extract_audio_stream(video_url)
        print(f"Extracted Audio Info: {audio_info}")
        return jsonify(audio_info)
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'error': f'Error processing request: {str(e)}'}), 500


def extract_video_id(video_url):
    """Extract video ID from YouTube URL."""
    if "youtube.com/watch?v=" in video_url:
        video_id = video_url.split("v=")[-1]
        return video_id
    elif "youtu.be/" in video_url:
        video_id = video_url.split("/")[-1]
        return video_id
    return None


def fetch_video_metadata(video_id):
    """Fetch video metadata using YouTube Data API."""
    try:
        request = youtube.videos().list(
            part="snippet,contentDetails",
            id=video_id
        )
        response = request.execute()

        if not response.get('items'):
            return None

        snippet = response['items'][0]['snippet']
        content_details = response['items'][0]['contentDetails']

        return {
            'title': snippet['title'],
            'uploader': snippet['channelTitle'],
            'duration': content_details['duration'],
            'is_embeddable': snippet.get('embeddable', False),  # Check if the video is embeddable
            'availability': response['items'][0].get('status', {}).get('uploadStatus', 'processed')  # Check availability
        }
    
    except googleapiclient.errors.HttpError as e:
        print(f"YouTube API error: {str(e)}")
        return None


def is_video_available(metadata):
    """Check if video is available (not deleted, private, or restricted)."""
    # Ensure availability status is processed (uploaded and not deleted)
    return metadata.get('availability') == 'processed'


def extract_audio_stream(video_url):
    """Extract audio stream URL and metadata using yt-dlp."""
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'skip_download': True,
        'no_warnings': True,
        'extract_flat': False
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            # Attempt to fetch video information
            info_dict = ydl.extract_info(video_url, download=False)
            print(f"Video info fetched successfully: {info_dict}")
        except yt_dlp.utils.DownloadError as e:
            print(f"DownloadError: {str(e)}")
            raise

        # Find the best audio stream
        audio_url = next(
            (f['url'] for f in info_dict['formats'] if f['ext'] in ['m4a', 'mp3', 'webm']), None
        )
        if not audio_url:
            raise ValueError("No audio stream found")

        return {
            'audioUrl': audio_url,
            'title': info_dict.get('title', 'Unknown Title'),
            'writer': info_dict.get('uploader', 'Unknown Uploader'),
            'duration': info_dict.get('duration', 0)  # Duration in seconds
        }


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)