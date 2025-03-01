import argparse
from main import TechNewsAggregator


def test_fetch():
    aggregator = TechNewsAggregator()

    print("\n🔍 Testing news fetching from each source...\n")

    print("Fetching from Hacker News...")
    hn_news = aggregator.fetch_hacker_news()
    print(f"✓ Found {len(hn_news)} stories\n")

    print("Fetching from Reddit...")
    reddit_news = aggregator.fetch_reddit()
    print(f"✓ Found {len(reddit_news)} posts\n")

    print("Fetching from Dev.to...")
    dev_news = aggregator.fetch_dev_to()
    print(f"✓ Found {len(dev_news)} articles\n")

    print("Fetching from Stack Exchange...")
    se_news = aggregator.fetch_stack_exchange()
    print(f"✓ Found {len(se_news)} questions\n")

    print("Fetching from github...")
    ns = aggregator.fetch_github_trending()
    print(f"{len(ns)}questions\n")

    print("Fetching from news...")
    nl = aggregator.fetch_newsapi_tech()
    print(f"{len(nl)}questions\n")

    print("Fetching from Ars Technica...")
    ars_news = aggregator.fetch_ars_technica()
    print(f"✓ Found {len(ars_news)} articles\n")

    print("Fetching from VentureBeat...")
    venture_news = aggregator.fetch_venture_beat()
    print(f"✓ Found {len(venture_news)} articles\n")

    print("Fetching from ZDNet...")
    zdnet_news = aggregator.fetch_zdnet()
    print(f"✓ Found {len(zdnet_news)} articles\n")
    print("Fetching from TechRadar...")
    techradar_news = aggregator.fetch_tech_radar()
    print(f"✓ Found {len(techradar_news)} articles\n")


    print("Fetching from Hackernoon...")
    hackernoon_news = aggregator.fetch_hackernoon()
    print(f"✓ Found {len(hackernoon_news)} articles\n")

    print("Fetching from Science...")
    scince_news = aggregator.fetch_sciencedaily_rss()
    print(f"✓ Found {len(hackernoon_news)} articles\n")

    return all([hn_news, reddit_news, dev_news, se_news,nl,ns,venture_news,hackernoon_news,techradar_news,zdnet_news,scince_news])


def preview_newsletter():
    aggregator = TechNewsAggregator()
    content = aggregator.generate_newsletter()

    with open('newsletter_preview.html', 'w', encoding='utf-8') as f:
        f.write(content)

    print("\n✓ Newsletter preview saved to 'newsletter_preview.html'")


def send_test_email(test_email):
    aggregator = TechNewsAggregator()

    aggregator.add_subscriber(test_email)

    print(f"\n📧 Sending test newsletter to {test_email}...")

    aggregator.send_newsletter()
    aggregator.remove_subscriber(test_email)

    print("✓ Test complete!")


def main():
    parser = argparse.ArgumentParser(description='Test News Aggregator functionality')
    parser.add_argument('--action', choices=['fetch', 'preview', 'send'],
                        default='fetch', help='Action to perform')
    parser.add_argument('--email', help='Email address for test sending')

    args = parser.parse_args()

    if args.action == 'fetch':
        test_fetch()
    elif args.action == 'preview':
        preview_newsletter()
    elif args.action == 'send':
        if not args.email:
            print("Error: Email address required for send action")
            return
        send_test_email(args.email)


if __name__ == "__main__":
    main()