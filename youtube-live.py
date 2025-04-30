import subprocess
import json
import logging
from flask import Flask, request, Response, jsonify
from urllib.parse import quote

app = Flask(__name__)

# Set up logging to show info, warnings, and errors
logging.basicConfig(level=logging.INFO)

@app.route('/stream', methods=['GET'])
def stream():
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'URL parameter is required'}), 400

    try:
        # Ensure URL is properly encoded
        url = quote(url, safe=':/?=&')
        
        # Get stream info with more detailed output
        info_command = ['streamlink', '--json', '--loglevel', 'debug', url]
        info_process = subprocess.Popen(info_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        info_output, info_error = info_process.communicate()

        if info_process.returncode != 0:
            try:
                error_msg = info_error.decode('utf-8', errors='replace')
            except Exception as e:
                error_msg = f"Failed to decode error message: {str(e)}"
            logging.error(f'Streamlink error: {error_msg}')
            return jsonify({'error': 'Failed to retrieve stream info', 'details': error_msg}), 500

        # Parse the JSON output
        try:
            stream_info = json.loads(info_output.decode('utf-8', errors='replace'))
        except json.JSONDecodeError as e:
            logging.error(f'JSON decode error: {str(e)}')
            return jsonify({'error': 'Failed to parse stream info'}), 500

        # Check if streams are available
        if 'streams' not in stream_info or not stream_info['streams']:
            if 'youtube.com' in url.lower() or 'youtu.be' in url.lower():
                yt_command = ['youtube-dl', '--get-url', '--youtube-skip-dash-manifest', url]
                yt_process = subprocess.Popen(yt_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                yt_url, yt_error = yt_process.communicate()
                
                if yt_process.returncode != 0:
                    try:
                        error_msg = yt_error.decode('utf-8', errors='replace')
                    except Exception as e:
                        error_msg = f"Failed to decode error message: {str(e)}"
                    logging.error(f'youtube-dl error: {error_msg}')
                    return jsonify({'error': 'No valid streams found'}), 404
                
                url = yt_url.decode('utf-8', errors='replace').strip()
                info_command = ['streamlink', '--json', url]
                info_process = subprocess.Popen(info_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                info_output, info_error = info_process.communicate()
                try:
                    stream_info = json.loads(info_output.decode('utf-8', errors='replace'))
                except json.JSONDecodeError as e:
                    logging.error(f'JSON decode error: {str(e)}')
                    return jsonify({'error': 'Failed to parse stream info'}), 500

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
        client_ip = request.remote_addr  # Get client IP for logging

        def generate():
            try:
                logging.info(f"Starting stream for client {client_ip} from {url}")
                while True:
                    data = process.stdout.read(4096)
                    if not data:
                        break
                    yield data
            except GeneratorExit:
                # Log when client disconnects
                logging.info(f"Client {client_ip} disconnected from stream {url}")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                finally:
                    process.stdout.close()
                    process.stderr.close()
            except Exception as e:
                logging.error(f'Error in generator for {client_ip}: {str(e)}')
                process.terminate()
                process.stdout.close()
                process.stderr.close()

        # Create response with cleanup
        response = Response(generate(), content_type='video/mp2t')
        
        @response.call_on_close
        def cleanup():
            if process.poll() is None:  # Process is still running
                logging.info(f"Cleaning up stream process for client {client_ip} from {url}")
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