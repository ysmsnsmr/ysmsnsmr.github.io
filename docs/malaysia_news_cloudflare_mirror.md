# Malaysia News Cloudflare Pages mirror

The mirror publishes the existing public Malaysia News pages, Markdown and map
script. It does not publish other repository files or require API secrets. The
existing GitHub Pages site and news generation workflow remain unchanged.

Cloudflare Pages Git integration settings:

- Production branch: `main`; framework preset: none.
- Build command: `python3 scripts/build_malaysia_cloudflare_pages.py`.
- Build output directory: `cloudflare-malaysia-news-dist`.
- Disable preview branch deployments; no secrets are needed for the build.
- The root URL redirects to `/news/malaysia/`.

After deployment, check the index, a daily page, its Markdown link, the map and
article links. Verify that a later scheduled GitHub Actions commit triggers a
successful deployment and that the latest day is updated. To stop the mirror,
disable automatic production deployments in Cloudflare.
