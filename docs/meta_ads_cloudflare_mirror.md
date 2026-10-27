# Meta Ads Cloudflare Pages mirror

This is an experimental additional static delivery endpoint. GitHub Pages and
the scheduled collection workflow remain the primary implementation. The
mirror publishes only the files enumerated in
`scripts/build_meta_ads_cloudflare_pages.py`; it does not publish `data/`,
workflows, source code, or API keys. Search indexing is disabled through the
Cloudflare `_headers` output. Favorites are local to each browser origin.

Cloudflare Pages Git integration settings:

- Production branch: `main`; framework preset: none.
- Build command: `python3 scripts/build_meta_ads_cloudflare_pages.py`.
- Build output directory: `cloudflare-meta-ads-dist`.
- Disable preview branch deployments; no OpenAI or TypeSafe secrets are needed.
- Open `/meta-ads-updates/ja/` or `/meta-ads-updates/` on the mirror hostname.

Check the English and Japanese lists, detail links including `?id=`, source
links, 404s and `X-Robots-Tag` after deployment. Verify that a later
GitHub Actions feed commit actually starts a Cloudflare build and that the
published JSON is updated; a successful collection alone is not proof of a
successful deploy. Company network access remains a separate check. If the
mirror is unusable, disable its automatic deployments in Cloudflare and keep
using the existing GitHub Pages site.
