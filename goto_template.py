import ffmpeg

# 1) declare inputs (files) ➜ pick streams
v0 = ffmpeg.input('some.mp4').video
a0 = ffmpeg.input('some.mp4').audio

# 2) build pipelines (filters)
v  = v0.filter('scale', 1920, 1080)               # video chain
a  = a0                                           # audio chain (or more filters)

# 3) write output (map the exact streams you want)
ffmpeg.output(v, a, 'out.mp4',
              vcodec='libx264', acodec='aac', pix_fmt='yuv420p').run()

'''
Still + narration → image loops; -shortest makes video end with audio.

Still, no audio → t=... sets duration.

Image sequence → each shows 1/fps seconds; total = frames / fps.

Per-image custom durations → either per-image mini-clips + concat, or concat demuxer with duration lines.

Ken Burns doesn’t set duration; pair it with audio+-shortest or t=....'''