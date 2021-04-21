from asyncio.events import set_event_loop
from concurrent.futures.thread import ThreadPoolExecutor
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pprint import pprint
from typing import NamedTuple, Set
from urllib.parse import urljoin, urlparse
import requests

from requests_html import AsyncHTMLSession, HTML, HTMLSession
from tqdm import tqdm
import logging
from pathlib import Path
import argparse


_logger = logging.getLogger("scraper")


class ScrapeResult(NamedTuple):
    """ Represents the results from scraping one or more pages. """

    sources: Set[str]
    hrefs: Set[str]


def _scrape_url(url: str, scrollDelay: int = 10) -> ScrapeResult:
    """
    Scrapes a single page for images and links.

    Returns:
        A ScrapeResult object.
    """
    _logger.debug(f"_scrape_url: {url}")

    session = HTMLSession()
    r = session.get(url)
    html = r.html

    # Some images may only load when they're in view, so scroll each image into view.
    script = """
        async () => {
            const images = document.querySelectorAll('img');
            for (let image of images) {
                await new Promise(resolve => setTimeout(resolve, @SCROLL_DELAY));
                image.scrollIntoViewIfNeeded();
            }
        }
    """

    script = script.replace("@SCROLL_DELAY", str(scrollDelay))

    html.render(sleep=1, scrolldown=10)
    session.close()
    images = html.find("img")
    netloc = urlparse(url).netloc

    sources = {urljoin(url, img.attrs["src"]) for img in images if "src" in img.attrs}
    hrefs = {href for href in html.absolute_links if urlparse(href).netloc == netloc}

    return ScrapeResult(sources, hrefs)


def _scrape_recursive(url: str, depth: int = 0) -> Set[str]:
    """
    Recursively scrapes image sources starting from the given url up to the given depth.

    Parameters:
        url (string): url to scrape.
        depth: (int): if greater than 0, links will be followed up to the specified depth.
    """

    _logger.debug(f"{depth} - Scraping: {url}")
    result = _scrape_url(url)

    if depth <= 0:
        return result.sources
    else:
        sources = result.sources

        # with ProcessPoolExecutor() as executor:
        #     futures = {
        #         executor.submit(_scrape_recursive, href, depth=depth - 1): href
        #         for href in result.hrefs
        #     }

        #     for future in as_completed(futures):
        #         href = futures[future]
        #         try:
        #             data = future.result()
        #         except Exception as e:
        #             _logger.error(f"Failed to scrape: {href}\n{e}")
        #             continue
        #         else:
        #             _logger.debug(f"Scraped: {href}")
        #             sources |= data

        for href in result.hrefs:
            sources |= _scrape_recursive(href, depth=depth - 1)

        return sources


def scrape(url: str, depth: int = 0, savedir: os.PathLike = "images") -> None:
    """
    Recursively scrapes images starting from the given url up to the given depth.

    Parameters:
        url (string): url to scrape.
        depth (int): if greater than 0, links will be followed up to the specified depth.
        savedir (PathLike): location images should be saved.
    """

    sources = _scrape_recursive(url, depth=depth)

    try:
        os.makedirs(savedir)
    except FileExistsError:
        pass

    # Download images
    for src in tqdm(sources, desc="Downloading"):
        p = Path(urlparse(src).path)
        img = requests.get(src)
        fpath = os.path.join(savedir, p.name)
        with open(fpath, "wb") as f:
            f.write(img.content)


if __name__ == "__main__":
    # _logger.addHandler(logging.StreamHandler(sys.stdout))
    # _logger.setLevel(logging.DEBUG)

    parser = argparse.ArgumentParser(description="Scrape some images.")
    parser.add_argument(
        "url",
        type=str,
        help="the url to scrape",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        type=str,
        default="images",
        dest="savedir",
        help="location to save files to",
    )
    parser.add_argument(
        "-r",
        "--recurse",
        type=int,
        metavar="DEPTH",
        default=0,
        dest="depth",
        help="max depth to recurse when following links",
    )

    args = parser.parse_args()

    scrape(**vars(args))
