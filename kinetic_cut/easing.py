"""Finite, deterministic easing shared by preview, curves and frame preparation."""
import math

MODES=('Linear','Smooth','Hold','Ease In','Ease Out','Ease In Out','Bezier','Back Out','Bounce Out','Elastic Out')

def controls(raw=None):
    values=list(raw if raw is not None else (.2,0,.3,1))
    if len(values)!=4 or any(not math.isfinite(float(v)) for v in values):raise ValueError('Bezier needs four finite control coordinates')
    x1,y1,x2,y2=map(float,values)
    if not 0<=x1<=x2<=1 or not -4<=y1<=4 or not -4<=y2<=4:raise ValueError('Bezier control times must be ordered in 0–1; values must be in -4–4')
    return [x1,y1,x2,y2]

def ease(q,mode='Linear',bezier=None):
    q=max(0.,min(1.,q))
    if q in (0.,1.):return q
    if mode=='Hold':return 0.
    if mode=='Smooth':return q*q*(3-2*q)
    if mode=='Ease In':return q*q*q
    if mode=='Ease Out':return 1-(1-q)**3
    if mode=='Ease In Out':return 4*q**3 if q<.5 else 1-(-2*q+2)**3/2
    if mode=='Back Out':return 1+2.70158*(q-1)**3+1.70158*(q-1)**2
    if mode=='Elastic Out':return 2**(-10*q)*math.sin((q*10-.75)*2*math.pi/3)+1
    if mode=='Bounce Out':
        n=7.5625; d=2.75
        if q<1/d:return n*q*q
        if q<2/d:return n*(q-1.5/d)**2+.75
        if q<2.5/d:return n*(q-2.25/d)**2+.9375
        return n*(q-2.625/d)**2+.984375
    if mode=='Bezier':
        x1,y1,x2,y2=controls(bezier)
        def cubic(t,a,b):return 3*(1-t)**2*t*a+3*(1-t)*t*t*b+t**3
        lo=0.; hi=1.
        for _ in range(24):
            mid=(lo+hi)/2
            if cubic(mid,x1,x2)<q:lo=mid
            else:hi=mid
        return cubic((lo+hi)/2,y1,y2)
    return q
