"""Original editable UI motion study: vector assets and authored interaction sound.

Generates scene/audio assets only. The project is assembled in the live editor.
"""
import argparse,json,math,os,sys,wave
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
PAPER='#edf0eb'; WHITE='#ffffff'; INK='#182022'; MUTED='#7b8785'; TEAL='#15a98f'; CORAL='#ff886c'
DURATION=18.; CLICKS=(.65,3.45,4.85,7.95,9.35,10.55,15.65)

def keys(*pairs,mode='Bezier'):
    return [dict(time=t,value=v,interpolation=mode,**({'bezier':[.22,0,.3,1]} if mode=='Bezier' else {})) for t,v in pairs]

class Scene:
    def __init__(self):self.nodes=[]
    def add(self,kind,name,**data):
        identifier='layer-'+str(len(self.nodes)+1); self.nodes.append(dict(id=identifier,name=name,kind=kind,**data)); return identifier
    def text(self,text,x,y,size=22,parent='',color=INK,**data):
        defaults=dict(text=text,x=x,y=y,font_size=size,font='Segoe UI',bold=False,fill=color,parent=parent); defaults.update(data)
        return self.add('text',text or data.get('name','Animated value'),**defaults)
    def rect(self,name,x,y,w,h,parent='',color=WHITE,radius=20,**data):
        return self.add('rectangle',name,x=x,y=y,width=w,height=h,parent=parent,fill=color,radius=radius,**data)
    def circle(self,name,x,y,d,parent='',color=TEAL,**data):return self.add('ellipse',name,x=x,y=y,width=d,height=d,parent=parent,fill=color,**data)
    def path(self,name,points,parent='',color=INK,width=3,fill='none',**data):return self.add('path',name,path=points,parent=parent,fill=fill,stroke=color,stroke_width=width,**data)
    def window(self,name,start,end,**data):
        return self.add('group',name,start=start,end=end,x=540,y=540,keyframes={'opacity':keys((start,0),(start+.22,100),(end-.2,100),(end,0))},**data)
    def mark(self,parent,x,y,color=TEAL,size=30):
        return self.path('Signal waveform',[['M',x-size*.48,y+size*.1],['L',x-size*.22,y+size*.1],['L',x-size*.08,y-size*.3],['L',x+size*.12,y+size*.35],['L',x+size*.26,y-size*.15],['L',x+size*.48,y-size*.15]],parent,color,3)

def build():
    s=Scene(); s.rect('Quiet paper canvas',540,540,1080,1080,color=PAPER,radius=0)
    s.circle('Subtle ambient glow',690,430,1050,color='#f5f7f2',opacity=30)
    # One continuous surface drives the whole edit; no pre-rendered widget footage.
    widths=keys((0,240),(.8,240),(1.25,700),(3,700),(3.4,700),(4.1,620),(7,620),(7.7,420),(8.2,420),(8.75,740),(11.9,740),(12.4,310),(12.7,310),(13.15,740),(15,740),(15.5,320),(16.3,320),(16.85,66))
    heights=keys((0,72),(.8,72),(1.25,88),(2.7,88),(3.25,310),(3.55,310),(4.1,340),(7,340),(7.7,88),(8.2,88),(8.75,470),(11.9,470),(12.4,72),(12.7,72),(13.15,430),(15,430),(15.5,72),(16.3,72),(16.85,66))
    body=dict(width=widths,height=heights,radius=keys((0,36),(1.25,32),(3.25,36),(4.1,44),(7.7,44),(8.75,38),(12.4,36),(13.15,38),(15.5,36)),x=keys((0,540),(16.3,540),(16.85,355)))
    s.rect('Morphing interface surface',540,540,240,72,radius=36,keyframes=body,shadow=dict(enabled=True,blur=24,opacity=14,x=0,y=14))
    dark=keys((0,0),(3.7,0),(4.05,100),(7,100),(7.7,0),(11.9,0),(12.35,100),(12.75,100),(13.1,0),(15,0),(15.5,100),(16.4,100),(16.85,0))
    s.rect('Dark player and status surface',540,540,240,72,color=INK,keyframes={**body,'opacity':dark})
    opening=s.window('Invitation',0,1.25)
    s.path('Search symbol',[['M',-69,-5],['C',-69,-20,-91,-20,-91,-5],['C',-91,10,-69,10,-69,-5],['M',-71,6],['L',-60,17]],opening,INK,2.6)
    s.text('Find a moment',12,0,20,opening)

    search=s.window('Search and suggestions',1.2,4.05)
    search_content=s.add('group','Search field contents',parent=search,keyframes={'y':keys((1.2,0),(2.7,0),(3.25,-105))})
    s.path('Search field icon',[['M',-295,-5],['C',-295,-18,-315,-18,-315,-5],['C',-315,8,-295,8,-295,-5],['M',-297,6],['L',-289,14]],search_content,MUTED,2.5)
    s.text('night drive',-265,0,26,search_content,text_align='left',text_mode='typewriter',caret=True,caret_period=.75,keyframes={'reveal':keys((1.4,0),(2.25,1),mode='Linear')})
    s.text('⌘ K',295,0,15,search_content,color=MUTED)
    results=s.add('group','Result cards',parent=search,start=2.75,keyframes={'opacity':keys((2.75,0),(3.25,100))})
    s.path('Field divider',[['M',-310,-59],['L',310,-59]],results,'#e7ece8',1.2)
    for n,(name,sub,col) in enumerate((('Afterglow','Atmosphere · 0:32',CORAL),('Night Drive','Audio loop · 0:24',TEAL))):
        y=-4+n*89
        s.rect(name+' row',0,y,642,77,results,color='#f2f5f1' if n==0 else '#e4f5ee',radius=18)
        s.rect(name+' artwork',-266,y,49,49,results,color=col,radius=12,gradient=[col,'#6b83d4'])
        s.text(name,-225,y-12,23,results,bold=True,text_align='left')
        s.text(sub,-225,y+17,15,results,color=MUTED,text_align='left')
        if n:s.path('Result launch arrow',[['M',274,y],['L',288,y],['M',282,y-6],['L',288,y],['L',282,y+6]],results,TEAL,2.6)

    player=s.window('Night Drive player',3.95,7.45)
    s.rect('Album artwork',-185,-55,130,130,player,color=TEAL,radius=23,gradient=[TEAL,'#a56fd3',CORAL])
    for n in range(5):s.path('Artwork contour '+str(n),[['M',-237,-72+n*14],['C',-206,-109+n*16,-184,-18+n*13,-135,-78+n*12]],player,'#f0ffff',2,opacity=35)
    s.text('Night Drive',-87,-82,28,player,color=WHITE,bold=True,text_align='left')
    s.text('SIGNAL LIBRARY',-87,-42,13,player,color='#a8b8b5',text_align='left',tracking=1.5)
    s.text('A little more wonder.',-87,-7,17,player,color='#ccd5d0',text_align='left')
    s.path('Playback track',[['M',-260,70],['L',260,70]],player,'#445052',6)
    s.path('Playing progress',[['M',-260,70],['L',260,70]],player,WHITE,6,keyframes={'trim':keys((4.3,.08),(5.1,.08),(7.2,.64),mode='Linear')})
    s.circle('Playback dot',-218,70,13,player,color=WHITE,keyframes={'x':keys((4.3,-218),(5.1,-218),(7.2,73),mode='Linear')})
    s.text('',-260,98,12,player,color='#96a6a4',text_align='left',text_mode='counter',number_prefix='0:0',number_grouping=False,keyframes={'number':keys((4.3,0),(5.1,0),(7.2,3),mode='Linear')})
    s.text('0:24',260,98,12,player,color='#96a6a4',text_align='right')
    play=s.add('group','Play button',parent=player,start=4,end=5.05)
    s.path('Play triangle',[['M',-7,116],['L',11,128],['L',-7,140],['Z']],play,WHITE,0,fill=WHITE)
    pause=s.add('group','Pause button',parent=player,start=5.05)
    s.rect('Pause left',-5,128,4,22,pause,color=WHITE,radius=1); s.rect('Pause right',5,128,4,22,pause,color=WHITE,radius=1)
    for sign in (-1,1):
        x=sign*85; s.path('Skip '+str(sign),[['M',x-sign*6,119],['L',x+sign*6,128],['L',x-sign*6,137],['Z'],['M',x+sign*9,119],['L',x+sign*9,137]],player,WHITE,2,fill=WHITE)
    volume=s.window('Volume control',5.45,7.35); s.nodes[-1]['y']=788
    s.rect('Volume capsule',0,0,350,62,volume,radius=31,shadow=dict(enabled=True,opacity=12,blur=15,y=8))
    s.path('Speaker',[['M',-135,-5],['L',-129,-5],['L',-120,-12],['L',-120,12],['L',-129,5],['L',-135,5],['Z'],['M',-114,-8],['C',-106,-3,-106,3,-114,8]],volume,INK,2.4,fill=INK)
    s.path('Volume track',[['M',-95,0],['L',136,0]],volume,'#d9e1dc',5)
    s.path('Volume amount',[['M',-95,0],['L',136,0]],volume,TEAL,5,keyframes={'trim':keys((5.45,.38),(6.2,.38),(6.85,.85))})
    s.circle('Volume grip',-7,0,13,volume,keyframes={'x':keys((5.45,-7),(6.2,-7),(6.85,101))})

    toggle=s.window('Short-form toggle',7.4,8.75)
    s.text('Make a short',-66,0,24,toggle)
    s.rect('Switch rail',127,0,88,46,toggle,color='#c4cfc9',radius=23)
    s.rect('Switch on colour',127,0,88,46,toggle,color=TEAL,radius=23,keyframes={'opacity':keys((7.4,0),(8,0),(8.15,100))})
    s.circle('Switch knob',108,0,36,toggle,color=WHITE,keyframes={'x':keys((7.4,108),(8,108),(8.22,146),mode='Back Out')})

    settings=s.window('Export settings',8.55,12.1)
    s.text('Ready for your feed',-304,-176,30,settings,bold=True,text_align='left')
    s.text('Frame once. Share everywhere.',-304,-135,16,settings,color=MUTED,text_align='left')
    s.rect('Format segmented rail',0,-72,640,57,settings,color='#eef3ef',radius=28)
    s.rect('Selected format pill',-211,-72,204,49,settings,color=INK,radius=25,keyframes={'x':keys((8.55,-211),(9.4,-211),(9.72,211),mode='Back Out')})
    for x,label in ((-211,'Square'),(0,'Portrait'),(211,'Vertical')):
        s.text(label,x,-72,17,settings,color=INK)
        s.text(label,x,-72,17,settings,color=WHITE,keyframes={'opacity':keys((8.55,100 if x==-211 else 0),(9.4,100 if x==-211 else 0),(9.7,100 if x==211 else 0))})
    s.text('1080 × 1920',-304,8,27,settings,bold=True,text_align='left',start=9.65)
    s.text('1080 × 1080',-304,8,27,settings,bold=True,text_align='left',end=9.65)
    s.text('60 fps  ·  H.264',-304,47,17,settings,color=MUTED,text_align='left')
    s.mark(settings,-290,90,size=20); s.text('Audio included',-270,90,15,settings,color=MUTED,text_align='left')
    s.rect('Frame preview',220,68,133,151,settings,color=TEAL,radius=16,gradient=['#9addcf',TEAL,'#6876ba'],keyframes={'width':keys((8.55,133),(9.4,133),(9.75,94)),'height':keys((8.55,133),(9.4,133),(9.75,168))})
    s.circle('Preview sun',234,28,34,settings,color='#ffe7bd')
    s.path('Preview horizon',[['M',155,105],['C',191,45,231,123,279,58],['L',279,148],['L',155,148],['Z']],settings,'#17675e',0,fill='#17675e',opacity=70,mask=dict(kind='rectangle',x=220,y=68,width=94,height=168,radius=16))
    s.rect('Export button',-220,161,180,57,settings,color=INK,radius=29,keyframes={'width':keys((8.55,180),(10.6,180),(10.85,240)),'x':keys((8.55,-220),(10.6,-220),(10.85,-190))})
    s.text('Export',-220,161,19,settings,color=WHITE,end=10.65)
    s.text('',-190,161,17,settings,color=WHITE,text_mode='counter',number_prefix='Exporting ',number_suffix='%',start=10.65,end=11.65,keyframes={'number':keys((10.65,0),(11.6,100))})
    s.text('Ready ✓',-190,161,18,settings,color=WHITE,start=11.65)
    status=s.window('Export confirmation',12.05,12.95); s.mark(status,-108,0,color='#74e3c8',size=27); s.text('Ready to share',18,0,21,status,color=WHITE)

    chart=s.window('Delivery insights',12.95,15.5)
    s.text('A moment, amplified.',-295,-159,26,chart,bold=True,text_align='left')
    s.text('THIS WEEK',-295,-119,12,chart,color=MUTED,text_align='left',tracking=1.4)
    s.text('',-295,-66,47,chart,bold=True,text_mode='counter',text_align='left',keyframes={'number':keys((12.95,0),(14,12480))})
    s.text('plays and counting',-295,-17,15,chart,color=MUTED,text_align='left')
    s.rect('Insight tag',230,-148,120,33,chart,color='#e2f5ec',radius=16); s.text('+28.4%',230,-148,14,chart,color='#14866c')
    for y in (34,80,126):s.path('Chart guide '+str(y),[['M',-295,y],['L',295,y]],chart,'#edf0ec',1)
    graph=s.add('group','Revealed graph',parent=chart,mask=dict(kind='rectangle',x=0,y=85,width=600,height=165,keyframes={'width':keys((13.1,0),(14.1,600)),'x':keys((13.1,-300),(14.1,0))}))
    curve=[['M',-295,109],['C',-245,89,-230,119,-190,84],['C',-150,48,-120,106,-78,64],['C',-35,25,0,65,39,29],['C',85,-11,99,30,142,-6],['C',197,-52,230,-27,295,-67]]
    s.path('Trend fill',curve+[['L',295,141],['L',-295,141],['Z']],graph,TEAL,0,fill=TEAL,opacity=8)
    s.path('Trend line',curve,graph,TEAL,3.3)
    s.text('MON',-295,170,11,chart,color=MUTED,text_align='left'); s.text('SUN',295,170,11,chart,color=MUTED,text_align='right')
    tooltip=s.add('group','Chart hover value',parent=chart,start=14.1,end=15.35,keyframes={'x':keys((14.1,36),(15,264)),'y':keys((14.1,22),(15,-61)),'opacity':keys((14.1,0),(14.25,100),(15.2,100),(15.35,0))})
    s.circle('Hover dot',0,0,10,tooltip,color=WHITE,stroke=TEAL,stroke_width=3)
    s.rect('Hover label',0,-40,96,34,tooltip,color=INK,radius=10)
    s.text('',0,-40,13,tooltip,color=WHITE,text_mode='counter',keyframes={'number':keys((14.1,6890),(15,12480))})
    share=s.window('Send it out',15.3,16.65); s.text('Send it out',-10,0,22,share,color=WHITE); s.path('Share arrow',[['M',93,0],['L',116,0],['M',108,-8],['L',116,0],['L',108,8]],share,WHITE,2.5)
    ending=s.window('Signal signature',16.35,18.3)
    s.circle('Signal icon',-185,0,66,ending,color=TEAL,keyframes={'scale':keys((16.35,.45),(16.85,1),mode='Back Out'),'scale_y':keys((16.35,.45),(16.85,1),mode='Back Out')})
    s.mark(ending,-185,0,color=WHITE,size=37)
    s.text('SIGNAL',-125,0,59,ending,bold=True,text_align='left',tracking=3)
    s.text('Find your next moment.',0,95,22,ending,color=MUTED)
    s.text('A MOTION STUDY MADE IN KINETIC CUT',540,932,12,color=MUTED,tracking=1.6,start=16.8,keyframes={'opacity':keys((16.8,0),(17.3,100))})
    # Keep widget contents inside the evolving surface during each morph.
    for identifier in (search,player,toggle,settings,chart):
        group=next(n for n in s.nodes if n['id']==identifier)
        group['mask']=dict(kind='rectangle',width=740,height=470,radius=36,keyframes={'width':widths,'height':heights,'radius':body['radius']})
    # Authored curved pointer choreography and stationary click ripples.
    waypoints=[(0,818,784),(.45,593,547),(.9,593,547),(1.5,742,711),(2.9,742,711),(3.36,724,625),(3.65,724,625),(4.6,545,666),(5.1,545,666),(5.9,533,788),(6.2,533,788),(6.85,641,788),(7.15,641,788),(7.8,673,542),(8.2,673,542),(9.15,752,467),(9.6,752,467),(10.3,323,700),(10.9,323,700),(12,786,794),(13.25,333,632),(14.12,576,562),(15,804,479),(15.3,804,479),(15.58,552,542),(16,552,542),(17,827,792),(18,827,792)]
    for click,x,y in [(.65,593,547),(3.45,724,625),(4.85,545,666),(7.95,673,542),(9.35,752,467),(10.55,323,700),(15.65,552,542)]:
        s.circle('Click ripple '+str(click),x+3,y+3,12,color='none',stroke=TEAL,stroke_width=2,start=click,end=click+.42,keyframes={'width':keys((click,12),(click+.42,80)),'height':keys((click,12),(click+.42,80)),'opacity':keys((click,60),(click+.42,0))})
    pointer=s.add('group','Pointer choreography',keyframes={'x':keys(*[(t,x) for t,x,y in waypoints]),'y':keys(*[(t,y) for t,x,y in waypoints])})
    scale=[(0,1)]
    for click in CLICKS:scale.extend([(click-.04,1),(click+.035,.82),(click+.15,1)])
    pointer_node=next(n for n in s.nodes if n['id']==pointer); pointer_node['keyframes'].update(scale=keys(*scale),scale_y=keys(*scale))
    s.path('Mouse pointer',[['M',0,0],['L',0,27],['L',7.5,20.5],['L',12,31],['L',17,28.5],['L',12.5,18],['L',23,17],['Z']],pointer,WHITE,1.6,fill=INK,shadow=dict(enabled=True,blur=3,opacity=25,y=2))
    from kinetic_cut.motion import validate
    return validate(dict(version=1,canvas=[1080,1080],nodes=s.nodes,motion_blur=dict(samples=4,shutter=135)))

def sound(path):
    rate=48000; samples=np.zeros((round(DURATION*rate),2),np.float64); rng=np.random.default_rng(77)
    def add(at,values,gain=1,pan=0):
        start=round(at*rate); end=min(len(samples),start+len(values)); values=values[:end-start]*gain
        if start<0 or end<=start:return
        samples[start:end,0]+=values*math.sqrt((1-pan)/2); samples[start:end,1]+=values*math.sqrt((1+pan)/2)
    def tone(hz,d=.3):
        t=np.arange(round(d*rate))/rate; return np.sin(math.tau*hz*t)*np.exp(-t*9/d)*np.minimum(1,t/.005)
    # Spacious original minor-ninth bed, gentle pulse and tactile UI sounds.
    for section,notes in enumerate(((50,57,60,64),(46,53,57,60),(48,55,59,62),(43,50,57,59))):
        for note in notes:
            t=np.arange(round(4.5*rate))/rate; env=np.minimum(1,t/.45)*np.minimum(1,(4.5-t)/.8)
            add(section*4.5,(np.sin(math.tau*440*2**((note-69)/12)*t)+.18*np.sin(math.tau*440*2**((note-69)/12)*2*t))*env,.025,(-1)**note*.4)
        for n in range(6):add(section*4.5+n*.75,tone(440*2**((notes[n%4]+12-69)/12),.55),.045,(-1)**n*.35)
    for click in CLICKS:
        t=np.arange(round(.025*rate))/rate; add(click,rng.normal(0,1,len(t))*np.exp(-t*190)+np.sin(math.tau*1300*t)*np.exp(-t*220),.13)
        add(click+.04,tone(850,.055),.03)
    for at in np.linspace(1.42,2.22,11):
        t=np.arange(round(.025*rate))/rate; add(at,rng.normal(0,1,len(t))*np.exp(-t*230),.046,rng.uniform(-.25,.25))
    for at in (1,3.75,7.35,8.5,12.1,12.95,15.2,16.4):
        t=np.arange(round(.34*rate))/rate; noise=rng.normal(0,1,len(t)); filtered=np.convolve(noise,np.ones(24)/24,mode='same'); add(at,filtered*np.sin(np.pi*t/.34)**2,.10)
    for at in (11.65,16.7):
        for n,hz in enumerate((659.25,987.77,1318.51)):add(at+n*.075,tone(hz,.55),.09)
    samples=np.tanh(samples); samples*=.72/max(1e-8,np.abs(samples).max()); samples[:2400]*=np.linspace(0,1,2400)[:,None]; samples[-24000:]*=np.linspace(1,0,24000)[:,None]
    with wave.open(str(path),'wb') as f:f.setnchannels(2); f.setsampwidth(2); f.setframerate(rate); f.writeframes((samples*32767).astype('<i2').tobytes())
    return dict(duration=DURATION,peak=float(np.abs(samples).max()),rms=float(np.sqrt(np.mean(samples**2))),clicks=list(CLICKS))

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('output',type=Path); args=p.parse_args(); args.output.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('QT_QPA_PLATFORM','windows' if os.name=='nt' else 'offscreen'); from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QImage,QPainter,QColor
    from kinetic_cut.caption_fonts import load_fonts
    from kinetic_cut.motion import draw
    app=QApplication([]); load_fonts(); scene=build(); (args.output/'signal-scene.json').write_text(json.dumps(scene,indent=2),encoding='utf-8'); report=sound(args.output/'signal-sound.wav')
    times=[.3,2.2,3.25,5.4,6.7,8.1,9.85,11.1,13.75,14.8,15.8,17.5]
    sheet=QImage(1440,1128,QImage.Format_RGB32); sheet.fill(QColor(PAPER)); painter=QPainter(sheet)
    for n,t in enumerate(times):
        x=n%4*360; y=n//4*376; painter.drawImage(x,y,draw(scene,t,(360,360),60)); painter.setPen(QColor(INK)); painter.drawText(x+12,y+372,str(t)+'s')
    painter.end(); sheet.save(str(args.output/'contact-sheet.png')); (args.output/'sound.json').write_text(json.dumps(report,indent=2)); print(json.dumps(dict(nodes=len(scene['nodes']),sound=report)))
