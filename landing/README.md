# Munshiji - landing page

The public marketing page. A Vite + TypeScript project, not a framework app -
there's no router or component library here, just typed data modules driving
a handful of DOM-rendering functions (the bento grid, the phase track, the
multilingual command demo, the ambient waveform canvas). It builds to plain
static files, so it deploys anywhere that serves HTML.

```bash
npm install
npm run dev       # http://localhost:5173, hot-reloads on save
npm run build     # type-checks (tsc -b) then outputs static files to dist/
npm run preview   # serves the dist/ build locally, for a final check
```

## Layout

Multi-page, with clean URLs: every page except the homepage lives in its own
folder as `index.html`, so the build emits `dist/about/index.html` and static
hosts serve it at `/about` - no `.html` in any link.

```
index.html          Homepage - hero, showcase carousel, security, FAQ
about/index.html     Mission/story page                        -> /about
pricing/index.html   Plans and planned pricing                 -> /pricing
features/index.html  Full tool-pack breakdown                  -> /features
docs/index.html      Build-from-source + links to the real docs -> /docs
download/index.html  Download / install page                   -> /download
terms/index.html     Terms of service                          -> /terms
privacy/index.html   Privacy policy                            -> /privacy
src/main.ts          Homepage entry: waveform, command demo, showcase, FAQ
src/common.ts        Entry for every other page - renders whatever containers exist
src/data.ts          Typed content: demo phrases, tool cards, showcase slides, FAQs
src/header.ts        Floating nav pill, announcement bar, "More" dropdown
src/carousel.ts      Full-width tool showcase
src/features.ts      Tool grid rendered from data.ts
src/faq.ts           FAQ accordion
src/pricing.ts       Monthly/annual billing toggle
src/demo.ts          Multilingual command-demo cycler
src/waveform.ts      Canvas waveform animation
src/graphic.ts       Inline SVG graphics
src/reveal.ts        Fade-in-on-scroll, shared by every page
src/style.css        All styling - CSS custom properties for light/dark theming
public/              Static assets copied as-is (favicon, etc.)
```

Adding a page means creating `<name>/index.html` **and** listing it in
`vite.config.ts` - the build only emits pages named there. Link to it as
`/<name>`, never `/<name>.html`.

`vite.config.ts` also carries a small `directoryIndexUrls` plugin: real static
hosts resolve `/about` to `about/index.html` themselves, but Vite's dev and
preview servers don't, so without it every clean URL 404s locally while
working fine in production. `appType: "mpa"` is set alongside it so an unknown
path 404s instead of silently serving the homepage.

The header, topbar, and footer markup is duplicated across the page files
rather than templated - there's no build-time include mechanism here. Keep
them in sync by hand when nav or footer links change.

## Updating content

Change copy directly in the relevant `index.html`. Change the tool list,
showcase slides, or FAQs in `src/data.ts` - the DOM is rendered from those
arrays, so nothing else needs editing to add or reorder an entry. Speculative
product ideas beyond the committed roadmap belong in `../future-scope.md`,
not on the pricing or docs pages - keep those two scoped to what's actually
true today.

## Deploying

`npm run build` produces a fully static `dist/` - point Vercel/Netlify/GitHub
Pages at this directory (build command `npm run build`, publish directory
`dist`) with no server-side requirements. The clean URLs need no host-specific
rewrite rules: they're real directories with an `index.html` inside, which
every static host resolves natively.
