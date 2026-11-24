# YouTube Cookies Setup

YouTube blocks automated requests without authentication. You need to export cookies from your browser and drop them in the project folder.

## Option 1 — Browser extension (recommended)

1. Install **Get cookies.txt LOCALLY** for Chrome:
   https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc

2. Open youtube.com and sign in to your account

3. Click the extension icon → Export → Export

4. Save the file as `cookies.txt` in the same folder as `repurpose.py`

5. Run the script as usual

## Option 2 - Pull directly from browser

```bash
yt-dlp --cookies-from-browser chrome "https://www.youtube.com/watch?v=VIDEO_ID" --list-subs
```

Replace `chrome` with `firefox` or `edge` if needed.

## Notes

- Cookies expire after a week or two - if the script stops working, re-export them
- The `cookies.txt` file is basically a session token for your account - don't share it or commit it to a repo
