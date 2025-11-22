import yt_dlp
import sys
import os

def download_short(url):
    """
    Downloads a YouTube Short in HD MP4 format.
    """
    # Get the absolute path to the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Options for yt-dlp
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',  # Ensure MP4 and best quality
        'outtmpl': os.path.join(script_dir, '%(title)s.%(ext)s'),  # Save to script's directory
        'noplaylist': True,  # Download only single video
        'quiet': False,
        'no_warnings': True,
        # Speed optimizations (though yt-dlp is already fast)
        'concurrent_fragment_downloads': 5, 
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"Downloading: {url}")
            info_dict = ydl.extract_info(url, download=True)
            video_title = info_dict.get('title', 'Unknown Title')
            
            # Sanitize title for printing to avoid charmap errors on Windows consoles
            safe_title = video_title.encode('ascii', 'ignore').decode('ascii')
            print(f"\nSuccess! Downloaded: {safe_title}")
            print("File saved in the current directory.")
    except Exception as e:
        print(f"Error downloading video: {e}")

if __name__ == "__main__":
    # Enable UTF-8 output for Windows console if possible
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8')

    print("--- YouTube Shorts Downloader ---")
    
    # Check if URL is passed as command line argument
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = input("Enter the YouTube Short URL: ").strip()

    if url:
        download_short(url)
    else:
        print("No URL provided. Exiting.")
