from flask import Flask, jsonify, request
import logging
import urllib.parse
import yt_dlp

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

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

        # Clean and validate the URL
        decoded_url = urllib.parse.unquote(video_url)
        if 'youtube.com/watch?v=' not in decoded_url and 'youtu.be/' not in decoded_url and 'music.youtube.com' not in decoded_url:
            return jsonify({'error': 'Invalid YouTube URL'}), 400

        return extract_audio_info(decoded_url)
    except Exception as e:
        logging.error(f"Error in get_audio_info: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500

def extract_audio_info(video_url):
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'no_warnings': True,
            'quiet': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            
            if info is None:
                return jsonify({'error': 'Unable to extract video information'}), 400

            if 'entries' in info:
                # It's a playlist or a channel, we'll just use the first video
                video = info['entries'][0]
            else:
                video = info

            if video.get('is_live'):
                return jsonify({'error': 'Live videos are not supported'}), 400

            if video.get('age_limit', 0) > 0:
                return jsonify({'error': 'Age-restricted videos are not supported'}), 400

            audio_formats = [f for f in video['formats'] if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
            best_audio = max(audio_formats, key=lambda f: f.get('abr', 0))

            return jsonify({
                'title': video['title'],
                'uploader': video.get('uploader', 'Unknown'),
                'duration': video.get('duration'),
                'audioUrl': best_audio['url'],
                'format': best_audio['format'],
                'acodec': best_audio['acodec'],
                'abr': best_audio.get('abr')
            })

    except yt_dlp.utils.DownloadError as e:
        logging.error(f"yt-dlp error: {str(e)}")
        return jsonify({'error': f'Video info extraction failed: {str(e)}'}), 400
    except Exception as e:
        logging.error(f"Error in extract_audio_info: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
