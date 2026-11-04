"""Reusable motion assets: ready-made groups of layers (text reveals, UI pieces, lines, devices, layout helpers) that drop
straight into a Motion Composition, plus the user's own saved groups.

An asset is {name, category, description, duration, size, backdrop, nodes}. Nodes are ordinary composition layers laid
out around (0, 0) with times starting at 0; inserting wraps them in one group at the drop point and shifts every time by
the playhead, so the result is fully editable like any other layers.
"""
import copy
import json
import re
from pathlib import Path

PAPER = '#f4efec'; INK = '#1a1613'; GREY = '#8c857f'; LIGHT = '#d3cdc7'; ACCENT = '#c4573f'; CARD = '#efebe3'; DARK = '#1c1c1e'; PILL = '#e7e1da'
SERIF = 'Newsreader'; SERIF_M = 'Newsreader Medium'; STATE = 'Fraunces SemiBold'; SANS = 'Inter'; SANS_M = 'Inter Medium'; SANS_B = 'Inter SemiBold'
CATEGORIES = ('Text', 'UI', 'Lines & shapes', 'Devices', 'Layout', 'Mine')


def k(*pairs, ease='Ease Out'):
    return [dict(time=float(p[0]), value=float(p[1]), interpolation=p[2] if len(p) > 2 else ease) for p in pairs]


def fade(a, d=.3, to=100): return k((a, 0), (a + d, to))
def pop(a, d=.35, s=.6): return k((a, s, 'Back Out'), (a + d, 1))
def shadow(o=14, b=60, y=24): return dict(enabled=True, color='#3a2a1e', opacity=o, blur=b, x=0, y=y)


def text(id, value, x=0, y=0, size=60, font=SERIF, fill=INK, **kw):
    return dict(id=id, kind='text', text=value, x=x, y=y, font=font, font_size=size, bold=False, fill=fill, **kw)


def reveal(id, value, x=0, y=0, size=96, font=SERIF, fill=INK, start=0., runs=None, **kw):
    """Word-by-word blur-in that settles from light grey to the final colour."""
    node = text(id, value, x, y, size, font, fill, text_mode='word', stagger=.12, entry_duration=.5, entry_y=size * .13, entry_blur=12,
                entry_color=LIGHT, entry_easing='Ease Out', start=start, **kw)
    if runs: node['runs'] = runs
    return node


def rect(id, w, h, x=0, y=0, fill=CARD, r=0, **kw):
    return dict(id=id, kind='rectangle', x=x, y=y, width=w, height=h, radius=r, fill=fill, **kw)


CURSOR = [['M', 0, 0], ['L', 0, 40], ['L', 10, 31], ['L', 17, 46], ['L', 24, 43], ['L', 17, 28], ['L', 30, 28], ['Z']]


def cursor(id, xs, ys, press=None, start=0.):
    keys = dict(x=xs, y=ys)
    if press is not None: keys['scale'] = k((press, 1), (press + .08, .82), (press + .22, 1)); keys['scale_y'] = [dict(v) for v in keys['scale']]
    return dict(id=id, kind='path', path=CURSOR, fill=INK, stroke='#ffffff', stroke_width=2.5, start=start, keyframes=keys)


def mark(prefix, x=0, y=0, s=1., **kw):
    return [dict(id=prefix, kind='group', x=x, y=y, scale=s, scale_y=s, **kw),
            dict(id=prefix + '_moon', parent=prefix, kind='ellipse', width=92, height=92, fill=ACCENT),
            dict(id=prefix + '_cut', parent=prefix, kind='ellipse', x=24, y=-16, width=78, height=78, fill=PAPER),
            dict(id=prefix + '_star', parent=prefix, kind='polygon', sides=4, inner=.38, x=34, y=-36, width=26, height=26, fill=ACCENT)]


def child(parent, nodes):
    for n in nodes: n.setdefault('parent', parent)
    return nodes


# --------------------------------------------------------------------------------------------------------- built-ins
def a_word_reveal():
    return [reveal('t', 'Make it move.', size=110)], 2.2, (900, 260)


def a_italic_headline():
    return [reveal('t', 'Cuts the dead air.', size=96, runs=[dict(text='Cuts the '), dict(text='dead air.', italic=True)])], 2.2, (900, 240)


def a_accent_headline():
    return [reveal('t', 'Now your editor does too.', size=84, font=STATE,
                   runs=[dict(text='Now your '), dict(text='editor', italic=True, fill=ACCENT), dict(text=' does too.')])], 2.6, (1000, 240)


def a_headline_stack():
    nodes = [dict(id='stack', kind='group', layout=dict(type='stack', gap=26, reflow=.4)),
             reveal('h', 'Close the laptop.', size=100, parent='stack'),
             reveal('s', 'The edit carries on.', size=54, fill='#5b544e', font=SERIF, start=.7, parent='stack', runs=[dict(text='The edit carries on.', italic=True)])]
    return nodes, 2.4, (900, 360)


def a_wordmark():
    nodes = mark('m', -180, 0, keyframes=dict(scale=pop(0, .35, .55), scale_y=pop(0, .35, .55), opacity=fade(0, .15)))
    nodes.append(text('w', 'Overnight', -118, 6, 140, SERIF_M, text_align='left',
                      mask=dict(kind='rectangle', x=-560, y=0, width=1120, height=240, keyframes=dict(x=k((.32, -560, 'Ease In Out'), (.8, 560))))))
    return nodes, 1.6, (1040, 260)


def a_typewriter():
    return [text('t', 'find the best moments, caption it all', 0, 0, 34, SANS, '#3a3530', text_mode='typewriter', stagger=.03, caret=True)], 2.2, (900, 120)


def a_counter():
    return [text('n', '0', 0, -10, 150, SANS_B, INK, text_mode='counter', number_suffix='%', keyframes=dict(number=k((0, 0, 'Ease Out'), (1.4, 87)))),
            text('l', 'shipped overnight', 0, 100, 34, SANS, GREY, keyframes=dict(opacity=fade(.3)))], 1.8, (700, 340)


def a_pop_title():
    return [text('t', 'NO WAY', 0, 0, 140, SANS_B, '#ffffff', stroke='#000000', stroke_width=8, text_mode='character', stagger=.05, entry_duration=.3,
                 entry_scale=.4, entry_y=0, entry_easing='Back Out')], 1.4, (820, 260)


def a_label_pill():
    return [rect('p', 280, 64, fill=INK, r=32, keyframes=dict(scale=pop(0), scale_y=pop(0), opacity=fade(0, .15))),
            text('t', 'NEW FEATURE', 0, 2, 24, SANS_B, '#ffffff', tracking=3, keyframes=dict(opacity=fade(.15)))], 1.0, (420, 140)


def a_chat_card():
    nodes = [rect('card', 900, 300, fill=CARD, r=28, shadow=shadow(), keyframes=dict(y=k((0, 40), (.45, 0)), opacity=fade(0))),
             rect('thumb', 180, 102, -300, -60, fill='#b9c7d6', r=14, keyframes=dict(opacity=fade(.2), scale=pop(.2), scale_y=pop(.2))),
             text('type', 'tighten the pacing, caption every word', -410, 40, 28, SANS, '#3a3530', text_align='left', text_mode='typewriter', stagger=.025, start=.5, caret=True),
             text('meta', 'stream_night_14.mp4 · 4:12:09', -410, 110, 22, SANS, '#a39c95', text_align='left', keyframes=dict(opacity=fade(.4))),
             dict(id='send', kind='ellipse', x=390, y=110, width=58, height=58, fill=ACCENT, keyframes=dict(opacity=fade(.4), scale=k((1.75, 1), (1.81, .85), (1.95, 1)), scale_y=k((1.75, 1), (1.81, .85), (1.95, 1)))),
             dict(id='arrow', kind='path', path=[['M', 0, 12], ['L', 0, -12], ['M', -10, -2], ['L', 0, -12], ['L', 10, -2]], stroke='#ffffff', stroke_width=4, fill='none', x=390, y=110, keyframes=dict(opacity=fade(.4))),
             cursor('cur', k((1.1, 560, 'Ease In Out'), (1.7, 398)), k((1.1, 300, 'Ease In Out'), (1.7, 116)), press=1.72, start=1.1)]
    return nodes, 2.4, (1000, 420)


def a_toast():
    nodes = [dict(id='toast', kind='group', keyframes=dict(y=k((0, -60), (.35, 0)), opacity=fade(0, .25))),
             *child('toast', [rect('card', 840, 150, fill='#ffffff', r=40, shadow=shadow()), rect('icon', 84, 84, -340, 0, fill=CARD, r=20),
                              *mark('m', -340, 5, .55), text('app', 'Overnight', -270, -28, 30, SANS_B, INK, text_align='left'),
                              text('body', 'Your edit is ready to post', -270, 22, 28, SANS, '#4a443f', text_align='left'),
                              text('when', 'now', 360, -28, 22, SANS, '#a39c95', text_align='right')])]
    return nodes, 1.6, (960, 260)


def a_tab_bar():
    tabs = ['Hooks', 'Cuts', 'Zooms', 'Captions']; xs = [-300 + i * 200 for i in range(4)]
    pill = [dict(time=0., value=float(xs[0]), interpolation='Ease In Out')]
    for i in range(1, 4): pill += [dict(time=i * .7 - .15, value=float(xs[i - 1]), interpolation='Ease In Out'), dict(time=i * .7 + .15, value=float(xs[i]), interpolation='Ease In Out')]
    nodes = [rect('bar', 820, 70, fill=PILL, r=35), rect('pill', 180, 54, xs[0], fill='#ffffff', r=27, shadow=shadow(10, 10, 3), keyframes=dict(x=pill))]
    nodes += [text('t%d' % i, t, xs[i], 2, 25, SANS_M, '#6e6761') for i, t in enumerate(tabs)]
    return nodes, 2.6, (900, 140)


def a_status_chip():
    return [rect('chip', 330, 72, fill='#fbf9f6', r=36, shadow=shadow(12, 40, 14), keyframes=dict(scale=pop(0, .3, .85), scale_y=pop(0, .3, .85), opacity=fade(0, .2))),
            dict(id='dot', kind='ellipse', x=-128, width=16, height=16, fill=ACCENT, keyframes=dict(opacity=k((.2, 0), (.4, 100), (.7, 40), (1., 100), (1.3, 40), (1.6, 100)))),
            text('t', 'Working for 0:01', -92, 2, 26, SANS_M, '#4a443f', text_align='left', text_mode='counter', number_prefix='Working for 0:0',
                 keyframes=dict(number=k((.2, 1, 'Linear'), (1.8, 4))))], 2.0, (460, 140)


def a_progress():
    return [rect('track', 520, 8, fill='#e2dcd5', r=4), rect('fill', 520, 8, -260, fill=ACCENT, r=4, anchor_x=-260,
                                                          keyframes=dict(scale=k((.1, .01, 'Ease In Out'), (1.8, 1)), scale_y=k((.1, 1), (1.8, 1))))], 2.0, (640, 100)


def a_cursor_click():
    return [dict(id='ring', kind='ellipse', x=120, y=60, width=60, height=60, fill='none', stroke=ACCENT, stroke_width=4,
                 keyframes=dict(opacity=k((.78, 0), (.8, 90), (1.2, 0)), scale=k((.8, .3), (1.2, 1.4)), scale_y=k((.8, .3), (1.2, 1.4)))),
            cursor('cur', k((0, -160, 'Ease In Out'), (.7, 116)), k((0, -90, 'Ease In Out'), (.7, 54)), press=.75)], 1.4, (520, 320)


def a_button():
    return [rect('btn', 300, 84, fill=ACCENT, r=42, shadow=shadow(18, 30, 10), keyframes=dict(scale=k((.6, 1), (.68, .92), (.85, 1)), scale_y=k((.6, 1), (.68, .92), (.85, 1)))),
            text('t', 'Get started', 0, 2, 30, SANS_B, '#ffffff', keyframes=dict(scale=k((.6, 1), (.68, .92), (.85, 1)), scale_y=k((.6, 1), (.68, .92), (.85, 1))))], 1.2, (460, 180)


def a_toggle():
    return [rect('off', 150, 84, fill='#d8d2cb', r=42), rect('on', 150, 84, fill=ACCENT, r=42, keyframes=dict(opacity=k((.4, 0, 'Ease In Out'), (.7, 100)))),
            dict(id='knob', kind='ellipse', x=-33, width=66, height=66, fill='#ffffff', shadow=shadow(20, 10, 3), keyframes=dict(x=k((.4, -33, 'Ease In Out'), (.7, 33))))], 1.0, (300, 160)


def a_search():
    return [rect('bar', 760, 96, fill='#ffffff', r=48, shadow=shadow(10, 40, 12), keyframes=dict(opacity=fade(0, .2))),
            dict(id='lens', kind='ellipse', x=-318, y=-4, width=30, height=30, fill='none', stroke=GREY, stroke_width=4),
            dict(id='handle', kind='path', path=[['M', -302, 12], ['L', -290, 24]], stroke=GREY, stroke_width=4, fill='none'),
            text('q', 'best clutch moments this week', -270, 2, 32, SANS, '#3a3530', text_align='left', text_mode='typewriter', stagger=.035, start=.3, caret=True)], 2.0, (860, 160)


def a_like():
    heart = 'M0 30 C-40 0 -60 -30 -30 -48 C-12 -58 0 -44 0 -34 C0 -44 12 -58 30 -48 C60 -30 40 0 0 30 Z'
    return [dict(id='heart', kind='path', path_svg=heart, fill='#ff3b5c', keyframes=dict(scale=k((0, 0, 'Back Out'), (.4, 1.6)), scale_y=k((0, 0, 'Back Out'), (.4, 1.6)))),
            dict(id='burst', kind='emitter', emitter=dict(rate=0, bursts=[dict(time=.25, count=36)], speed=[220, 520], spread=360, life=[.4, .8], size=[10, 2], colors=['#ff8aa0', '#ffd1da'], gravity=0, shape='dot'))], 1.4, (420, 420)


def a_calendar():
    nodes = [text('mon', 'November', -476, -230, 22, SANS_M, '#6e6761', text_align='left', keyframes=dict(opacity=fade(0)))]
    days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']; w, h, g = 130, 74, 12
    for d, name in enumerate(days): nodes.append(text('d%d' % d, name, -476 + d * (w + g), -192, 17, SANS, '#a39c95', text_align='left', keyframes=dict(opacity=fade(0))))
    colours = ['#d98c6a', '#6a9bd9', '#7fbf8a', '#c9a24a', '#a07ad0', '#d96a8c']
    for c in range(30):
        r, cc = divmod(c, 7); x = -476 + w / 2 + cc * (w + g); y = -132 + r * (h + g); t = .3 + c * .05
        nodes.append(rect('c%d' % c, w, h, x, y, fill=PILL, r=10, keyframes=dict(opacity=fade(.05 + c * .01))))
        nodes.append(rect('f%d' % c, w, h, x, y, fill=colours[c % len(colours)], r=10, keyframes=dict(opacity=k((t, 0), (t + .12, 100)), scale=pop(t, .3, .7), scale_y=pop(t, .3, .7))))
    return nodes, 2.2, (1040, 560)


def a_curve_editor():
    p0 = [['M', -350, 150], ['C', -240, 150, -170, 30, -80, 10], ['C', 10, -10, 60, 140, 350, 150]]
    p1 = [['M', -350, 150], ['C', -210, 150, -160, -80, 0, -80], ['C', 140, -80, 160, 150, 350, 150]]
    nodes = [rect('card', 900, 440, fill='#222224', r=24, shadow=shadow(18), keyframes=dict(opacity=fade(0))),
             dict(id='grid', kind='grid', y=30, width=740, height=360, cell=74, fill='none', stroke='#333336', stroke_width=1.5),
             dict(id='curve', kind='path', path=p0, path_to=p1, fill='none', stroke='#e8e6e3', stroke_width=3.5, keyframes=dict(morph=k((.9, 0, 'Ease In Out'), (2., 1)), trim=k((.1, 0, 'Ease In Out'), (.7, 1)))),
             rect('key', 18, 18, -80, 10, fill='#4c8dff', rotation=45, keyframes=dict(opacity=fade(.5), x=k((.9, -80, 'Ease In Out'), (2., 0)), y=k((.9, 10, 'Ease In Out'), (2., -80)))),
             cursor('cur', k((.4, 220, 'Ease In Out'), (.9, -74), (2., 6, 'Ease In Out')), k((.4, 260, 'Ease In Out'), (.9, 16), (2., -74, 'Ease In Out')), press=.82, start=.4)]
    return nodes, 2.4, (1000, 540)


def a_media_card():
    return [rect('card', 860, 484, fill='#2a2d33', r=28, shadow=shadow(), keyframes=dict(opacity=fade(0), y=k((0, 40), (.45, 0)))),
            dict(id='img', kind='image', source='', image_fit='cover', width=860, height=484, mask=dict(kind='rectangle', width=860, height=484, radius=28)),
            text('cap', 'Choose an image in Layer → Choose image…', 0, 0, 26, SANS, '#9aa0a8', keyframes=dict(opacity=fade(.2)))], 1.2, (960, 580)


def a_video_card():
    return [rect('card', 860, 484, fill='#2a2d33', r=28, shadow=shadow(), keyframes=dict(opacity=fade(0), y=k((0, 40), (.45, 0)))),
            dict(id='video', kind='video', source='', image_fit='cover', width=860, height=484, mask=dict(kind='rectangle', width=860, height=484, radius=28)),
            text('cap', 'Set the video source in Layer → Choose video…', 0, 0, 26, SANS, '#9aa0a8', keyframes=dict(opacity=fade(.2)))], 1.2, (960, 580)


def a_loop_line():
    path = [['M', -600, 30], ['C', -360, 38, -210, 40, -120, 20], ['C', -40, 0, -70, -70, -108, -50], ['C', -145, -30, -110, 50, 0, 32],
            ['C', 110, 14, 150, -40, 110, -54], ['C', 68, -68, 58, 10, 150, 24], ['C', 260, 40, 410, 20, 610, 5]]
    return [dict(id='line', kind='path', path=path, fill='none', stroke=INK, stroke_width=3.5, trim=.5, trim_start=.5,
                 keyframes=dict(trim=k((0, .5, 'Ease In Out'), (.7, 1)), trim_start=k((0, .5, 'Ease In Out'), (.7, 0))))], 1.0, (1080, 200)


def a_underline():
    return [dict(id='line', kind='path', path=[['M', -260, 0], ['C', -120, 14, 120, -10, 260, 6]], fill='none', stroke=ACCENT, stroke_width=8,
                 keyframes=dict(trim=k((0, 0, 'Ease In Out'), (.5, 1))))], .8, (600, 100)


def a_scribble():
    path = [['M', -200, -10], ['C', -200, -110, 180, -120, 210, -20], ['C', 240, 70, -120, 110, -210, 40], ['C', -260, 0, -200, -80, -120, -96]]
    return [dict(id='ring', kind='path', path=path, fill='none', stroke=ACCENT, stroke_width=7, keyframes=dict(trim=k((0, 0, 'Ease In Out'), (.7, 1))))], 1.0, (560, 300)


def a_arrow():
    return [dict(id='shaft', kind='path', path=[['M', -220, 90], ['C', -120, -40, 60, -80, 200, -40]], fill='none', stroke=INK, stroke_width=6, keyframes=dict(trim=k((0, 0, 'Ease In Out'), (.55, 1)))),
            dict(id='head', kind='path', path=[['M', 170, -76], ['L', 206, -38], ['L', 160, -18]], fill='none', stroke=INK, stroke_width=6,
                 keyframes=dict(opacity=k((.5, 0), (.56, 100)), scale=pop(.5, .25), scale_y=pop(.5, .25)))], .9, (560, 300)


def a_brackets():
    nodes = []
    for i, (sx, sy) in enumerate(((-1, -1), (1, -1), (1, 1), (-1, 1))):
        nodes.append(dict(id='b%d' % i, kind='path', path=[['M', sx * 200, sy * 80], ['L', sx * 200, sy * 120], ['L', sx * 160, sy * 120]] if False else
                          [['M', sx * 160, sy * 120], ['L', sx * 200, sy * 120], ['L', sx * 200, sy * 80]], fill='none', stroke='#ffffff', stroke_width=5,
                          keyframes=dict(x=k((0, sx * 40), (.35, 0)), y=k((0, sy * 40), (.35, 0)), opacity=fade(0, .2))))
    return nodes, .8, (520, 340)


def a_sparkle():
    return [dict(id='spark', kind='emitter', emitter=dict(rate=0, bursts=[dict(time=0, count=60)], speed=[260, 640], spread=360, life=[.5, 1.], size=[8, 1], colors=['#ffd44d', '#fff3c4'], gravity=200)),
            dict(id='flash', kind='ellipse', width=120, height=120, fill='#fff3c4', blend='add', keyframes=dict(opacity=k((0, 100), (.4, 0)), scale=k((0, .3), (.4, 1.6)), scale_y=k((0, .3), (.4, 1.6))))], 1.2, (600, 600)


def a_laptop():
    return [rect('lid', 250, 160, 0, 80, fill=CARD, r=10, anchor_y=80, stroke=INK, stroke_width=5, keyframes=dict(scale_y=k((.6, 1, 'Ease In Out'), (1.1, .04)))),
            rect('base', 320, 14, 0, 88, fill=CARD, r=7, stroke=INK, stroke_width=5),
            rect('track', 260, 5, 0, 160, fill='#e2dcd5', r=2.5), rect('fill', 260, 5, -130, 160, fill=ACCENT, r=2.5, anchor_x=-130,
                                                                  keyframes=dict(scale=k((.2, .02, 'Ease In Out'), (1.8, .9)), scale_y=k((.2, 1), (1.8, 1))))], 2.0, (460, 420)


def a_phone():
    return [rect('body', 360, 720, fill='#111317', r=56, shadow=shadow(22, 70, 28), keyframes=dict(opacity=fade(0), y=k((0, 60), (.5, 0)))),
            rect('screen', 324, 684, fill='#2a2d33', r=40, keyframes=dict(opacity=fade(.1))),
            rect('notch', 110, 26, 0, -318, fill='#111317', r=13)], 1.0, (460, 800)


def a_browser():
    nodes = [rect('win', 920, 560, fill='#ffffff', r=22, shadow=shadow(16), keyframes=dict(opacity=fade(0), y=k((0, 40), (.45, 0)))),
             rect('bar', 920, 64, 0, -248, fill='#f1ede8', r=0), rect('addr', 520, 34, 40, -248, fill='#ffffff', r=17)]
    nodes += [dict(id='dot%d' % i, kind='ellipse', x=-420 + i * 26, y=-248, width=14, height=14, fill=c) for i, c in enumerate(('#ff5f57', '#febc2e', '#28c840'))]
    nodes.append(text('url', 'overnight.app', -160, -247, 20, SANS, '#8c857f', text_align='left'))
    return nodes, 1.0, (1000, 640)


def a_blur_slide():
    nodes = [dict(id='slide', kind='group', keyframes=dict(x=k((0, 120), (.4, 0), (1.6, 0, 'Ease In'), (2., -120)), blur_x=k((0, 50), (.4, 0), (1.6, 0, 'Ease In'), (2., 50)),
                                                           opacity=k((0, 0), (.2, 100), (1.8, 100), (2., 0)))),
             *child('slide', [rect('card', 860, 484, fill=DARK, r=26, shadow=shadow()), text('t', 'Panel content', 0, 0, 40, SANS_M, '#9aa0a8')])]
    return nodes, 2.0, (1080, 600)


def a_scene():
    return [dict(id='scene', kind='group', keyframes=dict(opacity=k((0, 0), (.25, 100), (2.7, 100, 'Ease In'), (3., 0)), blur=k((2.7, 0, 'Ease In'), (3., 14)))),
            *child('scene', [reveal('t', 'A new scene.', size=96)])], 3.0, (900, 260)


def a_stack():
    nodes = [dict(id='stack', kind='group', layout=dict(type='stack', gap=22, reflow=.4))]
    for i, (line, size, start) in enumerate((('First line', 90, 0.), ('Second line', 60, .6), ('Third line', 44, 1.2))):
        nodes.append(reveal('l%d' % i, line, size=size, start=start, parent='stack'))
    return nodes, 2.4, (900, 420)


BUILTIN = {
    'Word reveal': ('Text', 'Headline that blurs in word by word, settling from grey to ink.', a_word_reveal),
    'Headline with italic word': ('Text', 'Serif headline with an italic emphasis phrase in the same layer.', a_italic_headline),
    'Accent statement': ('Text', 'Bold statement with one italic accent-coloured word.', a_accent_headline),
    'Headline + subline stack': ('Text', 'Auto stack: the headline glides up as the subline arrives.', a_headline_stack),
    'Wordmark reveal': ('Text', 'Logo mark pops, then the name wipes out from behind it.', a_wordmark),
    'Typewriter line': ('Text', 'One line typed out with a blinking caret.', a_typewriter),
    'Counter': ('Text', 'Big number counting up with a caption.', a_counter),
    'Pop title': ('Text', 'Chunky outlined title; letters pop in.', a_pop_title),
    'Label pill': ('Text', 'Small caps label inside a pill.', a_label_pill),
    'Chat input card': ('UI', 'Prompt card with a thumbnail, typed request and a cursor clicking send.', a_chat_card),
    'Notification toast': ('UI', 'App notification that slides in from the top.', a_toast),
    'Tab bar': ('UI', 'Pill tab bar; the active pill slides across tabs.', a_tab_bar),
    'Status chip with timer': ('UI', 'Working-for chip with a pulsing dot and ticking time.', a_status_chip),
    'Progress bar': ('UI', 'Thin track that fills in the accent colour.', a_progress),
    'Cursor click': ('UI', 'Cursor glides in and clicks with a ripple.', a_cursor_click),
    'Button press': ('UI', 'Rounded button that presses down and back.', a_button),
    'Toggle switch': ('UI', 'Switch knob slides on.', a_toggle),
    'Search bar typing': ('UI', 'Search field with a typed query.', a_search),
    'Like burst': ('UI', 'Heart pops with a particle burst.', a_like),
    'Calendar fill': ('UI', 'Month grid; tiles pop in one by one (swap tiles for images).', a_calendar),
    'Curve editor': ('UI', 'Keyframe graph; a cursor drags the curve into a new shape.', a_curve_editor),
    'Media card': ('UI', 'Rounded card with a shadow for an image.', a_media_card),
    'Video card': ('UI', 'Rounded card with a shadow for a video clip.', a_video_card),
    'Loop line': ('Lines & shapes', 'Hand-drawn line with two loops, drawing out from the centre.', a_loop_line),
    'Underline draw': ('Lines & shapes', 'Marker underline that draws on.', a_underline),
    'Circle scribble': ('Lines & shapes', 'Loose hand-drawn circle around something.', a_scribble),
    'Arrow draw': ('Lines & shapes', 'Curved arrow that draws on; the head pops.', a_arrow),
    'Focus brackets': ('Lines & shapes', 'Four corner brackets close in on a subject.', a_brackets),
    'Sparkle burst': ('Lines & shapes', 'Additive flash with a burst of sparks.', a_sparkle),
    'Laptop close': ('Devices', 'Line-art laptop lid closes while progress fills.', a_laptop),
    'Phone frame': ('Devices', 'Phone body with a screen area.', a_phone),
    'Browser window': ('Devices', 'Browser window with address bar.', a_browser),
    'Blur slide panel': ('Layout', 'Group that slides in and out with horizontal motion blur.', a_blur_slide),
    'Scene (blur hand-off)': ('Layout', 'Scene group that fades in and blurs out for the next beat.', a_scene),
    'Auto stack': ('Layout', 'Vertical stack that re-centres as lines appear.', a_stack),
}
DARK_BACKDROP = {'Pop title', 'Focus brackets', 'Sparkle burst'}


def builtin(name):
    category, description, build = BUILTIN[name]
    nodes, duration, size = build()
    return dict(name=name, category=category, description=description, duration=float(duration), size=list(size),
                backdrop='#26282d' if name in DARK_BACKDROP else PAPER, nodes=nodes, builtin=True)


# ---------------------------------------------------------------------------------------------------------- user assets
def user_folder():
    from .config import CONFIG_DIR
    folder = Path(CONFIG_DIR) / 'motion-assets'; folder.mkdir(parents=True, exist_ok=True); return folder


def slug(name): return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:60] or 'asset'


def user_assets():
    out = []
    try: files = sorted(user_folder().glob('*.json'))
    except OSError: return out
    for path in files:
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(data, dict) and isinstance(data.get('nodes'), list):
                data.update(category='Mine', builtin=False, file=str(path)); out.append(data)
        except (OSError, ValueError): continue
    return out


def catalogue():
    """Every asset (built-ins first, then the user's own), without building node lists for the built-ins."""
    items = [dict(name=n, category=c, description=d, builtin=True) for n, (c, d, _) in BUILTIN.items()]
    items += [dict(name=a['name'], category='Mine', description=a.get('description', ''), builtin=False, file=a.get('file')) for a in user_assets()]
    return items


def get(name):
    if name in BUILTIN: return builtin(name)
    for asset in user_assets():
        if asset['name'] == name: return asset
    raise ValueError('Unknown motion asset %r. Use one of: %s' % (name, ', '.join(a['name'] for a in catalogue())))


def preview_scene(asset):
    """A standalone scene that frames the asset for thumbnails and hover previews."""
    w, h = asset.get('size', [900, 400]); pad = 60
    nodes = copy.deepcopy(asset['nodes'])
    root = dict(id='__asset_root__', kind='group', x=(w + pad * 2) / 2, y=(h + pad * 2) / 2)
    for n in nodes:
        if not n.get('parent'): n['parent'] = root['id']
    return dict(version=1, canvas=[w + pad * 2, h + pad * 2], nodes=[root] + nodes, background=dict(gradient=[asset.get('backdrop', PAPER)] * 2, angle=90))


def insert(scene, name, x=None, y=None, at=0.):
    """Add the asset's layers to `scene` inside one new group at (x, y) (default canvas centre), starting at time `at`.
    Returns (scene, group_id). Layer ids are made unique; follow targets and bound sound cues are remapped."""
    from .model import uid
    asset = get(name); scene = copy.deepcopy(scene); canvas = scene.get('canvas', [1080, 1920])
    x = canvas[0] / 2 if x is None else float(x); y = canvas[1] / 2 if y is None else float(y); at = max(0., float(at))
    taken = {n['id'] for n in scene.get('nodes', [])}; tag = uid()[:5]
    ids = {}
    for n in asset['nodes']:
        new = '%s_%s' % (n['id'], tag)
        while new in taken: new += 'x'
        ids[n['id']] = new; taken.add(new)
    group = '%s_%s' % (slug(name).replace('-', '_')[:24], tag)
    while group in taken: group += 'x'

    def shift(node):
        for key in ('start', 'end'):
            if key in node: node[key] = float(node[key]) + at
        for keys in node.get('keyframes', {}).values():
            for key in keys: key['time'] = float(key['time']) + at
        if isinstance(node.get('mask'), dict):
            for keys in node['mask'].get('keyframes', {}).values():
                for key in keys: key['time'] = float(key['time']) + at
    nodes = [dict(id=group, name=name, kind='group', x=x, y=y)]
    for n in copy.deepcopy(asset['nodes']):
        n['id'] = ids[n['id']]; n['parent'] = ids.get(n.get('parent', ''), group)
        if isinstance(n.get('follow'), dict) and n['follow'].get('path') in ids: n['follow']['path'] = ids[n['follow']['path']]
        shift(n); nodes.append(n)
    scene.setdefault('nodes', []).extend(nodes)
    for cue in copy.deepcopy(asset.get('sound_cues', [])):
        cue['id'] = uid(); cue['time'] = float(cue.get('time', 0)) + at
        if cue.get('node_id') in ids: cue['node_id'] = ids[cue['node_id']]
        scene.setdefault('sound_cues', []).append(cue)
    return scene, group


def capture(scene, layer_ids, name, at=0., description=''):
    """Turn selected layers (and their children) into an asset: positions relative to their shared parent's centre,
    times relative to the earliest key/start. Layers must share a parent."""
    from .motion_geometry import layout
    nodes = scene.get('nodes', []); by_id = {n['id']: n for n in nodes}
    chosen = [i for i in layer_ids if i in by_id]
    if not chosen: raise ValueError('Select the layers to save as an asset')
    tops = [i for i in chosen if by_id[i].get('parent', '') not in chosen]
    parents = {by_id[i].get('parent', '') for i in tops}
    if len(parents) != 1: raise ValueError('Saved layers must share one parent group')
    branch = set(chosen)
    while True:
        more = {n['id'] for n in nodes if n.get('parent') in branch} - branch
        if not more: break
        branch |= more
    picked = [copy.deepcopy(n) for n in nodes if n['id'] in branch]
    entries, _ = layout(scene, at)
    from PySide6.QtCore import QRectF
    bounds = QRectF()
    for i in branch:
        entry = entries.get(i)
        if entry and entry.get('visible') and not entry['hit'].isEmpty(): bounds = bounds.united(entry['hit'].boundingRect())
    parent = by_id.get(next(iter(parents)))
    centre = bounds.center() if not bounds.isEmpty() else None
    if centre is not None and parent is not None:
        inverse, ok = entries[parent['id']]['world'].inverted() if parent['id'] in entries else (None, False)
        if ok: centre = inverse.map(centre)
    cx, cy = (centre.x(), centre.y()) if centre is not None else (0., 0.)
    times = []
    for n in picked:
        times.append(n.get('start', 0.))
        for keys in n.get('keyframes', {}).values(): times += [key['time'] for key in keys]
    origin = min(times) if times else 0.
    for n in picked:
        if n['id'] in tops: n.pop('parent', None)
        for key in ('start', 'end'):
            if key in n: n[key] = max(0., n[key] - origin)
        for keys in n.get('keyframes', {}).values():
            for key in keys: key['time'] = max(0., key['time'] - origin)
        if isinstance(n.get('mask'), dict):
            for keys in n['mask'].get('keyframes', {}).values():
                for key in keys: key['time'] = max(0., key['time'] - origin)
        if n['id'] in tops:
            n['x'] = n.get('x', 0.) - cx; n['y'] = n.get('y', 0.) - cy
            for channel in ('x', 'y'):
                for key in n.get('keyframes', {}).get(channel, []): key['value'] -= cx if channel == 'x' else cy
    end = max([n.get('end', 0.) for n in picked if n.get('end', 1e5) < 1e5] + [max(times) - origin if times else 1.] + [1.])
    size = [max(120, bounds.width() + 40), max(80, bounds.height() + 40)] if not bounds.isEmpty() else [600, 400]
    cues = [copy.deepcopy(c) for c in scene.get('sound_cues', []) if c.get('node_id') in branch]
    for c in cues: c['time'] = max(0., c.get('time', 0.) - origin)
    return dict(name=name.strip()[:80] or 'My asset', category='Mine', description=description[:300], duration=float(end), size=size,
                backdrop=PAPER if not scene.get('background') else (scene['background'].get('gradient') or [PAPER])[0], nodes=picked, sound_cues=cues)


def save(asset):
    path = user_folder() / (slug(asset['name']) + '.json')
    data = {k: v for k, v in asset.items() if k not in ('builtin', 'file', 'category')}
    path.write_text(json.dumps(data, indent=1), encoding='utf-8'); return path


def delete(name):
    for asset in user_assets():
        if asset['name'] == name: Path(asset['file']).unlink(missing_ok=True); return True
    return False
