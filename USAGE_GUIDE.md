# Multi-Channel Content Repurposer

Takes a YouTube video and turns it into ready-to-post content for Twitter, LinkedIn, and your blog.

It first tries to pull subtitles directly from YouTube. If there aren't any, it downloads the audio and transcribes it locally with Whisper. Then feeds the transcript to GPT and you get your posts.

---

## Setup

You need Python 3.10 or higher:

```bash
python --version
```

If you don't have it, grab it from python.org.

Install dependencies:

```bash
pip install -r requirements.txt
```

If something fails, install directly:

```bash
pip install aiofiles python-dotenv openai rich faster-whisper yt-dlp
```

---

## OpenAI API key

Only needed for post generation. If you just want the transcript (`--subs-only`), skip this.

1. Sign up at openai.com
2. Create a Secret Key under API settings
3. Create a `.env` file in the project folder:

```
OPENAI_API_KEY=your_key_here
```

Keep this key private - treat it like a password.

---

## Usage

Always wrap the URL in quotes.

**Default — generates posts and saves them to `output/`:**

```bash
python repurpose.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

**With console preview - same as above but also prints results:**

```bash
python repurpose.py "https://www.youtube.com/watch?v=VIDEO_ID" --test
```

**Transcript only - no GPT, no API key needed:**

```bash
python repurpose.py "https://www.youtube.com/watch?v=VIDEO_ID" --subs-only
```

---

## Output files

Everything lands in the `output/` folder:

```
output/VIDEO_ID_twitter.md     - 5-tweet thread
output/VIDEO_ID_linkedin.md    - one LinkedIn post
output/VIDEO_ID_blog.md        - full blog article
output/VIDEO_ID_transcript.md  - plain transcript (--subs-only mode)
```

---

## Common issues

**"YouTube requires sign-in"**

You need cookies from your browser. See COOKIES_SETUP.md.

**"OPENAI_API_KEY not found"**

Make sure the `.env` file exists in the project folder and the key has no extra spaces or quotes:

```
OPENAI_API_KEY=sk-proj-...
```

**Network error / OpenAI not responding**

You probably need a VPN.

**Whisper hangs on first run**

It downloads the model on first use (~3 GB). Just wait it out - happens once.

**Got English subtitles instead of something else**

The script picks English first, then Spanish. If the video only has those, that's what you get. Whisper will auto-detect the spoken language from audio.

---

## How it works

- **yt-dlp** - pulls subtitles and audio from YouTube
- **faster-whisper** - transcribes audio locally, no external API
- **openai** - generates posts via GPT-4o-mini
- **rich** - colored terminal output
- **aiofiles** - async file writing

---

## Quick start from scratch

```bash
# 1. Go to the project folder
cd "Multi-Channel Content Repurposer"

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create your .env file with your OpenAI key

# 4. Test run
python repurpose.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --test

# 5. Full run
python repurpose.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# 6. Or just grab the transcript
python repurpose.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --subs-only
```
