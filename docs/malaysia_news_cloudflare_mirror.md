# Malaysia News Cloudflare Pages mirror

The mirror publishes the public Malaysia News pages, Markdown, map and
daily-page scripts. It does not publish other repository files or require API
secrets. GitHub Pages remains independently hosted; the news workflow generates
the latest home page and archive for both sites.

Cloudflare Pages Git integration settings:

- Production branch: `main`; framework preset: none.
- Build command: `python3 scripts/build_malaysia_cloudflare_pages.py`.
- Build output directory: `cloudflare-malaysia-news-dist`.
- Disable preview branch deployments; no secrets are needed for the build.
- The root URL displays the latest summary; `/news/malaysia/` remains available.
- The previous index is published as `/news/malaysia/archive.html`.

After deployment, check the index, a daily page, its Markdown link, the map and
article links. Verify that a later scheduled GitHub Actions commit triggers a
successful deployment and that the latest day is updated. To stop the mirror,
disable automatic production deployments in Cloudflare.
