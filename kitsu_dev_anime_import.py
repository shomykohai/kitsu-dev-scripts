import askitsu
import asyncio
import asyncpg
import enum
import json
import traceback
import typing

from colorama import Fore, Style
from datetime import datetime

"""
FILL ALL THE FIELDS WITH YOUR 
LOCAL DEV ENVIRONMENT INFORMATIONS
"""

KITSU_DB_NAME = "kitsu_development"
KITSU_DB_USER = "kitsu_development"
HOST = "INSERT POSTGRES HOST"
"""
To get postgres host if you're using
docker, do in your kitsu-tools folder:

docker container ls (To get the ID of "kitsu-tools-postgres")
docker inspect <ID-of-postgres-container>

And then search for "IPAddress" and paste it
inside the HOST string
"""


class Subtype(enum.Enum):
    TV: int = 0
    SPECIAL: int = 1
    OVA: int = 2
    ONA: int = 3
    MOVIE: int = 4
    MUSIC: int = 5


class AgeRating(enum.Enum):
    G: int = 0
    PG: int = 1
    R: int = 2
    R18: int = 3


class CharacterRole(enum.Enum):
    MAIN: int = 0
    RECURRING: int = 1
    BACKGROUND: int = 2
    CAMEO: int = 3


gqlquery = """
query anime($cursor: String){
  anime(first: 100, after: $cursor){
    edges{
      cursor
    }
    nodes{
        id
        slug
        createdAt
        updatedAt
        startDate
        endDate
        description
        status
        sfw
        animesub: subtype
        ageRating
        endDate
        season
        episodeCount
        episodeLength
        totalLength
        youtubeTrailerVideoId
        averageRatingRank
        averageRating
        userCountRank
        titles{
            canonical
            localized
        }
        tba
      	favoritesCount
      	originCountries
      	originLanguages
      	userCount
        ageRatingGuide
      	characters(first:1000){
          nodes{
            role
            createdAt
            updatedAt
            character{
              id
              names{
                localized
                canonical
              }
              createdAt
              updatedAt
              slug
              description
            }
          }
        }
      	categories(first: 100){
          nodes{
            id
          }
        }
      
    }
  }
}
"""

query_anime = """INSERT INTO public.anime(
    id,
    slug,
    age_rating,
    episode_count,
    episode_length,
    description,
    youtube_video_id,
    created_at,
    updated_at,
    average_rating,
    user_count,
    age_rating_guide,
    subtype,
    start_date,
    end_date,
    titles,
    canonical_title,
    popularity_rank,
    rating_rank,
    favorites_count,
    tba,
    episode_count_guess,
    total_length,
    origin_languages,
    origin_countries,
    original_locale
  )
	VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26);"""

query_genres = """
  INSERT INTO public.anime_genres(
  anime_id,
  genre_id
  )
  VALUES ($1, $2)
"""

query_anime_character = """
  INSERT INTO public.anime_characters (
    anime_id,
    character_id,
    role,
    created_at,
    updated_at
  )
  VALUES ($1, $2, $3, $4, $5)
"""

query_character = """
  INSERT INTO public.characters(
    id,
    name,
    created_at,
    updated_at,
    slug,
    description,
    canonical_name
  )
  VALUES ($1, $2, $3, $4, $5, $6, $7)
"""

imports = 0
id = 0
next_cursor = ""
anime: typing.List[askitsu.Anime] = []


async def get_anime(kitsu_client: askitsu.Client):
    global next_cursor
    global anime
    data = await kitsu_client.http.post_data(
        {"query": gqlquery, "variables": {"cursor": next_cursor}}
    )
    next_cursor = data["data"]["anime"]["edges"][-1]["cursor"]
    animes = data["data"]["anime"]["nodes"]
    anime_gen = [
        askitsu.Anime(anime_data, kitsu_client.http, kitsu_client.http._cache)
        for anime_data in animes
    ]
    for i in anime_gen:
        if i.description is None:
            anime_gen.remove(i)
    anime += anime_gen
    print(f"Fetched {Fore.RED}{len(anime_gen)}{Style.RESET_ALL} anime.")


async def run():
    global id
    global imports
    character_id = 0

    # Initialize
    try:
        db = await asyncpg.create_pool(
            database=KITSU_DB_NAME,
            user=KITSU_DB_USER,
            host=HOST,
        )
        print("@ CONNECTED TO DB")
    except Exception as e:
        print("Could not connect to DB.")
	traceback.print_exc()
        return
    try:
        kitsu = askitsu.Client(cache_expiration=0)
        print("@ askitsu Client initialized!")
    except:
        print("Could not initialize askitsu client.")
        return

    # Fetch a bunch of anime
    for _ in range(40):
        await get_anime(kitsu_client=kitsu)

    print(f"Total fetched anime: {Fore.RED}{len(anime)}{Style.RESET_ALL}.")
    # Add the data to the database
    for media in anime:
        try:
            # Convert the data
            titles = ""
            for key, value in media._titles.items():
                if value:
                    format_str = '"{0}"=>"{1}",'.format(key, value)
                    titles += format_str
            # Execute the query - Anime data
            await db.execute(
                query_anime,
                id,
                media.slug,
                AgeRating[media.age_rating].value,
                media.episode_count,
                media.episode_length,
                json.dumps(media.description),
                media.yt_id,
                media.created_at,
                media.updated_at,
                media.rating,
                media._attributes.get("userCount", 0),
                media._attributes.get("ageRatingGuide", ""),
                Subtype[media.subtype].value,
                media.started_at,
                media.ended_at,
                titles,
                media.canonical_title,
                media.popularity_rank,
                media.rating_rank,
                media._attributes.get("favoritesCount", 0),
                media._attributes.get("tba", ""),
                media.episode_count,
                media.total_length,
                media._attributes.get("origin_languages", None),
                media._attributes.get("origin_countries", None),
                media._attributes.get("original_locale", ""),
            )

            # Execute the query - Anime Genres
            for genres in media._attributes["categories"]["nodes"]:
                try:
                    await db.execute(query_genres, id, int(genres["id"]))
                except:
                    pass

            # Execute the query - Character
            for characters in media._attributes["characters"]["nodes"]:
                try:
                    await db.execute(
                        query_character,
                        character_id,
                        characters["character"]["slug"],
                        datetime.strptime(
                            characters["character"]["createdAt"], "%Y-%m-%dT%H:%M:%SZ"
                        ),
                        datetime.strptime(
                            characters["character"]["updatedAt"], "%Y-%m-%dT%H:%M:%SZ"
                        ),
                        characters["character"]["slug"],
                        json.dumps(characters["character"]["description"]),
                        characters["character"]["names"]["canonical"],
                    )
                    await db.execute(
                        query_anime_character,
                        id,
                        character_id,
                        CharacterRole[characters["role"]].value,
                        datetime.strptime(
                            characters["createdAt"], "%Y-%m-%dT%H:%M:%SZ"
                        ),
                        datetime.strptime(
                            characters["updatedAt"], "%Y-%m-%dT%H:%M:%SZ"
                        ),
                    )
                    character_id += 1
                except:
                    pass

            id += 1
            imports += 1
            print(
                f"{Fore.GREEN}Insert into db: {Fore.WHITE}{media.id}{Fore.GREEN} as {Fore.WHITE}{id}{Style.RESET_ALL}"
            )
        except Exception as e:
            # If any error occurs when converting the anime data, we skip the anime
            print(f"{Fore.RED}Skip: {Fore.WHITE}{media.id}{Style.RESET_ALL}: {e}")
    anime.remove(media)

    # Close DB and askitsu connections
    await db.close()
    await kitsu.close()
    print(f"Imported {imports} anime into db")


asyncio.run(run())
