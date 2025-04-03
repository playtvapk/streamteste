import subprocess
import json
import logging
from flask import Flask, request, Response, jsonify
import signal
import os

app = Flask(__name__)

# Set up logging to only show warnings and errors
logging.basicConfig(level=logging.WARNING)

@app.route('/stream', methods=['GET'])
def stream():
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'URL parameter is required'}), 400

    try:
        # Get stream info with more detailed output
        info_command = ['streamlink', '--json', '--loglevel', 'debug', url]
        info_process = subprocess.Popen(info_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        info_output, info_error = info_process.communicate()

        if info_process.returncode != 0:
            error_msg = info_error.decode()
            logging.error(f'Streamlink error: {error_msg}')
            return jsonify({'error': 'Failed to retrieve stream info', 'details': error_msg}), 500

        # Parse the JSON output
        stream_info = json.loads(info_output)

        # Check if streams are available
        if 'streams' not in stream_info or not stream_info['streams']:
            if 'youtube.com' in url.lower() or 'youtu.be' in url.lower():
                yt_command = ['youtube-dl', '--get-url', '--youtube-skip-dash-manifest', url]
                yt_process = subprocess.Popen(yt_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                yt_url, yt_error = yt_process.communicate()
                
                if yt_process.returncode != 0:
                    logging.error(f'youtube-dl error: {yt_error.decode()}')
                    return jsonify({'error': 'No valid streams found'}), 404
                
                url = yt_url.decode().strip()
                info_command = ['streamlink', '--json', url]
                info_process = subprocess.Popen(info_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                info_output, info_error = info_process.communicate()
                stream_info = json.loads(info_output)

        best_quality = stream_info['streams'].get('best')
        if not best_quality:
            return jsonify({'error': 'No valid streams found'}), 404

        # Command to run Streamlink
        command = [
            'streamlink',
            url,
            'best',
            '--hls-live-restart',
            '--stdout'
        ]

        # Start the subprocess
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        def generate():
            try:
                while True:
                    data = process.stdout.read(4096)
                    if not data:
                        break
                    yield data
            except GeneratorExit:
                # Client disconnected, terminate the process
                process.terminate()
                try:
                    process.wait(timeout=5)  # Give it 5 seconds to terminate gracefully
                except subprocess.TimeoutExpired:
                    process.kill()  # Force kill if it doesn't terminate
                finally:
                    process.stdout.close()
                    process.stderr.close()
            except Exception as e:
                logging.error(f'Error in generator: {str(e)}')
                process.terminate()
                process.stdout.close()
                process.stderr.close()

        # Create response with cleanup
        response = Response(generate(), content_type='video/mp2t')
        
        @response.call_on_close
        def cleanup():
            if process.poll() is None:  # Process is still running
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                finally:
                    process.stdout.close()
                    process.stderr.close()

        return response

    except Exception as e:
        logging.error(f'Error occurred: {str(e)}')
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=6095)