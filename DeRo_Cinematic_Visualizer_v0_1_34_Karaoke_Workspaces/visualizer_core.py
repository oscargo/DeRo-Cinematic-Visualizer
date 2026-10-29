"""Reusable, deterministic cinematic spectrum/particle renderer.

No GUI dependency. Renderer.render(seconds) returns RGB PIL.Image and works in
standalone exports or as a rendering component inside DeRo Sync.
"""
from __future__ import annotations
from functools import lru_cache
from dataclasses import dataclass
import math
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

@dataclass
class Settings:
    width: int = 1920
    height: int = 1080
    fps: int = 60
    title: str = "LOVE NIGHT"
    bars: int = 384
    spectrum_mapping: str = 'Stepped'
    spectrum_style: str = 'Classic bars'
    spectrum_mirrored: bool = True
    spectrum_density: float = 1.
    spectrum_fill: float = .58
    spectrum_color_end: str = '#35a5ff'
    frequency_min: float = 50.
    frequency_max: float = 10584.
    frequency_scale: str = 'Linear'
    spectrum_gain: float = 1.5
    spectrum_width: float = 0.8
    spectrum_x: float = 0.5
    spectrum_y: float = 0.9
    title_size: float = 0.12
    title_x: float = 0.5
    title_y: float = 0.42
    title_font: str = "Sans"
    title_bold: bool = False
    title_italic: bool = False
    title_uppercase: bool = False
    title_color: str = "#f8f9fd"
    artist: str = ""
    artist_size: float = 0.08
    artist_x: float = 0.5
    artist_y: float = 0.585
    artist_font: str = "Sans"
    artist_bold: bool = False
    artist_italic: bool = False
    artist_uppercase: bool = False
    artist_color: str = "#f8f9fd"
    spectrum_height: float = 0.198
    particle_continuous: bool = True
    particles_enabled: bool = True
    particle_reactivity: str = 'Bass'
    particle_direction: str = 'Out'
    particle_reactive: bool = True
    particle_color: str = '#ebeef7'
    spectrum_color: str = '#f0f6ff'
    overlay_enabled: bool = False
    overlay_path: str = ''
    overlay_size: float = .2
    overlay_x: float = .5
    overlay_y: float = .5
    overlay_opacity: float = 1.
    overlay_shape: str = 'Original'
    particle_speed: float = 20.0
    dust_count: int = 130
    reactive_fraction: float = 0.24
    sensitivity: float = 3.0
    background: str = ""
    seed: int = 42
    export_encoder: str = "Auto (GPU if available)"


def audio_features(samples: np.ndarray, sample_rate: int, fps: int, bars: int, frequency_min=50., frequency_max=None, frequency_scale='Linear', spectrum_mapping='Stepped', cancel_check=None) -> np.ndarray:
    """Frequency-band energies (frames, bars) from mono 16/32bit decoded audio.

    Linear bands by default from 50 Hz to min(14000, sample_rate * .48),
    compressed and smoothed independently. Default 22050 Hz audio: 50-10584 Hz.
    Spectral extraction happens once, not in the rendering loop.
    """
    samples = np.asarray(samples, dtype=np.float32).reshape(-1)
    nframes = max(1, math.ceil(len(samples) / sample_rate * fps))
    upper=min(14000,sample_rate*.48) if frequency_max is None else float(frequency_max)
    if not 0<float(frequency_min)<upper<=sample_rate*.5:
        raise ValueError('Frequency range must fit within the analysis sample rate.')
    if not 16<=bars<=2048:raise ValueError('Band count must be between 16 and 2048.')
    nfft = 8192 if sample_rate>22050 else 4096
    freqs = np.fft.rfftfreq(nfft, 1 / sample_rate)
    spacing=np.geomspace if frequency_scale=='Logarithmic' else np.linspace
    edges = spacing(float(frequency_min),upper,bars+1)
    # Integrate a linearly interpolated power spectrum at fractional FFT
    # coordinates. Integer edge rounding copied one FFT bin into adjacent bands.
    coordinates=edges/(sample_rate/nfft)
    lower=np.clip(np.floor(coordinates).astype(int),0,len(freqs)-2)
    fractions=coordinates-lower
    widths=np.diff(coordinates)
    legacy_edges=np.clip(np.searchsorted(freqs,edges),1,len(freqs)-1)
    legacy_lo=legacy_edges[:-1]
    legacy_hi=np.maximum(legacy_edges[1:],legacy_lo+1)
    if spectrum_mapping not in ('Stepped','Balanced','Smooth'):raise ValueError('Unknown spectrum peak shape.')
    energies = np.zeros((nframes, bars), np.float32)
    window = np.hanning(nfft).astype(np.float32)
    for i in range(nframes):
        if cancel_check is not None and i%64==0:cancel_check()
        midpoint = round((i + .5) * sample_rate / fps)
        a = midpoint - nfft // 2
        b = a + nfft
        frame = np.zeros(nfft, np.float32)
        left, right = max(0, a), min(len(samples), b)
        if right > left:
            frame[left - a:right - a] = samples[left:right]
        magnitude = np.abs(np.fft.rfft(frame * window))
        power = magnitude * magnitude
        cs=np.concatenate(([0.],np.cumsum((power[:-1]+power[1:])*.5,dtype=np.float64)))
        integral=cs[lower]+power[lower]*fractions+.5*(power[lower+1]-power[lower])*fractions**2
        values=np.diff(integral)/widths
        smooth=np.sqrt(np.maximum(values,0))
        if spectrum_mapping=='Smooth':energies[i,:]=smooth
        else:
            legacy_cs=np.concatenate(([0.],np.cumsum(power,dtype=np.float64)))
            stepped=np.sqrt(np.maximum((legacy_cs[legacy_hi]-legacy_cs[legacy_lo])/np.maximum(legacy_hi-legacy_lo,1),0))
            energies[i,:]=stepped if spectrum_mapping=='Stepped' else (stepped+smooth)*.5
    # Static relative scaling preserves quiet/loud dynamics; avoid per-frame normalization.
    # Use the actual song-wide maximum, not a percentile followed by clipping.
    # A percentile ceiling flattened the strongest bins into a visible shelf.
    reference = max(float(np.max(energies)), 1e-7)
    energies = (energies / reference) ** .68 * .95
    for i in range(1, nframes):
        if cancel_check is not None and i%64==0:cancel_check()
        drop = .79
        energies[i] = np.maximum(energies[i], energies[i-1] * drop)
    return energies


class Renderer:
    def __init__(self, settings: Settings, features: np.ndarray | None = None, cancel_check=None):
        self.cancel_check=cancel_check
        if cancel_check is not None:cancel_check()
        self.s = settings
        self.overlay_cache_key=None
        self.overlay_cache=None
        self.features = features
        self.rng = np.random.default_rng(settings.seed)
        self.particles = self._make_particles() if settings.particles_enabled else []
        self._particles_initialized = settings.particles_enabled
        self.trajectories = self._particle_trajectories()
        self.base = self._background()

    def _background(self):
        w, h = self.s.width, self.s.height
        if self.s.background:
            img = Image.open(self.s.background).convert('RGB')
            scale = max(w / img.width, h / img.height)
            img = img.resize((round(img.width*scale), round(img.height*scale)), Image.Resampling.LANCZOS)
            x, y = (img.width-w)//2, (img.height-h)//2
            return img.crop((x,y,x+w,y+h))
        # Dark navy gradient: intentional fallback without requiring source video.
        y = np.linspace(0, 1, h, dtype=np.float32)
        color1 = np.array([6, 13, 26], dtype=np.float32)
        color2 = np.array([14, 22, 38], dtype=np.float32)
        rows = color1[None, :] * (1-y[:, None]) + color2[None, :] * y[:, None]
        return Image.fromarray(np.broadcast_to(rows[:, None, :], (h, w, 3)).astype('uint8').copy(), 'RGB')

    def _make_particles(self):
        """Seeded independent flecks; continuous mode supplies fresh particles."""
        r = self.rng
        result = []
        for _ in range(self.s.dust_count):
            x, y = r.random(2)
            # Loose outward drift with large angular jitter. Each particle moves
            # differently and never shares a synchronized orbital animation.
            angle = math.atan2(y - .5, (x - .5) * 1.35) + r.normal(0, .65)
            if r.random() < .18:
                angle = r.uniform(-math.pi, math.pi)
            if self.s.particle_direction!='Out':
                angle={'Right':0,'Left':math.pi,'Up':-math.pi/2,'Down':math.pi/2}[self.s.particle_direction]+r.normal(0,.12)
            speed = r.uniform(.0004, .0020)
            result.append(dict(x=float(x), y=float(y), vx=float(math.cos(angle)*speed),
                vy=float(math.sin(angle)*speed),
                size=float(r.choice([.7, 1, 1.4, 2, 3, 4], p=[.18,.22,.25,.20,.11,.04])),
                alpha=float(r.uniform(.10,.55)), kind=int(r.integers(0,4)),
                reactive=bool(r.random()<self.s.reactive_fraction),
                blur=bool(r.random()<.16)))
        return result

    def _particle_trajectories(self):
        """Build frame-indexed particle paths once, independent of render order.

        A beat produces a positive outward velocity impulse, not a size bounce.
        Speeds decay gently, never reverse, and points disappear beyond the
        image. Stronger beats give a larger impulse (with graceful limiting).
        """
        count = len(self.particles)
        if not count:
            self.particle_fades=np.ones((1,0),np.float32)
            return np.zeros((1, 0, 2), dtype=np.float32)
        nframes = len(self.features) if self.features is not None else self.s.fps * 20
        nframes = max(1, nframes)
        r = np.random.default_rng(self.s.seed + 1907)
        pos = np.array([[p['x'], p['y']] for p in self.particles], np.float64)
        vel = np.array([[p['vx'], p['vy']] for p in self.particles], np.float64)
        base_vel=vel.copy()
        spawn=np.random.default_rng(self.s.seed+7813)
        fade_frames=max(1,round(self.s.fps*.6))
        born=np.full(count,-fade_frames,dtype=int)
        self.particle_fades=np.ones((nframes,count),np.float32)
        reactive = np.array([p['reactive'] for p in self.particles], dtype=bool)
        # Each particle has its own response curve and small directional variation.
        gains = r.uniform(.55, 1.40, count)
        results = np.empty((nframes, count, 2), dtype=np.float32)
        if self.features is None:
            bass_track = np.zeros(nframes, np.float32)
        else:
            bass_track = self.reactive_energy(self.features)
        smooth = 0.
        previous = 0.
        for i in range(nframes):
            if self.cancel_check is not None and i%64==0:self.cancel_check()
            bass = float(bass_track[i])
            smooth = .91*smooth + .09*bass
            onset = max(0., bass - previous*.82)
            previous = bass
            # Most activity is quiet; big transients get noticeably more push.
            strength = min(1.0, max(0., onset - .035)*1.55 + max(0., bass-smooth-.08)*.55)
            if self.s.particle_reactive and strength > 0 and reactive.any():
                # Outward velocity, with independent minor asymmetry per fleck.
                direction = pos - np.array([.5, .5])
                direction[:, 0] *= 1.25
                angles = np.arctan2(direction[:,1], direction[:,0]) + r.normal(0,.20,count)
                if self.s.particle_direction!='Out':
                    angles=np.full(count,{'Right':0,'Left':math.pi,'Up':-math.pi/2,'Down':math.pi/2}[self.s.particle_direction])+r.normal(0,.12,count)
                impulse = (strength ** 1.4) * .00058 * self.s.sensitivity * gains
                vel[reactive, 0] += np.cos(angles[reactive])*impulse[reactive]
                vel[reactive, 1] += np.sin(angles[reactive])*impulse[reactive]
            # Drag on beat momentum (not position). Preserve some underlying drift.
            vel = base_vel + (vel-base_vel)*.994
            # Cap exceptional peak motion; do not oscillate or spring back.
            speed = np.linalg.norm(vel,axis=1)
            cap = .0065
            vel *= np.minimum(1., cap/np.maximum(speed,1e-9))[:,None]
            pos += vel * self.s.particle_speed / self.s.fps
            if self.s.particle_continuous:
                expired=np.flatnonzero(np.any((pos<-.025)|(pos>1.025),axis=1))
                for index in expired:
                    mode=self.s.particle_direction
                    if mode=='Out':
                        x,y=spawn.uniform(.12,.88,2)
                        angle=math.atan2(y-.5,(x-.5)*1.35)+spawn.normal(0,.4)
                    elif mode in ('Left','Right'):
                        x=-.015 if mode=='Right' else 1.015
                        y=spawn.uniform(.06,.94)
                        angle=(0 if mode=='Right' else math.pi)+spawn.normal(0,.12)
                    else:
                        x=spawn.uniform(.06,.94)
                        y=-.015 if mode=='Down' else 1.015
                        angle=(math.pi/2 if mode=='Down' else -math.pi/2)+spawn.normal(0,.12)
                    speed=spawn.uniform(.0004,.0020)
                    pos[index]=(x,y)
                    base_vel[index]=(math.cos(angle)*speed,math.sin(angle)*speed)
                    vel[index]=base_vel[index]
                    born[index]=i
                edge=np.minimum(pos,1-pos).min(axis=1)
                self.particle_fades[i]=np.clip((i-born)/fade_frames,0,1)*np.clip(edge/.04,0,1)
            results[i] = pos
        return results

    def _energy(self, seconds):
        if self.features is None or len(self.features)==0:
            return np.zeros(self.s.bars, dtype=np.float32)
        index = min(max(0, round(seconds*self.s.fps)), len(self.features)-1)
        v = self.features[index]
        if len(v) != self.s.bars:
            return np.interp(np.linspace(0,1,self.s.bars), np.linspace(0,1,len(v)),v)
        return v

    def render(self, seconds: float) -> Image.Image:
        s = self.s
        if s.particles_enabled and not self._particles_initialized:
            self.particles = self._make_particles()
            self.trajectories = self._particle_trajectories()
            self._particles_initialized = True
        w,h = s.width,s.height
        img = self.base.copy().convert('RGBA')
        energy = self._energy(seconds)
        bass = float(self.reactive_energy(energy))
        mid = float(np.mean(energy[s.bars//6:s.bars*2//3]))
        treble = float(np.mean(energy[s.bars*2//3:]))
        dust = Image.new('RGBA', (w,h))
        d = ImageDraw.Draw(dust, 'RGBA')
        scale = h/1080
        frame_index = min(len(self.trajectories)-1, max(0, round(seconds*s.fps)))
        positions = self.trajectories[frame_index]
        for particle_index,(p, position) in enumerate(zip(self.particles if s.particles_enabled else [], positions)):
            x, y = float(position[0])*w, float(position[1])*h
            # Continuous births fade in; outgoing particles fade at the edges.
            if x < -12 or y < -12 or x > w+12 or y > h+12:
                continue
            react = p['reactive'] and s.particle_reactive
            size = p['size']*scale*(1 + (.45*bass*s.sensitivity if react else 0))
            opacity = float(self.particle_fades[frame_index,particle_index])*p['alpha']*(1 + (.5*mid + .3*treble)*s.sensitivity if react else 1)
            a = max(0,min(210, int(opacity*255)))
            col = tuple(bytes.fromhex(s.particle_color.lstrip('#')))+(a,)
            if p['kind']==0:  # irregular tiny dust
                d.polygon([(x-size,y),(x+size*.4,y-size*.65),(x+size,y+size*.3),(x-size*.3,y+size)], fill=col)
            elif p['kind']==1:  # slim airborne flake
                d.line([(x-size*.3,y-size),(x+size*.4,y+size)], fill=col, width=max(1,round(size*.6)))
            elif p['kind']==2:  # scattered soft light point
                d.ellipse((x-size,y-size,x+size,y+size), fill=col)
            else:  # short fleck
                d.line([(x-size*.8,y),(x+size*.9,y-size*.4)], fill=col,width=max(1,round(size*.7)))
        if s.dust_count:
            # Small blur creates natural diffusion without erasing all sharp dust flecks.
            img = Image.alpha_composite(img, dust)
        self.compose_image_element(img)
        overlay=Image.new('RGBA',(w,h))
        g=ImageDraw.Draw(overlay,'RGBA')
        spectrum=self.spectrum_layer(energy)
        img=Image.alpha_composite(img,spectrum)
        for row in ('title','artist'):
            text=getattr(s,row)
            if not text:continue
            font=self.title_font(row)
            if getattr(s,row+'_uppercase'):text=text.upper()
            g.text((w*getattr(s,row+'_x'),h*getattr(s,row+'_y')),text,font=font,
                   anchor='mm',fill=getattr(s,row+'_color'))
        return Image.alpha_composite(img,overlay).convert('RGB')

    def title_font(self,row="title"):
        s=self.s
        size=max(1,round(s.height*getattr(s,row+'_size')))
        family={'Sans':'DejaVuSans','Serif':'DejaVuSerif','Mono':'DejaVuSansMono'}.get(getattr(s,row+'_font'),'DejaVuSans')
        italic='Italic' if getattr(s,row+'_font')=='Serif' else 'Oblique'
        suffix=('-Bold'+italic if getattr(s,row+'_italic') else '-Bold') if getattr(s,row+'_bold') else ('-'+italic if getattr(s,row+'_italic') else '')
        windows={'Sans':'arial','Serif':'times','Mono':'cour'}[getattr(s,row+'_font')]
        windows+=('bi' if getattr(s,row+'_bold') and getattr(s,row+'_italic') else 'bd' if getattr(s,row+'_bold') else 'i' if getattr(s,row+'_italic') else '')
        candidates=[family+suffix+'.ttf',os.path.join(os.environ.get('WINDIR','C:/Windows'),'Fonts',windows+'.ttf')]
        return _load_font(tuple(candidates),size)

    def compose_image_element(self,frame):
        s=self.s
        if not s.overlay_enabled or not s.overlay_path:return
        key=(s.overlay_path,s.overlay_size,s.overlay_opacity,s.overlay_shape,s.width,s.height)
        if key!=self.overlay_cache_key:
            with Image.open(s.overlay_path) as source:image=source.convert('RGBA')
            if s.overlay_shape=='Circle':
                side=min(image.size);left=(image.width-side)//2;top=(image.height-side)//2
                image=image.crop((left,top,left+side,top+side))
            width=max(1,round(s.width*s.overlay_size))
            height=max(1,round(image.height*width/image.width))
            image=image.resize((width,height),Image.Resampling.LANCZOS)
            alpha=image.getchannel('A')
            if s.overlay_shape=='Circle':
                mask=Image.new('L',image.size)
                ImageDraw.Draw(mask).ellipse((0,0,width-1,height-1),fill=255)
                from PIL import ImageChops
                alpha=ImageChops.multiply(alpha,mask)
            image.putalpha(alpha.point(lambda value:round(value*s.overlay_opacity)))
            self.overlay_cache=image;self.overlay_cache_key=key
        image=self.overlay_cache
        frame.alpha_composite(image,(round(s.width*s.overlay_x-image.width/2),round(s.height*s.overlay_y-image.height/2)))

    def spectrum_layer(self,energy):
        s=self.s;w,h=s.width,s.height
        layer=Image.new('RGBA',(w,h));draw=ImageDraw.Draw(layer)
        center=w*s.spectrum_x;baseline=round(h*s.spectrum_y)
        span=max(20,w*s.spectrum_width);maxheight=h*s.spectrum_height
        count=max(8,min(4096,round(s.bars*s.spectrum_density)))
        if s.spectrum_mirrored:
            count=max(8,count//2*2)
            half=count//2
            values=self.map_spectrum_values(energy,half)
            amplitudes=np.concatenate((values[::-1],values))
            color_positions=np.concatenate((np.linspace(1,0,half),np.linspace(0,1,half)))
        else:
            amplitudes=self.map_spectrum_values(energy,count)
            color_positions=np.linspace(0,1,count)
        step=span/(count+2)
        xs=center+(np.arange(count)-(count-1)/2)*step
        heights=np.maximum(1,(amplitudes*s.spectrum_gain)**.9*maxheight)
        primary=np.array(tuple(bytes.fromhex(s.spectrum_color[1:])))
        secondary=np.array(tuple(bytes.fromhex(s.spectrum_color_end[1:])))
        gradient=s.spectrum_style in ('Gradient bars','Reflected bars','Filled spectrum')
        if s.spectrum_style=='Filled spectrum':
            points=[(float(xs[0]),baseline)]+[(float(x),float(baseline-y)) for x,y in zip(xs,heights)]+[(float(xs[-1]),baseline)]
            mask=Image.new('L',(w,h));ImageDraw.Draw(mask).polygon(points,fill=220)
            colors=Image.new('RGBA',(w,h));cd=ImageDraw.Draw(colors)
            for x in range(max(0,int(xs[0])),min(w,int(xs[-1])+1)):
                ratio=abs(x-center)/(span/2) if s.spectrum_mirrored else (x-xs[0])/max(1,xs[-1]-xs[0])
                rgb=tuple(np.round(primary*(1-ratio)+secondary*ratio).clip(0,255).astype(int))
                cd.line((x,0,x,h),fill=rgb+(255,))
            colors.putalpha(mask);layer=colors;draw=ImageDraw.Draw(layer)
        else:
            barwidth=max(1,round(step*s.spectrum_fill))
            for x,height,ratio in zip(xs,heights,color_positions):
                rgb=tuple(np.round(primary*(1-ratio)+secondary*ratio).astype(int)) if gradient else tuple(primary)
                xx=round(float(x));top=round(float(baseline-height))
                draw.rounded_rectangle((xx-barwidth//2,top,xx+barwidth//2,baseline),radius=barwidth//2,fill=rgb+(220,))
        draw.line((center-span/2,baseline+2,center+span/2,baseline+2),fill=tuple(primary)+(115,),width=max(1,round(h/1080)))
        if s.spectrum_style=='Glow bars':
            glow=layer.filter(ImageFilter.GaussianBlur(max(1,h/270)))
            layer=Image.alpha_composite(glow,layer)
        if s.spectrum_style=='Reflected bars' and 0<baseline<h-3:
            depth=min(h-baseline-3,max(1,round(maxheight*.7)),baseline+1)
            reflection=layer.crop((0,0,w,baseline+1)).transpose(Image.Transpose.FLIP_TOP_BOTTOM).crop((0,0,w,depth))
            alpha=np.asarray(reflection.getchannel('A'),dtype=np.float32)*np.linspace(.35,0,depth)[:,None]
            reflection.putalpha(Image.fromarray(alpha.astype('uint8')))
            layer.alpha_composite(reflection,(0,baseline+3))
        return layer

    def reactive_energy(self,features):
        s=self.s
        if s.particle_reactivity=='Displayed range':return np.mean(features,axis=-1)
        spacing=np.geomspace if s.frequency_scale=='Logarithmic' else np.linspace
        edges=spacing(s.frequency_min,s.frequency_max,features.shape[-1]+1)
        centers=np.sqrt(edges[:-1]*edges[1:]) if s.frequency_scale=='Logarithmic' else (edges[:-1]+edges[1:])/2
        low,high={'Bass':(20,250),'Vocals / Midrange':(250,4000),'Treble':(4000,20000)}[s.particle_reactivity]
        selected=(centers>=low)&(centers<high)
        if not selected.any():return np.zeros(features.shape[:-1],np.float32)
        return np.mean(features[...,selected],axis=-1)

    def map_spectrum_values(self,energy,count):
        positions=np.linspace(0,len(energy)-1,count)
        smooth=np.interp(positions,np.arange(len(energy)),energy)
        if self.s.spectrum_mapping=='Smooth':return smooth
        stepped=energy[positions.astype(int)]
        return stepped if self.s.spectrum_mapping=='Stepped' else (stepped+smooth)*.5


@lru_cache(maxsize=64)
def _load_font(candidates,size):
    for candidate in candidates:
        try:return ImageFont.truetype(candidate,size)
        except OSError:pass
    return ImageFont.load_default(size=size)
