import json
from pytube import YouTube
from flask import Flask, jsonify, request
import logging
import subprocess
import urllib.parse
import os

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

        # Extract video ID
        if 'youtube.com/watch?v=' in decoded_url:
            video_id = decoded_url.split('watch?v=')[1].split('&')[0]
        else:
            video_id = decoded_url.split('youtu.be/')[1].split('?')[0]

        # Reconstruct clean URL
        clean_url = f'https://youtube.com/watch?v={video_id}'
        
        return download_audio_with_pytube(clean_url)
    except Exception as e:
        logging.error(f"Error in get_audio: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500

def download_audio_with_pytube(video_url):
    try:
        yt = YouTube(video_url)
        
        # Get the audio stream
        stream = yt.streams.filter(only_audio=True).first()
        if not stream:
            return jsonify({'error': 'No audio stream available'}), 400

        # Create unique filename using video ID
        video_id = video_url.split('watch?v=')[1]
        output_path = '/tmp'
        temp_file = os.path.join(output_path, f'{video_id}.mp4')
        
        # Download the audio
        stream.download(output_path=output_path, filename=f'{video_id}.mp4')
        
        # Convert to MP3
        mp3_file = os.path.join(output_path, f'{video_id}.mp3')
        subprocess.run(['ffmpeg', '-i', temp_file, '-vn', '-acodec', 'libmp3lame', mp3_file], check=True)
        
        # Clean up the temporary file
        if os.path.exists(temp_file):
            os.remove(temp_file)

        return jsonify({
            'audioUrl': mp3_file,
            'title': yt.title,
            'writer': yt.author
        })

    except subprocess.CalledProcessError as e:
        logging.error(f"FFmpeg error: {str(e)}")
        return jsonify({'error': 'Error converting audio'}), 500
    except Exception as e:
        logging.error(f"Error in download_audio: {str(e)}")
        return jsonify({'error': f'Download error: {str(e)}'}), 500

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)