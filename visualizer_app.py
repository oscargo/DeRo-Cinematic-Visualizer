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
from tkinter import filedialog, messagebox, ttk, colorchooser, font as tkfont
from PIL import Image, ImageTk
from visualizer_core import Settings, Renderer, audio_features
from audio_io import load_audio
from export_video import export
from project_io import DEFAULTS, validate_settings, save_project, load_project

class Application:
    def __init__(self, root):
        self.root=root
        self.root.title('DeRo Cinematic Visualizer v0.1.8 - Creative Projects')
        self.root.geometry('1400x940')
        self.root.minsize(1120,820)
        self.preview_frame=None
        self.preview_resize_job=None
        self.folder_preferences = self._load_folder_preferences()
        self.project_vars={}
        for key,value in DEFAULTS.items():
            kind=tk.BooleanVar if isinstance(value,bool) else tk.IntVar if isinstance(value,int) else tk.DoubleVar if isinstance(value,float) else tk.StringVar
            self.project_vars[key]=kind(value=value)
            setattr(self,key,self.project_vars[key])
        self.project_path=None
        self.pending_selection=None
        self.layout_job=None
        self.status=tk.StringVar(value='Select an audio file. Requires FFmpeg available on PATH.')
        self.position=tk.DoubleVar(value=0)
        self.selection_start=tk.DoubleVar(value=0)
        self.selection_end=tk.DoubleVar(value=0)
        self.selection_text=tk.StringVar(value="Start 0.000s  |  End 0.000s  |  Length 0.000s")
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
        self.saved_project_state=self.project_state()
        self.root.protocol('WM_DELETE_WINDOW',self.close_project)
        for key in ('title','title_size','title_x','title_y','title_font','title_bold','title_italic',
                    'title_uppercase','title_color','spectrum_width','spectrum_x','spectrum_y','spectrum_height'):
            self.project_vars[key].trace_add('write',self.schedule_layout_preview)
        root.after(150,self.poll)

    def configure_theme(self):
        families={name.lower():name for name in tkfont.families(self.root)}
        self.ui_font=next((families[name] for name in ('segoe ui','inter','dejavu sans','arial','helvetica') if name in families),'TkDefaultFont')
        self.root.configure(background='#0b101a')
        style=ttk.Style(self.root)
        style.theme_use('clam')
        self.root.option_add('*Font', (self.ui_font,10))
        self.root.option_add('*TCombobox*Listbox.background','#1c2739')
        self.root.option_add('*TCombobox*Listbox.foreground','#e5ebf5')
        self.root.option_add('*TCombobox*Listbox.selectBackground','#456cbd')
        style.configure('.',background='#101827',foreground='#e5ebf5',font=(self.ui_font,10))
        style.configure('TFrame',background='#101827')
        style.configure('Shell.TFrame',background='#0b101a')
        style.configure('TLabel',background='#101827',foreground='#e5ebf5')
        style.configure('Muted.TLabel',foreground='#96a6bf')
        style.configure('Section.TLabel',foreground='#8fa9d5',font=(self.ui_font,9,'bold'))
        style.configure('Heading.TLabel',font=(self.ui_font,17,'bold'))
        style.configure('Brand.TLabel',background='#0b101a',font=(self.ui_font,23,'bold'))
        style.configure('Subtitle.TLabel',background='#0b101a',foreground='#96a6bf')
        style.configure('Badge.TLabel',background='#192b40',foreground='#9ac7e8',padding=(12,6),font=(self.ui_font,9,'bold'))
        style.configure('TButton',background='#202e44',foreground='#e5ebf5',borderwidth=0,
                        padding=(12,9),font=(self.ui_font,10))
        style.map('TButton',background=[('pressed','#344967'),('active','#2c405e')],
                  foreground=[('disabled','#5f6e85')])
        style.configure('Accent.TButton',background='#82b8f9',foreground='#0c192b',font=(self.ui_font,10,'bold'))
        style.map('Accent.TButton',background=[('pressed','#5795e3'),('active','#a1ccff')])
        for name in ('TEntry','TCombobox','TSpinbox'):
            style.configure(name,fieldbackground='#192538',background='#263752',foreground='#edf3ff',
                            bordercolor='#2a3a52',lightcolor='#2a3a52',darkcolor='#2a3a52',
                            insertcolor='#ffffff',arrowsize=13,padding=7)
            style.map(name,fieldbackground=[('readonly','#192538')],
                      foreground=[('readonly','#edf3ff')],bordercolor=[('focus','#82b8f9')])
        style.configure('Horizontal.TScale',background='#101827',troughcolor='#263752',borderwidth=0)
        style.configure('Horizontal.TProgressbar',background='#82b8f9',troughcolor='#1c2b41',borderwidth=0)
        style.configure('TCheckbutton',background='#101827',foreground='#e5ebf5',padding=2)
        style.map('TCheckbutton',background=[('active','#192538')])
        style.configure('TSeparator',background='#263247')

    def build(self):
        self.configure_theme()
        menu=tk.Menu(self.root)
        file_menu=tk.Menu(menu,tearoff=False)
        for label,command,shortcut in (('New project',self.new_project,'Ctrl+N'),('Open project...',self.open_project,'Ctrl+O'),
                ('Save project',self.save_project_file,'Ctrl+S'),('Save project as...',lambda:self.save_project_file(True),'Ctrl+Shift+S')):
            file_menu.add_command(label=label,command=command,accelerator=shortcut)
        menu.add_cascade(label='File',menu=file_menu)
        self.root.configure(menu=menu)
        for shortcut,command in (('<Control-n>',self.new_project),('<Control-o>',self.open_project),
                ('<Control-s>',self.save_project_file),('<Control-Shift-S>',lambda:self.save_project_file(True))):
            self.root.bind(shortcut,lambda event,cmd=command:cmd())
        shell=ttk.Frame(self.root,style='Shell.TFrame',padding=(24,18))
        shell.pack(fill='both',expand=True)
        header=ttk.Frame(shell,style='Shell.TFrame');header.pack(fill='x',pady=(0,18))
        brand=ttk.Frame(header,style='Shell.TFrame');brand.pack(side='left')
        ttk.Label(brand,text='DeRo  /  Cinematic Visualizer',style='Brand.TLabel').pack(anchor='w')
        ttk.Label(brand,text='Shape the sound. Set the atmosphere.',style='Subtitle.TLabel').pack(anchor='w',pady=(4,0))
        ttk.Label(header,text='CREATIVE PROJECTS  /  v0.1.8',style='Badge.TLabel').pack(side='right')
        body=ttk.Frame(shell,style='Shell.TFrame');body.pack(fill='both',expand=True)
        body.columnconfigure(1,weight=1);body.rowconfigure(0,weight=1)
        sidebar=ttk.Frame(body,padding=18,width=290)
        sidebar.grid(row=0,column=0,sticky='nsew',padx=(0,18));sidebar.grid_propagate(False)
        sidebar.columnconfigure(0,weight=1)
        # Scroll the inspector on smaller screens and with large system fonts.
        inspector=tk.Canvas(sidebar,background='#101827',highlightthickness=0,width=254)
        scroll=ttk.Scrollbar(sidebar,orient='vertical',command=inspector.yview)
        inspector.configure(yscrollcommand=scroll.set)
        inspector.grid(row=0,column=0,sticky='nsew');scroll.grid(row=0,column=1,sticky='ns')
        sidebar.rowconfigure(0,weight=1)
        controls=ttk.Frame(inspector)
        window=inspector.create_window((0,0),window=controls,anchor='nw')
        controls.bind('<Configure>',lambda e:inspector.configure(scrollregion=inspector.bbox('all')))
        inspector.bind('<Configure>',lambda e:inspector.itemconfigure(window,width=e.width))
        def wheel(event):
            pointer=self.root.winfo_containing(event.x_root,event.y_root)
            if pointer is not None and str(pointer).startswith(str(sidebar)):
                units=(-1 if event.num==4 else 1) if event.num in (4,5) else (-1 if event.delta>0 else 1)
                inspector.yview_scroll(units*3,'units')
        self.root.bind('<MouseWheel>',wheel,add='+')
        self.root.bind('<Button-4>',wheel,add='+')
        self.root.bind('<Button-5>',wheel,add='+')

        def section(text):
            ttk.Label(controls,text=text,style='Section.TLabel').pack(anchor='w',pady=(16,10))
        def field(label,var,values=None):
            ttk.Label(controls,text=label,style='Muted.TLabel').pack(anchor='w',pady=(7,5))
            widget=(ttk.Combobox(controls,textvariable=var,values=values,state='readonly')
                    if values else ttk.Entry(controls,textvariable=var))
            widget.pack(fill='x')
            return widget
        ttk.Label(controls,text='Your composition',style='Heading.TLabel').pack(anchor='w')
        ttk.Label(controls,text='Build a scene around your music.',style='Muted.TLabel').pack(anchor='w',pady=(5,0))
        section('01  /  SOURCE')
        field('Music file',self.audio)
        ttk.Button(controls,text='Choose music...',command=self.browse_audio).pack(fill='x',pady=(6,2))
        field('Background image / optional',self.background)
        ttk.Button(controls,text='Choose image...',command=self.browse_background).pack(fill='x',pady=(6,2))
        section('02  /  TITLE & LAYOUT')
        field('Display title',self.title)
        field('Typeface',self.title_font,('Sans','Serif','Mono'))
        styles=ttk.Frame(controls);styles.pack(fill='x',pady=8)
        for label,var in (('Bold',self.title_bold),('Italic',self.title_italic),('Caps',self.title_uppercase)):
            ttk.Checkbutton(styles,text=label,variable=var).pack(side='left')
        ttk.Button(controls,text='Title color...',command=self.choose_title_color).pack(fill='x')
        def numeric(label,var,low,high,step=1):
            row=ttk.Frame(controls);row.pack(fill='x',pady=(9,0))
            ttk.Label(row,text=label,style='Muted.TLabel').pack(side='left')
            ttk.Spinbox(row,textvariable=var,from_=low,to=high,increment=step,width=6).pack(side='right')
        def arrows(target):
            pad=ttk.Frame(controls);pad.pack(fill='x',pady=(7,0))
            for i,(label,dx,dy) in enumerate((('<',-1,0),('^',0,-1),('v',0,1),('>',1,0))):
                pad.columnconfigure(i,weight=1)
                ttk.Button(pad,text=label,width=4,command=lambda x=dx,y=dy:self.nudge(target,x,y)).grid(row=0,column=i,sticky='ew',padx=1)
        numeric('Title size (% height)',self.title_size,.5,12,.1)
        numeric('Title X (%)',self.title_x,0,100)
        numeric('Title Y (%)',self.title_y,0,100)
        arrows('title')
        ttk.Button(controls,text='Reset title layout',command=lambda:self.reset_layout('title')).pack(fill='x',pady=(7,0))
        section('03  /  SPECTRUM')
        numeric('Width (%)',self.spectrum_width,10,100)
        width_buttons=ttk.Frame(controls);width_buttons.pack(fill='x',pady=(7,0))
        ttk.Button(width_buttons,text='< Narrower',command=lambda:self.change_width(-2)).pack(side='left',fill='x',expand=True)
        ttk.Button(width_buttons,text='Wider >',command=lambda:self.change_width(2)).pack(side='left',fill='x',expand=True,padx=(4,0))
        numeric('Height (% frame)',self.spectrum_height,1,30,.5)
        numeric('Spectrum X (%)',self.spectrum_x,0,100)
        numeric('Spectrum Y (%)',self.spectrum_y,0,100)
        arrows('spectrum')
        ttk.Button(controls,text='Reset spectrum layout',command=lambda:self.reset_layout('spectrum')).pack(fill='x',pady=(7,0))
        section('04  /  ATMOSPHERE')
        for label,var,low,high,step in (('Dust particles',self.dust,0,800,1),
                ('Reactive particles (%)',self.reactive,0,100,1),('Sensitivity',self.sensitivity,.1,3,.1)):
            row=ttk.Frame(controls);row.pack(fill='x',pady=(12,0))
            ttk.Label(row,text=label,style='Muted.TLabel').pack(side='left')
            ttk.Spinbox(row,from_=low,to=high,increment=step,textvariable=var,width=6).pack(side='right')
        field('Spectrum bands',self.bands,(32,64,96,128,192,256,384,512))
        section('05  /  OUTPUT')
        field('Resolution',self.res,('1920 x 1080','1280 x 720','854 x 480'))
        field('Frames per second',self.fps,(60,30))
        ttk.Button(controls,text='Quick test / 480p / 30 FPS',command=self.quick_test_preset).pack(fill='x',pady=(10,0))
        ttk.Button(controls,text='Open export folder',command=self.open_export_folder).pack(fill='x',pady=(8,12))

        workspace=ttk.Frame(body,style='Shell.TFrame');workspace.grid(row=0,column=1,sticky='nsew')
        workspace.columnconfigure(0,weight=1);workspace.rowconfigure(0,weight=1)
        preview=ttk.Frame(workspace,padding=16);preview.grid(row=0,column=0,sticky='nsew')
        preview.columnconfigure(0,weight=1);preview.rowconfigure(1,weight=1)
        toolbar=ttk.Frame(preview);toolbar.grid(row=0,column=0,sticky='ew',pady=(0,12))
        ttk.Label(toolbar,text='Scene preview',style='Heading.TLabel').pack(side='left')
        ttk.Button(toolbar,text='Save PNG',command=self.save_preview).pack(side='right')
        ttk.Button(toolbar,text='Refresh preview',command=self.prepare_preview).pack(side='right',padx=8)
        viewport=ttk.Frame(preview);viewport.grid(row=1,column=0,sticky='nsew')
        viewport.pack_propagate(False)
        self.canvas=tk.Label(viewport,text='YOUR NEXT VISUAL STARTS HERE\n\nChoose music to bring this scene to life.',
                             font=(self.ui_font,14),background='#080e19',foreground='#91a5c5',borderwidth=0)
        self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Configure>',self.resize_preview)
        transport=ttk.Frame(preview);transport.grid(row=2,column=0,sticky='ew',pady=(12,0))
        ttk.Button(transport,text='Play / Pause',command=self.toggle_play).pack(side='left')
        self.scrub=ttk.Scale(transport,from_=0,to=100,variable=self.position,command=lambda _:self.display_frame())
        self.scrub.pack(side='left',fill='x',expand=True,padx=12)
        ttk.Label(transport,text='SILENT PREVIEW',style='Section.TLabel').pack(side='right')

        selection=ttk.Frame(workspace,padding=(16,12));selection.grid(row=1,column=0,sticky='ew',pady=(12,0))
        heading=ttk.Frame(selection);heading.pack(fill='x')
        ttk.Label(heading,text='Export range',style='Heading.TLabel').pack(side='left')
        ttk.Button(heading,text='Full song',command=self.full_song).pack(side='right')
        self.range_canvas=tk.Canvas(selection,height=38,background='#101827',highlightthickness=0,cursor='hand2')
        self.range_canvas.pack(fill='x',pady=(5,0))
        self.range_canvas.bind('<Configure>',lambda event:self.update_selection())
        self.range_canvas.bind('<Button-1>',self.drag_selection)
        self.range_canvas.bind('<B1-Motion>',self.drag_selection)
        self.range_canvas.bind('<ButtonRelease-1>',lambda event:setattr(self,'range_handle',None))
        times=ttk.Frame(selection);times.pack(fill='x')
        for label,var in (('Start (s)',self.selection_start),('End (s)',self.selection_end)):
            ttk.Label(times,text=label,style='Muted.TLabel').pack(side='left',padx=(0,6))
            entry=ttk.Entry(times,textvariable=var,width=9);entry.pack(side='left',padx=(0,16))
            entry.bind('<Return>',lambda event:self.update_selection())
            entry.bind('<FocusOut>',lambda event:self.update_selection())
        ttk.Label(selection,textvariable=self.selection_text,style='Muted.TLabel').pack(anchor='w',pady=(8,4))
        buttons=ttk.Frame(selection);buttons.pack(fill='x')
        for i,(label,cmd) in enumerate((('Set start here',lambda:self.set_boundary('start')),
                ('Set end here',lambda:self.set_boundary('end')),('Play selection',lambda:self.start_playback(True)),
                ('Pause',self.pause),('Loop selection',lambda:self.start_playback(True,True)),
                ('Play from start',lambda:self.start_playback(False)))):
            buttons.columnconfigure(i%3,weight=1)
            ttk.Button(buttons,text=label,command=cmd).grid(row=i//3,column=i%3,sticky='ew',padx=(0,6),pady=3)
        footer=ttk.Frame(workspace,padding=16);footer.grid(row=2,column=0,sticky='ew',pady=(12,0))
        action=ttk.Frame(footer);action.pack(fill='x')
        ttk.Label(action,text='Ready when you are.',style='Heading.TLabel').pack(side='left')
        ttk.Button(action,text='Export MP4',style='Accent.TButton',command=self.export_file).pack(side='right')
        self.progress=ttk.Progressbar(footer,maximum=100,mode='determinate',length=100)
        self.progress.pack(fill='x',pady=(12,8))
        self.status_label=ttk.Label(footer,textvariable=self.status,style='Muted.TLabel',wraplength=580)
        self.status_label.pack(anchor='w',fill='x')
        self.status_label.bind('<Configure>',lambda e:self.status_label.configure(wraplength=max(100,e.width)))
        ttk.Label(footer,text='Preview is silent / Export includes music',style='Muted.TLabel').pack(anchor='w',pady=(4,0))

    def schedule_layout_preview(self,*args):
        if self.layout_job is not None:self.root.after_cancel(self.layout_job)
        self.layout_job=self.root.after(100,self.apply_layout_preview)

    def apply_layout_preview(self):
        self.layout_job=None
        if self.renderer is None:return
        try:
            values=validate_settings({key:var.get() for key,var in self.project_vars.items()})
            for key in ('title','title_font','title_bold','title_italic','title_uppercase','title_color'):
                setattr(self.renderer.s,key,values[key])
            for key in ('title_size','title_x','title_y','spectrum_width','spectrum_x','spectrum_y','spectrum_height'):
                setattr(self.renderer.s,key,values[key]/100)
            self.display_frame()
        except (ValueError,tk.TclError):pass

    def nudge(self,target,dx,dy):
        try:
            for axis,delta in (('x',dx),('y',dy)):
                var=self.project_vars[target+'_'+axis]
                var.set(round(max(0,min(100,var.get()+delta)),2))
        except (ValueError,tk.TclError):self.status.set('Enter a valid position first.')

    def change_width(self,delta):
        try:self.spectrum_width.set(max(10,min(100,self.spectrum_width.get()+delta)))
        except (ValueError,tk.TclError):self.status.set('Enter a valid spectrum width first.')

    def reset_layout(self,target):
        keys=('title_x','title_y','title_size') if target=='title' else ('spectrum_x','spectrum_y','spectrum_width','spectrum_height')
        for key in keys:self.project_vars[key].set(DEFAULTS[key])

    def choose_title_color(self):
        color=colorchooser.askcolor(color=self.title_color.get(),parent=self.root,title='Title color')[1]
        if color:self.title_color.set(color)

    def project_state(self):
        values=validate_settings({key:var.get() for key,var in self.project_vars.items()})
        end=self.selection_end.get()
        return values,[self.selection_start.get(),end if end>0 else None]

    def confirm_replace(self):
        if self.busy:
            messagebox.showinfo('Please wait','Wait for the current analysis or export to finish.');return False
        try:changed=self.project_state()!=self.saved_project_state
        except (ValueError,tk.TclError):changed=True
        if not changed:return True
        answer=messagebox.askyesnocancel('Unsaved project','Save your changes before continuing?')
        if answer is None:return False
        return self.save_project_file() if answer else True

    def update_project_title(self):
        name=os.path.basename(self.project_path) if self.project_path else 'Untitled'
        self.root.title(f'{name} - DeRo Cinematic Visualizer v0.1.8 - Creative Projects')

    def clear_media(self):
        self.pause()
        self.samples=None;self.features=None;self.renderer=None;self.preview_frame=None
        self.loaded_audio_path=None;self.length=0;self.position.set(0)
        self.selection_start.set(0);self.selection_end.set(0)
        self.pending_selection=None
        self.scrub.configure(to=0);self.progress['value']=0
        self.canvas.configure(image='',text='YOUR NEXT VISUAL STARTS HERE\n\nChoose music to bring this scene to life.')
        self.update_selection()
        self.last_export_path=None

    def new_project(self):
        if not self.confirm_replace():return
        self.clear_media()
        for key,value in DEFAULTS.items():self.project_vars[key].set(value)
        self.project_path=None
        self.saved_project_state=self.project_state()
        self.update_project_title()
        self.status.set('New project. All composition settings restored to defaults.')

    def save_project_file(self,save_as=False):
        if self.busy:
            messagebox.showinfo('Please wait','Wait for the current analysis or export to finish.');return False
        try:
            values,selection=self.project_state()
            path=self.project_path
            if save_as or not path:
                path=filedialog.asksaveasfilename(defaultextension='.dero',filetypes=[('DeRo project','*.dero')],
                    initialfile=os.path.basename(path) if path else 'Untitled.dero')
            if not path:return False
            save_project(path,values,*selection)
            self.project_path=os.path.abspath(path)
            self.saved_project_state=self.project_state()
            self.update_project_title()
            self.status.set('Project saved: '+self.project_path)
            return True
        except (OSError,ValueError,tk.TclError) as exc:
            messagebox.showerror('Could not save project',str(exc));return False

    def open_project(self):
        if not self.confirm_replace():return
        path=filedialog.askopenfilename(filetypes=[('DeRo project','*.dero'),('JSON project','*.json')])
        if not path:return
        try:values,selection=load_project(path)
        except (OSError,ValueError) as exc:
            messagebox.showerror('Could not open project',str(exc));return
        self.clear_media()
        for key,value in values.items():self.project_vars[key].set(value)
        self.project_path=os.path.abspath(path)
        self.selection_start.set(selection[0]);self.selection_end.set(selection[1] or 0)
        self.pending_selection=selection
        self.saved_project_state=self.project_state()
        self.update_project_title()
        missing=[key for key in ('audio','background') if values[key] and not os.path.isfile(values[key])]
        if missing:
            self.status.set('Project opened. Missing media: '+', '.join(missing)+'. Choose replacement files in the sidebar.')
            return
        if values['audio']:self.prepare_preview()
        else:self.status.set('Project opened. Choose music to preview.')

    def close_project(self):
        if self.confirm_replace():self.root.destroy()

    def quick_test_preset(self):
        self.res.set('854 x 480')
        self.fps.set(30)
        self.status.set('Quick test output: 480p / 30 FPS. Choose a short export range below the preview.')

    def resize_preview(self,event=None):
        if self.preview_resize_job is not None:self.root.after_cancel(self.preview_resize_job)
        self.preview_resize_job=self.root.after(60,self.fit_preview)

    def fit_preview(self):
        self.preview_resize_job=None
        if self.preview_frame is None:return
        frame=self.preview_frame.copy()
        frame.thumbnail((max(1,self.canvas.winfo_width()-8),max(1,self.canvas.winfo_height()-8)),Image.Resampling.LANCZOS)
        self.photo=ImageTk.PhotoImage(frame)
        self.canvas.configure(image=self.photo,text='')

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
        return Settings(width=w,height=h,fps=self.fps.get(),title=self.title.get(),dust_count=max(0,min(800,self.dust.get())),reactive_fraction=max(0,min(1,self.reactive.get()/100)),sensitivity=max(.1,min(3,self.sensitivity.get())),background=self.background.get().strip(),bars=self.bands.get(),spectrum_width=self.spectrum_width.get()/100,
            spectrum_x=self.spectrum_x.get()/100,spectrum_y=self.spectrum_y.get()/100,
            spectrum_height=self.spectrum_height.get()/100,title_size=self.title_size.get()/100,
            title_x=self.title_x.get()/100,title_y=self.title_y.get()/100,title_font=self.title_font.get(),
            title_bold=self.title_bold.get(),title_italic=self.title_italic.get(),
            title_uppercase=self.title_uppercase.get(),title_color=self.title_color.get())

    def prepare_preview(self):
        if self.busy:return
        path=self.audio.get().strip()
        if not os.path.isfile(path):
            self.status.set('Select a valid music file first.');return
        try:
            validate_settings({key:var.get() for key,var in self.project_vars.items()})
            settings=self.settings(preview=True)
        except (ValueError,tk.TclError) as exc:
            self.status.set(str(exc));return
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
            self.preview_frame=frame
            self.fit_preview()
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
            self.selection_text.set(f'Start {start:.3f}s  |  End {end:.3f}s  |  Length {end-start:.3f}s')
        except (ValueError,tk.TclError):
            self.selection_text.set('Enter start and end times in seconds.')
            return
        canvas=self.range_canvas
        canvas.delete('all')
        width=max(1,canvas.winfo_width()-24)
        x1=12+width*max(0,min(1,start/(self.length or 1)))
        x2=12+width*max(0,min(1,end/(self.length or 1)))
        canvas.create_line(12,17,width+12,17,fill='#34435e',width=8)
        canvas.create_line(x1,17,x2,17,fill='#82b8f9',width=8)
        for x in (x1,x2):canvas.create_rectangle(x-5,3,x+5,31,fill='#b9d8ff',outline='')

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
            validate_settings({key:var.get() for key,var in self.project_vars.items()})
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
                    if self.pending_selection is not None:
                        start,end=self.pending_selection
                        self.selection_start.set(min(start,max(0,self.length-1/sr)))
                        self.selection_end.set(min(end,self.length) if end is not None else self.length)
                        if self.selection_end.get()<=self.selection_start.get():self.full_song()
                        self.pending_selection=None
                        self.saved_project_state=self.project_state()
                        self.update_selection()
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
