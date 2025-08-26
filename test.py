import ffmpeg

def get_duration_seconds(path: str) -> float:
    info = ffmpeg.probe(path)
    # prefer an audio stream duration
    for s in info.get("streams", []):
        if s.get("codec_type") == "audio" and "duration" in s:
            return float(s["duration"])
    # fallback to container duration
    if "format" in info and "duration" in info["format"]:
        return float(info["format"]["duration"])
    raise ValueError("Duration not found")

voice = ffmpeg.input("narration.wav").audio
bgm   = ffmpeg.input("bgm.wav").audio.filter("volume", 0.75)

# Sum the tracks (normalize intelligently across overlaps)
blended = ffmpeg.filter([bgm, voice], "amix", inputs=2, dropout_transition=200)

# Trim to narration duration
dur = get_duration_seconds("narration.wav")
blended = blended.filter("atrim", end=dur).filter("asetpts", "PTS-STARTPTS")

ffmpeg.output(blended, "out/mix_blended.wav",
              acodec="pcm_s16le", ar=48000, ac=2).overwrite_output().run(quiet=True)
