#!/usr/bin/env python
import argparse
import os
import webbrowser

try:
    from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
except ImportError:
    from urllib import urlencode

    from urlparse import parse_qs, urlparse, urlunparse
parser = argparse.ArgumentParser(description="Butterfly tab opener.")
parser.add_argument(
    "location",
    nargs="?",
    default=os.getcwd(),
    help="Directory to open the new tab in. (Defaults to current)",
)
args = parser.parse_args()

url_parts = urlparse(os.getenv("LOCATION", "/"))
query = parse_qs(url_parts.query)
query["path"] = os.path.abspath(args.location)

url = urlunparse(url_parts._replace(path="")._replace(query=urlencode(query)))
if not webbrowser.open(url):
    print("Unable to open browser, please go to %s" % url)
