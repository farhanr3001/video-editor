import subprocess
import os

clips = [
    {
        'id': 'beat_01',
        'input': 'car_drives_into_lake.mp4',
        'ss': '00:00:50.0',
        'to': '00:00:54.2',
        'filter': 'crop=338:600:472:120,scale=1080:1920:flags=bicubic'
    },
    {
        'id': 'beat_02',
        'input': 'mythbusters_sinking.mp4',
        'ss': '00:01:52.0',
        'to': '00:01:55.9',
        'filter': 'crop=198:352:221:0,scale=1080:1920:flags=bicubic'
    },
    {
        'id': 'beat_03',
        'input': 'mythbusters_sinking.mp4',
        'ss': '00:03:19.0',
        'to': '00:03:22.9',
        'filter': 'crop=198:352:221:0,scale=1080:1920:flags=bicubic'
    },
    {
        'id': 'beat_04',
        'input': 'mythbusters_sinking.mp4',
        'ss': '00:02:18.0',
        'to': '00:02:21.5',
        'filter': 'crop=198:352:221:0,scale=1080:1920:flags=bicubic'
    },
    {
        'id': 'beat_05',
        'input': 'underwater_escape.mp4',
        'ss': '00:00:11.0',
        'to': '00:00:14.8',
        'filter': 'crop=405:720:437:0,scale=1080:1920:flags=bicubic'
    },
    {
        'id': 'beat_06',
        'input': 'seatbelt_buckle.mp4',
        'ss': '00:00:19.5',
        'to': '00:00:23.2',
        'filter': 'crop=202:360:219:0,scale=1080:1920:flags=bicubic'
    },
    {
        'id': 'beat_07',
        'input': 'escape_four_people.mp4',
        'ss': '00:00:04.0',
        'to': '00:00:08.0',
        'filter': 'crop=182:324:197:0,scale=1080:1920:flags=bicubic'
    },
    {
        'id': 'beat_08',
        'input': 'window_switch_demo.mp4',
        'ss': '00:00:14.0',
        'to': '00:00:18.7',
        'filter': 'crop=1215:2160:300:0,scale=1080:1920:flags=bicubic'
    },
    {
        'id': 'beat_09',
        'input': 'laminated_glass_warning.mp4',
        'ss': '00:00:27.5',
        'to': '00:00:31.3',
        'filter': 'crop=607:1080:656:0,scale=1080:1920:flags=bicubic'
    },
    {
        'id': 'beat_10',
        'input': 'mythbusters_window.mp4',
        'ss': '00:00:15.5',
        'to': '00:00:19.5',
        'filter': 'scale=1080:1920:flags=bicubic'
    },
    {
        'id': 'beat_11',
        'input': 'mythbusters_window.mp4',
        'ss': '00:01:10.0',
        'to': '00:01:14.4',
        'filter': 'scale=1080:1920:flags=bicubic'
    },
    {
        'id': 'beat_12',
        'input': 'escape_four_people.mp4',
        'ss': '00:00:13.5',
        'to': '00:00:17.6',
        'filter': 'crop=182:324:197:0,scale=1080:1920:flags=bicubic'
    },
    {
        'id': 'beat_13',
        'input': 'mythbusters_sinking.mp4',
        'ss': '00:01:59.0',
        'to': '00:02:03.0',
        'filter': 'crop=198:352:221:0,scale=1080:1920:flags=bicubic'
    },
    {
        'id': 'beat_14',
        'input': 'test_swimming.mp4',
        'ss': '00:00:01.0',
        'to': '00:00:05.05',
        'filter': 'crop=607:1080:656:0,scale=1080:1920:flags=bicubic'
    },
]

out_dir = os.path.abspath('build/sinking_car_assets/processed_clips')
os.makedirs(out_dir, exist_ok=True)

for c in clips:
    in_path = os.path.abspath(os.path.join('build/sinking_car_assets/videos', c['input']))
    out_path = os.path.abspath(os.path.join(out_dir, f"{c['id']}.mp4"))
    cmd = [
        'ffmpeg', '-y',
        '-ss', c['ss'],
        '-to', c['to'],
        '-i', in_path,
        '-vf', c['filter'] + ',fps=60',
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-crf', '19',
        '-pix_fmt', 'yuv420p',
        '-an',
        out_path
    ]
    print(f"Processing {c['id']}...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Error on {c['id']}: {res.stderr[-300:]}")
    else:
        print(f"Success on {c['id']}!")

print("All clips completed!")
