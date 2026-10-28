"""Reusable, deterministic cinematic spectrum/particle renderer.

No GUI dependency. Renderer.render(seconds) returns RGB PIL.Image and works in
standalone exports or as a rendering component inside DeRo Sync.
"""
from __future__ import annotations
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
    spectrum_width: float = 0.82
    spectrum_x: float = 0.5
    spectrum_y: float = 0.906
    title_size: float = 0.02
    title_x: float = 0.5
    title_y: float = 0.79
    title_font: str = "Sans"
    title_bold: bool = False
    title_italic: bool = False
    title_uppercase: bool = True
    title_color: str = "#f8f9fd"
    spectrum_height: float = 0.068
    dust_count: int = 130
    reactive_fraction: float = 0.25
    sensitivity: float = 1.0
    background: str = ""
    seed: int = 42


def audio_features(samples: np.ndarray, sample_rate: int, fps: int, bars: int) -> np.ndarray:
    """Frequency-band energies (frames, bars) from mono 16/32bit decoded audio.

    Log-spaced 50-14000 Hz bands, compressed and smoothed independently.
    Spectral extraction happens once, not in the rendering loop.
    """
    samples = np.asarray(samples, dtype=np.float32).reshape(-1)
    nframes = max(1, math.ceil(len(samples) / sample_rate * fps))
    nfft = 4096
    freqs = np.fft.rfftfreq(nfft, 1 / sample_rate)
    edges = np.geomspace(50, min(14000, sample_rate * .48), bars + 1)
    idx = np.searchsorted(freqs, edges)
    idx = np.clip(idx, 1, len(freqs) - 1)
    energies = np.zeros((nframes, bars), np.float32)
    window = np.hanning(nfft).astype(np.float32)
    for i in range(nframes):
        midpoint = round((i + .5) * sample_rate / fps)
        a = midpoint - nfft // 2
        b = a + nfft
        frame = np.zeros(nfft, np.float32)
        left, right = max(0, a), min(len(samples), b)
        if right > left:
            frame[left - a:right - a] = samples[left:right]
        magnitude = np.abs(np.fft.rfft(frame * window))
        # Vectorized band RMS keeps 384/512-band analysis practical.
        power = magnitude * magnitude
        cs = np.concatenate(([0.], np.cumsum(power, dtype=np.float64)))
        lo = idx[:-1]
        hi = np.maximum(idx[1:], lo + 1)
        values = (cs[hi] - cs[lo]) / np.maximum(hi-lo, 1)
        energies[i, :] = np.sqrt(np.maximum(values, 0))
    # Static relative scaling preserves quiet/loud dynamics; avoid per-frame normalization.
    reference = max(float(np.percentile(energies, 98)), 1e-7)
    energies = np.clip((energies / reference) ** .68, 0, 1)
    for i in range(1, nframes):
        drop = .79
        energies[i] = np.maximum(energies[i], energies[i-1] * drop)
    return energies


class Renderer:
    def __init__(self, settings: Settings, features: np.ndarray | None = None):
        self.s = settings
        self.features = features
        self.rng = np.random.default_rng(settings.seed)
        self.particles = self._make_particles()
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
        """Seeded, independent flecks. No wrapping, recycling, or tiled paths."""
        r = self.rng
        result = []
        for _ in range(self.s.dust_count):
            x, y = r.random(2)
            # Loose outward drift with large angular jitter. Each particle moves
            # differently and never shares a synchronized orbital animation.
            angle = math.atan2(y - .5, (x - .5) * 1.35) + r.normal(0, .65)
            if r.random() < .18:
                angle = r.uniform(-math.pi, math.pi)
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
            return np.zeros((1, 0, 2), dtype=np.float32)
        nframes = len(self.features) if self.features is not None else self.s.fps * 20
        nframes = max(1, nframes)
        r = np.random.default_rng(self.s.seed + 1907)
        pos = np.array([[p['x'], p['y']] for p in self.particles], np.float64)
        vel = np.array([[p['vx'], p['vy']] for p in self.particles], np.float64)
        reactive = np.array([p['reactive'] for p in self.particles], dtype=bool)
        # Each particle has its own response curve and small directional variation.
        gains = r.uniform(.55, 1.40, count)
        results = np.empty((nframes, count, 2), dtype=np.float32)
        if self.features is None:
            bass_track = np.zeros(nframes, np.float32)
        else:
            bass_track = np.mean(self.features[:, :max(1, self.s.bars//6)], axis=1)
        smooth = 0.
        previous = 0.
        for i in range(nframes):
            bass = float(bass_track[i])
            smooth = .91*smooth + .09*bass
            onset = max(0., bass - previous*.82)
            previous = bass
            # Most activity is quiet; big transients get noticeably more push.
            strength = min(1.0, max(0., onset - .035)*1.55 + max(0., bass-smooth-.08)*.55)
            if strength > 0 and reactive.any():
                # Outward velocity, with independent minor asymmetry per fleck.
                direction = pos - np.array([.5, .5])
                direction[:, 0] *= 1.25
                angles = np.arctan2(direction[:,1], direction[:,0]) + r.normal(0,.20,count)
                impulse = (strength ** 1.4) * .00058 * self.s.sensitivity * gains
                vel[reactive, 0] += np.cos(angles[reactive])*impulse[reactive]
                vel[reactive, 1] += np.sin(angles[reactive])*impulse[reactive]
            # Drag on beat momentum (not position). Preserve some underlying drift.
            base_vel = np.array([[p['vx'],p['vy']] for p in self.particles])
            vel = base_vel + (vel-base_vel)*.994
            # Cap exceptional peak motion; do not oscillate or spring back.
            speed = np.linalg.norm(vel,axis=1)
            cap = .0065
            vel *= np.minimum(1., cap/np.maximum(speed,1e-9))[:,None]
            pos += vel / self.s.fps
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
        w,h = s.width,s.height
        img = self.base.copy().convert('RGBA')
        energy = self._energy(seconds)
        bass = float(np.mean(energy[:max(1,s.bars//6)]))
        mid = float(np.mean(energy[s.bars//6:s.bars*2//3]))
        treble = float(np.mean(energy[s.bars*2//3:]))
        dust = Image.new('RGBA', (w,h))
        d = ImageDraw.Draw(dust, 'RGBA')
        scale = h/1080
        frame_index = min(len(self.trajectories)-1, max(0, round(seconds*s.fps)))
        positions = self.trajectories[frame_index]
        for p, position in zip(self.particles, positions):
            x, y = float(position[0])*w, float(position[1])*h
            # Exiting flecks are gone permanently; never wrap or bounce.
            if x < -12 or y < -12 or x > w+12 or y > h+12:
                continue
            react = p['reactive']
            size = p['size']*scale*(1 + (.45*bass*s.sensitivity if react else 0))
            opacity = p['alpha']*(1 + (.5*mid + .3*treble)*s.sensitivity if react else 1)
            a = max(0,min(210, int(opacity*255)))
            col = (235,238,247,a)
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
        overlay=Image.new('RGBA',(w,h))
        g=ImageDraw.Draw(overlay,'RGBA')
        center=round(w*s.spectrum_x)
        baseline=round(h*s.spectrum_y)
        sw=max(20,round(w*s.spectrum_width))
        bandcount=s.bars//2
        bw=sw/(s.bars+2)
        maxbar=h*s.spectrum_height
        # Mirrored left/right frequencies, low frequencies near center.
        for k in range(bandcount):
            idx = int(k / max(1,bandcount-1)*(s.bars-1))
            amp = float(energy[idx])
            height = max(1.0, (amp*s.sensitivity)**.9*maxbar)
            xoff=(k+.5)*bw
            barw=max(1, round(bw*.58))
            for sign in (-1,1):
                xx=round(center+sign*xoff)
                g.rounded_rectangle((xx-barw//2, round(baseline-height), xx+barw//2, baseline), radius=barw//2,fill=(240,246,255,220))
        g.line((center-sw/2,baseline+2,center+sw/2,baseline+2),fill=(240,245,255,115),width=max(1,round(h/1080)))
        if s.title:
            font=self.title_font()
            title=s.title.upper() if s.title_uppercase else s.title
            g.text((w*s.title_x,h*s.title_y),title,font=font,anchor='mm',fill=s.title_color)
        return Image.alpha_composite(img,overlay).convert('RGB')

    def title_font(self):
        s=self.s
        size=max(1,round(s.height*s.title_size))
        family={'Sans':'DejaVuSans','Serif':'DejaVuSerif','Mono':'DejaVuSansMono'}.get(s.title_font,'DejaVuSans')
        italic='Italic' if s.title_font=='Serif' else 'Oblique'
        suffix=('-Bold'+italic if s.title_italic else '-Bold') if s.title_bold else ('-'+italic if s.title_italic else '')
        windows={'Sans':'arial','Serif':'times','Mono':'cour'}[s.title_font]
        windows+=('bi' if s.title_bold and s.title_italic else 'bd' if s.title_bold else 'i' if s.title_italic else '')
        candidates=[family+suffix+'.ttf',os.path.join(os.environ.get('WINDIR','C:/Windows'),'Fonts',windows+'.ttf')]
        for candidate in candidates:
            try:return ImageFont.truetype(candidate,size)
            except OSError:pass
        return ImageFont.load_default(size=size)
