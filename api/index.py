import json
from flask import Flask, jsonify, request
import logging
import subprocess
import urllib.parse
import os
import yt_dlp

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    return response

@app.route('/get-audio', methods=['GET'])
def get_audio():
    try:
        video_url = request.args.get('url')
        if not video_url:
            return jsonify({'error': 'Missing video URL parameter'}), 400

        # Clean and validate the URL
        decoded_url = urllib.parse.unquote(video_url)
        if 'youtube.com/watch?v=' not in decoded_url and 'youtu.be/' not in decoded_url:
            return jsonify({'error': 'Invalid YouTube URL'}), 400

        return download_audio_with_ytdlp(decoded_url)
    except Exception as e:
        logging.error(f"Error in get_audio: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500

def download_audio_with_ytdlp(video_url):
    try:
        output_path = '/tmp'
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': os.path.join(output_path, '%(id)s.%(ext)s'),
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            video_id = info['id']
            title = info['title']
            uploader = info['uploader']

        mp3_file = os.path.join(output_path, f'{video_id}.mp3')

        return jsonify({
            'audioUrl': mp3_file,
            'title': title,
            'writer': uploader
        })

    except Exception as e:
        logging.error(f"Error in download_audio: {str(e)}")
        return jsonify({'error': f'Download error: {str(e)}'}), 500

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)