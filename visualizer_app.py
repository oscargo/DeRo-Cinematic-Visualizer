"""Standalone Tkinter GUI; renderer and exporter don't depend on Tkinter."""
import os
import json
import subprocess
import sys
import queue
import shutil
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import ImageTk
from visualizer_core import Settings, Renderer, audio_features
from audio_io import load_audio
from export_video import export

class Application:
    def __init__(self, root):
        self.root=root
        self.root.title('DeRo Cinematic Visualizer v0.1.5')
        self.root.geometry('1120x810')
        self.folder_preferences = self._load_folder_preferences()
        self.audio=tk.StringVar()
        self.background=tk.StringVar()
        self.title=tk.StringVar(value='LOVE NIGHT')
        self.dust=tk.IntVar(value=130)
        self.reactive=tk.IntVar(value=25)
        self.sensitivity=tk.DoubleVar(value=1.0)
        self.fps=tk.IntVar(value=60)
        self.bands=tk.IntVar(value=384)
        self.res=tk.StringVar(value='1920 x 1080')
        self.status=tk.StringVar(value='Select an audio file. Requires FFmpeg available on PATH.')
        self.position=tk.DoubleVar(value=0)
        self.selection_start=tk.DoubleVar(value=0)
        self.selection_end=tk.DoubleVar(value=0)
        self.selection_text=tk.StringVar(value="Start 0.000s • End 0.000s • Length 0.000s")
        self.loop_selection=False
        self.play_selection=False
        self.loaded_audio_path=None
        self.length=0
        self.samples=None
        self.features=None
        self.renderer=None
        self.last_preview_settings=None
        self.q=queue.Queue()
        self.busy=False
        self.playing=False
        self.last_export_path=None
        self.last_export_folder=self.folder_preferences.get('export', '')
        self.t0=0.0
        self.build()
        root.after(150,self.poll)

    def build(self):
        # Two-column top controls follow the user's v0.1.0 screenshot arrangement.
        pane=ttk.Frame(self.root,padding=10)
        pane.pack(fill='both',expand=True)
        top=ttk.Frame(pane)
        top.pack(fill='x',pady=(0,6))
        top.columnconfigure(0,weight=6)
        top.columnconfigure(1,weight=5)
        left=ttk.Frame(top);left.grid(row=0,column=0,sticky='nsew',padx=(0,16))
        right=ttk.Frame(top);right.grid(row=0,column=1,sticky='nsew')
        left.columnconfigure(1,weight=1)
        for i,(label,var,cmd) in enumerate((
            ('Music file',self.audio,self.browse_audio),
            ('Background image',self.background,self.browse_background))):
            ttk.Label(left,text=label).grid(row=i,column=0,sticky='w',padx=(0,6),pady=3)
            ttk.Entry(left,textvariable=var).grid(row=i,column=1,sticky='ew',pady=3)
            ttk.Button(left,text='Browse',command=cmd).grid(row=i,column=2,padx=(6,0),pady=3)
        first=ttk.Frame(right);first.pack(fill='x',pady=3)
        ttk.Label(first,text='Title').pack(side='left',padx=(0,4))
        ttk.Entry(first,textvariable=self.title,width=18).pack(side='left',padx=(0,8))
        ttk.Label(first,text='Dust count').pack(side='left',padx=(0,3))
        ttk.Spinbox(first,from_=0,to=800,textvariable=self.dust,width=5).pack(side='left',padx=(0,8))
        ttk.Label(first,text='Reactive %').pack(side='left',padx=(0,3))
        ttk.Spinbox(first,from_=0,to=100,textvariable=self.reactive,width=4).pack(side='left',padx=(0,8))
        ttk.Label(first,text='Sensitivity').pack(side='left',padx=(0,3))
        ttk.Spinbox(first,from_=0.1,to=3.0,increment=.1,textvariable=self.sensitivity,width=5).pack(side='left')
        second=ttk.Frame(right);second.pack(fill='x',pady=3)
        ttk.Label(second,text='Resolution').pack(side='left',padx=(0,4))
        ttk.Combobox(second,textvariable=self.res,values=('1920 x 1080','1280 x 720','854 x 480'),width=13,state='readonly').pack(side='left',padx=(0,8))
        ttk.Label(second,text='FPS').pack(side='left',padx=(0,4))
        ttk.Combobox(second,textvariable=self.fps,values=(60,30),width=4,state='readonly').pack(side='left',padx=(0,8))
        ttk.Button(second,text='Refresh Preview',command=self.prepare_preview).pack(side='left',padx=(0,6))
        ttk.Button(second,text='Export MP4',command=self.export_file).pack(side='left',padx=(0,6))
        ttk.Button(second,text='Open Export Folder',command=self.open_export_folder).pack(side='left')
        band_row=ttk.Frame(pane);band_row.pack(fill='x',pady=(2,4))
        ttk.Label(band_row,text='Spectrum bands').pack(side='left',padx=(0,6))
        band_box=ttk.Combobox(band_row,textvariable=self.bands,values=(32,64,96,128,192,256,384,512),width=7,state='readonly')
        band_box.pack(side='left')
        ttk.Label(band_row,text='384 = 4x the original 96 bands; mirrored around center',foreground='#526278').pack(side='left',padx=12)
        transport=ttk.Frame(pane);transport.pack(fill='x',pady=(2,2))
        ttk.Button(transport,text='Play / Pause Visuals (silent)',command=self.toggle_play).pack(side='left')
        self.scrub=ttk.Scale(transport,from_=0,to=100,variable=self.position,command=lambda _:self.display_frame())
        self.scrub.pack(side='left',fill='x',expand=True,padx=9)
        ttk.Button(transport,text='Save Preview PNG',command=self.save_preview).pack(side='left')
        selection=ttk.LabelFrame(pane,text='Preview / export selection',padding=6)
        selection.pack(fill='x',pady=4)
        self.range_canvas=tk.Canvas(selection,height=34,background='#142039',highlightthickness=0)
        self.range_canvas.pack(fill='x')
        self.range_canvas.bind('<Configure>',lambda event:self.update_selection())
        self.range_canvas.bind('<Button-1>',self.drag_selection)
        self.range_canvas.bind('<B1-Motion>',self.drag_selection)
        self.range_canvas.bind('<ButtonRelease-1>',lambda event:setattr(self,'range_handle',None))
        times=ttk.Frame(selection);times.pack(fill='x')
        for label,var in (('Start (s)',self.selection_start),('End (s)',self.selection_end)):
            ttk.Label(times,text=label).pack(side='left',padx=(0,4))
            entry=ttk.Entry(times,textvariable=var,width=10)
            entry.pack(side='left',padx=(0,12))
            entry.bind('<Return>',lambda event:self.update_selection())
            entry.bind('<FocusOut>',lambda event:self.update_selection())
        ttk.Label(times,textvariable=self.selection_text).pack(side='left')
        buttons=ttk.Frame(selection);buttons.pack(fill='x',pady=(5,0))
        for label,cmd in (('Full Song',self.full_song),('Start at playhead',lambda:self.set_boundary('start')),
                          ('End at playhead',lambda:self.set_boundary('end')),
                          ('Play Selection',lambda:self.start_playback(True)),('Pause',self.pause),
                          ('Loop Selection',lambda:self.start_playback(True,True)),
                          ('Play from Start',lambda:self.start_playback(False))):
            ttk.Button(buttons,text=label,command=cmd).pack(side='left',padx=(0,4))
        self.progress=ttk.Progressbar(pane,maximum=100,mode='determinate')
        self.progress.pack(fill='x',pady=(4,3))
        ttk.Label(pane,textvariable=self.status,wraplength=1400).pack(anchor='w')
        ttk.Label(pane,text='Preview animation is silent. Exported MP4 contains the music. 75% drifting / 25% reactive by default.',foreground='#526278').pack(anchor='w',pady=(0,3))
        self.canvas=tk.Label(pane,text='Choose music, then click Refresh Preview',background='#091425',foreground='white')
        self.canvas.pack(fill='both',expand=True,pady=(2,0))

    @staticmethod
    def _preferences_file():
        # Store independently of the application folder; survives updates and moves.
        config_home = os.environ.get('APPDATA') or os.path.join(os.path.expanduser('~'), '.config')
        return os.path.join(config_home, 'DeRo_Cinematic_Visualizer', 'folders.json')

    def _load_folder_preferences(self):
        try:
            with open(self._preferences_file(), 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                return {key: val for key, val in data.items()
                        if key in ('music', 'background', 'export') and isinstance(val, str)}
        except (OSError, ValueError, TypeError):
            pass
        return {}

    def _remember_folder(self, category, file_path):
        folder = os.path.dirname(os.path.abspath(file_path))
        if not os.path.isdir(folder):
            return
        self.folder_preferences[category] = folder
        pref_file = self._preferences_file()
        try:
            os.makedirs(os.path.dirname(pref_file), exist_ok=True)
            temp_file = pref_file + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.folder_preferences, f, indent=2)
            os.replace(temp_file, pref_file)
        except OSError:
            # Directory persistence must never stop the user from loading a file.
            pass

    def _browse_initial_folder(self, category, current_path):
        # Each file picker retains its own directory: music, background, export.
        choices = [self.folder_preferences.get(category, '')]
        if current_path.strip():
            choices.append(os.path.dirname(os.path.abspath(current_path.strip())))
        choices.append(os.path.expanduser('~'))
        for folder in choices:
            if folder and os.path.isdir(folder):
                return folder
        return os.getcwd()

    def browse_audio(self):
        p=filedialog.askopenfilename(initialdir=self._browse_initial_folder('music',self.audio.get()),
            filetypes=[('Audio files','*.wav *.mp3 *.flac *.m4a *.aac *.ogg *.wma'),('All files','*.*')])
        if p:
            self._remember_folder('music',p)
            self.audio.set(p)
            self.pause()
            self.samples=None;self.features=None;self.renderer=None
            self.prepare_preview()

    def browse_background(self):
        p=filedialog.askopenfilename(initialdir=self._browse_initial_folder('background',self.background.get()),
            filetypes=[('Images','*.png *.jpg *.jpeg *.webp *.bmp'),('All files','*.*')])
        if p:
            self._remember_folder('background',p)
            self.background.set(p);self.renderer=None;self.prepare_preview()

    def settings(self,preview=False):
        w,h=map(int,self.res.get().split(' x '))
        if preview:
            w,h=960,540
        return Settings(width=w,height=h,fps=self.fps.get(),title=self.title.get(),dust_count=max(0,min(800,self.dust.get())),reactive_fraction=max(0,min(1,self.reactive.get()/100)),sensitivity=max(.1,min(3,self.sensitivity.get())),background=self.background.get().strip(),bars=self.bands.get(),spectrum_width=0.62)

    def prepare_preview(self):
        if self.busy:return
        path=self.audio.get().strip()
        if not os.path.isfile(path):
            self.status.set('Select a valid music file first.');return
        settings=self.settings(preview=True)
        self.busy=True;self.status.set('Analyzing music frequencies...')
        def worker():
            try:
                if self.samples is None or path != self.loaded_audio_path:
                    samples,sr=load_audio(path)
                else:samples,sr=self.samples
                features=audio_features(samples,sr,settings.fps,settings.bars)
                renderer=Renderer(settings,features)
                self.q.put(('ready',(samples,sr,features,renderer,path)))
            except Exception as exc:self.q.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def display_frame(self):
        if self.renderer is None:return
        pos=min(self.length,max(0,self.position.get()))
        try:
            frame=self.renderer.render(pos)
            self.photo=ImageTk.PhotoImage(frame)
            self.canvas.configure(image=self.photo,text='')
        except Exception as exc:self.status.set(f'Preview error: {exc}')

    def selection_bounds(self):
        start,end=float(self.selection_start.get()),float(self.selection_end.get())
        import math
        if not math.isfinite(start) or not math.isfinite(end):
            raise ValueError('Selection times must be finite numbers.')
        if not 0 <= start < end <= self.length:
            raise ValueError('Choose a range with 0 ≤ Start < End ≤ song duration.')
        return start,end

    def update_selection(self):
        try:
            start,end=self.selection_start.get(),self.selection_end.get()
            self.selection_text.set(f'Start {start:.3f}s • End {end:.3f}s • Length {end-start:.3f}s')
        except (ValueError,tk.TclError):
            self.selection_text.set('Enter start and end times in seconds.')
            return
        canvas=self.range_canvas
        canvas.delete('all')
        width=max(1,canvas.winfo_width()-24)
        x1=12+width*max(0,min(1,start/(self.length or 1)))
        x2=12+width*max(0,min(1,end/(self.length or 1)))
        canvas.create_line(12,17,width+12,17,fill='#34435e',width=8)
        canvas.create_line(x1,17,x2,17,fill='#667bce',width=8)
        for x in (x1,x2):canvas.create_rectangle(x-5,3,x+5,31,fill='#ffd24c',outline='')

    def drag_selection(self,event):
        if self.length<=0:return
        width=max(1,self.range_canvas.winfo_width()-24)
        t=max(0,min(self.length,(event.x-12)/width*self.length))
        try:start,end=self.selection_bounds()
        except (ValueError,tk.TclError):
            self.full_song();start,end=0,self.length
        handle=getattr(self,'range_handle',None)
        if handle is None:
            handle='start' if abs(t-start)<=abs(t-end) else 'end'
            self.range_handle=handle
        gap=min(1/self.fps.get(),self.length)
        if handle=='start':self.selection_start.set(max(0,min(t,end-gap)))
        else:self.selection_end.set(min(self.length,max(t,start+gap)))
        self.update_selection()

    def full_song(self):
        self.selection_start.set(0)
        self.selection_end.set(self.length)
        self.update_selection()

    def set_boundary(self,which):
        t=max(0,min(self.length,self.position.get()))
        try:
            other=self.selection_end.get() if which=='start' else self.selection_start.get()
            if (which=='start' and t>=other) or (which=='end' and t<=other):
                raise ValueError('Start must be earlier than End.')
            (self.selection_start if which=='start' else self.selection_end).set(t)
            self.update_selection()
        except (ValueError,tk.TclError) as exc:self.status.set(str(exc))

    def pause(self):
        self.playing=False

    def start_playback(self,selection=False,loop=False):
        if self.renderer is None:return
        try:
            start,end=self.selection_bounds() if selection else (0,self.length)
        except (ValueError,tk.TclError) as exc:
            self.status.set(str(exc));return
        already_playing=self.playing
        self.play_selection=selection
        self.loop_selection=loop
        self.position.set(start)
        self.t0=time.monotonic()-start
        self.playing=True
        if not already_playing:self.animate()

    def toggle_play(self):
        if self.playing:self.pause();return
        if self.renderer is None:return
        self.play_selection=False;self.loop_selection=False
        self.t0=time.monotonic()-self.position.get()
        self.playing=True
        self.animate()

    def animate(self):
        if not self.playing:return
        try:
            start,end=self.selection_bounds() if self.play_selection else (0,self.length)
        except (ValueError,tk.TclError):self.pause();return
        t=time.monotonic()-self.t0
        if t>=end:
            if self.loop_selection:
                t=start+(t-start)%(end-start)
                self.t0=time.monotonic()-t
            else:
                self.position.set(end);self.display_frame();self.pause();return
        self.position.set(t)
        self.display_frame()
        self.root.after(50,self.animate)

    def save_preview(self):
        if not self.renderer:return messagebox.showinfo('Preview','Analyze music first.')
        p=filedialog.asksaveasfilename(defaultextension='.png',filetypes=[('PNG image','*.png')])
        if p:
            self.renderer.render(self.position.get()).save(p)
            self.status.set('Saved preview: '+p)

    def _open_path(self, path):
        """Open with OS default handler; run from Tk main thread only."""
        if sys.platform == 'win32':
            os.startfile(path)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', path])
        else:
            subprocess.Popen(['xdg-open', path])

    def open_export_folder(self):
        # Open the most recent export directory, including after restarting the app.
        folder=self._browse_initial_folder('export', self.last_export_path or '')
        if not self.folder_preferences.get('export') and not self.last_export_path:
            messagebox.showinfo('Export folder', 'No export folder has been selected yet.')
            return
        if not os.path.isdir(folder):
            messagebox.showerror('Export folder missing', folder)
            return
        try:
            if sys.platform == 'win32' and os.path.isfile(self.last_export_path):
                subprocess.Popen(['explorer.exe', '/select,', os.path.normpath(self.last_export_path)])
            else:
                self._open_path(folder)
        except OSError as exc:
            messagebox.showerror('Could not open export folder', str(exc))

    def export_file(self):
        if self.busy:return
        if not os.path.isfile(self.audio.get()):return messagebox.showerror('Audio missing','Select a music file first.')
        if not shutil.which('ffmpeg'):return messagebox.showerror('FFmpeg missing','Install FFmpeg and add it to PATH.')
        if self.loaded_audio_path != self.audio.get().strip():
            self.prepare_preview()
            return messagebox.showinfo('Analyze music','Wait for the preview, then choose the export range.')
        try:
            start,end=self.selection_bounds()
            settings=self.settings()
        except (ValueError,tk.TclError) as exc:
            return messagebox.showerror('Invalid selection',str(exc))
        audio_path=self.audio.get().strip()
        out=filedialog.asksaveasfilename(
            initialdir=self._browse_initial_folder('export', self.last_export_path or ''),
            defaultextension='.mp4', filetypes=[('MP4 video','*.mp4')])
        if not out:return
        # A chosen destination counts as the last used folder even if export fails.
        self._remember_folder('export', out)
        self.last_export_folder=os.path.dirname(os.path.abspath(out))
        if os.path.abspath(out)==os.path.abspath(self.audio.get()):return messagebox.showerror('Invalid path','Export path must differ from input.')
        self.pause()
        self.busy=True
        self.status.set('Exporting video. High-resolution rendering may be slow.')
        def worker():
            try:
                export(audio_path,out,settings,progress=lambda i,n:self.q.put(('progress',(i,n))),
                       start_seconds=start,end_seconds=end)
                if not os.path.isfile(out) or os.path.getsize(out) == 0:
                    raise RuntimeError('Export returned without a valid output MP4.')
                self.q.put(('finished',out))
            except Exception as exc:self.q.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def poll(self):
        try:
            while True:
                kind,data=self.q.get_nowait()
                if kind=='ready':
                    samples,sr,features,renderer,path=data
                    self.samples=samples,sr
                    self.features=features;self.renderer=renderer
                    self.length=len(samples)/sr
                    if path != self.loaded_audio_path:
                        self.position.set(0)
                        self.full_song()
                    self.loaded_audio_path=path
                    self.scrub.configure(to=self.length)
                    self.busy=False
                    self.status.set(f'Preview ready. Duration: {self.length:.1f}s | {len(features)} spectrum frames.')
                    self.display_frame()
                elif kind=='error':
                    self.busy=False
                    self.status.set('Error: '+data)
                    messagebox.showerror('Visualizer',data)
                elif kind=='progress':
                    i,n=data;self.progress['value']=i/n*100
                    self.status.set(f'Exporting MP4: {i/n*100:.1f}% ({i}/{n} frames)')
                elif kind=='finished':
                    self.busy=False;self.progress['value']=100
                    self.status.set('Export completed: '+data)
                    self.last_export_path=os.path.abspath(data)
                    try:
                        self._open_path(self.last_export_path)
                    except OSError as exc:
                        messagebox.showwarning('Export saved',
                            f'Export completed, but Windows could not open the MP4 automatically.\n\n'
                            f'{self.last_export_path}\n\n{exc}\n\n'
                            'Use Open Export Folder to find the file.')
        except queue.Empty:pass
        self.root.after(150,self.poll)

if __name__=='__main__':
    root=tk.Tk()
    Application(root)
    root.mainloop()
