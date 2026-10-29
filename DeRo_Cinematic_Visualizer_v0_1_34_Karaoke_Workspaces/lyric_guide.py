"""Fast live layout guide. Exact frames/export use libass, including wrapping/fades."""
from PIL import ImageDraw,ImageFont
from functools import lru_cache

@lru_cache(maxsize=64)
def guide_font(family,size,bold):
    candidates=[family, family+'.ttf','arialbd.ttf' if bold else 'arial.ttf','DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf']
    for name in candidates:
        try:return ImageFont.truetype(name,size)
        except OSError:pass
    return ImageFont.load_default()

def draw_lyric_guide(frame,seconds,document):
    if not document.style['enabled'] or not document.events:return frame
    style=document.style;events=document.events;lead=style['lyric_lead_seconds'];mode=style['lyric_display_mode']
    selected=next((i for i,(a,b,_) in enumerate(events) if a-lead<=seconds<=b),None)
    if selected is None:return frame
    rows=[selected]
    if mode in ('preview','alternating') and selected+1<len(events):rows.append(selected+1)
    elif mode=='classic_flow':
        count=int(style['classic_flow_lines']);start=selected//count*count;rows=list(range(start,min(start+count,len(events))))
    if mode=='alternating' and selected%2:rows.reverse()
    image=frame.copy();g=ImageDraw.Draw(image);size=max(10,round(style['lyric_font_size']*frame.height/1080));font=guide_font(style['lyric_font_family'],size,style['lyric_font_bold'])
    center=frame.height*style['lyric_vertical_percent']/100;outline=max(1,round(style['lyric_outline']*frame.height/1080))
    for row,i in enumerate(rows):
        words=document.words.get(str(i),[]);text=events[i][2]
        # Fit the live guide; final libass wrapping is checked with Exact frame.
        while g.textlength(text,font=font)>frame.width*.92 and size>10:
            size-=1;font=guide_font(style['lyric_font_family'],size,style['lyric_font_bold'])
        width=g.textlength(text,font=font);x=(frame.width-width)/2;y=center+(row-(len(rows)-1)/2)*size*1.6
        if not words:words=[[events[i][0],events[i][1],word] for word in text.split()]
        for a,b,word in words:
            color=style['lyric_sung_color'] if seconds>=b else style['lyric_unsung_color']
            g.text((x,y),word,font=font,fill=color,anchor='lm',stroke_width=outline,stroke_fill='black')
            if a<=seconds<b:
                fraction=(seconds-a)/(b-a);word_width=g.textlength(word,font=font)
                overlay=image.copy();og=ImageDraw.Draw(overlay);og.text((x,y),word,font=font,fill=style['lyric_sung_color'],anchor='lm',stroke_width=outline,stroke_fill='black')
                box=(max(0,int(x-outline)),max(0,int(y-size)),min(frame.width,int(x+word_width*fraction)),min(frame.height,int(y+size)))
                if box[2]>box[0] and box[3]>box[1]:image.paste(overlay.crop(box),box[:2]);g=ImageDraw.Draw(image)
            x+=g.textlength(word+' ',font=font)
    return image
