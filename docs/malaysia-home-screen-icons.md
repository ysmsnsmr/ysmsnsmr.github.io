# Malaysia News Shortcut Icons

`news/malaysia/icon-v1.svg` is the font-independent vector master. The committed
opaque RGB PNGs provide 32px browser, 152/167/180px Apple touch, and 192/512px
manifest icons. The green background is full bleed and the MY/news mark stays
inside the maskable icon safe circle. Generate PNGs from the SVG when revising
the artwork; bump the asset version in filenames and metadata for a new design.
No image tool or Node package is required during scheduled or hosting builds.

The generator adds the shared icon metadata to home, archive and daily pages.
The Cloudflare allowlist includes these same static assets and rewrites the root
home's relative links as it does other news assets. The relative manifest URLs
resolve to `/news/malaysia/` on either host, so the Android start URL always opens
the latest news, rather than a fixed date or the user's unrelated portfolio.

This provides shortcut branding only: `display` remains `browser`; there is no
service worker, offline news cache, notification permission or standalone mode.
The saved name is `MY生活ニュース`. Existing device shortcuts may need to be
removed and added again; real iOS/iPadOS/Android home-screen appearance must be
confirmed on a physical device, not inferred from browser emulation.

References:
- [Apple Web Clip icons and launch titles](https://developer.apple.com/library/archive/documentation/AppleApplications/Reference/SafariWebContent/ConfiguringWebApplications/ConfiguringWebApplications.html)
- [W3C Web Application Manifest](https://www.w3.org/TR/appmanifest/)
