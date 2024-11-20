import csv
import re
from datetime import datetime, timedelta
from requests import request, Response
from typing import (
    Final,
    List,
    Optional,
)

TOKEN: str = "" # User token to fetch feed
KITSU_FEED_ENDPOINT: Final[str] = "https://kitsu.app/api/edge/feeds/global/global?filter[kind]=posts&page[limit]=150&include=subject,subject.user,subject.user.posts"
REQUEST_HEADERS: Final[dict] = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json", "User-Agent": "Kitsu Spam Detector (by @shomy on kitsu.app)"}


VIETAMESE_REGEX: Final[str] = r"\b[^\W\d_][àáảãạâầấẩẫậđèéẻẽẹêềếểễệìíỉĩòóỏõọôồốổỗộơờởỡùúủũụýỳỷỹ]*[^\0\W\d_]*\b"

WHITELISTED_DOMAINS: List[str] = [
    "https://kitsu.io/",
    "https://kitsu.app/",
    "https://youtube.com/",
    "https://youtu.be/",
]



def get_feed() -> dict:
    data: Response = request("GET", headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}, url=KITSU_FEED_ENDPOINT)
    return data.json()


def get_posts_activity(feed: dict) -> dict:
    """
    Filter the global feed to get posts activities to later fetch posts.
    """
    filtered_feed: dict = {}
    feed.pop("data") # Only fetch global feed and not groups
    for activity in feed["included"]:
        if not "verb" in activity["attributes"].keys():
            continue

        if not activity["attributes"]["verb"] == "post":
            continue

        if activity["relationships"]["subject"]["data"] == None and activity["attributes"]["foreignId"] == None:
            continue

        post_id: int = activity["attributes"]["foreignId"].split(":")[1] # e.g. Post:911000 -> 911000
        filtered_feed[post_id] = activity

    return filtered_feed


def get_posts(activity_feed: dict, feed: dict) -> dict:
    """
    Filters the global feed and returns only the posts
    """
    feed_posts: dict = {}
    for item in feed["included"]:
        if item["type"] == "posts":
            feed_posts[item["id"]] = item

    return feed_posts


def get_users_from_feed(posts_feed: dict, feed: dict) -> dict:
    """
    Filters the users related only to the posts in the filtered feed

    This removes users that appear on stuff like comments.
    """
    users: dict = {}
    filtered_users: dict = {}

    # We first fetch all the id of every user in the feed
    for item in feed["included"]:
        if item["type"] == "users":
            users[item["id"]] = item

    # Now we filter the users in the feed
    for post_id, post_data in posts_feed.items():
        if post_data["relationships"]["user"]["data"] == None:
            continue
        
        ## Get the user
        if post_data["relationships"]["user"]["data"]["id"] in users.keys():
            filtered_users[post_data["relationships"]["user"]["data"]["id"]] = users[post_data["relationships"]["user"]["data"]["id"]] 

    return filtered_users



def filter_spam(posts: dict, users: dict) -> dict:
    """
    Filters out the feed and returns only what is considered spam
    """
    filtered_posts: dict = posts.copy()

    seven_days_ago: datetime = datetime.now().astimezone() - timedelta(days=7)
    for post_id, post_data in posts.items():
        # First of all, we check if the post has embeds:
        if post_data["attributes"]["embed"] == None:
            filtered_posts.pop(post_id)
            continue
        
        # If it has embeds, we check if it's a website link and
        # not witelisted
        if post_data["attributes"]["embed"]["url"] in WHITELISTED_DOMAINS: # or post_data["attributes"]["embed"]["kind"] != "website":
            filtered_posts.pop(post_id)
            continue
        
        # Here we are sure we're dealing with something that is either a normal user post
        # or something that could be spam, so we check the actual user!
        user_id: str = post_data["relationships"]["user"]["data"]["id"]
        user: dict = users[user_id]

        user_created_at: datetime = datetime.strptime(user["attributes"]["createdAt"], "%Y-%m-%dT%H:%M:%S.%f%z")
        
        # If the user is older than 7 days, we remove the post
        if user_created_at < seven_days_ago:
            filtered_posts.pop(post_id)
            continue
        
        trust_score: int = 100
        # The user account is new!
        # Decrease the trust score by 10%
        trust_score -= 10
        # Spam account tend to have one post, same content of the post in the about me section and the
        # url of the website in the domain section.

        response: Response = request("GET", url="https://kitsu.app/api/edge/users/%s/profile-links" % user_id, headers={"Content-Type": "application/json"})
        profile_links: dict = response.json()
        
        # If the embed url is the same as one of the profile links, we decrease the trust score by 20 points
        for link in profile_links["data"]:
            if link["attributes"]["url"] == post_data["attributes"]["embed"]["url"]:
                # User seem to have the same url in of the embed!
                trust_score -= 20
                break
        
        # If the spam account has exactly one post, we decrease the trust score again!
        if user["attributes"]["postsCount"] == 1:
            trust_score -= 20

        # Most of the spam is in vietnamese, so we lower the trust score a lot if the post is mostly in vietnamese
        regex_match = re.findall(VIETAMESE_REGEX, post_data["attributes"]["content"], flags=re.IGNORECASE | re.MULTILINE)
        if len(regex_match) > len(post_data["attributes"]["content"].split(" ")) * 0.6:
            trust_score -= 50

        # Add useful fields to the post for later analysis
        filtered_posts[post_id]["trust_score"] = trust_score
        filtered_posts[post_id]["user_id"] = user_id
        filtered_posts[post_id]["user_name"] = user["attributes"]["name"]
        filtered_posts[post_id]["user_description"] = user["attributes"]["description"]
        filtered_posts[post_id]["user_account_creation_date"] = user["attributes"]["createdAt"]

    return filtered_posts


def make_csv(spam_feed: dict) -> None:
    """
    Writes all the spam feed to a csv
    """
    with open("spam_feed.csv", "rw", newline="") as f:
        spam_writer = csv.writer(f)
        spam_reader = csv.reader(f)
        spam_data = list(spam_reader)
        header = ["USER_ID", "USER_NAME","POST_ID", "POST_CONTENT", "TRUST_SCORE", "USER_DESCRIPTION", "USER_ACCOUNT_CREATION_DATE"]
        if spam_data == []:
            spam_writer.writerow(header)
        for post_id, post_data in spam_feed.items():
            post_data_tuple = (
                post_data["relationships"]["user"]["data"]["id"],
                post_data["user_name"],
                post_id,
                post_data["attributes"]["content"],
                post_data["trust_score"],
                post_data["user_description"],
                post_data["user_account_creation_date"]
            )
            if post_data_tuple not in spam_data:
                spam_writer.writerow(post_data_tuple)


if __name__ == "__main__":
    print("Fetching feed...")
    feed: dict = get_feed()
    post_activity: dict = get_posts_activity(feed)
    filtered_feed: dict = get_posts(post_activity, feed)
    users: dict = get_users_from_feed(posts_feed=filtered_feed, feed=feed)

    print("Got the feed! Got %d users and %d posts" % (len(users), len(filtered_feed)))
    print("Filtering feed...")
    filtered: dict = filter_spam(filtered_feed, users)
    print("Filtered feed! Got %d spam posts" % (len(filtered)))

    if len(filtered) > 0:
        print("Writing to CSV...")
        make_csv(filtered)
        print("Done!")
    
    else:
        print("No spam found!")
