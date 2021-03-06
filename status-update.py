#!/usr/bin/env python
from twitter import *
import requests
from bs4 import BeautifulSoup
import argparse
import yaml
import datetime

from local_library_searching import album_selector

with open("/home/david/swarbs_turntable/swarbs-turntable-login.yaml", "r") as stream:
    try:
        config = yaml.safe_load(stream)
        auth = OAuth(
            config["access_token"],
            config["access_token_secret"],
            config["api_key"],
            config["api_secret_key"],
        )
        library_path = config["library_path"]
    except yaml.YAMLError as exc:
        print("Could not load configuration file")
        raise
    except KeyError:
        print("Could not load OAuth correctly")
        raise

try:
    template = config["template"]
except KeyError:
    print("Using Default Config")
    template = "{artist} - {title} ({year}) \n{url}"


def _update_status(filled_template, imagedata):
    t = Twitter(auth=auth)
    t_upload = Twitter(domain="upload.twitter.com", auth=auth)
    img_id = t_upload.media.upload(media=imagedata)["media_id_string"]
    t.statuses.update(
        status=filled_template, media_ids=img_id,
    )


def update_status_soundcloud_mix(
    url, artist=None, title=None, year=None, artist_title=False, image=None
):
    r = requests.get(url)
    soup = BeautifulSoup(r.content, "html.parser")

    foundtitle, foundartist = soup.find("h1").find_all("a")
    if artist_title:
        a, t = foundtitle.string.split("-")
        if artist is None:
            artist = a
        if title is None:
            title = t
    if title is None:
        title = foundtitle.string.strip()
    if artist is None:
        artist = foundartist.string.strip()
    if year is None:
        year = soup.find("time").string[:4]
    filled_template = template.format(artist=artist, title=title, year=year, url=url)

    print("About to Tweet: ", filled_template)
    ok = input("Does this look right? (y/n) ")

    if ok == "y" and image is None:
        img_link = soup.find("img")["src"]
        imagedata = requests.get(img_link).content
        print("Tweeting: ", filled_template)
        _update_status(filled_template, imagedata)
    elif ok == "y":
        with open(image, encoding="latin") as imagedata:
            print("Tweeting: ", filled_template)
            _update_status(filled_template, imagedata.read())


def _nts_template_filler(
    results, channel, artist=None, title=None, time="now", swap=False, joint_hosts=False
):
    """Handle NTS Shows that don't have a title"""
    bt = results[channel - 1][time]["embeds"]["details"]["name"]
    # Remove ampersand issues

    bt = bt.replace("amp;", "")

    # Handle Re-records, and remove (R) symbol -- usually present in broadcast_title
    broad = results[channel - 1][time]["broadcast_title"]
    if broad.find("(R)") > 0:
        print("This is a re-record, fetching original time.")
        year = results[channel - 1][time]["embeds"]["details"]["broadcast"][:4]
        bt = bt.replace(" (R)", "")
    else:
        year = "LIVE"

    if bt.find("W/") > 0:
        # If a big W in there, split on that
        broadcast_title = bt.split("W/")
    elif bt.find("w/") > 0:
        # Otherwise try and split on little w
        broadcast_title = bt.split("w/")
    elif bt.find("-") > 0:
        # Or split on dash
        broadcast_title = bt.split("-")
    else:
        # Handle "Presents:"
        broadcast_title = bt.split(" Presents: ")

    if len(broadcast_title) == 2 and joint_hosts:
        # Account for Host w/ Guest setups
        host = broadcast_title[0].strip()
        guest = broadcast_title[1].strip()
        if swap:
            broadcast_title = [guest + " & " + host]
        else:
            broadcast_title = [host + " & " + guest]
    elif len(broadcast_title) == 2:
        # A W was there somewhere - reformat to match templateamp
        if title is None:
            title = broadcast_title[0].strip()
        if artist is None:
            artist = broadcast_title[1].strip()

        if swap:
            # Assuming deep copy not needed
            s = title
            title = artist
            artist = s
    # New if statement for single
    if len(broadcast_title) == 1:
        # Single dj title, so set the title to NTS + date
        if artist is None:
            artist = broadcast_title[0].strip()
        if title is None:
            if year == "LIVE":
                t = results[channel - 1][time]["start_timestamp"]
            else:
                # Re record
                t = results[channel - 1][time]["embeds"]["details"]["broadcast"]
            yr = t[2:4]
            month = t[5:7]
            day = t[8:10]
            title = "NTS " + day + "/" + month + "/" + yr

    return template.format(
        artist=artist,
        title=title,
        year=year,
        url="https://www.nts.live/" + str(channel),
    )


def _nts_check(filled_template, prev_answers=(False, False, False, False)):
    print("About to Tweet: ", filled_template)
    ok = input("Does this look right? ([y]es/[n]ext/[s]wap/[g]uest) ")

    if ok == "y":
        return (True, False, False)
    elif ok == "n":
        return (prev_answers[0], not prev_answers[1], prev_answers[2], prev_answers[3])
    elif ok == "s":
        return (prev_answers[0], prev_answers[1], not prev_answers[2], prev_answers[3])
    elif ok == "g":
        return (prev_answers[0], prev_answers[1], prev_answers[2], not prev_answers[3])
    else:
        return (False, False, False)


def update_status_ntslive(channel, artist=None, title=None):
    r = requests.get("https://www.nts.live/api/v2/live")
    results = r.json()["results"]
    print("Data for Channel ", results[channel - 1]["channel_name"])

    filled_template = _nts_template_filler(results, channel, artist, title)
    flags = _nts_check(filled_template)
    time = "now"
    # 0 = y, 1 = next show, 2 = swap order of show/artist
    while flags[0] or flags[1] or flags[2] or flags[3]:
        if flags[0]:
            img_link = results[channel - 1][time]["embeds"]["details"]["media"][
                "picture_large"
            ]
            imagedata = requests.get(img_link).content
            _update_status(filled_template, imagedata)
            flags = [False, False, False, False]  # Exit loop
        else:
            if flags[1]:
                time = "next"
            else:
                time = "now"
            swap = flags[2]
            joint_hosts = flags[3]
            filled_template = _nts_template_filler(
                results, channel, artist, title, time, swap, joint_hosts
            )
            flags = _nts_check(filled_template, flags)


# Netil less favourable due to lack of artwork
# def update_status_netil(artist=None, title=None):
#     r = requests.get("https://studio.mixlr.com/api/stations/4/schedule.json")
#     results = r.json()
#     time = "on_air"
#     bt = results[time]["show"]["title"]
#     artist = results[time]["show"]["host"]


def threads_template_filler(long_title, channel=1):
    title = None
    if long_title.find("w/") > 0:
        # Try and split on little w
        title, artist = long_title.split("w/")
    else:
        artist = long_title
    if title is None:
        t = datetime.datetime.now()
        yr = str(t.year)[2:]
        day = t.day
        month = t.month
        title = "{}/{}/{}".format(day, month, yr)
    # ToDo handle different channels
    year = "LIVE"
    print(title, artist)
    return template.format(
        artist=artist, title=title, year=year, url="https://threadsradio.com/",
    )


def threads(artist=None, title=None, year=None):
    r = requests.get("https://public.radio.co/stations/s1e48aa7d7/status")
    results = r.json()
    long_title = results["current_track"]["title"]
    year = "LIVE"
    temp = threads_template_filler(long_title)
    img_url = results["current_track"]["artwork_url_large"]
    imagedata = requests.get(img_link).content


def local_file_in_library(artist, library_location=None):
    if library_location:
        lib = library_location
    else:
        lib = library_path
    data, img_data = album_selector(artist, lib)
    if None in data:
        pass
    elif img_data is None:
        print("No 'cover.jpg' file found for this album")
    else:
        filled_template = template.format(
            artist=data[0], title=data[1], year=data[2], url=""
        )
        # remove /n from it
        filled_template = filled_template[:-1]
        print("Tweeting: ", filled_template)
        _update_status(filled_template, img_data)


parser = argparse.ArgumentParser()
parser.add_argument(
    "source",
    help="Either URL to grab data from, or filesystem location. (Soundcloud/NTS)",
)
parser.add_argument("-a", "--artist", default=None, help="Artist override for tweet")
parser.add_argument("-t", "--title", default=None, help="Title override for tweet")
parser.add_argument("-l", "--library", default=None, help="Location of Music Library")
parser.add_argument("-i", "--image", default=None, help="Image override for tweet")
parser.add_argument(
    "-at",
    "--artist_title",
    action="store_true",
    help="Title contains ARTIST - TITLE already",
)
parser.add_argument("-y", "--year", default=None, help="Year override for tweet")
parser.add_argument("-n", "--nts", default=1, help="NTS Channel (1/2)")
args = parser.parse_args()

if "soundcloud" in args.source:
    print("Source: Soundcloud")
    update_status_soundcloud_mix(
        args.source, args.artist, args.title, args.year, args.artist_title, args.image
    )
elif "nts.live" in args.source:
    print("Source: NTS Live")
    update_status_ntslive(int(args.nts), args.artist, args.title)
elif "threads" in args.source:
    print("Source: Threads Radio")
    threads(args.artist, args.title, args.year)

elif "local" in args.source:
    print("Source: Local Library")
    local_file_in_library(args.artist, args.library)
