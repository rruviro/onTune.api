from flask import Flask, jsonify, request
import logging
import re
import json
import requests
from bs4 import BeautifulSoup
import yt_dlp
import urllib.parse
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

# Use the API key directly
API_KEY = 'AIzaSyC_dbpXvWmDjWCAjM1VLrgJFwyeaQPnGyg'

# Build the YouTube client
youtube = build('youtube', 'v3', developerKey=API_KEY)

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
        logging.error(f"Failed to read links.txt: {str(e)}")
        return jsonify({'error': f'Failed to read links.txt: {str(e)}'}), 500

    if not playlist_urls:
        return jsonify({'error': 'No playlist URLs found in links.txt'}), 400

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


@app.route('/get-audio', methods=['GET'])
def get_audio():
    video_url = request.args.get('url')  # Get the video URL from the query parameter

    if not video_url:
        return jsonify({'error': 'Missing video URL parameter'}), 400

    # Extract the video ID from the URL
    video_id = extract_video_id(video_url)
    if not video_id:
        return jsonify({'error': 'Invalid video URL'}), 400

    # Fetch video details using YouTube Data API
    video_details = fetch_video_details(video_id)
    if 'error' in video_details:
        return jsonify(video_details), 400

    # Use yt-dlp to fetch audio URL
    audio_info = fetch_audio_url(video_url)
    if 'error' in audio_info:
        return jsonify(audio_info), 400

    # Combine video details and audio info
    response = {
        'title': video_details.get('title'),
        'description': video_details.get('description'),
        'channelTitle': video_details.get('channelTitle'),
        'audioUrl': audio_info.get('audioUrl')
    }

    return jsonify(response)


def fetch_video_details(video_id):
    """Fetch video details from YouTube Data API."""
    try:
        response = youtube.videos().list(
            part='snippet',
            id=video_id
        ).execute()

        if not response['items']:
            return {'error': 'Video not found'}

        video = response['items'][0]['snippet']
        return {
            'title': remove_parentheses(video.get('title', 'Unknown Title')),
            'description': video.get('description', 'No description'),
            'channelTitle': video.get('channelTitle', 'Unknown Channel')
        }
    except Exception as e:
        return {'error': f'YouTube API error: {str(e)}'}


def fetch_audio_url(video_url):
    """Use yt-dlp to fetch the audio URL."""
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'geo_bypass': True,
        'geo_bypass_country': 'PH',
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info_dict = ydl.extract_info(video_url, download=False)
            return {'audioUrl': info_dict.get("url")}
        except yt_dlp.utils.DownloadError as e:
            return {'error': f'YouTube DownloadError: {str(e)}'}
        except Exception as e:
            return {'error': f'General Error: {str(e)}'}


def extract_video_id(video_url):
    """Extract the video ID from the YouTube URL."""
    import re
    match = re.search(r'v=([a-zA-Z0-9_-]{11})', video_url)
    return match.group(1) if match else None

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)