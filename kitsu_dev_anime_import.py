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
  anime(first: 20, after: $cursor){
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
              image{
                blurhash
                original{
                  name
                  url
                  width
                  height
                }
                views{
                  name
                  url
                  width
                  height
                }
              }
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

      	posterImage{
          blurhash
          original{
            name
            url
            width
            height
          }
          views{
            name
            url
            width
            height
          }
        }

        bannerImage{
          blurhash
          original{
            name
            url
            width
            height
          }
          views{
            name
            url
            width
            height
          }     
        }
      
    }
  }
}
"""

categories_gqlquery = """
query {
  categories(first: 243){
    totalCount
    nodes{
      createdAt
      updatedAt
      slug
      children(first: 2000){
        totalCount
      }
      parent{
        id
      }
      isNsfw
      description
     	title 
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
    original_locale,
    poster_image_data,
    cover_image_data
  )
	VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28);"""

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

query_media_character = """
  INSERT INTO public.media_characters (
    media_id,
    media_type,
    character_id,
    role,
    created_at,
    updated_at
  )
  VALUES ($1, $2, $3, $4, $5, $6)
"""

query_character = """
  INSERT INTO public.characters(
    id,
    name,
    created_at,
    updated_at,
    slug,
    description,
    canonical_name,
    primary_media_id,
    primary_media_type,
    names,
    image_data
  )
  VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
"""

query_casting = """
  INSERT INTO public.castings(
    id,
    media_id,
    character_id,
    role,
    created_at,
    updated_at,
    voice_actor,
    featured,
    language,
    media_type
  )
  VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)

"""

query_categories = """
  INSERT INTO public.categories(
    id,
    title,
    slug,
    parent_id,
    nsfw,
    created_at,
    updated_at,
    child_count,
    description
  )
  VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)


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
        #Filter any data that may cause problems
        #or that is not useful
        if i.description is None:
            anime_gen.remove(i)
        elif i._attributes["ageRating"] is None:
            anime_gen.remove(i)
        elif i.ended_at is None or i.started_at is None:
            anime_gen.remove(i)
    anime += anime_gen
    print(f"Fetched {Fore.RED}{len(anime_gen)}{Style.RESET_ALL} anime.")


async def convert_media_images(image_data: dict) -> typing.Optional[dict]:
    if not image_data:
        return None
    id = str(image_data["original"]["url"])[23::]
    # print(id)

    derivates_name = [image_size["name"] for image_size in image_data["views"]]
    derivates = {
        name: {
            "id": str(image["url"])[23::],
            "storage": "store",
            "metadata": {
                "width": image["width"],
                "height": image["height"],
                # "blurhash": image["blurhash"]
            },
        }
        for name, image in zip(derivates_name, image_data["views"])
    }
    new_dict = {
        "id": id,
        "storage": "store",
        "metadata": {
            "width": image_data["original"]["width"],
            "height": image_data["original"]["height"],
            "blurhash": image_data["blurhash"],
        },
        "derivates": derivates,
    }
    # print(new_dict)
    return new_dict


async def convert_to_datetime(timestamp: str) -> datetime:
    return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")


async def match_canonical_title(titles: dict) -> str:
    if "en_jp" in titles:
      return "en_jp"
    return next(iter(titles))

async def run():
    global id
    global imports
    character_id = 1

    # Initialize
    try:
        db = await asyncpg.create_pool(
            database=KITSU_DB_NAME, user=KITSU_DB_USER, host=HOST, port="5432"
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

    # Fetch categories
    categories = await kitsu.http.post_data({"query": categories_gqlquery})
    print(
        f"Total fetched categories: {Fore.RED}{categories['data']['categories']['totalCount']}{Style.RESET_ALL}."
    )
    for cid, category in enumerate(categories["data"]["categories"]["nodes"]):
        try:
            parent_id = category["parent"]
            if parent_id is not None:
                parent_id = int(parent_id.get("id", None))
            await db.execute(
                query_categories,
                cid,
                category["title"].get("en", ""),
                category["slug"],
                parent_id,
                category["isNsfw"],
                await convert_to_datetime(category["createdAt"]),
                await convert_to_datetime(category["updatedAt"]),
                category["children"]["totalCount"],
                json.dumps(category["description"].get("en", "")),
            )
            print(f"Add category: {Fore.GREEN}{category['slug']}{Style.RESET_ALL}.")
        except Exception as e:
            print(f"Skip category: {Fore.RED}{category['slug']}{Style.RESET_ALL}.", e)

    # Fetch a bunch of anime
    for _ in range(3):
        await get_anime(kitsu_client=kitsu)

    print(f"Total fetched anime: {Fore.RED}{len(anime)}{Style.RESET_ALL}.")

    # Add the data to the database
    for media in anime:
        try:
            # Convert the data
            characters_added: bool = False
            

            poster_image = await convert_media_images(media._attributes["posterImage"])
            cover_image = await convert_media_images(media._attributes["bannerImage"])
            age_rating = media._attributes["ageRating"]
            if age_rating is not None:
                age_rating = AgeRating[media.age_rating].value
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
                age_rating,
                media.episode_count,
                media.episode_length,
                json.dumps({"en": media.description}),
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
                await match_canonical_title(media._titles),
                media.popularity_rank,
                media.rating_rank,
                media._attributes.get("favoritesCount", 0),
                media._attributes.get("tba", ""),
                media.episode_count,
                media.total_length,
                media._attributes.get("origin_languages", None),
                media._attributes.get("origin_countries", None),
                media._attributes.get("original_locale", ""),
                json.dumps(poster_image),
                json.dumps(cover_image),
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
                        characters["character"]["names"]["canonical"],
                        datetime.strptime(
                            characters["character"]["createdAt"], "%Y-%m-%dT%H:%M:%SZ"
                        ),
                        datetime.strptime(
                            characters["character"]["updatedAt"], "%Y-%m-%dT%H:%M:%SZ"
                        ),
                        characters["character"]["slug"],
                        json.dumps(characters["character"]["description"]),
                        await match_canonical_title(characters["character"]["names"]["localized"]),
                        id,
                        "anime",
                        json.dumps(characters["character"]["names"]["localized"]),
                        json.dumps(await convert_media_images(characters["character"]["image"]))
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
                    await db.execute(
                        query_media_character,
                        id,
                        "anime",
                        character_id,
                        CharacterRole[characters["role"]].value,
                        datetime.strptime(
                            characters["createdAt"], "%Y-%m-%dT%H:%M:%SZ"
                        ),
                        datetime.strptime(
                            characters["updatedAt"], "%Y-%m-%dT%H:%M:%SZ"
                        ),
                    )
                    await db.execute(
                      query_casting,
                      character_id,
                      id,
                      character_id,
                      "Producer",
                      await convert_to_datetime(characters["createdAt"]),
                      await convert_to_datetime(characters["updatedAt"]),
                      True,
                      True,
                      "En",
                      "Anime"
                    )
                    character_id += 1
                    characters_added = True
                except:
                    pass

            id += 1
            imports += 1
            print(
                f"{Fore.GREEN}IMPORT: {Fore.WHITE}Insert into db: {Fore.GREEN}{media.slug}{Style.RESET_ALL} " \
                f"as {Fore.CYAN}{id}{Style.RESET_ALL} " \
                f"| Characters: {Fore.CYAN if characters_added else Fore.LIGHTRED_EX}{characters_added}{Style.RESET_ALL}"
            )
        except Exception as e:
            # If any error occurs when converting the anime data, we skip the anime
            print(f"{Fore.RED}SKIP: {Fore.WHITE}{media.id}{Style.RESET_ALL}: {e}")
            print(media._attributes)
    anime.remove(media)

    # Close DB and askitsu connections
    await db.close()
    await kitsu.close()
    print(f"Imported {imports} anime into db")


asyncio.run(run())

