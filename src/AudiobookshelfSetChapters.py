import logging

import requests

# --- CONFIGURATION ---
ABS_SERVER_URL = "http://audiobookshelf_default:80"  # Replace with your ABS URL
API_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJrZXlJZCI6IjFmMTFjZDkzLTJiMzEtNGQyZC1hMmY2LWJlZWQ2ZWU2ODBhZCIsIm5hbWUiOiJ5dC1kbHAtbWluaS13ZWIiLCJ0eXBlIjoiYXBpIiwiaWF0IjoxNzkxMzI0MzIxfQ.GOt1ITdSpYuEKyxVk3yQ6oQLAjAmQpyG3TWqNn-rM80"           # Your ABS API Token
# hardcoded until I have more libraries
LIB_NAME="Youtube Library"
LIB_ID="7fe5a9dd-b601-4b20-86de-97be1fc5ce74"

headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json"
}

logger = logging.getLogger(__name__)

def get_library_id(lib_name):
    """Fetches all libraries and returns the ID matching lib_name."""
    url = f"{ABS_SERVER_URL}/api/libraries"
    response = requests.get(url, headers=headers)
    response.raise_for_status()

    data = response.json()
    for library in data.get("libraries", []):
        if library.get("name") == lib_name:
            return library.get("id")
    return None

def get_book_id(lib_id, book_name):
    """Searches the library for a book title and returns its ID."""
    url = f"{ABS_SERVER_URL}/api/libraries/{lib_id}/search"
    params = {"q": book_name}

    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()

    data = response.json()
    # Check inside the bookResults array
    book_results = data.get("book", [])
    if book_results:
        # Grab the first match's library item ID
        return book_results[0].get("libraryItem", {}).get("id")
    return None

def auto_set_chapters_from_tracks(book_id):
    # 1. Fetch the latest track information for the library item
    item_url = f"{ABS_SERVER_URL}/api/items/{book_id}"
    response = requests.get(item_url, headers=headers)
    
    if response.status_code != 200:
        logger.warning(f"Failed to fetch item metadata: {response.text}")
        return

    book_data = response.json()
    
    # 2. Extract track information to map into chapters
    # ABS calculates absolute start/end times chronologically across tracks
    audio_tracks = book_data.get("media", {}).get("audioFiles", [])
    if not audio_tracks:
        logger.warning("No audio tracks found for this item.")
        return

    chapters_payload = []
    current_time = 0.0
    
    # Sort tracks by their sequence (disc number, then track number)
    sorted_tracks = sorted(audio_tracks, key=lambda t: t.get("addedAt", 0))

    for idx, track in enumerate(sorted_tracks):
        duration = float(track.get("duration", 0.0))
        end_time = current_time + duration
        
        # Use filename or ID3 title tag for the chapter name
        title = f"{idx+1} {track.get('metadata', {}).get("filename")}"
        
        chapters_payload.append({
            "id": idx,
            "start": current_time,
            "end": end_time,
            "title": title
        })
        current_time = end_time

    # 3. Post the mapped chapters back into Audiobookshelf
    chapters_url = f"{ABS_SERVER_URL}/api/items/{book_id}/chapters"
    payload = {"chapters": chapters_payload}
    
    update_response = requests.post(chapters_url, headers=headers, json=payload)
    if update_response.status_code == 200 and update_response.json().get("success"):
        logger.info(f"Successfully mapped {len(chapters_payload)} track files to chapters!")
    else:
        logger.info(f"Failed to update chapters: {update_response.text}")

def setChapByFiles(book_name):
    book_id = get_book_id(LIB_ID, book_name)
    auto_set_chapters_from_tracks(book_id)

if __name__ == "__main__":
    # auto_set_chapters_from_tracks()
    lib_name = "Youtube Library"
    book_name = "预备2"
    lib_id = get_library_id(lib_name)
    logger.info(lib_name + " id = " + lib_id)
    book_id = get_book_id(lib_id, book_name)
    logger.info(book_name + " id = " + book_id)
    auto_set_chapters_from_tracks(book_id)

