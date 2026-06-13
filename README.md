# The Resume Vault — Sales Website

Website and digital product platform for the Resume Vault and Get Hired Faster
Collection — a single-page marketing site for **The Resume Vault** and
**The Interview Room**, two interactive AI career-coaching tools by
Toni Powell / Dream Job Finder.

## Stack

Pure static HTML/CSS/JS — no build step, no dependencies. Deployable anywhere
(GitHub Pages, Netlify, Vercel, Replit static hosting).

- `index.html` — the full landing page (hero, tools, how-it-works, about,
  pricing, agency partner section, FAQ)
- `styles.css` — brand design system (navy / antique gold / cream, Fraunces +
  Inter typefaces) with responsive layout and scroll-reveal animations
- `script.js` — intersection-observer reveals, mobile nav, FAQ accordion
- `assets/favicon.svg` — vault-dial brand mark

## Run locally

```sh
python3 -m http.server 8000
# open http://localhost:8000
```

## Deploy

Push the repository to any static host. For GitHub Pages: Settings → Pages →
deploy from the `main` branch root.
