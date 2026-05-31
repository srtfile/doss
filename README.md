# Anime Stream Finder

Get Megaplay / Vidwish stream URLs for any anime episode using MAL ID.

## Web UI
Live at: **https://srtfile.github.io/doss/**

Enter your GitHub token + MAL ID + episode → get stream URLs in ~30-60s.

## Common MAL IDs
| Anime | MAL ID |
|-------|--------|
| Naruto | 20 |
| Naruto: Shippuden | 1735 |
| One Piece | 21 |
| Bleach | 269 |
| Attack on Titan | 16498 |
| Demon Slayer | 38000 |
| Jujutsu Kaisen | 40748 |
| Hunter x Hunter (2011) | 11061 |
| Fullmetal Alchemist: Brotherhood | 5114 |
| My Hero Academia | 31964 |

## Local usage
```bash
pip install requests beautifulsoup4
python anime_search.py                    # interactive
python anime_search.py --mal 1735 --ep 1  # direct
python anime_search.py -q "naruto" -e 1   # search
```
