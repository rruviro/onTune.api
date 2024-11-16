from flask import Flask, jsonify, request
import logging
import urllib.parse
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

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
# Use the environment variable
API_KEY = os.environ.get('AIzaSyC_dbpXvWmDjWCAjM1VLrgJFwyeaQPnGyg')

# Only build the YouTube client if API_KEY is available
youtube = build('youtube', 'v3', developerKey=API_KEY) if API_KEY else None

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    return response

@app.route('/get-audio-info', methods=['GET'])
def get_audio_info():
    if not youtube:
        return jsonify({'error': 'YouTube API key not configured'}), 500

    try:
        video_url = request.args.get('url')
        if not video_url:
            return jsonify({'error': 'Missing video URL parameter'}), 400

        video_id = extract_video_id(video_url)
        if not video_id:
            return jsonify({'error': 'Invalid YouTube URL'}), 400

        return fetch_video_info(video_id)
    except Exception as e:
        logging.error(f"Error in get_audio_info: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500

def extract_video_id(url):
    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.hostname in ('youtu.be', 'www.youtu.be'):
        return parsed_url.path[1:]
    if parsed_url.hostname in ('youtube.com', 'www.youtube.com', 'music.youtube.com'):
        if 'v' in urllib.parse.parse_qs(parsed_url.query):
            return urllib.parse.parse_qs(parsed_url.query)['v'][0]
    return None

def fetch_video_info(video_id):
    try:
        response = youtube.videos().list(
            part='snippet,contentDetails',
            id=video_id
        ).execute()

        if not response['items']:
            return jsonify({'error': 'Video not found'}), 404

        video_info = response['items'][0]
        snippet = video_info['snippet']
        content_details = video_info['contentDetails']

        return jsonify({
            'title': snippet['title'],
            'uploader': snippet['channelTitle'],
            'duration': content_details['duration'],
            'thumbnail': snippet['thumbnails']['high']['url'],
            'description': snippet['description']
        })

    except HttpError as e:
        logging.error(f"YouTube API error: {str(e)}")
        return jsonify({'error': f'YouTube API error: {str(e)}'}), 400

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
