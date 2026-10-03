"""Clip-level title envelopes, shared by preview and all ASS title components."""
import math,re

def opacity(item,at):
    elapsed=at-item.start; value=max(0,min(1,item.opacity/100))
    if item.fade_in>0:value*=max(0,min(1,elapsed/item.fade_in))
    if item.fade_out>0:value*=max(0,min(1,(item.duration-elapsed)/item.fade_out))
    return value

def apply_ass(lines,titles,fps):
    def seconds(value):
        h,m,s=map(float,value.split(':')); return h*3600+m*60+s
    result=[]
    for line in lines:
        if not line.startswith('Dialogue: '):result.append(line); continue
        parts=line.split(',',9); item=titles.get(parts[3])
        if item is None or (item.fade_in<=0 and item.fade_out<=0 and item.opacity==100):result.append(line); continue
        start,end=seconds(parts[1]),seconds(parts[2]); text=parts[9]; close=text.find('}')
        if not text.startswith('{') or close<0:result.append(line); continue
        tags=text[1:close]; match=re.search(r'\\alpha&H([0-9a-fA-F]{2})&',tags); base=1-int(match[1],16)/255 if match else 1.
        animated=bool(re.search(r'\\fad\(',tags)); tags=re.sub(r'\\fad\([^)]*\)','',tags)
        def value(at):
            factor=opacity(item,at)
            if animated:factor*=max(0,min(1,(at-start)/.1))*max(0,min(1,(end-at)/.1))
            return max(0,min(255,round(255*(1-base*factor))))
        boundaries=[item.start,item.start+item.fade_in,item.start+item.duration-item.fade_out,item.start+item.duration]
        if animated:boundaries.extend((start+.1,end-.1))
        knots=sorted({start,end,*[max(start,min(end,v)) for v in boundaries]})
        times=[start]
        for a,b in zip(knots,knots[1:]):
            # Non-overlapping fades are linear. Sample overlaps at output frame
            # cadence so simultaneous fade-in/out preserves the preview product.
            count=max(1,math.ceil((b-a)*fps)) if abs(value((a+b)/2)-(value(a)+value(b))/2)>1 else 1
            times.extend(a+(b-a)*n/count for n in range(1,count+1))
        tags+=f'\\alpha&H{value(start):02X}&'
        for a,b in zip(times,times[1:]):
            if value(a)!=value(b):tags+=f'\\t({round((a-start)*1000)},{round((b-start)*1000)},\\alpha&H{value(b):02X}&)'
        parts[9]='{'+tags+'}'+text[close+1:]; result.append(','.join(parts))
    return result
