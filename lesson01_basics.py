from pathlib import Path
import ffmpeg, logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
ROOT = Path(".").resolve()
OUT = (ROOT / "out"); OUT.mkdir(exist_ok=True)

def images_to_video(pattern="frames/frame_%03d.png",
                    fps=30,
                    out_path=OUT / "silent.mp4",
                    ) -> Path:
    logging.info((f"images -> video | pattern={pattern} fps={fps} -> {out_path}"))
    stream=(
        ffmpeg
        .input(pattern, framerate=fps)
        .output(str(out_path), vcodec="libx264", pix_fmt="yuv420p", preset="veryfast")
    )

    # See the underlying ffmpeg command (helps learning):
    # print("CMD:", " ".join(ffmpeg.compile(stream)))
    stream.overwrite_output().run(capture_stdout=True, capture_stderr=True)
    return out_path

def image_plus_audio(
    img="panel.jpg",
    wav="narration.wav",
    size=(1920, 1080),
    out_path=OUT / "panel_clip_static.mp4",
):
    w, h = size
    logging.info(f"image+audio -> clip | {img} + {wav} -> {out_path}")

    vsrc = ffmpeg.input(img, loop=1, framerate=30)   # input container
    asrc = ffmpeg.input(wav)                         # input container

    v = vsrc.video.filter("scale", w, h)             # VIDEO stream node
    a = asrc.audio                                   # AUDIO stream node

    stream = (
        ffmpeg
        .output(
            v, a, str(out_path),
            vcodec="libx264",
            pix_fmt="yuv420p",
            acodec="pcm_s16le",
            ar=48000, ac=2,                   # pin sane audio params
            tune="stillimage",
            shortest=None,                    # end when narration ends
            movflags="+faststart",            # nicer playback on macOS
        )
        # explicit mapping removes any guesswork:
        .global_args("-map", "0:v:0", "-map", "1:a:0")
        .overwrite_output()
    )

    print("CMD:", " ".join(ffmpeg.compile(stream)))
    # capture stderr so you see encoder/mapping messages
    stream.run(capture_stdout=True, capture_stderr=True)
    return out_path

def image_plus_audio_kenburns(img="panel.jpg", wav="narration.wav",
                              size=(1920,1080), fps=30,
                              zoom_increment=0.006,
                              out_path=OUT/"panel_clip_kenburns.mp4"):
    w,h = size
    logging.info(f"image+audio (kenburns) -> {out_path}")
    img_in = ffmpeg.input(img, loop=1, framerate=fps)
    aud_in = ffmpeg.input(wav)
    v = (img_in
         .filter("scale", 3840, -1) # upscale for nicer zoom quality
         .filter("zoompan", z=f"zoom+{zoom_increment}",
                 d=9999, s=f"{w}x{h}", fps=fps))
    stream = ffmpeg.output(
        v, aud_in, str(out_path),
        vcodec="libx264", pix_fmt="yuv420p",
        acodec="pcm_s16le", shortest=None
    )
    # print("CMD:", " ".join(ffmpeg.compile(stream)))
    stream.overwrite_output().run(capture_stdout=True, capture_stderr=True)
    return out_path

from pathlib import Path

def concat_reencode(clips, out_path=OUT/"chapter_concat.mp4"):
    # filter-based concat: v1,a1,v2,a2,... -> concat -> v,a
    logging.info(f"concat {len(clips)} clips -> {out_path}")
    ins = [ffmpeg.input(str(p)) for p in clips]
    streams = []
    for s in ins:
        streams.extend([s.video, s.audio])
    joined = ffmpeg.concat(*streams, v=1, a=1).node
    v_out, a_out = joined[0], joined[1]
    stream = ffmpeg.output(v_out, a_out, str(out_path),
                           vcodec="libx264", pix_fmt="yuv420p",
                           acodec="pcm_s16le", preset="veryfast")
    # print("CMD:", " ".join(ffmpeg.compile(stream)))
    stream.overwrite_output().run(capture_stdout=True, capture_stderr=True)
    return out_path

def draw_text(in_path, text="(soft gasp)",
              out_path=OUT/"with_text.mp4",
              font="/Library/Fonts/Arial.ttf", fontsize=56,
              x="(w-tw)/2", y="h*0.12"):
    logging.info(f"drawtext on {in_path} -> {out_path}")
    inp = ffmpeg.input(str(in_path))
    v = inp.video.filter(
        "drawtext",
        text=text,
        fontfile=font,  # use fontfile on mac to avoid font lookup issues
        fontcolor="white",
        fontsize=str(fontsize),
        x=x, y=y,
        box=1, boxcolor="black@0.4", boxborderw=8
    )
    stream = ffmpeg.output(v, inp.audio, str(out_path),
                           vcodec="libx264", pix_fmt="yuv420p", acodec="aac")
    # print("CMD:", " ".join(ffmpeg.compile(stream)))
    stream.overwrite_output().run(capture_stdout=True, capture_stderr=True)
    return out_path

import ffmpeg

def add_bgm_with_ducking(video_path,
                         narration_wav="narration.wav",
                         bgm_path="bgm.wav",
                         out_path="out/ducked.mp4"):
    v = ffmpeg.input(video_path).video
    voice = ffmpeg.input(narration_wav).audio
    music = ffmpeg.input(bgm_path).audio.filter("volume", 0.4)  # pre-attenuate BGM

    # 1) make ducked BGM (voice is the sidechain trigger)
    ducked_bgm = ffmpeg.filter(
        [music, voice], "sidechaincompress",
        threshold=0.1, ratio=8, attack=20, release=300
    )

    # 2) mix DUCKED BGM + VOICE
    mixed = ffmpeg.filter([ducked_bgm, voice], "amix", inputs=2, dropout_transition=200)

    # 3) end when the shortest stream ends (your narration),
    #    keep video stream as-is
    (
        ffmpeg
        .output(v, mixed, str(out_path),
                vcodec="copy",                       # video untouched
                acodec="pcm_s16le", ar=48000, ac=2,  # WAV-in-MP4 for now (works on your Mac)
                shortest=None, movflags="+faststart")
        .overwrite_output()
        .run(capture_stdout=True, capture_stderr=True)
    )
    return out_path


# mn_video_wrap.py
from __future__ import annotations
from pathlib import Path
import ffmpeg
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

class FFErr(RuntimeError): pass

class Clip:
    """
    Fluent builder around a single clip (video+audio streams).
    We store the *current* video stream (self.v) and audio stream (self.a).
    """
    def __init__(self):
        self.v = None  # current video stream node
        self.a = None  # current audio stream node
        self._fps = 30
        self._size = (1920,1080)
        self._tune_still = False

    # ------- Sources -------
    def from_image(self, img: str | Path, fps: int = 30, loop: bool = True) -> "Clip":
        self._fps = fps
        img = str(img)
        self.v = ffmpeg.input(img, loop=1 if loop else 0, framerate=fps)
        self._tune_still = True
        return self

    def from_video(self, mp4: str | Path) -> "Clip":
        s = ffmpeg.input(str(mp4))
        self.v, self.a = s.video, s.audio
        self._tune_still = False
        return self

    def with_audio(self, wav: str | Path) -> "Clip":
        self.a = ffmpeg.input(str(wav)).audio
        return self

    # ------- Video transforms -------
    def resize(self, w: int, h: int) -> "Clip":
        self._size = (w,h)
        self.v = self.v.filter("scale", w, h)
        return self

    def kenburns(self, zoom_increment: float = 0.0006) -> "Clip":
        w,h = self._size
        # upscale before zoom to preserve detail
        self.v = (self.v.filter("scale", 3840, -1)
                       .filter("zoompan", z=f"zoom+{zoom_increment}",
                               d=9999, s=f"{w}x{h}", fps=self._fps))
        return self

    def draw_text(self, text: str, fontfile: str = "/Library/Fonts/Arial.ttf",
                  fontsize: int = 56, x: str="(w-tw)/2", y: str="h*0.12") -> "Clip":
        self.v = self.v.filter(
            "drawtext",
            text=text,
            fontfile=fontfile,
            fontcolor="white",
            fontsize=str(fontsize),
            x=x, y=y,
            box=1, boxcolor="black@0.4", boxborderw=8
        )
        return self

    # ------- Output -------
    def save(self, out_path: str | Path, shortest: bool = True) -> Path:
        if self.v is None:
            raise FFErr("No video stream set. Did you call from_image() or from_video()?")

        kwargs = dict(vcodec="libx264", pix_fmt="yuv420p")
        if self._tune_still:
            kwargs["tune"] = "stillimage"

        out_path = Path(out_path)
        stream = None
        if self.a is not None:
            stream = ffmpeg.output(self.v, self.a, str(out_path), acodec="aac", **kwargs)
            if shortest:
                stream = stream.global_args("-shortest")
        else:
            stream = ffmpeg.output(self.v, str(out_path), **kwargs)

        try:
            logging.info(f"render clip -> {out_path}")
            # print("CMD:", " ".join(ffmpeg.compile(stream)))
            stream.overwrite_output().run(capture_stdout=True, capture_stderr=True)
        except ffmpeg.Error as e:
            raise FFErr(e.stderr.decode(errors="ignore"))
        return out_path


class Chapter:
    """
    Collect pre-rendered clips (file paths) and concatenate them with a safe re-encode.
    """
    def __init__(self):
        self._clips: list[Path] = []

    def add(self, clip_path: str | Path) -> "Chapter":
        p = Path(clip_path)
        if not p.exists():
            raise FFErr(f"Clip not found: {p}")
        self._clips.append(p)
        return self

    def render(self, out_path: str | Path) -> Path:
        if not self._clips:
            raise FFErr("No clips to concatenate.")
        logging.info(f"concat {len(self._clips)} clips -> {out_path}")

        ins = [ffmpeg.input(str(p)) for p in self._clips]
        streams = []
        for s in ins:
            streams.extend([s.video, s.audio])
        v_out, a_out = ffmpeg.concat(*streams, v=1, a=1).node
        stream = ffmpeg.output(v_out, a_out, str(out_path),
                               vcodec="libx264", pix_fmt="yuv420p",
                               acodec="aac", preset="veryfast")
        try:
            # print("CMD:", " ".join(ffmpeg.compile(stream)))
            stream.overwrite_output().run(capture_stdout=True, capture_stderr=True)
        except ffmpeg.Error as e:
            raise FFErr(e.stderr.decode(errors="ignore"))
        return Path(out_path)





if __name__ == "__main__":
    ()
