from youtube.youtube import generate_rss_feed

if __name__ == "__main__":
    rss_feed = generate_rss_feed()
    print(rss_feed.decode("utf-8"))
