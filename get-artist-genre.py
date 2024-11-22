from dotenv import load_dotenv
import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from tabulate import tabulate
from typing import List

load_dotenv()

client_id = os.getenv('SPOTIFY_CLIENT_ID')
client_secret = os.getenv('SPOTIFY_SECRET')

spotify = spotipy.Spotify(
    client_credentials_manager=SpotifyClientCredentials(
        client_id=client_id,
        client_secret=client_secret
    )
)

def get_artist_genres(artist_id: str) -> List[str]:
    try:
        artist_info = spotify.artist(artist_id)
        return artist_info['genres']
    except Exception as e:
        print(f"Error fetching artist info: {e}")
        return []

def print_genres_table(artist_id: str) -> None:
    # Get artist name and genres
    artist_info = spotify.artist(artist_id)
    artist_name = artist_info['name']
    genres = get_artist_genres(artist_id)
    
    # Prepare data for tabulate
    table_data = [[i+1, genre] for i, genre in enumerate(genres)]
    headers = ['#', 'Genre']
    
    # Print artist name and table
    print(f"\nArtist: {artist_name}")
    print(tabulate(table_data, headers=headers, tablefmt='grid'))

def main():
    print("Spotify Artist Genre Lookup")
    print("-" * 25)
    
    while True:
        artist_id = input("\nEnter Spotify Artist ID (or 'q' to quit): ").strip()
        
        if artist_id.lower() == 'q':
            break
            
        try:
            print_genres_table(artist_id)
        except Exception as e:
            print(f"Error: {e}")
            print("Please check if the Artist ID is correct.")

if __name__ == "__main__":
    main()
