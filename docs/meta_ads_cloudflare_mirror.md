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

## ホーム画面ショートカット

英語・日本語のTOPには、端末のホーム画面で使用するアイコンと各言語のWeb App Manifestを設定しています。Manifestは通常のブラウザ表示を指定し、オフライン機能や通知は追加しません。Cloudflare用ビルドの許可リストにはSVG、180／192／512pxのPNGと両言語のManifestを含めます。ホーム画面への追加手順や表示は端末・ブラウザによって異なり、既存ショートカットには更新が反映されない場合があります。
