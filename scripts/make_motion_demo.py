"""Author original MAKE TIME scene templates and a 20-second electronic score.

Only creates assets. Import the score and place the JSON compositions through
the editor/MCP so the resulting timeline remains a normal editable project.
"""
import argparse,json,math,os,sys,wave
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
INK='#101315'; PAPER='#f4f1e8'; LEMON='#e8ff69'; PINK='#ff6b95'; TEAL='#5ce1d2'

def keys(*values,mode='Bezier'):
    result=[dict(time=t,value=v,interpolation=mode) for t,v in values]
    if mode=='Bezier':
        for k in result:k['bezier']=[.18,0,.28,1]
    return result

class Scene:
    def __init__(self,color=INK):
        self.nodes=[]; self.n=0
        self.add('rectangle',x=540,y=960,width=1080,height=1920,fill=color)
    def add(self,kind,**data):
        self.n+=1; identifier=data.pop('id',f'layer-{self.n:03d}'); self.nodes.append(dict(id=identifier,kind=kind,**data)); return identifier
    def text(self,text,x,y,size,color=PAPER,**data):
        properties=dict(text=text,x=x,y=y,font_size=size,font='Anton',fill=color,bold=False); properties.update(data)
        return self.add('text',**properties)
    def label(self,text,y,color=PAPER,**data):
        size=data.pop('font_size',30); properties=dict(font='Poppins',bold=True,tracking=4); properties.update(data)
        return self.text(text,540,y,size,color,**properties)
    def line(self,y,color=PAPER):
        self.add('path',path=[['M',100,y],['L',980,y]],fill='none',stroke=color,stroke_width=2,keyframes={'trim':keys((.15,0),(.8,1))})
    def circle(self,x,y,size,color,**data):return self.add('ellipse',x=x,y=y,width=size,height=size,fill=color,**data)
    def finish(self,incoming=None,outgoing=None):
        from kinetic_cut.motion import validate
        if incoming:self.add('rectangle',x=540,y=960,width=2160,height=2160,fill=incoming,end=.4,keyframes={'x':keys((0,540),(.38,2160))})
        if outgoing:self.add('rectangle',x=-1100,y=960,width=2160,height=2160,fill=outgoing,start=3.65,keyframes={'x':keys((3.65,-1100),(4,540))})
        return validate(dict(version=1,canvas=[1080,1920],nodes=self.nodes,motion_blur=dict(samples=4,shutter=180)))

def clock(scene,x,y,size,colour=LEMON,parent=''):
    group=scene.add('group',x=x,y=y,parent=parent,keyframes={'rotation':keys((0,-20),(1,0),(4,35),mode='Smooth')})
    scene.circle(0,0,size,'none',parent=group,stroke=colour,stroke_width=5,keyframes={'trim':keys((0,0),(.7,1))})
    for n in range(12):
        angle=n*math.tau/12
        scene.add('path',parent=group,path=[['M',math.sin(angle)*size*.41,-math.cos(angle)*size*.41],['L',math.sin(angle)*size*.45,-math.cos(angle)*size*.45]],fill='none',stroke=colour,stroke_width=6)
    hand=scene.add('group',parent=group,keyframes={'rotation':keys((0,-90),(3.8,450),mode='Linear')})
    scene.add('path',parent=hand,path=[['M',0,20],['L',0,-size*.34]],fill='none',stroke=colour,stroke_width=10)
    scene.circle(0,0,24,colour,parent=group)
    return group

def build():
    scenes=[]
    s=Scene(); s.label('01 / THE ONLY CURRENCY',245,LEMON); s.line(320,LEMON)
    clock(s,540,890,860,colour='#465245')
    s.text('24',540,865,460,LEMON,text_mode='character',entry_easing='Back Out',entry_duration=.55,stagger=.1,entry_y=200,entry_rotation=-10,entry_scale=.65)
    s.text('HOURS.',540,1185,130,PAPER,tracking=10,text_mode='character',start=.45,entry_duration=.4,stagger=.04,entry_y=60)
    s.label('SAME DAY. EVERY DAY.',1480,LEMON,start=.8,text_mode='word',stagger=.08,entry_duration=.3,entry_y=40)
    s.circle(180,1650,24,PINK,keyframes={'scale':keys((0,0),(.4,1),mode='Back Out'),'scale_y':keys((0,0),(.4,1),mode='Back Out')})
    s.text('WHAT WILL YOU DO WITH IT?',605,1650,26,PAPER,font='Poppins',bold=True,tracking=1,start=1)
    scenes.append(('01-24-hours',s.finish(outgoing=PINK)))

    s=Scene(); s.label('02 / THE ATTENTION ECONOMY',245,PINK)
    s.text("DON'T",540,475,192,PINK,text_mode='character',entry_easing='Back Out',entry_duration=.45,stagger=.03,entry_y=-120)
    phone=s.add('group',x=540,y=920,keyframes={'rotation':keys((0,-20),(.55,4),(3.65,-4),mode='Back Out'),'y':keys((0,1150),(.65,920),(3.6,890))})
    s.add('rectangle',parent=phone,width=430,height=720,radius=52,fill='#21272c',stroke=PAPER,stroke_width=6)
    screen=s.add('group',parent=phone,y=35,mask=dict(kind='rectangle',width=370,height=595))
    feed=s.add('group',parent=screen,keyframes={'y':keys((0,180),(3.9,-670),mode='Linear')})
    for n in range(6):
        y=n*225-170; s.add('rectangle',parent=feed,y=y,width=330,height=195,radius=22,fill=(PINK,TEAL,LEMON)[n%3])
        s.text('ONE MORE',0,y-20,44,INK,parent=feed,font='Poppins',bold=True)
        s.text('JUST ONE MORE.',0,y+48,21,INK,parent=feed,font='Poppins',bold=True,tracking=1)
    s.add('rectangle',parent=phone,y=-303,width=120,height=13,radius=6,fill=PAPER)
    s.text('SPEND IT',540,1390,128,PAPER,text_mode='word',start=.3,stagger=.08,entry_duration=.4,entry_y=85)
    s.text('SCROLLING.',540,1535,128,PINK,text_mode='character',start=.6,stagger=.025,entry_easing='Back Out',entry_duration=.4,entry_y=70)
    s.label('YOUR ATTENTION HAS A PRICE.',1690,PAPER,start=1.3,font_size=25,tracking=1)
    scenes.append(('02-stop-scrolling',s.finish(incoming=PINK,outgoing=LEMON)))

    s=Scene(); s.label('03 / TAKE IT BACK',245,LEMON)
    s.circle(540,985,940,LEMON,keyframes={'scale':keys((0,.02),(.6,1),(3.6,1.035),mode='Back Out'),'scale_y':keys((0,.02),(.6,1),(3.6,1.035),mode='Back Out')})
    s.circle(540,985,1050,'none',stroke=LEMON,stroke_width=3,keyframes={'trim':keys((.1,0),(1.4,1))})
    s.text('MAKE',540,820,265,INK,start=.2,text_mode='character',entry_duration=.45,entry_easing='Back Out',stagger=.045,entry_y=120,entry_rotation=-8)
    s.text('TIME.',540,1120,300,INK,start=.55,text_mode='character',entry_duration=.4,entry_easing='Back Out',stagger=.045,entry_y=120)
    s.label('LESS NOISE.',430,PAPER,start=.5,text_mode='word',entry_duration=.25,stagger=.1)
    s.label('MORE SIGNAL.',1510,PAPER,start=.8,text_mode='word',entry_duration=.25,stagger=.1)
    s.add('path',x=540,y=1690,path=[['M',-35,0],['L',35,0],['M',12,-23],['L',35,0],['L',12,23]],fill='none',stroke=PINK,stroke_width=9,keyframes={'trim':keys((1,0),(1.5,1)),'rotation':keys((1,-45),(2,0),mode='Back Out')})
    scenes.append(('03-make-time',s.finish(incoming=LEMON,outgoing=TEAL)))

    s=Scene(); s.label('04 / INVEST IN YOURSELF',245,TEAL)
    s.text('FOR WHAT',540,430,100,PAPER,text_mode='word',entry_duration=.35,stagger=.07)
    s.text('MATTERS.',540,605,172,TEAL,text_mode='character',entry_easing='Back Out',entry_duration=.4,stagger=.035,entry_y=100)
    symbols=[([['M',0,-50],['L',50,0],['L',0,50],['L',-50,0],['Z']],[['M',-45,-45],['L',45,-45],['L',45,45],['L',-45,45],['Z']]),
             ([['M',-45,-45],['L',0,-25],['L',45,-45],['L',45,40],['L',0,60],['L',-45,40],['Z']],None),
             ([['M',0,45],['C',-100,-15,-35,-95,0,-40],['C',35,-95,100,-15,0,45],['Z']],None)]
    for n,(word,colour) in enumerate(zip(('CREATE','LEARN','CONNECT'),(LEMON,TEAL,PINK))):
        at=.25+n*.23; end_y=930+n*270
        card=s.add('group',x=540,y=end_y,keyframes={'x':keys((at,1300),(.8+n*.23,540),mode='Back Out'),'rotation':keys((at,15),(.8+n*.23,(-1)**n*2),(3.6,(-1)**n*-.5),mode='Back Out')})
        s.add('rectangle',parent=card,width=840,height=225,radius=28,fill=colour)
        source,target=symbols[n]; data=dict(parent=card,x=-295,path=source,fill=INK)
        if target:data.update(path_to=target,keyframes={'morph':keys((1.2,0),(2.1,1),(3.6,0))})
        s.add('path',**data); s.text(word,85,0,82,INK,parent=card)
    scenes.append(('04-what-matters',s.finish(incoming=TEAL,outgoing=LEMON)))

    s=Scene(); s.label('05 / START WITH ONE THING',245,LEMON); s.line(330,LEMON)
    clock(s,540,920,970,colour='#344638')
    s.text('YOUR TIME.',540,720,152,PAPER,text_mode='character',entry_easing='Back Out',entry_duration=.45,stagger=.028,entry_y=110)
    s.text('YOUR MOVE.',540,1000,150,LEMON,start=.4,text_mode='character',entry_easing='Back Out',entry_duration=.45,stagger=.028,entry_y=120)
    c=s.add('group',x=540,y=1365,keyframes={'scale':keys((.7,.4),(1.3,1),mode='Back Out'),'scale_y':keys((.7,.4),(1.3,1),mode='Back Out'),'opacity':keys((.7,0),(1,100))})
    s.add('rectangle',parent=c,width=800,height=145,radius=72,fill=LEMON); s.text('MAKE SOMETHING.',0,0,43,INK,parent=c,font='Poppins',bold=True,tracking=1)
    s.label('A FILM MADE IN KINETIC CUT',1650,PAPER,start=1.2,font_size=24,tracking=2)
    scenes.append(('05-your-move',s.finish(incoming=LEMON)))
    return scenes

def score(path):
    rate=48000; length=20.; audio=np.zeros((int(length*rate),2),np.float64); rng=np.random.default_rng(2048)
    def add(at,sound,gain=1,pan=0):
        start=round(at*rate); sound=np.asarray(sound)*gain; end=min(len(audio),start+len(sound))
        if end<=start:return
        audio[start:end,0]+=sound[:end-start]*math.sqrt((1-pan)/2); audio[start:end,1]+=sound[:end-start]*math.sqrt((1+pan)/2)
    def tone(f,duration,decay=4):
        t=np.arange(round(duration*rate))/rate; envelope=np.minimum(1,t/.008)*np.exp(-decay*t/duration)
        return (np.sin(math.tau*f*t)+.22*np.sin(math.tau*f*2*t)+.08*np.sin(math.tau*f*3*t))*envelope
    for beat in range(40):
        t=np.arange(round(.38*rate))/rate; phase=math.tau*(46*t+100*.022*(1-np.exp(-t/.022))); kick=np.sin(phase)*np.exp(-t*13)
        add(beat*.5,kick,.65)
        if beat%2:
            t=np.arange(round(.18*rate))/rate; noise=rng.normal(0,1,len(t)); add(beat*.5,(np.diff(noise,prepend=0)*.25+np.sin(math.tau*185*t)*.35)*np.exp(-t*22),.35)
    for tick in range(80):
        t=np.arange(round(.07*rate))/rate; noise=rng.normal(0,1,len(t)); add(tick*.25,np.diff(noise,prepend=0)*np.exp(-t*70),.047,(-1)**tick*.55)
    chords=((57,60,64),(53,57,60),(48,52,55),(55,59,62),(57,60,64))
    for section,chord in enumerate(chords):
        for note in chord:add(section*4,tone(440*2**((note-69)/12),4,1.5),.08,(-1)**note*.3)
        for n in range(16):
            note=chord[n%3]+12+(12 if n%8>=4 else 0); add(section*4+n*.25,tone(440*2**((note-69)/12),.22,4),.13,(-1)**n*.3)
        for n in range(8):add(section*4+n*.5,tone(440*2**((chord[0]-12-69)/12),.42,4),.28)
    for at in (3.7,7.7,11.7,15.7):
        t=np.arange(round(.3*rate))/rate; add(at,rng.normal(0,1,len(t))*np.sin(np.pi*t/.3)**2,.06)
    # Short stereo echo, controlled peaks and a clean tail without clipping.
    delay=round(.1875*rate); original=audio.copy(); audio[delay:,0]+=original[:-delay,1]*.17; audio[delay:,1]+=original[:-delay,0]*.17
    audio=np.tanh(audio*1.2); audio*=.89/max(1e-8,np.abs(audio).max()); audio[:240]*=np.linspace(0,1,240)[:,None]; audio[-24000:]*=np.linspace(1,0,24000)[:,None]
    with wave.open(str(path),'wb') as f:f.setnchannels(2); f.setsampwidth(2); f.setframerate(rate); f.writeframes((audio*32767).astype('<i2').tobytes())
    return dict(seconds=length,sample_rate=rate,peak=float(np.abs(audio).max()),rms=float(np.sqrt(np.mean(audio**2))))

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('output',type=Path); args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from kinetic_cut.caption_fonts import load_fonts
    from kinetic_cut.motion import draw
    from PySide6.QtGui import QImage,QPainter,QColor
    app=QApplication([]); load_fonts(); scenes=build(); inventory=[]
    contact=QImage(1080,784,QImage.Format_RGB32); contact.fill(QColor(INK)); painter=QPainter(contact)
    for n,(name,scene) in enumerate(scenes):
        path=args.output/(name+'.json'); path.write_text(json.dumps(scene,indent=2),encoding='utf-8'); inventory.append(dict(name=name,start=n*4,duration=4,scene=scene))
        preview=draw(scene,1.7,(216,384),30); painter.drawImage(n*216,0,preview)
        preview=draw(scene,.4,(216,384),30); painter.drawImage(n*216,400,preview)
    painter.end(); contact.save(str(args.output/'contact-sheet.png'))
    metadata=score(args.output/'make-time-score.wav'); (args.output/'timeline.json').write_text(json.dumps(inventory,indent=2),encoding='utf-8'); (args.output/'score.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    print(json.dumps(dict(scenes=len(scenes),audio=metadata,output=str(args.output.resolve()))))
