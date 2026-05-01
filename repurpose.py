import os
import re
import sys
import asyncio
import argparse
from functools import partial
from pathlib import Path
from typing import Optional

import aiofiles
from dotenv import load_dotenv
from openai import AsyncOpenAI
from rich.console import Console
from rich.theme import Theme

load_dotenv()
console = Console(theme=Theme({"info": "cyan", "warning": "yellow", "error": "red bold"}))


class ContentRepurposer:

    def __init__(self, api_key: Optional[str] = None):
        self.client = AsyncOpenAI(api_key=api_key) if api_key else None
        self.output_dir = Path("output")
        self.output_dir.mkdir(exist_ok=True)

    def parse_youtube_url(self, url: str) -> Optional[str]:
        patterns = [
            r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",
            r"(?:embed\/)([0-9A-Za-z_-]{11})",
            r"(?:youtu\.be\/)([0-9A-Za-z_-]{11})",
        ]
        for pattern in patterns:
            m = re.search(pattern, url)
            if m:
                return m.group(1)
        return None

    def _cookie_args(self) -> list[str]:
        for name in ("cookies.txt", "cookies.json"):
            p = Path(name)
            if p.exists():
                console.print(f"[info]Using {name}[/info]")
                return ["--cookies", str(p.resolve())]
        console.print("[warning]No cookies file found, trying without auth[/warning]")
        return []

    def _check_ytdlp_error(self, stderr: str, stdout: str) -> None:
        err = stderr.lower()
        out = stdout.lower()
        if "sign in to confirm" in err or "sign in to confirm" in out:
            raise ValueError(
                "❌ YouTube requires sign-in to access this video.\n\n"
                "Fix:\n"
                "1. Install the 'Get cookies.txt LOCALLY' Chrome extension\n"
                "2. Go to youtube.com and log in\n"
                "3. Click the extension icon → Export\n"
                "4. Save the file as cookies.txt next to repurpose.py\n"
                "5. Run again"
            )
        if "video unavailable" in err or "is private" in err:
            raise ValueError("❌ Video is unavailable or private.")
        if "not a valid url" in err:
            raise ValueError("❌ Invalid YouTube URL.")

    async def _fetch_subtitles(self, video_id: str) -> Optional[str]:
        console.print(f"[info]📄 Looking for subtitles: {video_id}...[/info]")

        cmd = [
            "yt-dlp",
            "--write-subs",
            "--write-auto-subs",
            "--sub-langs", "en,es",
            "--skip-download",
            "--no-playlist",
            "--output", video_id,
            *self._cookie_args(),
            f"https://www.youtube.com/watch?v={video_id}",
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=60)
        stdout_text = stdout_b.decode("utf-8", errors="replace")
        stderr_text = stderr_b.decode("utf-8", errors="replace")

        console.print(f"[dim]yt-dlp: {stderr_text[:150].strip() or 'ok'}[/dim]")

        if proc.returncode != 0:
            self._check_ytdlp_error(stderr_text, stdout_text)
            console.print(f"[warning]yt-dlp exit code {proc.returncode}, falling back to Whisper[/warning]")
            return None

        all_vtt = list(Path(".").glob(f"{video_id}.*.vtt"))
        if not all_vtt:
            console.print("[warning]⚠️ No subtitles found, switching to Whisper[/warning]")
            return None

        # pick best available: en > es > whatever
        chosen = None
        for lang in ("en", "es"):
            for f in all_vtt:
                if f".{lang}." in f.name or f".{lang}-" in f.name:
                    chosen = f
                    break
            if chosen:
                break
        if not chosen:
            chosen = all_vtt[0]

        console.print(f"[info]Subtitles: {chosen.name}[/info]")
        content = chosen.read_text(encoding="utf-8")

        for f in all_vtt:
            f.unlink(missing_ok=True)
        Path(f"{video_id}.info.json").unlink(missing_ok=True)

        text = self._parse_vtt(content)
        console.print(f"[info]✓ Subtitles loaded ({len(text)} chars)[/info]")
        return text

    def _parse_vtt(self, content: str) -> str:
        parts = []
        for line in content.split("\n"):
            line = line.strip()
            if (
                line
                and not line.startswith("WEBVTT")
                and not line.startswith("NOTE")
                and not re.match(r"^\d{2}:\d{2}", line)
                and not re.match(r"^\d+$", line)
            ):
                parts.append(line)
        text = " ".join(parts)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    async def _download_audio(self, video_id: str) -> Path:
        console.print(f"[info]🎵 Downloading audio for {video_id}...[/info]")

        cmd = [
            "yt-dlp",
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "--no-playlist",
            "--output", f"{video_id}_audio",
            *self._cookie_args(),
            f"https://www.youtube.com/watch?v={video_id}",
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=600)
        stdout_text = stdout_b.decode("utf-8", errors="replace")
        stderr_text = stderr_b.decode("utf-8", errors="replace")

        if proc.returncode != 0:
            self._check_ytdlp_error(stderr_text, stdout_text)
            raise ValueError(f"❌ yt-dlp failed to download audio:\n{stderr_text[:300]}")

        audio = Path(f"{video_id}_audio.mp3")
        if not audio.exists():
            candidates = list(Path(".").glob(f"{video_id}_audio*"))
            if not candidates:
                raise ValueError("❌ Audio file not found after download")
            audio = candidates[0]

        console.print(f"[info]✓ Audio: {audio.name} ({audio.stat().st_size // 1024} KB)[/info]")
        return audio

    def _run_whisper(self, audio: Path) -> str:
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise RuntimeError("❌ faster-whisper not installed.\nRun: pip install faster-whisper")

        console.print("[info]🧠 Whisper large-v3 running (takes a few minutes)...[/info]")

        # cpu + int8 works without a GPU — swap to cuda/float16 if you have one
        model = WhisperModel("large-v3", device="cpu", compute_type="int8")
        segments, info = model.transcribe(
            str(audio),
            beam_size=5,
            language=None,
            vad_filter=True,
        )

        console.print(f"[info]Detected language: {info.language} ({info.language_probability:.0%})[/info]")
        return " ".join(s.text.strip() for s in segments).strip()

    async def _transcribe(self, audio: Path) -> str:
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(None, partial(self._run_whisper, audio))
        finally:
            audio.unlink(missing_ok=True)

    async def get_transcript(self, video_id: str) -> str:
        # step 1 — subtitles
        try:
            text = await self._fetch_subtitles(video_id)
            if text and len(text) > 50:
                return text
        except ValueError:
            raise
        except Exception as e:
            console.print(f"[warning]⚠️ Subtitle error: {e}[/warning]")

        # step 2 — whisper fallback
        console.print("[info]🎙️ No subtitles, falling back to Whisper...[/info]")
        audio = await self._download_audio(video_id)
        text = await self._transcribe(audio)

        if not text or len(text) < 50:
            raise ValueError("❌ Whisper couldn't transcribe this video. Try a different one.")

        console.print(f"[info]✓ Transcript done ({len(text)} chars)[/info]")
        return text

    def _trim(self, text: str, max_chars: int = 12000) -> str:
        if len(text) <= max_chars:
            return text
        cut = text[:max_chars].rfind(" ")
        return text[:cut if cut != -1 else max_chars] + "..."

    async def _gpt(self, text: str, prompt: str) -> str:
        r = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text},
            ],
            temperature=0.7,
            max_tokens=4000,
        )
        return r.choices[0].message.content

    async def gen_twitter(self, text: str) -> str:
        return await self._gpt(text, """Write a Twitter thread of exactly 5 tweets based on the transcript.

Rules:
1. Each tweet under 200 characters
2. First tweet is a hook that grabs attention
3. Hashtags in every tweet
4. Last tweet ends with a retweet CTA
5. Number them: 1/5, 2/5, etc.

Format:
---
Tweet 1/5: [text]

Tweet 2/5: [text]
---""")

    async def gen_linkedin(self, text: str) -> str:
        return await self._gpt(text, """Write one LinkedIn post based on the transcript.

Rules:
1. Engaging, sparks discussion
2. Emojis where they fit
3. CTA at the end
4. First-person voice

Structure:
🎯 Main takeaway

[Body]

💭 Question for readers

#Hashtags""")

    async def gen_blog(self, text: str) -> str:
        return await self._gpt(text, """Write a blog post based on the transcript.

Rules:
1. H1 title at the top
2. H2 for each section
3. Numbered lists where they fit
4. "Conclusion" section at the end

Format:
---
# H1 Title

## Section 1

Text...

## Conclusion

Closing thoughts...
---""")

    async def generate_all(self, text: str) -> dict[str, str]:
        raw = await asyncio.gather(
            self.gen_twitter(text),
            self.gen_linkedin(text),
            self.gen_blog(text),
            return_exceptions=True,
        )
        platforms = ["twitter", "linkedin", "blog"]
        results = {}
        for platform, res in zip(platforms, raw):
            if isinstance(res, Exception):
                console.print(f"[warning]⚠️ Error generating {platform}: {res}[/warning]")
                results[platform] = f"Error: {res}"
            else:
                results[platform] = res
        return results

    async def _save(self, video_id: str, name: str, content: str) -> Path:
        fp = self.output_dir / f"{video_id}_{name}.md"
        async with aiofiles.open(fp, "w", encoding="utf-8") as f:
            await f.write(content)
        return fp

    async def process(self, url: str) -> dict:
        video_id = self.parse_youtube_url(url)
        if not video_id:
            raise ValueError("❌ Couldn't parse a video ID from that URL.")

        console.print(f"[info]📥 Video: {video_id}[/info]")

        transcript = self._trim(await self.get_transcript(video_id))
        console.print(f"[info]✨ Transcript ready ({len(transcript)} chars)[/info]")
        console.print("[info]🚀 Generating content...[/info]")

        results = await self.generate_all(transcript)

        fps = await asyncio.gather(*[
            self._save(video_id, platform, content)
            for platform, content in results.items()
        ])
        for fp in fps:
            console.print(f"[info]✅ {fp.name}[/info]")

        return results

    async def process_subs_only(self, url: str) -> str:
        video_id = self.parse_youtube_url(url)
        if not video_id:
            raise ValueError("❌ Couldn't parse a video ID from that URL.")

        console.print(f"[info]📄 Fetching transcript: {video_id}[/info]")
        transcript = await self.get_transcript(video_id)

        fp = self.output_dir / f"{video_id}_transcript.md"
        async with aiofiles.open(fp, "w", encoding="utf-8") as f:
            await f.write(transcript)

        console.print(f"[info]✅ Saved: {fp.name}[/info]")
        return transcript


async def main(url: str, test_mode: bool = False, subs_only: bool = False) -> None:
    if not url:
        console.print("[error]❌ Provide a YouTube URL.[/error]")
        console.print('[info]Example: python repurpose.py "https://youtu.be/dQw4w9WgXcQ"[/info]')
        sys.exit(1)

    if subs_only:
        r = ContentRepurposer()
        try:
            with console.status("[bold green]Fetching transcript..."):
                transcript = await r.process_subs_only(url)
            console.print("[bold green]🎉 Done! File saved to output/[/bold green]\n")
            console.print(transcript)
        except ValueError as e:
            console.print(f"[error]{e}[/error]")
            sys.exit(1)
        except Exception as e:
            console.print(f"[error]❌ Error: {e}[/error]")
            sys.exit(1)
        return

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        console.print("[error]❌ OPENAI_API_KEY not found.[/error]")
        console.print("[info]Add this to your .env file: OPENAI_API_KEY=your_key_here[/info]")
        sys.exit(1)

    r = ContentRepurposer(api_key=api_key)
    try:
        with console.status("[bold green]Processing video..."):
            results = await r.process(url)

        console.print("[bold green]🎉 Done! Files saved to output/[/bold green]")

        if test_mode:
            for platform, content in results.items():
                console.print(f"\n[info]=== {platform.upper()} ===[/info]")
                console.print(content)
    except ValueError as e:
        console.print(f"[error]{e}[/error]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[error]❌ Error: {e}[/error]")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="YouTube → Twitter / LinkedIn / Blog posts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  python repurpose.py "https://youtu.be/xxx"\n'
            '  python repurpose.py "https://youtu.be/xxx" --test\n'
            '  python repurpose.py "https://youtu.be/xxx" --subs-only\n'
        ),
    )
    parser.add_argument("url", nargs="?", help="YouTube video URL")
    parser.add_argument("--test", action="store_true", help="Print output to console in addition to saving files")
    parser.add_argument("--subs-only", action="store_true", dest="subs_only",
                        help="Only fetch the transcript, skip post generation")

    args = parser.parse_args()
    asyncio.run(main(args.url, args.test, args.subs_only))
