# Spotify API Tools

This project provides tools to interact with the Spotify API, allowing users to search for artists and retrieve their genres.

## Features

- **Search Artists**: Search for artists by name and display their details (such as artist ID) in a tabulated format.
- **Get Artist Genres**: Retrieve and display the genres associated with a specific artist. Requires artist ID

## Requirements

- Python 3.6+
- Spotipy
- Python-dotenv
- Tabulate

## Setup

1. Clone the repository:
    ```sh
    git clone https://github.com/yourusername/spotify-api-tools.git
    cd spotify-api-tools
    ```

2. Create a virtual environment and activate it:
    ```sh
    python -m venv .venv
    source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`
    ```

3. Install the required packages:
    ```sh
    pip install -r requirements.txt
    ```

4. Create a `.env` file in the root directory and add your Spotify API credentials:
    ```env
    SPOTIFY_CLIENT_ID="your_client_id"
    SPOTIFY_SECRET="your_client_secret"
    ```

## Usage

### Search Artists

Run the `search-authors.py` script to search for artists by name and get their ID:

```sh
python search-authors.py
```

#### Example Usage

```sh
python search-authors.py                                                                                                                                                                ─╯
Spotify Artist Search Tool
-------------------------

Enter artist name to search (or 'q' to quit): Taylor Swift
+-----+----------------------------------------+------------------------+-------------+--------------+
|   # | Artist Name                            | Artist ID              | Followers   |   Popularity |
+=====+========================================+========================+=============+==============+
|   1 | Taylor Swift                           | 06HL4z0CvFAxyc27GXpf02 | 126,340,960 |          100 |
+-----+----------------------------------------+------------------------+-------------+--------------+
|   2 | Salish Matter                          | 4CB8mmEbDXVxkzNpJgkj65 | 243,719     |           34 |
+-----+----------------------------------------+------------------------+-------------+--------------+
|   3 | Taylor Swift Piano Covers              | 0DwbGCdaD8YLRiVUEiV70Q | 3,970       |           33 |
+-----+----------------------------------------+------------------------+-------------+--------------+
|   4 | Olivia Rodrigo                         | 1McMsnEElThX1knmY4oliG | 41,413,747  |           89 |
+-----+----------------------------------------+------------------------+-------------+--------------+
|   5 | Taylor Swift - Evermore - Piano Covers | 3vZoN5cnYOycsJ5KsFkjo5 | 200         |            5 |
+-----+----------------------------------------+------------------------+-------------+--------------+
|   6 | Tate McRae                             | 45dkTj5sMRSjrmBSBeiHym | 6,234,266   |           86 |
+-----+----------------------------------------+------------------------+-------------+--------------+
|   7 | taylorr swiftt                         | 7oW3aIseIypoEqcOqvzUfS | 126         |            7 |
+-----+----------------------------------------+------------------------+-------------+--------------+
|   8 | Kidz Bop Kids                          | 1Vvvx45Apu6dQqwuZQxtgW | 1,268,993   |           68 |
+-----+----------------------------------------+------------------------+-------------+--------------+
|   9 | Brandon Taylor Smith                   | 0CkM1sLkP3yQW8I7ja51am | 95          |           35 |
+-----+----------------------------------------+------------------------+-------------+--------------+
|  10 | Adele                                  | 4dpARuHxo51G3z768sgnrY | 60,292,280  |           87 |
+-----+----------------------------------------+------------------------+-------------+--------------+
```

### Get Artist Genres

Use IDs from `search-authors.py` as input to this script

```sh
# Provide desired artist ID
python get-artist-genre.py
```

#### Example Usage

```sh
python get-artist-genre.py                                                                                                                                                              ─╯
Spotify Artist Genre Lookup
-------------------------

Enter Spotify Artist ID (or 'q' to quit): 06HL4z0CvFAxyc27GXpf02

Artist: Taylor Swift
+-----+---------+
|   # | Genre   |
+=====+=========+
|   1 | pop     |
+-----+---------+
```