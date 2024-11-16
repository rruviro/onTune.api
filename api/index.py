from flask import Flask, jsonify, request
import logging
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

@app.route('/get-audio-info', methods=['GET'])
def get_audio_info():
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
