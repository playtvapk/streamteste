import xml.etree.ElementTree as ET
import logging
import re
import requests

# Set up logging to show only info and above
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def parse_xml(file_path):
    """Parse the XML file and extract channel information."""
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()

        channels = []
        for channel in root.findall('channel'):
            channel_info = {
                'name': (channel.find('channel-name').text or '').strip() if channel.find('channel-name') is not None else 'Unknown',
                'tvg-id': (channel.find('tvg-id').text or '').strip() if channel.find('tvg-id') is not None else 'Unknown',
                'tvg-name': (channel.find('tvg-name').text or '').strip() if channel.find('tvg-name') is not None else 'Unknown',
                'tvg-logo': (channel.find('tvg-logo').text or '').strip() if channel.find('tvg-logo') is not None else '',
                'group-title': (channel.find('group-title').text or '').strip() if channel.find('group-title') is not None else 'General',
                'youtube-url': (channel.find('youtube-url').text or '').strip() if channel.find('youtube-url') is not None else ''
            }
            if channel_info['youtube-url']:
                channels.append(channel_info)
            else:
                logging.warning(f"Skipping channel '{channel_info['name']}' due to missing YouTube URL.")
        return channels
    except Exception as e:
        logging.error(f'Failed to parse XML file: {str(e)}')
        return None

def extract_youtube_stream(youtube_url):
    """Extract the live HLS stream URL from a YouTube URL."""
    try:
        # Simulate a request to YouTube to extract the HLS m3u8 link
        response = requests.get(youtube_url)
        if response.status_code != 200:
            logging.error(f"Failed to access YouTube URL {youtube_url}. HTTP Status: {response.status_code}")
            return None

        # Match the HLS m3u8 URL in the page content
        hls_match = re.search(r'https?://[^\s]+\.m3u8', response.text)
        if hls_match:
            return hls_match.group(0)
        else:
            logging.warning(f"No HLS m3u8 link found for {youtube_url}.")
            return None
    except Exception as e:
        logging.error(f"Error extracting stream for {youtube_url}: {str(e)}")
        return None

def generate_m3u(channels, output_file):
    """Generate an M3U playlist from channel information."""
    try:
        with open(output_file, 'w') as m3u:
            m3u.write('#EXTM3U\n')
            for channel in channels:
                stream_url = extract_youtube_stream(channel['youtube-url'])
                if stream_url:
                    # Write the HLS URL only (without extra data)
                    m3u.write(f'#EXTINF:-1 tvg-id="{channel["tvg-id"]}" tvg-name="{channel["tvg-name"]}" '
                              f'tvg-logo="{channel["tvg-logo"]}" group-title="{channel["group-title"]}",' 
                              f'{channel["name"]}\n')
                    # Output only the value of hlsManifestUrl without quotes
                    hls_url = stream_url.split('hlsManifestUrl":"')[1].split('"')[0]
                    m3u.write(f'{hls_url}\n')
                    logging.info(f"{channel['name']} exported successfully")
                else:
                    logging.warning(f"Failed to export {channel['name']}. Stream URL not found.")
    except Exception as e:
        logging.error(f'Failed to generate M3U file: {str(e)}')

if __name__ == '__main__':
    xml_file = 'youtubelinks.xml'
    output_m3u = 'youtube_output.m3u'

    channels = parse_xml(xml_file)
    if channels:
        generate_m3u(channels, output_m3u)
    else:
        logging.error('No channels found. Exiting.')
