"""SVG path data (the `d` attribute) converted to the motion composition path commands M, L, C, Q and Z."""
import math,re

_TOKEN=re.compile(r'([MmLlHhVvCcSsQqTtAaZz])|([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)')
_ARGS={'M':2,'L':2,'H':1,'V':1,'C':6,'S':4,'Q':4,'T':2,'A':7,'Z':0}

def _arc(x1,y1,rx,ry,phi,large,sweep,x2,y2):
    """Endpoint arc to cubic Beziers (SVG implementation notes F.6.5)."""
    if (x1,y1)==(x2,y2):return []
    rx,ry=abs(rx),abs(ry)
    if not rx or not ry:return [['L',x2,y2]]
    p=math.radians(phi); c,s=math.cos(p),math.sin(p)
    dx,dy=(x1-x2)/2,(y1-y2)/2; x1p=c*dx+s*dy; y1p=-s*dx+c*dy
    lam=x1p**2/rx**2+y1p**2/ry**2
    if lam>1:rx*=math.sqrt(lam); ry*=math.sqrt(lam)
    num=rx**2*ry**2-rx**2*y1p**2-ry**2*x1p**2; den=rx**2*y1p**2+ry**2*x1p**2
    k=math.sqrt(max(0,num/den)) if den else 0
    if large==sweep:k=-k
    cxp=k*rx*y1p/ry; cyp=-k*ry*x1p/rx
    cx=c*cxp-s*cyp+(x1+x2)/2; cy=s*cxp+c*cyp+(y1+y2)/2
    def angle(ux,uy,vx,vy):
        a=math.atan2(ux*vy-uy*vx,ux*vx+uy*vy); return a
    t1=angle(1,0,(x1p-cxp)/rx,(y1p-cyp)/ry); dt=angle((x1p-cxp)/rx,(y1p-cyp)/ry,(-x1p-cxp)/rx,(-y1p-cyp)/ry)
    if not sweep and dt>0:dt-=2*math.pi
    elif sweep and dt<0:dt+=2*math.pi
    parts=max(1,math.ceil(abs(dt)/(math.pi/2)-1e-9)); step=dt/parts; out=[]
    alpha=4/3*math.tan(step/4)
    for n in range(parts):
        a1=t1+n*step; a2=a1+step
        def point(a):return (cx+rx*math.cos(a)*c-ry*math.sin(a)*s,cy+rx*math.cos(a)*s+ry*math.sin(a)*c)
        def deriv(a):return (-rx*math.sin(a)*c-ry*math.cos(a)*s,-rx*math.sin(a)*s+ry*math.cos(a)*c)
        p1=point(a1); p2=point(a2); d1=deriv(a1); d2=deriv(a2)
        out.append(['C',p1[0]+alpha*d1[0],p1[1]+alpha*d1[1],p2[0]-alpha*d2[0],p2[1]-alpha*d2[1],p2[0],p2[1]])
    out[-1][5],out[-1][6]=x2,y2
    return out

def parse(d,limit=2048):
    """Return absolute path commands. Raises ValueError for malformed data."""
    if not isinstance(d,str) or len(d)>200000:raise ValueError('SVG path data must be text')
    tokens=[(m.group(1),m.group(2)) for m in _TOKEN.finditer(d)]
    if re.sub(_TOKEN,'',d).strip(' ,\t\r\n'):raise ValueError('SVG path contains unsupported characters')
    out=[]; i=0; cur=(0.,0.); start=(0.,0.); command=''; last_c=None; last_q=None
    def number():
        nonlocal i
        if i>=len(tokens) or tokens[i][1] is None:raise ValueError('SVG path is missing a number')
        v=float(tokens[i][1]); i+=1; return v
    while i<len(tokens):
        if tokens[i][0]:command=tokens[i][0]; i+=1
        elif not command:raise ValueError('SVG path must start with a command')
        upper=command.upper(); rel=command.islower()
        if upper=='Z':
            out.append(['Z']); cur=start; last_c=last_q=None
            if i<len(tokens) and tokens[i][1] is not None:raise ValueError('SVG path has extra numbers after Z')
            continue
        args=[number() for _ in range(_ARGS[upper])] if upper!='A' else None
        if upper=='A':
            rx,ry,phi=number(),number(),number()
            fa=number(); fs=number(); x=number(); y=number()
            if rel:x+=cur[0]; y+=cur[1]
            out.extend(_arc(cur[0],cur[1],rx,ry,phi,bool(fa),bool(fs),x,y)); cur=(x,y); last_c=last_q=None
        else:
            ox,oy=cur if rel else (0,0)
            if upper=='M':
                cur=(args[0]+ox,args[1]+oy); start=cur; out.append(['M',*cur]); command='l' if rel else 'L'; last_c=last_q=None
            elif upper=='L':cur=(args[0]+ox,args[1]+oy); out.append(['L',*cur]); last_c=last_q=None
            elif upper=='H':cur=(args[0]+(cur[0] if rel else 0),cur[1]); out.append(['L',*cur]); last_c=last_q=None
            elif upper=='V':cur=(cur[0],args[0]+(cur[1] if rel else 0)); out.append(['L',*cur]); last_c=last_q=None
            elif upper=='C':
                p=[args[0]+ox,args[1]+oy,args[2]+ox,args[3]+oy,args[4]+ox,args[5]+oy]; out.append(['C',*p]); last_c=(p[2],p[3]); last_q=None; cur=(p[4],p[5])
            elif upper=='S':
                a=(2*cur[0]-last_c[0],2*cur[1]-last_c[1]) if last_c else cur
                p=[a[0],a[1],args[0]+ox,args[1]+oy,args[2]+ox,args[3]+oy]; out.append(['C',*p]); last_c=(p[2],p[3]); last_q=None; cur=(p[4],p[5])
            elif upper=='Q':
                p=[args[0]+ox,args[1]+oy,args[2]+ox,args[3]+oy]; out.append(['Q',*p]); last_q=(p[0],p[1]); last_c=None; cur=(p[2],p[3])
            elif upper=='T':
                a=(2*cur[0]-last_q[0],2*cur[1]-last_q[1]) if last_q else cur
                p=[a[0],a[1],args[0]+ox,args[1]+oy]; out.append(['Q',*p]); last_q=(p[0],p[1]); last_c=None; cur=(p[2],p[3])
        if len(out)>limit:raise ValueError('SVG path expands to more than %d commands'%limit)
    if out and out[0][0]!='M':raise ValueError('SVG path must start with M')
    return out
