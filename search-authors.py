from dotenv import load_dotenv
import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from tabulate import tabulate
from typing import List, Dict

load_dotenv()

client_id = os.getenv('SPOTIFY_CLIENT_ID')
client_secret = os.getenv('SPOTIFY_SECRET')

spotify = spotipy.Spotify(
    client_credentials_manager=SpotifyClientCredentials(
        client_id=client_id,
        client_secret=client_secret
    )
)

def search_artists(query: str) -> List[Dict]:
    try:
        results = spotify.search(q=query, type='artist', limit=10)
        return results['artists']['items']
    except Exception as e:
        print(f"Error searching artists: {e}")
        return []

def print_artists_table(artists: List[Dict]) -> None:
    if not artists:
        print("\nNo artists found matching your search.")
        return
    
    table_data = []
    for i, artist in enumerate(artists, 1):
        followers = format(artist['followers']['total'], ',')
        table_data.append([
            i,
            artist['name'],
            artist['id'],
            followers,
            artist['popularity']
        ])
    
    headers = ['#', 'Artist Name', 'Artist ID', 'Followers', 'Popularity']
    print(tabulate(table_data, headers=headers, tablefmt='grid'))

def main():
    print("Spotify Artist Search Tool")
    print("-" * 25)
    
    while True:
        search_query = input("\nEnter artist name to search (or 'q' to quit): ").strip()
        
        if search_query.lower() == 'q':
            break
            
        if not search_query:
            print("Please enter a search term.")
            continue
            
        try:
            artists = search_artists(search_query)
            print_artists_table(artists)
        except Exception as e:
            print(f"Error: {e}")
            print("Please try a different search term.")

if __name__ == "__main__":
    main()
