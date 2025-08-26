import ffmpeg

voice = ffmpeg.input('narration.wav').audio
bgm   = ffmpeg.input('bgm.wav').audio.filter('volume', 0.4)

# Sidechain-duck BGM under voice (pro NLE vibe)
# mixed = ffmpeg.filter([bgm, voice], 'sidechaincompress',
#                       threshold=0.05, ratio=8, attack=20, release=300)

# Or simple equal mix:
mixed = ffmpeg.filter([bgm, voice], 'amix', inputs=2, dropout_transition=200)

# Base video = looped panel
v = ffmpeg.input('panel.jpg', loop=1, framerate=30).video.filter('scale', 1920, 1080)

ffmpeg.output(v, None, 'out/track_mix.mp4',
              vcodec='libx264', acodec='aac', pix_fmt='yuv420p',
              **{'tune':'stillimage'}, shortest=None).run(quiet=True)

#Analogy: two audio tracks stacked vertically; both audible at once (with ducking).
