# Multi-Channel Content Repurposer

Turn any YouTube video into ready-to-post content for Twitter, LinkedIn, and your blog - in one command.

```bash
python repurpose.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

## How it works

1. Tries to pull subtitles directly from YouTube via yt-dlp
2. If there are none, downloads the audio and transcribes it locally with Whisper large-v3
3. Feeds the transcript to GPT-4o-mini and generates platform-specific posts
4. Saves everything to the `output/` folder as Markdown files

No subtitles? No problem - the Whisper fallback handles it automatically.

## Output

```
output/VIDEO_ID_twitter.md     5-tweet thread
output/VIDEO_ID_linkedin.md    LinkedIn post
output/VIDEO_ID_blog.md        full blog article
```

## Requirements

- Python 3.10+
- OpenAI API key
- yt-dlp, faster-whisper, and a few other packages (see below)

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
OPENAI_API_KEY=your_key_here
```

## Usage

```bash
# generate posts
python repurpose.py "https://www.youtube.com/watch?v=VIDEO_ID"

# generate posts and print to console
python repurpose.py "https://www.youtube.com/watch?v=VIDEO_ID" --test

# transcript only, no GPT
python repurpose.py "https://www.youtube.com/watch?v=VIDEO_ID" --subs-only
```

## YouTube authentication

Some videos require you to be signed in. If you hit that, export cookies from your browser and save them as `cookies.txt` in the project folder. See [COOKIES_SETUP.md](COOKIES_SETUP.md) for step-by-step instructions.

## Stack

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - subtitles and audio extraction
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) - local speech-to-text
- [openai-python](https://github.com/openai/openai-python) - GPT-4o-mini
- [rich](https://github.com/Textualize/rich) - terminal output

## License

MIT
