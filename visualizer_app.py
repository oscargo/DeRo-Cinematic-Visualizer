"""DeRo Cinematic Visualizer v0.1.35 — Karaoke Workspaces.

Resizable dark desktop studio with project controls, highlighted media actions,
and click-to-play timeline navigation. Preview has switchable sound; exports include audio.
Renderer and exporter are independent of Tkinter.
"""
import os
import json
import subprocess
import sys
import queue
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from preview_cache import PreviewCache
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, colorchooser, font as tkfont
from PIL import Image, ImageTk
from visualizer_core import Settings, Renderer, audio_features
from audio_io import load_audio, read_metadata, suggested_name
from song_identity import find_names,suggest_names,filename_names,review_names
from song_separation import separate_song,MODELS
from export_timing import ExportTimer,ExportETA,format_duration
from export_control import ExportControl,ExportCancelled
from export_diagnostics import ExportReport,report_json
from export_video import export
from video_encoder import ENCODER_CHOICES
from preview_audio import PreviewAudio, decode_preview
from notifications import completion_tone
from project_io import DEFAULTS, validate_settings, save_project, load_project, load_project_full
from karaoke_workspace import KaraokeWorkspace
from lyric_model import LyricDocument
from lyric_render import IdentityRenderer
from lyric_guide import draw_lyric_guide
from audio_mix import mix_spec,prepare_mix

class Application(KaraokeWorkspace):
    def __init__(self, root):
        self.root=root
        self.root.title('DeRo Cinematic Visualizer v0.1.35 - Karaoke Workspaces')
        self.root.geometry('1400x940')
        self.root.minsize(1040,820)
        self.root.resizable(True,True)
        self.preview_frame=None
        self.preview_resize_job=None
        self.fullscreen_window=None
        self.fullscreen_canvas=None
        self.folder_preferences = self._load_folder_preferences()
        self.project_vars={}
        for key,value in DEFAULTS.items():
            kind=tk.BooleanVar if isinstance(value,bool) else tk.IntVar if isinstance(value,int) else tk.DoubleVar if isinstance(value,float) else tk.StringVar
            self.project_vars[key]=kind(value=value)
            setattr(self,key,self.project_vars[key])
        self.spectrum_summary=tk.StringVar(value='384 visible bars / 192 per side')
        self.reset_text_defaults={'title':'','artist':''}
        self.reset_buttons={}
        self.project_path=None
        self.project_name=tk.StringVar(value='Untitled project')
        self.pending_selection=None
        self.layout_job=None
        self.metadata_pending_path=None
        self.song_lookup_generation=0
        self.song_lookup_control=None
        self.song_import_generation=0
        self.separation_control=None
        self.separation_started=None
        self.song_workflow_status=tk.StringVar(value='Choose a song to begin.')
        self.song_overview=tk.StringVar(value='No song loaded')
        self.separation_status=tk.StringVar(value='Ready — choose a song or import existing stems.')
        self.separation_elapsed=tk.StringVar(value='Elapsed: 00:00:00 · Total: —')
        self.export_control=None
        self.last_export_report=None
        self.close_when_export_done=False
        self.cancel_requested=False
        self.export_eta=None
        self.export_remaining=tk.StringVar(value='Remaining: —')
        self.export_outcome=None
        self.compact_export_text=tk.StringVar(value='')
        self.compact_device=tk.StringVar(value='')
        self.export_timer=ExportTimer()
        self.export_time=tk.StringVar(value=self.export_timer.text())
        self.export_device=tk.StringVar(value="Encoding: — | Rendering: CPU")
        self.encoder_status=tk.StringVar(value="Encoder: checked when export starts")
        self.status=tk.StringVar(value='Browse audio to import a song.')
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
        self.preview_cache=PreviewCache()
        self.particle_executor=ThreadPoolExecutor(max_workers=1)
        self.particle_future=None
        self.particle_request=None
        self.particle_generation=0
        self.q=queue.Queue()
        self.busy=False
        self.playing=False
        self.last_export_path=None
        self.last_export_folder=self.folder_preferences.get('export', '')
        self.sound_enabled=self.preview_sound
        self.preview_player=PreviewAudio()
        self.preview_audio=None
        self.t0=0.0
        self.init_karaoke()
        self.build()
        self.install_reset_controls()
        self.saved_project_state=self.project_state()
        self.saved_lyrics=self.lyric_document.snapshot()
        self.root.protocol('WM_DELETE_WINDOW',self.close_project)
        for key in ('fps','bands','frequency_min','frequency_max','frequency_scale','spectrum_mapping','spectrum_style','spectrum_mirrored',
                    'spectrum_density','spectrum_fill','spectrum_color_end','particle_continuous','particles_enabled','particle_reactivity','particle_direction','particle_reactive','particle_color','spectrum_color',
                    'overlay_enabled','overlay_path','overlay_size','overlay_x','overlay_y','overlay_opacity','overlay_shape',
                    'dust','reactive','sensitivity','title','title_size','title_x','title_y','title_font','title_bold','title_italic',
                    'title_uppercase','title_color','artist','artist_size','artist_x','artist_y','artist_font',
                    'artist_bold','artist_italic','artist_uppercase','artist_color','particle_speed','spectrum_gain','spectrum_width','spectrum_x','spectrum_y','spectrum_height'):
            self.project_vars[key].trace_add('write',self.schedule_layout_preview)
        self.sound_enabled.trace_add('write',lambda *args:setattr(self.preview_player,'muted',not self.sound_enabled.get()))
        self.title.trace_add('write',lambda *args:self.update_project_title())
        self.artist.trace_add('write',lambda *args:self.update_project_title())
        self.update_project_title()
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
        style.configure('CompactBrand.TLabel',background='#0b101a',font=(self.ui_font,15,'bold'))
        style.configure('Brand.TLabel',background='#0b101a',font=(self.ui_font,23,'bold'))
        style.configure('ProjectName.TLabel',background='#0b101a',foreground='#b9d8ff',font=(self.ui_font,11,'bold'))
        style.configure('Subtitle.TLabel',background='#0b101a',foreground='#96a6bf')
        style.configure('Badge.TLabel',background='#192b40',foreground='#9ac7e8',padding=(12,6),font=(self.ui_font,9,'bold'))
        style.configure('TButton',background='#202e44',foreground='#e5ebf5',borderwidth=0,
                        padding=(12,9),font=(self.ui_font,10))
        style.map('TButton',background=[('pressed','#344967'),('active','#2c405e')],
                  foreground=[('disabled','#5f6e85')])
        style.configure('Accent.TButton',background='#82b8f9',foreground='#0c192b',font=(self.ui_font,10,'bold'))
        style.map('Accent.TButton',background=[('pressed','#5795e3'),('active','#a1ccff')])
        for name,color,hover in (('Music.TButton','#65cbb6','#8ae1cf'),('Image.TButton','#b4a2ef','#cbbcf9')):
            style.configure(name,background=color,foreground='#0c192b',font=(self.ui_font,10,'bold'))
            style.map(name,background=[('pressed',hover),('active',hover)])
        style.configure('Studio.Vertical.TScrollbar',background='#8faed6',troughcolor='#17243a',
                        bordercolor='#17243a',lightcolor='#8faed6',darkcolor='#8faed6',
                        arrowcolor='#10213a',arrowsize=24,width=24,gripsize=18)
        style.map('Studio.Vertical.TScrollbar',background=[('pressed','#c1dafa'),('active','#afcff7')])
        for name in ('TEntry' ,'TCombobox','TSpinbox'):
            style.configure(name,fieldbackground='#192538',background='#263752',foreground='#edf3ff',
                            bordercolor='#2a3a52',lightcolor='#2a3a52',darkcolor='#2a3a52',
                            insertcolor='#ffffff',arrowsize=13,padding=7)
            style.map(name,fieldbackground=[('readonly','#192538')],
                      foreground=[('readonly','#edf3ff')],bordercolor=[('focus','#82b8f9')])
        style.configure('Horizontal.TScale',background='#101827',troughcolor='#263752',borderwidth=0)
        style.configure('Horizontal.TProgressbar',background='#82b8f9',troughcolor='#1c2b41',borderwidth=0)
        style.configure('Compact.Horizontal.TProgressbar',thickness=6)
        style.configure('CompactSuccess.TLabel',background='#101827',foreground='#b6f7d1')
        style.configure('TCheckbutton',background='#101827',foreground='#e5ebf5',padding=2)
        style.map('TCheckbutton',background=[('active','#192538')])
        style.configure('Success.TFrame',background='#123b30',relief='solid',borderwidth=1)
        style.configure('Success.TLabel',background='#123b30',foreground='#b6f7d1',font=(self.ui_font,12,'bold'))
        style.configure('SuccessBody.TLabel',background='#123b30',foreground='#d6efe1')
        style.configure('TSeparator',background='#263247')
        self.switch_images=[]
        for enabled in (False,True):
            icon=Image.new('RGBA',(38,22))
            from PIL import ImageDraw
            drawing=ImageDraw.Draw(icon)
            drawing.rounded_rectangle((1,2,37,20),radius=9,fill='#527cb4' if enabled else '#3b475b')
            x=26 if enabled else 12
            drawing.ellipse((x-8,3,x+8,19),fill='#dceaff' if enabled else '#a4afc0')
            self.switch_images.append(ImageTk.PhotoImage(icon))
        style.element_create('StudioToggle.indicator','image',self.switch_images[0],
                             ('selected',self.switch_images[1]),sticky='')
        style.layout('Switch.TCheckbutton',[('Checkbutton.padding',{'sticky':'nswe','children':[
            ('StudioToggle.indicator',{'side':'right','sticky':''}),
            ('Checkbutton.label',{'side':'left','sticky':'w'})]})])
        style.configure('Switch.TCheckbutton',background='#101827',foreground='#e5ebf5',padding=(0,5))


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
        shell=ttk.Frame(self.root,style='Shell.TFrame',padding=(20,12))
        shell.pack(fill='both',expand=True)
        header=ttk.Frame(shell,style='Shell.TFrame');header.pack(fill='x',pady=(0,10))
        header.columnconfigure(1,weight=1)
        brand=ttk.Frame(header,style='Shell.TFrame');brand.grid(row=0,column=0,sticky='w',padx=(0,14))
        ttk.Label(brand,text='DeRo / Cinematic Visualizer',style='CompactBrand.TLabel').pack(anchor='w')
        ttk.Label(brand,textvariable=self.project_name,style='ProjectName.TLabel',
                  wraplength=240,justify='left').pack(anchor='w',pady=(8,0))
        project_actions=ttk.Frame(header,style='Shell.TFrame');project_actions.grid(row=0,column=2,sticky='e',padx=(14,0))
        ttk.Label(project_actions,text='v0.1.35',style='Muted.TLabel').pack(anchor='e',pady=(0,8))
        project_buttons=ttk.Frame(project_actions,style='Shell.TFrame');project_buttons.pack(anchor='e')
        for label,command in (('New',self.new_project),('Open',self.open_project),
                              ('Save',self.save_project_file),('Save As',lambda:self.save_project_file(True))):
            ttk.Button(project_buttons,text=label,command=command,padding=(10,7)).pack(side='left',padx=(4,0))
        export_status=ttk.Frame(header,padding=(10,8))
        self.notification_frame=export_status
        export_status.grid(row=0,column=1,sticky='ew')
        export_status.columnconfigure(0,weight=1)
        self.export_strip=export_status
        status_row=ttk.Frame(export_status)
        status_row.grid(row=0,column=0,sticky='ew')
        status_row.columnconfigure(0,weight=1)
        self.status_label=ttk.Label(status_row,textvariable=self.status,style='Muted.TLabel',width=1,anchor='w')
        self.status_label.grid(row=0,column=0,sticky='ew')
        self.cancel_export_button=ttk.Button(status_row,text='Cancel',command=self.cancel_export,width=6,padding=(6,2))
        self.cancel_export_button.grid(row=0,column=1,padx=(8,0))
        self.cancel_export_button.grid_remove()
        self.view_report_button=ttk.Button(status_row,text='Details',command=self.view_export_report,width=6,padding=(6,2))
        self.view_report_button.grid(row=0,column=2,padx=(8,0))
        self.view_report_button.grid_remove()
        self.progress=ttk.Progressbar(export_status,maximum=100,mode='determinate',length=100,style='Compact.Horizontal.TProgressbar')
        self.progress.grid(row=1,column=0,sticky='ew',pady=(5,4))
        self.progress.grid_remove()
        self.export_meta_row=ttk.Frame(export_status)
        self.export_meta_row.grid(row=2,column=0,sticky='ew')
        self.export_meta_row.columnconfigure(0,weight=1)
        self.export_meta_label=ttk.Label(self.export_meta_row,textvariable=self.compact_export_text,
                                       style='Muted.TLabel',width=1,anchor='w')
        self.export_meta_label.grid(row=0,column=0,sticky='ew')
        ttk.Label(self.export_meta_row,textvariable=self.compact_device,style='Muted.TLabel').grid(row=0,column=1,padx=(8,0))
        self.export_meta_row.grid_remove()
        export_status.bind('<Configure>',lambda event:self.update_export_strip())
        body=tk.PanedWindow(shell,orient='horizontal',background='#0b101a',borderwidth=0,
                            sashwidth=5,sashpad=0,showhandle=False,
                            sashcursor='sb_h_double_arrow',opaqueresize=True)
        body.pack(fill='both',expand=True)
        sidebar=ttk.Frame(body,padding=(8,14),width=420)
        body.add(sidebar,minsize=360,width=420,stretch='never')
        rail=ttk.Frame(sidebar,style='Shell.TFrame',padding=(0,0,8,0))
        rail.grid(row=0,column=0,sticky='ns')
        sidebar.columnconfigure(1,weight=1)
        # Scroll the inspector on smaller screens and with large system fonts.
        inspector=tk.Canvas(sidebar,background='#101827',highlightthickness=0,width=254)
        scroll=ttk.Scrollbar(sidebar,orient='vertical',command=inspector.yview,style='Studio.Vertical.TScrollbar')
        inspector.configure(yscrollcommand=scroll.set)
        inspector.grid(row=0,column=1,sticky='nsew');scroll.grid(row=0,column=2,sticky='ns')
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

        content_root=controls
        self.inspector_pages={}
        self.navigation_buttons={}
        def section(text):
            nonlocal controls
            name={'01  /  SOURCE':'Audio','BACKDROP':'Backdrop','02  /  TITLE & LAYOUT':'Text',
                  '03  /  SPECTRUM':'Visualizer','04  /  ATMOSPHERE':'Elements','05  /  OUTPUT':'Output','SEPARATION':'Separation'}[text]
            controls=ttk.Frame(content_root,padding=(10,4,10,14))
            self.inspector_pages[name]=controls
            if name not in ('Audio','Separation'):
                ttk.Label(controls,text=name,style='Heading.TLabel').pack(anchor='w',pady=(5,8))
                ttk.Button(controls,text='Reset this panel',command=lambda n=name:self.reset_panel(n)).pack(fill='x',pady=(0,12))
            button=ttk.Button(rail,text='Song' if name=='Audio' else name,width=9,padding=(6,18),command=lambda n=name:self.show_inspector(n))
            button.pack(fill='x',pady=(0,8))
            self.navigation_buttons[name]=button
        def field(label,var,values=None):
            ttk.Label(controls,text=label,style='Muted.TLabel').pack(anchor='w',pady=(7,5))
            widget=(ttk.Combobox(controls,textvariable=var,values=values,state='readonly')
                    if values else ttk.Entry(controls,textvariable=var))
            widget.pack(fill='x')
            return widget
        section('01  /  SOURCE')
        ttk.Label(controls,text='Song information',style='Section.TLabel').pack(anchor='w',pady=(4,8))
        ttk.Button(controls,text='Browse audio...',style='Music.TButton',command=self.browse_audio).pack(fill='x',pady=(0,10))
        self.song_title_entry=field('Song title',self.title)
        self.artist_name_entry=field('Artist name',self.artist)
        field('Audio path',self.audio)
        field('Song language',self.song_language,('Auto Detect','English','Spanish / Español'))
        ttk.Button(controls,text='Retrieve artist and song metadata',command=self.retrieve_audio_metadata).pack(fill='x',pady=(12,5))
        ttk.Button(controls,text='Review song information',command=self.review_current_song).pack(fill='x',pady=(0,5))
        self.find_song_button=ttk.Button(controls,text='Find artist and song online',command=self.find_artist_and_song)
        self.find_song_button.pack(fill='x')
        section('SEPARATION')
        ttk.Label(controls,text='Vocal separation',style='Section.TLabel').pack(anchor='w',pady=(4,8))
        field('Model',self.demucs_model,tuple(MODELS))
        self.start_separation_button=ttk.Button(controls,text='Separate song with Demucs',style='Music.TButton',command=self.start_separation)
        self.start_separation_button.pack(fill='x',pady=(10,5))
        self.cancel_separation_button=ttk.Button(controls,text='Cancel separation',command=self.cancel_separation,state='disabled')
        self.cancel_separation_button.pack(fill='x')
        ttk.Button(controls,text='Separation setup...',command=self.show_separation_setup).pack(fill='x',pady=(5,0))
        field('Instrumental track',self.instrumental)
        ttk.Button(controls,text='Browse instrumental...',command=lambda:self.browse_stem('instrumental')).pack(fill='x',pady=(5,6))
        field('Vocal track',self.vocals)
        ttk.Button(controls,text='Browse vocals...',command=lambda:self.browse_stem('vocals')).pack(fill='x',pady=(5,6))
        self.audio_track_selector=field('Preview and export audio',self.audio_track,('Original mix','Instrumental','Vocals','Stem mix'))
        field('Instrumental level (%)',self.instrumental_gain)
        field('Vocal level (%)',self.vocal_gain)
        self.audio_track_selector.bind('<<ComboboxSelected>>',lambda event:self.prepare_preview())
        section('BACKDROP')
        field('Background image / optional',self.background)
        ttk.Button(controls,text='Choose background...',style='Image.TButton',command=self.browse_background).pack(fill='x',pady=(6,2))
        ttk.Button(controls,text='Use default backdrop',command=lambda:self.reset_background()).pack(fill='x',pady=6)
        section('02  /  TITLE & LAYOUT')
        ttk.Label(controls,text='Song text appearance',style='Section.TLabel').pack(anchor='w',pady=(8,0))
        field('Typeface',self.title_font,('Sans','Serif','Mono'))
        styles=ttk.Frame(controls);styles.pack(fill='x',pady=8)
        for label,var in (('Bold',self.title_bold),('Italic',self.title_italic),('Caps',self.title_uppercase)):
            ttk.Checkbutton(styles,text=label,variable=var).pack(fill='x',pady=2)
        ttk.Button(controls,text='Title color...',command=self.choose_title_color).pack(fill='x')
        def numeric(label,var,low,high,step=1):
            row=ttk.Frame(controls);row.pack(fill='x',pady=(9,0))
            ttk.Label(row,text=label,style='Muted.TLabel',wraplength=145).pack(side='left')
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
        ttk.Label(controls,text='Artist text appearance',style='Section.TLabel').pack(anchor='w',pady=(16,0))
        field('Artist typeface',self.artist_font,('Sans','Serif','Mono'))
        artist_styles=ttk.Frame(controls);artist_styles.pack(fill='x',pady=8)
        for label,var in (('Bold',self.artist_bold),('Italic',self.artist_italic),('Caps',self.artist_uppercase)):
            ttk.Checkbutton(artist_styles,text=label,variable=var).pack(fill='x',pady=2)
        ttk.Button(controls,text='Artist color...',command=lambda:self.choose_title_color('artist')).pack(fill='x')
        numeric('Artist size (% height)',self.artist_size,.5,12,.1)
        numeric('Artist X (%)',self.artist_x,0,100)
        numeric('Artist Y (%)',self.artist_y,0,100)
        arrows('artist')
        ttk.Button(controls,text='Reset artist layout',command=lambda:self.reset_layout('artist')).pack(fill='x',pady=(7,0))
        section('03  /  SPECTRUM')
        field('Peak shape',self.spectrum_mapping,('Stepped','Balanced','Smooth'))
        ttk.Label(controls,text='Stepped = previous look / Smooth = current look / Balanced = in between',style='Muted.TLabel',wraplength=240).pack(anchor='w',pady=5)
        field('Appearance',self.spectrum_style,('Classic bars','Gradient bars','Glow bars','Reflected bars','Filled spectrum'))
        ttk.Checkbutton(controls,text='Mirror around center',style='Switch.TCheckbutton',variable=self.spectrum_mirrored).pack(fill='x',pady=6)
        numeric('Analysis bands',self.bands,16,2048,16)
        band_buttons=ttk.Frame(controls);band_buttons.pack(fill='x',pady=6)
        ttk.Button(band_buttons,text='Fewer bands',command=lambda:self.adjust_bands(-32)).pack(side='left',fill='x',expand=True)
        ttk.Button(band_buttons,text='More bands',command=lambda:self.adjust_bands(32)).pack(side='left',fill='x',expand=True)
        ttk.Label(controls,text='More bands = finer analysis; not always more independent detail.',style='Muted.TLabel',wraplength=240).pack(anchor='w',pady=4)
        numeric('Bar density (%)',self.spectrum_density,25,200,5)
        ttk.Label(controls,textvariable=self.spectrum_summary,style='Section.TLabel',wraplength=240).pack(anchor='w',pady=6)
        ttk.Label(controls,text='Draw fewer or more bars from the same analyzed frequencies.',style='Muted.TLabel',wraplength=240).pack(anchor='w',pady=4)
        numeric('Bar thickness (%)',self.spectrum_fill,10,100,5)
        ttk.Label(controls,text='Thin = wider gaps; thick = tightly packed. Filled style ignores gaps.',style='Muted.TLabel',wraplength=240).pack(anchor='w',pady=4)
        field('Frequency spacing',self.frequency_scale,('Logarithmic','Linear'))
        numeric('Minimum frequency (Hz)',self.frequency_min,20,19999,10)
        numeric('Maximum frequency (Hz)',self.frequency_max,21,20000,100)
        preset=tk.StringVar(value='Choose a frequency preset')
        self.frequency_preset_var=preset
        preset_row=ttk.Frame(controls);preset_row.pack(fill='x',pady=8)
        selector=ttk.Combobox(preset_row,textvariable=preset,state='readonly',values=('Original range','Whole spectrum','Bass','Vocals / Midrange','Treble'))
        ttk.Button(preset_row,text='Reset',width=5,padding=(4,5),command=self.reset_frequency_controls).pack(side='right',padx=(5,0))
        selector.pack(side='left',fill='x',expand=True)
        selector.bind('<<ComboboxSelected>>',lambda event:self.set_frequency_preset(preset.get()))
        ttk.Label(controls,text='Band/range changes reanalyze music automatically. Original: 50–10,584 Hz.',style='Muted.TLabel',wraplength=240).pack(anchor='w',pady=4)
        ttk.Button(controls,text='Gradient end color...',command=lambda:self.choose_element_color('spectrum_color_end')).pack(fill='x',pady=6)
        ttk.Button(controls,text='Spectrum color...',command=lambda:self.choose_element_color('spectrum_color')).pack(fill='x',pady=8)
        numeric('Spectrum sensitivity (x)',self.spectrum_gain,.1,3,.1)
        ttk.Label(controls,text='Lower = shorter bars',style='Muted.TLabel').pack(anchor='w',pady=(5,0))
        gain_buttons=ttk.Frame(controls);gain_buttons.pack(fill='x',pady=(7,0))
        for label,value in (('Lower',.5),('Normal',1.),('Higher',1.5)):
            ttk.Button(gain_buttons,text=label,width=6,command=lambda v=value:self.spectrum_gain.set(v)).pack(side='left',fill='x',expand=True,padx=1)
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
        ttk.Label(controls,text='PARTICLES',style='Section.TLabel').pack(anchor='w',pady=(0,8))
        ttk.Checkbutton(controls,text='Show particles',style='Switch.TCheckbutton',variable=self.particles_enabled).pack(anchor='w')
        ttk.Checkbutton(controls,text='Continuous particles',style='Switch.TCheckbutton',variable=self.particle_continuous).pack(anchor='w',pady=6)
        ttk.Label(controls,text='On: new particles fade in as others leave. Off: original non-recycling motion.',style='Muted.TLabel',wraplength=240).pack(anchor='w',pady=4)
        field('Beat source',self.particle_reactivity,('Bass','Vocals / Midrange','Treble','Displayed range'))
        ttk.Label(controls,text='Uses frequencies inside the selected Visualizer range. Presets set this to Displayed range.',style='Muted.TLabel',wraplength=240).pack(anchor='w',pady=5)
        field('Direction',self.particle_direction,('Out','Left','Right','Up','Down'))
        ttk.Checkbutton(controls,text='React to music',style='Switch.TCheckbutton',variable=self.particle_reactive).pack(anchor='w',pady=8)
        ttk.Button(controls,text='Particle color...',command=lambda:self.choose_element_color('particle_color')).pack(fill='x')
        numeric('Particle speed (x)',self.particle_speed,.1,30,.1)
        for label,var,low,high,step in (('Dust particles',self.dust,0,800,1),
                ('Reactive particles (%)',self.reactive,0,100,1),('Particle response (x)',self.sensitivity,.1,3,.1)):
            row=ttk.Frame(controls);row.pack(fill='x',pady=(12,0))
            ttk.Label(row,text=label,style='Muted.TLabel',wraplength=145).pack(side='left')
            ttk.Spinbox(row,from_=low,to=high,increment=step,textvariable=var,width=6).pack(side='right')
        ttk.Button(controls,text='What do these controls do?',command=self.explain_particles).pack(fill='x',pady=(12,0))
        ttk.Separator(controls).pack(fill='x',pady=18)
        ttk.Label(controls,text='IMAGE / LOGO',style='Section.TLabel').pack(anchor='w',pady=(0,8))
        ttk.Button(controls,text='+ Add image...',style='Image.TButton',command=self.browse_overlay).pack(fill='x')
        ttk.Checkbutton(controls,text='Show image',style='Switch.TCheckbutton',variable=self.overlay_enabled).pack(anchor='w',pady=8)
        field('Image file',self.overlay_path)
        field('Shape',self.overlay_shape,('Original','Circle'))
        numeric('Image width (%)',self.overlay_size,1,100)
        numeric('Opacity (%)',self.overlay_opacity,0,100)
        numeric('Image X (%)',self.overlay_x,0,100)
        numeric('Image Y (%)',self.overlay_y,0,100)
        arrows('overlay')
        ttk.Button(controls,text='Remove image',command=self.remove_overlay).pack(fill='x',pady=(10,0))
        section('05  /  OUTPUT')
        field('Resolution',self.res,('1920 x 1080','1280 x 720','854 x 480'))
        field('Frames per second',self.fps,(60,30))
        field('Video encoder',self.export_encoder,ENCODER_CHOICES)
        ttk.Label(controls,textvariable=self.encoder_status,style='Muted.TLabel',wraplength=240).pack(anchor='w',pady=5)
        ttk.Label(controls,text='GPU accelerates MP4 encoding. Preview and visual rendering use CPU.',style='Muted.TLabel',wraplength=240).pack(anchor='w',pady=4)
        ttk.Checkbutton(controls,text='Completion tone',style='Switch.TCheckbutton',variable=self.completion_sound).pack(anchor='w',pady=(10,0))
        ttk.Checkbutton(controls,text='Open video after export',style='Switch.TCheckbutton',variable=self.auto_open_export).pack(anchor='w',pady=(6,0))
        ttk.Button(controls,text='Test completion chime',command=self.play_completion_chime).pack(fill='x',pady=6)
        ttk.Button(controls,text='Quick test / 480p / 30 FPS',command=self.quick_test_preset).pack(fill='x',pady=(10,0))

        self.inspector_canvas=inspector
        self.show_inspector('Audio')
        workspace=ttk.Frame(body,style='Shell.TFrame');body.add(workspace,minsize=620,stretch='always')
        workspace.columnconfigure(0,weight=1);workspace.rowconfigure(0,weight=1)
        preview=ttk.Frame(workspace,padding=16);preview.grid(row=0,column=0,sticky='nsew')
        preview.columnconfigure(0,weight=1);preview.rowconfigure(1,weight=1)
        toolbar=ttk.Frame(preview);toolbar.grid(row=0,column=0,sticky='ew',pady=(0,12))
        ttk.Label(toolbar,text='Scene preview',style='Heading.TLabel').pack(side='left')
        ttk.Button(toolbar,text='Save PNG',command=self.save_preview).pack(side='right')
        ttk.Button(toolbar,text='Refresh preview',command=self.prepare_preview).pack(side='right',padx=8)
        ttk.Button(toolbar,text='Fullscreen',command=self.open_fullscreen_preview).pack(side='right')
        self.root.bind('<F11>',lambda event:self.open_fullscreen_preview())
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
        self.scrub.bind('<Button-1>',self.timeline_click)
        self.scrub.bind('<B1-Motion>',self.timeline_click)
        ttk.Checkbutton(transport,text='Sound on',style='Switch.TCheckbutton',variable=self.sound_enabled,command=self.toggle_sound).pack(side='right')

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
        ttk.Button(times,text='Export MP4',style='Accent.TButton',command=self.export_file).pack(side='right')
        ttk.Button(times,text='Open export folder',command=self.open_export_folder).pack(side='right',padx=(8,8))
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
        self.build_song_workspaces(workspace)
        self.build_karaoke(workspace)

    def build_song_workspaces(self,workspace):
        self.song_workspace=ttk.Frame(workspace,padding=20)
        ttk.Label(self.song_workspace,text='Import song',style='Heading.TLabel').pack(anchor='w')
        ttk.Label(self.song_workspace,text='Browse audio, review its names, then begin a fresh project and separate vocals automatically.',
                  style='Muted.TLabel',wraplength=560).pack(anchor='w',pady=(6,20))
        ttk.Label(self.song_workspace,text='PROJECT OVERVIEW',style='Section.TLabel').pack(anchor='w')
        ttk.Label(self.song_workspace,textvariable=self.song_overview,wraplength=560).pack(anchor='w',pady=(12,8))
        ttk.Label(self.song_workspace,textvariable=self.song_workflow_status,style='Muted.TLabel',wraplength=560).pack(anchor='w',pady=(0,14))
        for label in ('01  Import song','02  Separate vocals','03  Paste exact lyrics',
                      '04  Align and review words','05  Design cinematic lyrics','06  Preview and export MP4'):
            ttk.Label(self.song_workspace,text=label,padding=(12,9)).pack(fill='x',pady=3)
        ttk.Button(self.song_workspace,text='Open visualizer preview',command=self.open_visualizer_preview).pack(anchor='w',pady=(16,0))
        self.separation_workspace=ttk.Frame(workspace,padding=20)
        ttk.Label(self.separation_workspace,text='Vocal separation',style='Heading.TLabel').pack(anchor='w')
        ttk.Label(self.separation_workspace,textvariable=self.separation_status,wraplength=560).pack(anchor='w',pady=(12,8))
        ttk.Label(self.separation_workspace,textvariable=self.separation_elapsed,style='Muted.TLabel').pack(anchor='w',pady=(0,8))
        self.separation_progress=ttk.Progressbar(self.separation_workspace,mode='indeterminate')
        self.separation_progress.pack(fill='x',pady=(0,12))
        ttk.Label(self.separation_workspace,text='Processing details',style='Section.TLabel').pack(anchor='w',pady=(0,8))
        log_frame=ttk.Frame(self.separation_workspace);log_frame.pack(fill='both',expand=True)
        self.separation_log=tk.Text(log_frame,wrap='word',height=12,background='#080e19',foreground='#c9d7eb',state='disabled')
        log_scroll=ttk.Scrollbar(log_frame,command=self.separation_log.yview)
        self.separation_log.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side='right',fill='y');self.separation_log.pack(fill='both',expand=True)
        ttk.Button(self.separation_workspace,text='Open visualizer preview',command=self.open_visualizer_preview).pack(anchor='w',pady=(12,0))
        for variable in (self.audio_track,self.instrumental_gain,self.vocal_gain):variable.trace_add('write',self.schedule_layout_preview)
        self.show_inspector('Audio')

    def play_completion_chime(self):
        completion_tone(on_error=lambda error:self.q.put(('tone_error',error)))

    def notification_state(self,success=False):
        self.notification_frame.configure(style='TFrame')
        self.status_label.configure(style='CompactSuccess.TLabel' if success else 'Muted.TLabel')

    def update_export_strip(self):
        if not hasattr(self,'export_meta_label'):return
        active=self.export_control is not None
        has_report=self.last_export_report is not None
        if active or has_report:
            self.progress.grid()
            self.export_meta_row.grid()
        else:
            self.progress.grid_remove()
            self.export_meta_row.grid_remove()
        if active:
            self.cancel_export_button.grid()
            self.view_report_button.grid_remove()
            elapsed=self.export_time.get().partition(': ')[2]
            remaining=self.export_remaining.get().partition(': ')[2]
            remaining=remaining.split(' (estimate')[0]
            remaining=('finalizing...' if remaining.startswith('finalizing') else remaining)
            narrow=self.export_strip.winfo_width()<430
            if self.cancel_requested:text='Canceling · '+elapsed
            elif narrow:text=elapsed+' · '+remaining+(' left' if remaining.startswith('~') else '')
            else:text='Elapsed '+elapsed+' · '+('Left '+remaining if remaining.startswith('~') else remaining)
        elif has_report:
            self.cancel_export_button.grid_remove()
            self.view_report_button.grid()
            duration=self.export_time.get().partition(': ')[2]
            state={'success':'Completed in','canceled':'Canceled after','failed':'Failed after'}.get(self.export_outcome,'Export time')
            text=state+' '+duration
        else:
            self.cancel_export_button.grid_remove()
            self.view_report_button.grid_remove()
            text=''
        device=self.export_device.get()
        device=('GPU' if 'GPU —' in device else 'CPU fallback' if 'CPU (fallback)' in device else
                'Checking...' if 'checking' in device else 'CPU' if 'Encoding: CPU' in device else '')
        self.compact_export_text.set(text)
        self.compact_device.set(device)

    def reset_frequency_controls(self):
        for key in ('frequency_min','frequency_max','frequency_scale','particle_reactivity'):self.reset_setting(key)
        self.frequency_preset_var.set('Original range')

    def reset_setting(self,key):
        if key in ('title','artist'):
            value=self.reset_text_defaults.get(key,'')
        else:value=DEFAULTS[key]
        # Keep a valid frequency range when resetting one dependent endpoint.
        if key=='frequency_min':
            try:
                if self.frequency_max.get()<=value:self.frequency_max.set(DEFAULTS['frequency_max'])
            except (ValueError,tk.TclError):self.frequency_max.set(DEFAULTS['frequency_max'])
        if key=='frequency_max':
            try:
                if self.frequency_min.get()>=value:self.frequency_min.set(DEFAULTS['frequency_min'])
            except (ValueError,tk.TclError):self.frequency_min.set(DEFAULTS['frequency_min'])
        self.project_vars[key].set(value)
        if key=='preview_sound':self.toggle_sound()
        self.schedule_layout_preview()

    def panel_setting_keys(self,name):
        keys=[key for key in DEFAULTS if key not in ('audio','background','overlay_path')]
        if name=='Audio':return ['preview_sound']
        if name=='Backdrop':return []
        if name=='Text':return [key for key in keys if key.startswith(('title','artist'))]
        if name=='Visualizer':return [key for key in keys if key.startswith(('spectrum_','frequency_')) or key=='bands']
        if name=='Elements':return [key for key in keys if key.startswith(('particle','overlay_')) or key in ('dust','reactive','sensitivity')]
        return ['res','fps','export_encoder','completion_sound','auto_open_export']

    def reset_panel(self,name):
        keys=self.panel_setting_keys(name)
        if not keys:
            self.status.set('Backdrop has a file selection only. Use default backdrop to remove the image.')
            return
        for key in keys:
            if key not in ('title','artist'):self.reset_setting(key)
        self.status.set(name+' settings restored to defaults. Selected files and song names kept.')

    def reset_all_settings(self):
        if not messagebox.askyesno('Reset all settings',
            'Restore all appearance, particle, playback, and output settings to defaults?\n\n'
            'Your selected files, song/artist names, project path, and export range will be kept.',parent=self.root):return
        for key in DEFAULTS:
            if key not in ('audio','background','overlay_path','title','artist','instrumental','vocals','song_language'):self.reset_setting(key)
        self.status.set('All settings restored to defaults. Files, song names, and selection kept.')

    def install_reset_controls(self):
        variables={str(var):key for key,var in self.project_vars.items()}
        skip={'audio','background','overlay_path','title','artist','song_language','demucs_model','instrumental','vocals','audio_track'}
        colors={'Title color...':'title_color','Artist color...':'artist_color',
            'Spectrum color...':'spectrum_color','Gradient end color...':'spectrum_color_end','Particle color...':'particle_color'}
        def walk(parent):
            for widget in parent.winfo_children():
                yield widget
                yield from walk(widget)
        for widget in list(walk(self.root)):
            key=None
            if isinstance(widget,(ttk.Entry,ttk.Combobox,ttk.Spinbox)):
                key=variables.get(str(widget.cget('textvariable')))
            elif isinstance(widget,ttk.Checkbutton):key=variables.get(str(widget.cget('variable')))
            elif isinstance(widget,ttk.Button):key=colors.get(str(widget.cget('text')))
            if key is None or key in skip or widget.winfo_manager()!='pack':continue
            info=widget.pack_info();parent=info.pop('in')
            row=ttk.Frame(parent)
            row.pack(before=widget,**info)
            options={name:values[-1] for name,values in widget.configure().items() if name!='class'}
            bindings={sequence:widget.bind(sequence) for sequence in widget.bind()}
            widget.pack_forget()
            # Recreate the visible control with the row as its actual parent.
            # Retain the hidden original so its registered Tcl callbacks remain valid.
            replacement=type(widget)(row,**options)
            for sequence,script in bindings.items():replacement.bind(sequence,script)
            reset=ttk.Button(row,text='Reset',width=5,padding=(4,5),command=lambda k=key:self.reset_setting(k))
            reset.pack(side='right',padx=(5,0))
            replacement.pack(side='left',fill='x',expand=True)
            self.reset_buttons.setdefault(key,[]).append(reset)
        ttk.Button(self.inspector_canvas.master,text='Reset all settings',command=self.reset_all_settings).grid(
            row=1,column=0,columnspan=3,sticky='ew',pady=(10,0))

    def adjust_bands(self,delta):
        try:self.bands.set(max(16,min(2048,self.bands.get()+delta)))
        except (ValueError,tk.TclError):self.status.set('Enter a band count from 16 to 2048.')

    def set_frequency_preset(self,name):
        low,high={'Original range':(50,10584),'Whole spectrum':(20,20000),
                  'Bass':(20,250),'Vocals / Midrange':(250,4000),'Treble':(4000,20000)}[name]
        self.frequency_min.set(low);self.frequency_max.set(high)
        self.particle_reactivity.set('Displayed range')

    def explain_particles(self):
        messagebox.showinfo('Particle controls',
            'Particle speed (0.1–30x): multiplies how fast every particle moves. '
            '1x is the original speed; 10x is ten times faster.\n\n'
            'Dust particles (0–800): number of particles that start in the scene.\n\n'
            'Reactive particles (0–100%): approximate share that reacts to music; '
            'the rest drift normally.\n\n'
            'Particle response (0.1–3x): strength of beat-driven movement, size, '
            'and brightness for the reactive particles. React to music must be on.\n\n'
            'Continuous particles replaces departing particles with fresh ones that fade in. '
            'Turn it off for the original non-recycling behavior.',parent=self.root)

    def show_inspector(self,name):
        for key,page in self.inspector_pages.items():
            page.pack_forget()
            self.navigation_buttons[key].configure(style='Accent.TButton' if key==name else 'TButton')
        self.inspector_pages[name].pack(fill='both',expand=True)
        self.inspector_canvas.yview_moveto(0)
        self.inspector_canvas.after_idle(lambda:self.inspector_canvas.configure(scrollregion=self.inspector_canvas.bbox('all')))

        if hasattr(self,'song_workspace'):
            for overlay in (self.song_workspace,self.separation_workspace,*getattr(self,'karaoke_overlays',{}).values()):overlay.place_forget()
            overlay=self.song_workspace if name=='Audio' else self.separation_workspace if name=='Separation' else getattr(self,'karaoke_overlays',{}).get(name)
            if overlay is not None:
                overlay.place(relx=0,rely=0,relwidth=1,relheight=1)
                overlay.tkraise()

    def reset_background(self):
        self.background.set('')
        if self.renderer is not None:
            self.renderer.s.background=''
            self.renderer.base=self.renderer._background()
            self.display_frame()

    def choose_element_color(self,key):
        var=self.project_vars[key]
        color=colorchooser.askcolor(color=var.get(),parent=self.root,title='Element color')[1]
        if color:var.set(color)

    def browse_overlay(self):
        path=filedialog.askopenfilename(filetypes=[('Images','*.png *.jpg *.jpeg *.webp *.bmp')])
        if not path:return
        try:
            with Image.open(path) as image:image.verify()
        except (OSError,ValueError) as exc:
            messagebox.showerror('Could not load image',str(exc));return
        self.overlay_path.set(path)
        self.overlay_enabled.set(True)
        self.show_inspector('Elements')

    def remove_overlay(self):
        self.overlay_enabled.set(False)
        self.overlay_path.set('')

    def schedule_layout_preview(self,*args):
        if self.layout_job is not None:self.root.after_cancel(self.layout_job)
        self.layout_job=self.root.after(100,self.apply_layout_preview)

    def apply_layout_preview(self):
        self.layout_job=None
        try:
            count=max(8,min(4096,round(self.bands.get()*self.spectrum_density.get()/100)))
            if self.spectrum_mirrored.get():
                count=max(8,count//2*2)
                summary=f'{count} visible bars / {count//2} per side'
            else:summary=f'{count} visible bars / bass left, treble right'
            self.spectrum_summary.set(summary)
        except (ValueError,tk.TclError):pass
        if self.renderer is None:return
        try:
            if self.loaded_audio_path!=self.active_audio_path():
                if not self.busy:self.prepare_preview()
                return
            values=validate_settings({key:var.get() for key,var in self.project_vars.items()})
            if any(getattr(self.renderer.s,target)!=values[source] for target,source in
                   (('fps','fps'),('bars','bands'),('frequency_min','frequency_min'),('frequency_max','frequency_max'),('frequency_scale','frequency_scale'),('spectrum_mapping','spectrum_mapping'))):
                if not self.busy:self.prepare_preview()
                return
            for key in ('title','title_font','title_bold','title_italic','title_uppercase','title_color',
                        'artist','artist_font','artist_bold','artist_italic','artist_uppercase','artist_color','spectrum_gain','particle_color','spectrum_color',
                        'overlay_enabled','overlay_path','overlay_shape','spectrum_style','spectrum_mirrored','spectrum_color_end'):
                setattr(self.renderer.s,key,values[key])
            for key in ('title_size','title_x','title_y','artist_size','artist_x','artist_y','spectrum_width','spectrum_x','spectrum_y','spectrum_height','overlay_size','overlay_x','overlay_y','overlay_opacity','spectrum_density','spectrum_fill'):
                setattr(self.renderer.s,key,values[key]/100)
            particle_values={'particles_enabled':values['particles_enabled'],'particle_continuous':values['particle_continuous'],'particle_speed':values['particle_speed'],'particle_direction':values['particle_direction'],
                'particle_reactive':values['particle_reactive'],'particle_reactivity':values['particle_reactivity'],'dust_count':values['dust'],
                'reactive_fraction':values['reactive']/100,'sensitivity':values['sensitivity']}
            changed=any(getattr(self.renderer.s,key)!=value for key,value in particle_values.items())
            if changed:
                self.request_particle_preview(particle_values)
            elif self.particle_request is not None:
                self.particle_generation+=1
                self.particle_request=None
                if self.particle_future is not None:self.particle_future.cancel()
            self.display_frame()
        except (ValueError,OSError,tk.TclError) as exc:self.status.set(str(exc))

    def request_particle_preview(self, values):
        source=self.renderer
        request=(id(source),tuple(values.items()))
        if request==self.particle_request:return
        self.particle_request=request
        self.particle_generation+=1
        generation=self.particle_generation
        if self.particle_future is not None:self.particle_future.cancel()
        # Only copied settings and read-only features cross the worker boundary.
        settings=replace(source.s,**values)
        features=self.features
        future=self.particle_executor.submit(Renderer,settings,features)
        self.particle_future=future
        def completed(result):
            if result.cancelled():return
            try:self.q.put(('particles_ready',(generation,source,result.result(),None)))
            except Exception as exc:self.q.put(('particles_ready',(generation,source,None,str(exc))))
        future.add_done_callback(completed)

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
        keys=tuple(target+'_'+key for key in ('x','y','size')) if target in ('title','artist') else ('spectrum_x','spectrum_y','spectrum_width','spectrum_height')
        for key in keys:self.project_vars[key].set(DEFAULTS[key])

    def choose_title_color(self,row='title'):
        var=self.project_vars[row+'_color']
        color=colorchooser.askcolor(color=var.get(),parent=self.root,title='Text color')[1]
        if color:var.set(color)

    def filename_stem(self):
        return suggested_name(self.artist.get(),self.title.get())

    def project_state(self):
        values=validate_settings({key:var.get() for key,var in self.project_vars.items()})
        end=self.selection_end.get()
        return values,[self.selection_start.get(),end if end>0 else None]

    def confirm_replace(self):
        if self.busy:
            messagebox.showinfo('Please wait','Wait for the current analysis or export to finish.');return False
        try:changed=(self.project_state()!=self.saved_project_state or self.lyric_document.snapshot()!=self.saved_lyrics or self.lyrics_editor.get('1.0','end-1c')!=self.lyric_document.text)
        except (ValueError,tk.TclError):changed=True
        if not changed:return True
        answer=messagebox.askyesnocancel('Unsaved project','Save your changes before continuing?')
        if answer is None:return False
        return self.save_project_file() if answer else True

    def update_project_title(self):
        name=os.path.basename(self.project_path) if self.project_path else self.filename_stem()
        display_name=os.path.splitext(name)[0] if self.project_path else name
        self.project_name.set(display_name if display_name!='Untitled' else 'Untitled project')
        if hasattr(self,'song_overview'):
            title=self.title.get().strip();artist=self.artist.get().strip()
            self.song_overview.set(title+'\n'+(artist or 'Artist not provided') if title else 'No song loaded')
        self.root.title(f'{name} - DeRo Cinematic Visualizer v0.1.35 - Karaoke Workspaces')

    def clear_media(self):
        self.reset_karaoke()
        self.song_import_generation+=1
        self.particle_generation+=1;self.particle_request=None
        if self.particle_future is not None:self.particle_future.cancel()
        self.invalidate_song_lookup()
        self.pause()
        self.preview_player.load(None)
        self.preview_audio=None
        self.samples=None;self.features=None;self.renderer=None;self.preview_frame=None
        self.loaded_audio_path=None;self.length=0;self.position.set(0)
        self.selection_start.set(0);self.selection_end.set(0)
        self.pending_selection=None
        self.metadata_pending_path=None
        self.scrub.configure(to=0);self.progress['value']=0
        self.canvas.configure(image='',text='YOUR NEXT VISUAL STARTS HERE\n\nChoose music to bring this scene to life.')
        if self.fullscreen_canvas is not None:
            self.fullscreen_canvas.configure(image='',text='Choose music to preview.')
        self.update_selection()
        self.last_export_path=None
        self.song_workflow_status.set('Choose a song to begin.')
        self.separation_status.set('Ready — choose a song or import existing stems.')
        self.separation_elapsed.set('Elapsed: 00:00:00 · Total: —')
        self.separation_progress.stop();self.separation_progress.configure(mode='determinate',value=0)
        self.notification_state()

    def new_project(self):
        if not self.confirm_replace():return
        self.clear_media()
        for key,value in DEFAULTS.items():self.project_vars[key].set(value)
        self.project_path=None
        self.reset_text_defaults={'title':'','artist':''}
        self.saved_project_state=self.project_state()
        self.saved_lyrics=self.lyric_document.snapshot()
        self.update_project_title()
        self.status.set('New project. All composition settings restored to defaults.')

    def save_project_file(self,save_as=False):
        if self.busy:
            messagebox.showinfo('Please wait','Wait for the current analysis or export to finish.');return False
        try:
            values,selection=self.project_state()
            path=self.project_path
            if save_as or not path:
                path=filedialog.asksaveasfilename(initialdir=self._browse_initial_folder('project',self.project_path or ''),defaultextension='.dero',filetypes=[('DeRo project','*.dero')],
                    initialfile=self.filename_stem()+'.dero')
            if not path:return False
            if self.lyrics_editor.get('1.0','end-1c')!=self.lyric_document.text:
                messagebox.showinfo('Apply lyric edits','Apply the lyric edits before saving the project.');return False
            save_project(path,values,*selection,lyrics=self.lyric_document.snapshot())
            self.project_path=os.path.abspath(path)
            self._remember_folder('project',path)
            self.saved_project_state=self.project_state()
            self.saved_lyrics=self.lyric_document.snapshot()
            self.update_project_title()
            self.status.set('Project saved: '+self.project_path)
            return True
        except (OSError,ValueError,tk.TclError) as exc:
            messagebox.showerror('Could not save project',str(exc));return False

    def open_project(self):
        if not self.confirm_replace():return
        path=filedialog.askopenfilename(initialdir=self._browse_initial_folder('project',self.project_path or ''),filetypes=[('DeRo project','*.dero'),('JSON project','*.json')])
        if not path:return
        try:values,selection,lyrics=load_project_full(path)
        except (OSError,ValueError) as exc:
            messagebox.showerror('Could not open project',str(exc));return
        self._remember_folder('project',path)
        self.clear_media()
        self.lyric_document=lyrics;self.refresh_lyrics()
        for key,value in values.items():self.project_vars[key].set(value)
        self.project_path=os.path.abspath(path) if path.lower().endswith('.dero') else None
        self.reset_text_defaults={key:values[key] for key in ('title','artist')}
        self.selection_start.set(selection[0]);self.selection_end.set(selection[1] or 0)
        self.pending_selection=selection
        self.saved_project_state=self.project_state()
        self.saved_lyrics=self.lyric_document.snapshot()
        self.update_project_title()
        self.song_workflow_status.set('Project loaded. Review its audio and stem paths before continuing.')
        missing=[key for key in ('audio','background','overlay_path') if values[key] and (key!='overlay_path' or values['overlay_enabled']) and not os.path.isfile(values[key])]
        if missing:
            self.status.set('Project opened. Missing media: '+', '.join(missing)+'. Choose replacement files in the sidebar.')
            return
        if values['audio']:self.prepare_preview()
        else:self.status.set('Project opened. Choose music to preview.')

    def close_project(self):
        if self.close_when_export_done:return
        if self.separation_control is not None:
            if messagebox.askyesno('Cancel separation and close?', 'Cancel vocal separation and close? Unsaved project changes will not be saved.',parent=self.root):
                self.close_when_export_done=True;self.cancel_separation()
            return
        if self.confirm_replace():
            if self.export_control is not None:
                self.close_when_export_done=True
                self.cancel_export()
                return
            self.destroy_application()

    def destroy_application(self):
        self.cancel_alignment();self.stop_monitor()
        self.invalidate_song_lookup()
        self.pause()
        self.close_fullscreen_preview()
        self.particle_executor.shutdown(wait=False,cancel_futures=True)
        for callback in self.root.tk.call('after','info'):
            try:self.root.after_cancel(callback)
            except tk.TclError:pass
        self.root.destroy()

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
        self.fit_fullscreen_preview()

    def open_fullscreen_preview(self):
        if self.fullscreen_window is not None:
            self.fullscreen_window.lift()
            self.fullscreen_window.focus_set()
            return
        window=tk.Toplevel(self.root)
        self.fullscreen_window=window
        window.title('DeRo / Karaoke Workspaces')
        window.configure(background='black')
        window.geometry(f'{window.winfo_screenwidth()}x{window.winfo_screenheight()}+0+0')
        window.attributes('-fullscreen',True)
        self.fullscreen_canvas=tk.Label(window,background='black',foreground='#dce8fb',
            text='Choose music to preview.',borderwidth=0)
        self.fullscreen_canvas.pack(fill='both',expand=True)
        self.fullscreen_canvas.bind('<Configure>',lambda event:self.fit_fullscreen_preview())
        ttk.Button(window,text='Exit fullscreen / Esc',command=self.close_fullscreen_preview).place(relx=1,x=-18,y=18,anchor='ne')
        ttk.Label(window,text='Space: Play / Pause   |   Esc: Exit fullscreen',style='Badge.TLabel').place(relx=.5,rely=1,y=-18,anchor='s')
        window.bind('<Escape>',lambda event:self.close_fullscreen_preview())
        window.bind('<F11>',lambda event:self.close_fullscreen_preview())
        window.bind('<space>',lambda event:self.toggle_play())
        window.protocol('WM_DELETE_WINDOW',self.close_fullscreen_preview)
        window.focus_set()
        window.after_idle(self.fit_fullscreen_preview)

    def fit_fullscreen_preview(self):
        target=self.fullscreen_canvas
        if target is None or self.preview_frame is None:return
        image=self.preview_frame
        scale=min(max(1,target.winfo_width())/image.width,max(1,target.winfo_height())/image.height)
        image=image.resize((max(1,round(image.width*scale)),max(1,round(image.height*scale))),Image.Resampling.LANCZOS)
        self.fullscreen_photo=ImageTk.PhotoImage(image)
        target.configure(image=self.fullscreen_photo,text='')

    def close_fullscreen_preview(self):
        window=self.fullscreen_window
        self.fullscreen_window=None
        self.fullscreen_canvas=None
        self.fullscreen_photo=None
        if window is not None:
            window.destroy()
            self.root.focus_set()

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
                        if key in ('music', 'background', 'export', 'project') and isinstance(val, str)}
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
        # Each file picker retains its own directory: music, background, export, project.
        choices = [self.folder_preferences.get(category, '')]
        if current_path.strip():
            choices.append(os.path.dirname(os.path.abspath(current_path.strip())))
        choices.append(os.path.expanduser('~'))
        for folder in choices:
            if folder and os.path.isdir(folder):
                return folder
        return os.getcwd()

    def browse_audio(self):
        if self.busy:
            self.status.set('Finish or cancel the current task before importing another song.')
            return
        path=filedialog.askopenfilename(initialdir=self._browse_initial_folder('music',self.audio.get()),
            filetypes=[('Audio files','*.wav *.mp3 *.flac *.m4a *.aac *.ogg *.wma'),('All files','*.*')])
        if not path or path==self.audio.get().strip():return
        self.invalidate_song_lookup()
        self.read_local_song_information(path,'import')

    def read_local_song_information(self,path,mode):
        if not os.path.isfile(path):
            self.status.set('Choose an existing music file first.');return
        self.song_import_generation+=1;generation=self.song_import_generation
        self.status.set('Reading local song information...')
        def worker():
            try:
                tags=read_metadata(path)
                file_artist,file_title=filename_names(path)
                original_title=tags['title'] or file_title
                original_artist=tags['artist'] or file_artist
                title,artist=review_names(original_title,original_artist)
                self.q.put(('local_song_information',(generation,path,mode,original_title,original_artist,title,artist)))
            except Exception as exc:self.q.put(('song_information_error',(generation,str(exc))))
        threading.Thread(target=worker,daemon=True).start()

    def retrieve_audio_metadata(self):
        self.read_local_song_information(self.audio.get().strip(),'retrieve')

    def review_current_song(self):
        path=self.audio.get().strip()
        if not os.path.isfile(path):self.status.set('Choose a music file first.');return
        title,artist=review_names(self.title.get(),self.artist.get())
        self.confirm_song_information(path,self.title.get(),self.artist.get(),title,artist,'review')

    def confirm_song_information(self,path,original_title,original_artist,title,artist,mode):
        window=tk.Toplevel(self.root);window.title('Confirm song information')
        window.transient(self.root);window.geometry('580x320');window.minsize(520,300)
        content=ttk.Frame(window,padding=18);content.pack(fill='both',expand=True)
        note=('Review the names before starting a new project and automatic vocal separation.' if mode=='import' else
              'Review or edit the song title and artist name. The original audio file is unchanged.')
        ttk.Label(content,text=note,wraplength=530).pack(anchor='w',pady=(0,12))
        song_value=tk.StringVar(value=title);artist_value=tk.StringVar(value=artist)
        ttk.Label(content,text='Song title',style='Muted.TLabel').pack(anchor='w')
        ttk.Entry(content,textvariable=song_value).pack(fill='x',pady=(4,10))
        ttk.Label(content,text='Artist name',style='Muted.TLabel').pack(anchor='w')
        ttk.Entry(content,textvariable=artist_value).pack(fill='x',pady=(4,10))
        message=tk.StringVar(value='Source: local audio tags or filename.')
        ttk.Label(content,textvariable=message,style='Muted.TLabel',wraplength=530).pack(anchor='w')
        buttons=ttk.Frame(content);buttons.pack(side='bottom',fill='x',pady=(12,0))
        def restore():song_value.set(original_title);artist_value.set(original_artist)
        def accept():
            if not song_value.get().strip():message.set('Enter a song title before continuing.');return
            if mode=='import':
                if not os.path.isfile(path):message.set('The selected audio file is no longer available.');return
                if not self.confirm_replace():return
                names=(song_value.get().strip(),artist_value.get().strip())
                window.destroy();self.import_confirmed_song(path,*names)
            else:
                self.metadata_pending_path=None
                self.title.set(song_value.get().strip());self.artist.set(artist_value.get().strip())
                self.reset_text_defaults={'title':self.title.get(),'artist':self.artist.get()}
                self.status.set('Song information updated.');window.destroy()
        def cancel():
            self.status.set('Song import canceled. The current project is unchanged.' if mode=='import' else 'Song information was left unchanged.')
            window.destroy()
        ttk.Button(buttons,text='Restore Original',command=restore).pack(side='left')
        ttk.Button(buttons,text='OK — Continue',command=accept).pack(side='right')
        ttk.Button(buttons,text='Cancel',command=cancel).pack(side='right',padx=8)
        window.protocol('WM_DELETE_WINDOW',cancel)
        window.grab_set()

    def import_confirmed_song(self,path,title,artist):
        self.busy=True # suppress track-change callbacks during the fresh-project reset
        self.clear_media()
        for key,value in DEFAULTS.items():self.project_vars[key].set(value)
        self.audio.set(path);self.title.set(title);self.artist.set(artist)
        self.project_path=None;self.saved_project_state=None
        self.reset_text_defaults={'title':title,'artist':artist}
        self.preview_cache=PreviewCache()
        self.metadata_pending_path=None
        self.song_workflow_status.set('Song imported. Starting vocal separation...')
        self._remember_folder('music',path);self.update_project_title()
        self.busy=False
        self.show_inspector('Separation')
        self.start_separation()

    def open_visualizer_preview(self):
        self.show_inspector('Text')
        if not self.busy and self.renderer is None:self.prepare_preview()

    def active_audio_path(self):
        choice=self.audio_track.get()
        if choice=='Stem mix':return mix_spec(self.instrumental.get(),self.vocals.get(),self.instrumental_gain.get(),self.vocal_gain.get())['path']
        path=(self.instrumental.get() if choice=='Instrumental' else self.vocals.get() if choice=='Vocals' else self.audio.get()).strip()
        if not path or not os.path.isfile(path):raise ValueError('The selected '+choice.lower()+' audio is missing. Choose or generate its file first.')
        return path

    def browse_stem(self,kind):
        if self.busy:self.status.set('Finish or cancel the current task first.');return
        path=filedialog.askopenfilename(filetypes=[('Audio files','*.wav *.mp3 *.flac *.m4a *.ogg'),('All files','*.*')])
        if path:
            self.project_vars[kind].set(path)
            self.separation_status.set('Existing '+('instrumental' if kind=='instrumental' else 'vocal')+' track imported.')
            self.song_workflow_status.set('Existing stems can be used for preview and export.')

    def show_separation_setup(self):
        messagebox.showinfo('Vocal separation setup',
            'Use the same Python 3.12 environment that runs DeRo Sync.\n\n'
            'If Demucs is missing, run Install_Vocal_Separation.bat beside this application. '
            'It checks your existing PyTorch installation before installing Demucs.\n\n'
            'Keep your working NVIDIA CUDA/PyTorch build. Models download on first use unless already cached.',parent=self.root)

    def start_separation(self):
        if self.busy:self.status.set('Finish or cancel the current task first.');return
        path=self.audio.get().strip()
        if not os.path.isfile(path):self.status.set('Choose a music file first.');return
        if not shutil.which('ffmpeg'):self.status.set('FFmpeg is required for vocal separation.');return
        control=ExportControl();self.separation_control=control;self.separation_started=time.monotonic()
        self.busy=True;self.pause();self.show_inspector('Separation')
        self.start_separation_button.configure(state='disabled');self.cancel_separation_button.configure(state='normal')
        self.separation_progress.configure(mode='indeterminate',value=0)
        self.separation_progress.start(12)
        self.separation_log.configure(state='normal');self.separation_log.delete('1.0','end');self.separation_log.configure(state='disabled')
        model=MODELS[self.demucs_model.get()]
        self.separation_status.set('Starting '+model+' vocal separation...')
        self.separation_elapsed.set('Elapsed: 00:00:00 · Total: running...')
        self.status.set('Separating vocals...')
        self.song_workflow_status.set('Vocal separation is running.')
        def worker():
            try:
                tracks=separate_song(path,model=model,control=control,emit=lambda text:self.q.put(('separation_log',text)))
                self.q.put(('separation_done',(path,tracks,None,False)))
            except ExportCancelled:self.q.put(('separation_done',(path,None,None,True)))
            except Exception as exc:self.q.put(('separation_done',(path,None,str(exc),False)))
        threading.Thread(target=worker,daemon=True).start()

    def cancel_separation(self):
        if self.separation_control is not None and self.separation_control.cancel():
            self.cancel_separation_button.configure(state='disabled')
            self.separation_status.set('Canceling vocal separation...')

    def invalidate_song_lookup(self):
        self.song_lookup_generation+=1
        if self.song_lookup_control is not None:self.song_lookup_control.cancel()
        self.song_lookup_control=None
        self.find_song_button.configure(state='normal',text='Find artist and song online')

    def find_artist_and_song(self):
        path=self.audio.get().strip()
        if not os.path.isfile(path):
            self.status.set('Choose a valid music file first.')
            return
        if self.song_lookup_control is not None:return
        self.song_lookup_generation+=1
        generation=self.song_lookup_generation
        control=ExportControl();self.song_lookup_control=control
        self.find_song_button.configure(state='disabled',text='Finding song information...')
        self.status.set('Reading the file tags, then searching for the artist and song...')
        def worker():
            try:
                suggestions,notice=find_names(path,cancel=control)
                self.q.put(('song_lookup',(generation,path,suggestions,notice,None)))
            except ExportCancelled:pass
            except Exception as exc:self.q.put(('song_lookup',(generation,path,[],'',str(exc))))
        threading.Thread(target=worker,daemon=True).start()

    def review_song_suggestions(self,generation,path,suggestions,notice):
        window=tk.Toplevel(self.root);window.title('Review artist and song')
        window.transient(self.root);window.geometry('720x460');window.minsize(600,440)
        content=ttk.Frame(window,padding=16);content.pack(fill='both',expand=True)
        ttk.Label(content,text='Review the names before applying them.',style='Section.TLabel').pack(anchor='w')
        ttk.Label(content,text='Search uses artist and title text only. Your audio is not uploaded.',
                  style='Muted.TLabel',wraplength=620).pack(anchor='w',pady=(5,12))
        tree=ttk.Treeview(content,columns=('song','artist','source'),show='headings',height=3,selectmode='browse')
        for key,label,width in (('song','Song title',220),('artist','Artist name',180),('source','Source',180)):
            tree.heading(key,text=label);tree.column(key,width=width,minwidth=80)
        tree.pack(fill='x')
        for index,suggestion in enumerate(suggestions):
            tree.insert('','end',iid=str(index),values=(suggestion.title,suggestion.artist,suggestion.source))
        song=tk.StringVar(value=self.title.get());artist=tk.StringVar(value=self.artist.get())
        ttk.Label(content,text='Song title',style='Muted.TLabel').pack(anchor='w',pady=(12,4))
        ttk.Entry(content,textvariable=song).pack(fill='x')
        ttk.Label(content,text='Artist name',style='Muted.TLabel').pack(anchor='w',pady=(8,4))
        ttk.Entry(content,textvariable=artist).pack(fill='x')
        message=tk.StringVar(value=notice)
        ttk.Label(content,textvariable=message,style='Muted.TLabel',wraplength=620).pack(anchor='w',pady=(8,0))
        def select(event=None):
            if tree.selection():
                suggestion=suggestions[int(tree.selection()[0])]
                song.set(suggestion.title);artist.set(suggestion.artist)
                message.set(notice+(' No artist name was found; enter it below.' if not suggestion.artist else ''))
        tree.bind('<<TreeviewSelect>>',select)
        if suggestions:tree.selection_set('0');select()
        buttons=ttk.Frame(content);buttons.pack(side='bottom',fill='x',pady=(12,0))
        def apply():
            if generation!=self.song_lookup_generation or path!=self.audio.get().strip():
                message.set('The selected music file has changed. Close this window and try again.')
                return
            title_value=song.get().strip();artist_value=artist.get().strip()
            if not title_value or not artist_value:
                message.set('Enter a song title and an artist name before applying them.')
                return
            self.metadata_pending_path=None
            self.title.set(title_value);self.artist.set(artist_value)
            self.reset_text_defaults={'title':title_value,'artist':artist_value}
            self.status.set('The song title and artist name have been updated.')
            window.destroy()
        def cancel():
            self.status.set('The song title and artist name were left unchanged.')
            window.destroy()
        ttk.Button(buttons,text='Apply names',command=apply).pack(side='right')
        ttk.Button(buttons,text='Cancel',command=cancel).pack(side='right',padx=(0,8))
        window.protocol('WM_DELETE_WINDOW',cancel)
        window.grab_set()

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
        return Settings(width=w,height=h,fps=self.fps.get(),export_encoder=self.export_encoder.get(),title=self.title.get(),dust_count=max(0,min(800,self.dust.get())),reactive_fraction=max(0,min(1,self.reactive.get()/100)),sensitivity=max(.1,min(3,self.sensitivity.get())),background=self.background.get().strip(),bars=self.bands.get(),spectrum_width=self.spectrum_width.get()/100,
            spectrum_x=self.spectrum_x.get()/100,spectrum_y=self.spectrum_y.get()/100,
            spectrum_height=self.spectrum_height.get()/100,title_size=self.title_size.get()/100,
            title_x=self.title_x.get()/100,title_y=self.title_y.get()/100,title_font=self.title_font.get(),
            title_bold=self.title_bold.get(),title_italic=self.title_italic.get(),
            title_uppercase=self.title_uppercase.get(),title_color=self.title_color.get(),
            overlay_enabled=self.overlay_enabled.get(),overlay_path=self.overlay_path.get(),
            overlay_size=self.overlay_size.get()/100,overlay_x=self.overlay_x.get()/100,
            overlay_y=self.overlay_y.get()/100,overlay_opacity=self.overlay_opacity.get()/100,overlay_shape=self.overlay_shape.get(),
            particle_continuous=self.particle_continuous.get(),particles_enabled=self.particles_enabled.get(),particle_reactivity=self.particle_reactivity.get(),particle_direction=self.particle_direction.get(),
            particle_reactive=self.particle_reactive.get(),particle_color=self.particle_color.get(),spectrum_color=self.spectrum_color.get(),
            spectrum_mapping=self.spectrum_mapping.get(),spectrum_style=self.spectrum_style.get(),spectrum_mirrored=self.spectrum_mirrored.get(),
            spectrum_density=self.spectrum_density.get()/100,spectrum_fill=self.spectrum_fill.get()/100,
            spectrum_color_end=self.spectrum_color_end.get(),frequency_min=self.frequency_min.get(),
            frequency_max=self.frequency_max.get(),frequency_scale=self.frequency_scale.get(),
            spectrum_gain=self.spectrum_gain.get(),particle_speed=self.particle_speed.get(),artist=self.artist.get(),artist_size=self.artist_size.get()/100,
            artist_x=self.artist_x.get()/100,artist_y=self.artist_y.get()/100,
            artist_font=self.artist_font.get(),artist_bold=self.artist_bold.get(),
            artist_italic=self.artist_italic.get(),artist_uppercase=self.artist_uppercase.get(),
            artist_color=self.artist_color.get())

    def prepare_preview(self):
        if self.busy:return
        try:path=self.active_audio_path()
        except (ValueError,OSError) as exc:self.status.set(str(exc));return
        try:
            validate_settings({key:var.get() for key,var in self.project_vars.items()})
            settings=self.settings(preview=True)
        except (ValueError,tk.TclError) as exc:
            self.status.set(str(exc));return
        self.pause()
        self.busy=True;self.status.set('Analyzing music frequencies...')
        metadata_pending=self.audio.get().strip()==self.metadata_pending_path
        metadata_path=self.audio.get().strip()
        cache=self.preview_cache
        try:mix=mix_spec(self.instrumental.get(),self.vocals.get(),self.instrumental_gain.get(),self.vocal_gain.get()) if self.audio_track.get()=='Stem mix' else None
        except (OSError,ValueError) as exc:
            self.busy=False;self.status.set('Stem mix unavailable: '+str(exc));return
        def worker():
            try:
                if mix is not None:prepare_mix(mix)
                if metadata_pending:
                    self.q.put(('metadata',(metadata_path,read_metadata(metadata_path))))
                samples,sr,playback,features=cache.prepare(path,settings,load_audio,decode_preview,audio_features)
                renderer=Renderer(settings,features)
                self.q.put(('ready',(samples,sr,features,renderer,path,playback)))
            except Exception as exc:self.q.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def display_frame(self):
        if self.renderer is None:return
        pos=min(self.length,max(0,self.position.get()))
        try:
            frame=IdentityRenderer(self.renderer,self.lyric_document).render(pos)
            frame=draw_lyric_guide(frame,pos,self.lyric_document)
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
        except (ValueError,OSError,tk.TclError) as exc:self.status.set(str(exc))

    def toggle_sound(self):
        self.preview_player.muted=not self.sound_enabled.get()
        if self.playing and self.preview_player.stream is None and self.sound_enabled.get():
            self.sync_preview_audio()

    def sync_preview_audio(self):
        self.preview_player.muted=not self.sound_enabled.get()
        # An unavailable device must not prevent visual-only preview.
        if self.preview_player.samples is None:return
        if not self.sound_enabled.get() and self.preview_player.stream is None:return
        try:
            end=self.selection_end.get() if self.play_selection else self.length
            self.preview_player.play(self.position.get(),end,self.loop_selection,
                                     loop_start=self.selection_start.get() if self.play_selection else 0)
        except Exception as exc:
            self.sound_enabled.set(False)
            self.status.set('Preview sound unavailable: '+str(exc)+'. Visual playback remains available.')

    def pause(self):
        self.stop_monitor()
        if self.playing and self.preview_player.stream is not None:
            self.position.set(self.preview_player.position())
        self.preview_player.stop()
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
        self.sync_preview_audio()
        if not already_playing:self.animate()

    def timeline_click(self,event):
        """Seek exactly to the pointer instead of the scale's default step."""
        if self.renderer is None or self.length<=0:return 'break'
        left=self.scrub.coords(0)[0]
        right=self.scrub.coords(self.length)[0]
        fraction=max(0,min(1,(event.x-left)/max(1,right-left)))
        seconds=fraction*self.length
        already_playing=self.playing
        self.play_selection=False
        self.loop_selection=False
        self.position.set(seconds)
        self.t0=time.monotonic()-seconds
        self.display_frame()
        self.playing=True
        self.sync_preview_audio()
        if not already_playing:self.animate()
        return 'break'

    def toggle_play(self):
        if self.playing:self.pause();return
        if self.renderer is None:return
        self.play_selection=False;self.loop_selection=False
        self.t0=time.monotonic()-self.position.get()
        self.playing=True
        self.sync_preview_audio()
        self.animate()

    def animate(self):
        if not self.playing:return
        try:
            start,end=self.selection_bounds() if self.play_selection else (0,self.length)
        except (ValueError,tk.TclError):self.pause();return
        if self.preview_player.stream is not None and self.play_selection:
            player=self.preview_player
            if player.start_frame!=round(start*player.rate) or player.end_frame!=min(len(player.samples),round(end*player.rate)):
                if not start<=self.position.get()<end:self.position.set(start)
                self.sync_preview_audio()
        t=self.preview_player.position() if self.preview_player.stream is not None else time.monotonic()-self.t0
        if t>=end-1/22050:
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
        p=filedialog.asksaveasfilename(initialfile=self.filename_stem()+'.png',defaultextension='.png',filetypes=[('PNG image','*.png')])
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
        try:active_path=self.active_audio_path()
        except (ValueError,OSError) as exc:return messagebox.showerror('Missing audio',str(exc))
        if self.loaded_audio_path != active_path:
            self.prepare_preview()
            return messagebox.showinfo('Analyze music','Wait for the preview, then choose the export range.')
        try:
            start,end=self.selection_bounds()
            validate_settings({key:var.get() for key,var in self.project_vars.items()})
            settings=self.settings()
        except (ValueError,tk.TclError) as exc:
            return messagebox.showerror('Invalid selection',str(exc))
        if self.lyric_control is not None:return messagebox.showinfo('Alignment running','Wait for alignment to finish before export.')
        if self.lyrics_editor.get('1.0','end-1c')!=self.lyric_document.text:return messagebox.showinfo('Apply lyrics','Apply the lyric edits before export.')
        lyric_snapshot=self.lyric_document.snapshot()
        if self.lyric_document.style['enabled'] and self.lyric_document.warnings():
            if not messagebox.askyesno('Review lyric timing','Some lyric timings are estimated or need review. Export them anyway?'):return
        audio_path=active_path
        out=filedialog.asksaveasfilename(
            initialdir=self._browse_initial_folder('export', self.last_export_path or ''),
            initialfile=self.filename_stem()+'.mp4',defaultextension='.mp4', filetypes=[('MP4 video','*.mp4')])
        if not out:return
        # A chosen destination counts as the last used folder even if export fails.
        self._remember_folder('export', out)
        self.last_export_folder=os.path.dirname(os.path.abspath(out))
        if os.path.normcase(os.path.realpath(out)) in tuple(os.path.normcase(os.path.realpath(p)) for p in (self.audio.get(),audio_path,self.instrumental.get(),self.vocals.get()) if p):return messagebox.showerror('Invalid path','Export path must differ from input.')
        self.pause()
        self.busy=True
        self.notification_state()
        self.progress['value']=0
        self.encoder_status.set('Preparing encoder...')
        self.export_device.set('Encoding: checking... | Rendering: CPU')
        self.status.set('Exporting video. High-resolution rendering may be slow.')
        cached_analysis=self.preview_cache.snapshot()
        control=ExportControl()
        self.export_control=control
        self.cancel_requested=False
        self.last_export_report=None
        self.cancel_export_button.configure(state='normal')
        self.export_eta=ExportETA()
        self.export_remaining.set(self.export_eta.text())
        diagnostics=ExportReport(settings)
        self.export_outcome=None
        export_started=self.export_timer.start()
        self.export_time.set(self.export_timer.text())
        self.update_export_strip()
        def worker():
            kind,payload='finished',out
            try:
                export(audio_path,out,settings,progress=lambda i,n:self.q.put(('progress',(i,n,time.monotonic()))),
                       start_seconds=start,end_seconds=end,cached_analysis=cached_analysis,
                       encoder_status=lambda message:self.q.put(('encoder',message)),
                       cancel=control,diagnostics=diagnostics,lyric_document=lyric_snapshot)
                if not os.path.isfile(out) or os.path.getsize(out)==0:
                    raise RuntimeError('Export returned without a valid output MP4.')
            except ExportCancelled:
                kind,payload='export_canceled',None
            except Exception as exc:
                kind,payload='error',str(exc)
                if diagnostics.data['status']=='success':
                    diagnostics.data.update(status='failed',failure_stage='output_validation',error_type=type(exc).__name__)
            finally:
                self.q.put(('export_report',diagnostics))
                self.q.put(('export_timing',time.monotonic()-export_started))
            self.q.put((kind,payload))
        threading.Thread(target=worker,daemon=True).start()

    def cancel_export(self):
        if self.export_control is not None and self.export_control.cancel():
            self.cancel_requested=True
            self.cancel_export_button.configure(state='disabled')
            self.status.set('Canceling export...')
            self.export_remaining.set('Remaining: canceling...')

    def finish_export_controls(self):
        self.export_control=None
        self.cancel_requested=False
        self.cancel_export_button.configure(state='disabled')
        if self.export_eta is not None:self.export_eta.finished=True
        self.export_remaining.set('Remaining: —')

    def view_export_report(self):
        report=self.last_export_report
        if report is None:return
        window=tk.Toplevel(self.root);window.title('Export details')
        window.geometry('760x520');window.minsize(540,360)
        buttons=ttk.Frame(window,padding=10);buttons.pack(side='bottom',fill='x')
        notebook=ttk.Notebook(window);notebook.pack(fill='both',expand=True,padx=10,pady=(10,0))
        overview=ttk.Frame(notebook,padding=16)
        technical=ttk.Frame(notebook)
        notebook.add(overview,text='Overview');notebook.add(technical,text='Technical report')
        data=report.data
        encoder=data.get('final_encoder') or 'Not started'
        summary=report.summary()
        ttk.Label(overview,text='Export '+data['status'],style='Section.TLabel').pack(anchor='w',pady=(0,12))
        ttk.Label(overview,text='Encoder: '+encoder+'  ·  Visual rendering: CPU').pack(anchor='w',pady=(0,12))
        summary_label=ttk.Label(overview,text=summary,justify='left',wraplength=650)
        summary_label.pack(anchor='w')
        explanation=ttk.Label(overview,text='Rendering and encoding overlap. Frame-feed time includes transfer and waiting.',
                              style='Muted.TLabel',wraplength=650)
        explanation.pack(anchor='w',pady=(14,0))
        def resize_details(event):
            for label in (summary_label,explanation):label.configure(wraplength=max(200,event.width-32))
        overview.bind('<Configure>',resize_details)
        text=tk.Text(technical,wrap='word',padx=12,pady=12)
        scroll=ttk.Scrollbar(technical,command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');text.pack(fill='both',expand=True)
        contents=summary+'\n\n'+report_json(data)
        text.insert('1.0',report_json(data));text.configure(state='disabled')
        def copy():
            window.clipboard_clear();window.clipboard_append(contents)
        ttk.Button(buttons,text='Close',command=window.destroy).pack(side='right')
        ttk.Button(buttons,text='Save JSON',command=lambda:self.save_export_report(report)).pack(side='right',padx=8)
        ttk.Button(buttons,text='Copy report',command=copy).pack(side='right')

    def save_export_report(self,report=None):
        report=self.last_export_report if report is None else report
        if report is None:return
        path=filedialog.asksaveasfilename(initialfile='DeRo_export_report.json',defaultextension='.json',
                                         filetypes=[('JSON report','*.json')])
        if not path:return
        try:
            with open(path,'w',encoding='utf-8') as stream:stream.write(report_json(report.data))
        except OSError as exc:messagebox.showerror('Could not save report',str(exc))

    def open_completed_export(self,path):
        if self.last_export_path!=path:return
        try:self._open_path(path)
        except OSError as exc:
            messagebox.showwarning('Export saved',f'Export completed, but the video could not open automatically.\n\n{path}\n\n{exc}')

    def poll(self):
        try:
            while True:
                kind,data=self.q.get_nowait()
                if kind=='local_song_information':
                    generation,path,mode,original_title,original_artist,title,artist=data
                    if generation!=self.song_import_generation:continue
                    if mode=='retrieve':
                        if path!=self.audio.get().strip():continue
                        if title:self.title.set(title)
                        if artist:self.artist.set(artist)
                        self.status.set('Song and artist metadata retrieved. The audio file is unchanged.')
                    else:self.confirm_song_information(path,original_title,original_artist,title,artist,mode)
                elif kind=='song_information_error':
                    generation,error=data
                    if generation==self.song_import_generation:self.status.set('Could not read song information: '+error)
                elif kind=='separation_log':
                    if data.startswith('Preparing stereo'):self.separation_status.set('Preparing compatible audio...')
                    elif data.startswith('Running '):self.separation_status.set('Processing — '+data.split('.')[0])
                    elif data.startswith('Validating '):
                        self.separation_status.set('Validating both stem files...')
                        self.separation_progress.configure(mode='indeterminate');self.separation_progress.start(12)
                    percentages=re.findall(r'(?<!\d)(\d{1,3}(?:\.\d+)?)\s*%',data)
                    if percentages:
                        self.separation_progress.stop()
                        self.separation_progress.configure(mode='determinate',value=min(100,max(0,float(percentages[-1]))))
                        self.separation_status.set('Demucs reported stage: '+percentages[-1]+'% (not overall completion)')
                    self.separation_log.configure(state='normal');self.separation_log.insert('end',data+'\n')
                    # Bound UI log memory on long model downloads/runs.
                    if int(self.separation_log.index('end-1c').split('.')[0])>1500:self.separation_log.delete('1.0','501.0')
                    self.separation_log.see('end');self.separation_log.configure(state='disabled')
                elif kind=='separation_done':
                    path,tracks,error,canceled=data
                    self.busy=False;self.separation_control=None;self.separation_progress.stop()
                    self.separation_progress.configure(mode='determinate',value=100 if tracks else 0)
                    self.start_separation_button.configure(state='normal');self.cancel_separation_button.configure(state='disabled')
                    elapsed=time.monotonic()-self.separation_started
                    duration=format_duration(elapsed)
                    self.separation_elapsed.set('Elapsed: '+duration+' · Total: '+duration)
                    if canceled:
                        self.separation_status.set(f'Canceled after {elapsed:.1f}s. The original song is unchanged.')
                        self.song_workflow_status.set('Vocal separation canceled. You can restart it or import stems.')
                    elif error:
                        self.separation_status.set('Separation failed. See processing details below.')
                        self.separation_log.configure(state='normal');self.separation_log.insert('end','\nERROR: '+error+'\n')
                        self.separation_log.see('end');self.separation_log.configure(state='disabled')
                        self.song_workflow_status.set('Separation needs attention. Import stems or retry after resolving the error.')
                        self.status.set('Vocal separation failed. See Separation for details.')
                    elif path==self.audio.get().strip():
                        self.instrumental.set(tracks[0]);self.vocals.set(tracks[1])
                        self.separation_status.set(f'Complete in {elapsed:.1f}s. Instrumental and vocal tracks are ready.')
                        self.song_workflow_status.set('Song imported and stems ready. Continue to the visualizer.')
                        self.status.set('Vocal separation complete.')
                        if self.completion_sound.get():self.play_completion_chime()
                        self.show_inspector('Text');self.prepare_preview()
                elif kind=='song_lookup':
                    generation,path,suggestions,notice,error=data
                    if generation!=self.song_lookup_generation:continue
                    self.song_lookup_control=None
                    self.find_song_button.configure(state='normal',text='Find artist and song online')
                    if path!=self.audio.get().strip():continue
                    if error:self.status.set('Could not read the song information: '+error)
                    else:
                        self.status.set('Review the artist and song names before applying them.')
                        self.review_song_suggestions(generation,path,suggestions,notice)
                elif kind=='export_report':
                    self.last_export_report=data
                    self.export_outcome=data.data['status']
                elif kind=='export_canceled':
                    self.busy=False
                    self.finish_export_controls()
                    self.notification_state()
                    self.status.set('Canceled. Existing output files were preserved.')
                elif kind=='export_timing':
                    self.export_timer.stop(data)
                    self.export_time.set(self.export_timer.text())
                elif kind=='encoder':
                    device=('GPU — NVIDIA NVENC' if data.startswith('NVIDIA NVENC') else
                            'CPU (fallback)' if data.startswith('CPU fallback') else 'CPU')
                    self.export_device.set('Encoding: '+device+' | Rendering: CPU')
                    self.encoder_status.set(data)
                    if not getattr(self,'cancel_requested',False):self.status.set(data)
                elif kind=='particles_ready':
                    generation,source,renderer,error=data
                    if generation!=self.particle_generation or self.renderer is not source:continue
                    self.particle_request=None
                    if error:
                        self.status.set('Particle preview failed: '+error)
                        continue
                    self.renderer=renderer
                    self.apply_layout_preview()
                elif kind=='metadata':
                    path,tags=data
                    if path==self.audio.get().strip() and path==self.metadata_pending_path:
                        self.title.set(tags['title'] or os.path.splitext(os.path.basename(path))[0])
                        self.artist.set(tags['artist'])
                        self.reset_text_defaults={'title':self.title.get(),'artist':self.artist.get()}
                        self.metadata_pending_path=None
                elif kind=='ready':
                    samples,sr,features,renderer,path,playback=data
                    self.preview_audio=playback
                    self.preview_player.load(playback)
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
                    self.apply_layout_preview()
                    self.display_frame()
                elif kind=='error':
                    if getattr(self,'export_control',None) is not None:self.finish_export_controls()
                    self.busy=False
                    self.notification_state()
                    self.status.set('Error: '+data)
                    messagebox.showerror('Visualizer',data)
                elif kind=='tone_error':
                    self.status.set('Sound could not play: '+data)
                elif kind=='progress':
                    if getattr(self,'cancel_requested',False):continue
                    i,n,*timestamp=data;self.progress['value']=i/n*100
                    if getattr(self,'export_eta',None) is not None:self.export_eta.update(i,n,now=timestamp[0] if timestamp else None)
                    self.status.set(f'Exporting MP4: {i/n*100:.1f}% ({i}/{n} frames)')
                elif kind=='finished':
                    self.finish_export_controls()
                    self.busy=False;self.progress['value']=100
                    self.notification_state(True)
                    self.status.set('Export complete · '+os.path.basename(data))
                    if self.completion_sound.get():self.play_completion_chime()
                    self.last_export_path=os.path.abspath(data)
                    if self.auto_open_export.get():
                        # Leave time to see the banner and hear the chime before
                        # another video player takes focus and starts its audio.
                        self.root.after(2000,lambda path=self.last_export_path:self.open_completed_export(path))
        except queue.Empty:pass
        if getattr(self,'close_when_export_done',False) and self.export_control is None and getattr(self,'separation_control',None) is None:
            self.destroy_application()
            return
        if getattr(self,'separation_control',None) is not None:
            self.separation_elapsed.set('Elapsed: '+format_duration(time.monotonic()-self.separation_started)+' · Total: running...')
        if getattr(self,'export_timer',None) is not None:
            self.export_time.set(self.export_timer.text())
        if getattr(self,'export_eta',None) is not None and not self.cancel_requested:
            self.export_remaining.set(self.export_eta.text())
        if hasattr(self,'export_meta_label'):self.update_export_strip()
        self.root.after(150,self.poll)

if __name__=='__main__':
    root=tk.Tk()
    Application(root)
    root.mainloop()
