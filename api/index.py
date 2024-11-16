import json
from flask import Flask, jsonify, request
import logging
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
            # First, just extract the info without downloading
            info = ydl.extract_info(video_url, download=False)
            
            if info is None:
                return jsonify({'error': 'Unable to extract video information'}), 400

            # Check if the video is available
            if 'entries' in info:
                # It's a playlist or a channel, we'll just use the first video
                video = info['entries'][0]
            else:
                video = info

            if video.get('is_live'):
                return jsonify({'error': 'Live videos are not supported'}), 400

            if video.get('age_limit', 0) > 0:
                return jsonify({'error': 'Age-restricted videos are not supported'}), 400

            # If we've made it this far, attempt to download
            ydl.download([video_url])

            video_id = video['id']
            title = video['title']
            uploader = video.get('uploader', 'Unknown')

        mp3_file = os.path.join(output_path, f'{video_id}.mp3')

        if not os.path.exists(mp3_file):
            return jsonify({'error': 'Failed to download audio file'}), 500

        return jsonify({
            'audioUrl': mp3_file,
            'title': title,
            'writer': uploader
        })

    except yt_dlp.utils.DownloadError as e:
        logging.error(f"yt-dlp download error: {str(e)}")
        return jsonify({'error': f'Video download failed: {str(e)}'}), 400
    except Exception as e:
        logging.error(f"Error in download_audio: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
