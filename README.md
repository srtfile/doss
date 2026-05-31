# Anime Stream Finder

Get Megaplay / Vidwish stream URLs for any anime episode using MAL ID.

## Files

| File | Purpose |
|------|---------|
| `anime_search.py` | Python backend — search, decrypt, get realid |
| `index.html` | Web UI — served via GitHub Pages |
| `.github/workflows/get_stream.yml` | GitHub Actions workflow — runs the Python script |

---

## Setup (GitHub Pages + Actions)

### 1. Create a GitHub repo and push these files

```bash
git init
git add .
git commit -m "initial"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

### 2. Enable GitHub Pages

- Go to your repo → **Settings** → **Pages**
- Source: **Deploy from a branch** → `main` branch → `/ (root)`
- Save — your page will be at `https://YOUR_USERNAME.github.io/YOUR_REPO/`

### 3. Edit index.html — set your repo info

Open `index.html` and change these two lines near the top of the `<script>`:

```js
const OWNER = 'YOUR_GITHUB_USERNAME';   // ← your GitHub username
const REPO  = 'YOUR_REPO_NAME';         // ← your repo name
```

Commit and push.

### 4. Create a GitHub Personal Access Token

- Go to: https://github.com/settings/tokens
- **Fine-grained tokens** → Generate new token
- Repository access: select your repo
- Permissions needed:
  - **Actions**: Read and Write
  - **Contents**: Read (for checkout)
- Copy the token (starts with `ghp_` or `github_pat_`)

### 5. Use the web page

1. Open `https://YOUR_USERNAME.github.io/YOUR_REPO/`
2. Paste your GitHub token in the token field
3. Enter a MAL ID and episode number
4. Click **Get Stream URLs**
5. Wait ~30–60 seconds for GitHub Actions to run
6. Results appear with copy buttons

---

## Common MAL IDs

| Anime | MAL ID |
|-------|--------|
| Naruto | 20 |
| Naruto: Shippuden | 1735 |
| One Piece | 21 |
| Bleach | 269 |
| Dragon Ball Z | 813 |
| Attack on Titan | 16498 |
| Demon Slayer | 38000 |
| Jujutsu Kaisen | 40748 |
| Hunter x Hunter (2011) | 11061 |
| Fullmetal Alchemist: Brotherhood | 5114 |
| My Hero Academia | 31964 |
| Black Clover | 34572 |

---

## Local usage (Python only)

```bash
pip install requests beautifulsoup4

# Interactive menu
python anime_search.py

# Direct MAL mode
python anime_search.py --mal 1735 --ep 1

# Search by name
python anime_search.py --query "naruto shippuden" --ep 1

# JSON output
python anime_search.py --mal 1735 --ep 1 --json
```

---

## How it works

```
Browser → GitHub API (workflow_dispatch)
    → GitHub Actions runner (Ubuntu)
        → anime_search.py --mal 1735 --ep 1 --json
            → mapper.nekostream.site  (get encrypted token)
            → anikototv.to/ajax/server  (decrypt → player URL)
            → megaplay.buzz/stream/s-2/{realid}/sub  (realid extracted)
        → result.json saved as artifact
    → Browser downloads artifact zip
    → JSZip unpacks → results rendered
```
