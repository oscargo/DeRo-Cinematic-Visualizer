"""Native Tkinter lyric editing, word synchronization and cinematic lyric design."""
import importlib.util
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk,filedialog,messagebox,colorchooser
import numpy as np
from PIL import ImageTk
from lyric_model import LyricDocument,STYLE_DEFAULTS
from lyric_render import exact_frame
from export_control import ExportControl,ExportCancelled
from preview_audio import PreviewAudio,decode_preview
from favorite_sites_ui import FavoriteSitesUI


class KaraokeWorkspace(FavoriteSitesUI):
    def init_karaoke(self):
        self.lyric_document=LyricDocument();self.lyric_undo=[];self.lyric_redo=[]
        self.saved_lyrics=self.lyric_document.snapshot();self.lyric_control=None
        self.alignment_summary={};self.alignment_inspector={};self.favorite_sites_window=None
        self.lyric_queue=__import__('queue').Queue();self.lyric_generation=0
        self.lyric_message=tk.StringVar(value='Paste the exact lyrics, then align and review the timings.')
        self.word_start=tk.StringVar(value='0.000');self.word_end=tk.StringVar(value='0.500')
        self.line_start=tk.StringVar(value='0.000');self.line_end=tk.StringVar(value='1.000')
        self.shift_seconds=tk.StringVar(value='0.100');self.word_zoom=tk.DoubleVar(value=10.)
        self.monitor_choice=tk.StringVar(value='Vocals');self.monitor_player=PreviewAudio()
        self.monitor_path=None;self.monitor_samples=None;self.monitoring=False;self.monitor_end=0
        self.monitor_loop=tk.BooleanVar(value=False)
        self.monitor_generation=0;self.waveform=None;self.wave_duration=0.;self.word_drag=None
        self.selected_line=0;self.selected_word=0;self.karaoke_overlays={}
        self.style_vars={}
        for key,value in STYLE_DEFAULTS.items():
            kind=tk.BooleanVar if isinstance(value,bool) else tk.StringVar
            self.style_vars[key]=kind(value=value)

    def build_karaoke(self,workspace):
        content=self.inspector_pages['Audio'].master
        rail=self.navigation_buttons['Audio'].master
        def page(name):
            panel=ttk.Frame(content,padding=(10,4,10,14));self.inspector_pages[name]=panel
            button=ttk.Button(rail,text=name,width=10,command=lambda:self.show_inspector(name))
            self.navigation_buttons[name]=button
            ttk.Label(panel,text=name,style='Heading.TLabel').pack(anchor='w',pady=(4,12))
            return panel
        def button(parent,label,command):
            widget=ttk.Button(parent,text=label,command=command);widget.pack(fill='x',pady=3);return widget
        def field(parent,label,var,values=None):
            ttk.Label(parent,text=label,style='Muted.TLabel').pack(anchor='w',pady=(8,4))
            w=ttk.Combobox(parent,textvariable=var,values=values,state='readonly') if values else ttk.Entry(parent,textvariable=var)
            w.pack(fill='x');return w
        lyrics=page('Lyrics')
        button(lyrics,'Import lyrics...',self.import_lyrics)
        button(lyrics,'Apply pasted lyrics',self.apply_lyrics)
        button(lyrics,'Save lyrics as text...',self.save_lyrics)
        button(lyrics,'Cancel alignment',self.cancel_alignment)
        button(lyrics,'Alignment setup...',self.alignment_setup)
        button(lyrics,'Review word timings',lambda:self.show_inspector('Word Sync'))
        button(lyrics,'Sync Inspector...',self.show_sync_inspector)
        ttk.Label(lyrics,text='Your pasted lyrics remain the source of truth. Alignment changes timing only.',wraplength=200,style='Muted.TLabel').pack(anchor='w',pady=14)
        words=page('Word Sync')
        ttk.Checkbutton(words,text='Loop selected line',variable=self.monitor_loop).pack(anchor='w',pady=4)
        field(words,'Monitor audio',self.monitor_choice,('Vocals','Instrumental','Original mix'))
        button(words,'Load monitoring audio',self.load_monitor)
        button(words,'Play selected line',self.play_word_line)
        button(words,'Pause',self.stop_monitor)
        field(words,'Word start (seconds)',self.word_start);field(words,'Word end (seconds)',self.word_end)
        button(words,'Apply word times',self.apply_word_times)
        nudge=ttk.Frame(words);nudge.pack(fill='x',pady=3)
        for label,amount in [('-10 ms',-.01),('+10 ms',.01)]:ttk.Button(nudge,text=label,command=lambda d=amount:self.nudge_word(d)).pack(side='left',expand=True,fill='x')
        button(words,'Set word start at playhead',lambda:self.word_at_playhead(False))
        button(words,'Set word end at playhead',lambda:self.word_at_playhead(True))
        button(words,'Tap next word',self.tap_next_word)
        field(words,'Line start (seconds)',self.line_start);field(words,'Line end (seconds)',self.line_end)
        button(words,'Apply line times',self.apply_line_times)
        field(words,'Shift all lyrics by seconds',self.shift_seconds)
        button(words,'Shift all lyrics',self.shift_lyrics)
        button(words,'Mark line reviewed',self.review_line)
        button(words,'Undo',self.undo_lyrics);button(words,'Redo',self.redo_lyrics)
        design=page('Video Designer')
        field(design,'Lyric layout',self.style_vars['lyric_display_mode'],('single','preview','alternating','classic_flow'))
        for label,key in [('Enable lyrics','enabled'),('Bold lyrics','lyric_font_bold'),('Keep song and artist visible','show_identity'),('Intro countdown','opening_progress_enabled'),('Silence progress','silence_progress_enabled')]:
            ttk.Checkbutton(design,text=label,variable=self.style_vars[key]).pack(anchor='w',pady=4)
        for label,key in [('Font family','lyric_font_family'),('Font size','lyric_font_size'),('Outline width','lyric_outline'),('Vertical position (%)','lyric_vertical_percent'),('Read-ahead (seconds)','lyric_lead_seconds'),('Flow lines (2 or 3)','classic_flow_lines'),('Flow fade in (ms)','classic_flow_fade_in'),('Flow fade out (ms)','classic_flow_fade_out')]:field(design,label,self.style_vars[key])
        for label,key in [('Unsung color','lyric_unsung_color'),('Sung color','lyric_sung_color')]:
            field(design,label,self.style_vars[key]);button(design,'Choose '+label.lower(),lambda k=key:self.lyric_color(k))
        field(design,'Line exit',self.style_vars['lyric_exit'],('Fade Out','None'))
        for label,key in [('Exit duration (ms)','lyric_exit_duration'),('Exit delay (ms)','lyric_exit_delay'),('Final fade (ms)','lyric_final_fade_out'),('Intro duration (seconds)','opening_progress_duration'),('Intro lead (seconds)','opening_progress_before'),('Silence threshold (seconds)','silence_progress_threshold'),('Identity intro (seconds)','identity_intro_seconds')]:field(design,label,self.style_vars[key])
        button(design,'Apply lyric design',self.apply_lyric_style)
        button(design,'Render exact preview frame',self.preview_exact_lyrics)
        button(design,'Export ASS subtitles...',self.save_ass)
        for label,target in [('Backdrop','Backdrop'),('Song and artist text','Text'),('Spectrum','Visualizer'),('Particles and logo','Elements')]:button(design,label,lambda t=target:self.show_inspector(t))
        for key in ('Audio','Separation','Lyrics','Word Sync','Video Designer','Output','Backdrop','Text','Visualizer','Elements'):
            b=self.navigation_buttons[key];b.pack_forget();b.configure(padding=(4,9));b.pack(fill='x',pady=(0,5))
        self.navigation_buttons['Output'].configure(text='Export')
        self.navigation_buttons['Video Designer'].configure(text='Designer')
        style=ttk.Style(self.root)
        style.configure('Treeview',background='#101c2c',fieldbackground='#101c2c',foreground='#dfebfa',rowheight=26,borderwidth=0)
        style.configure('Treeview.Heading',background='#202e44',foreground='#c8daf0',padding=(5,6),relief='flat')
        style.map('Treeview',background=[('selected','#315d86')],foreground=[('selected','#ffffff')])
        # Main editors share a single compact status footer.
        for name in ('Lyrics','Word Sync','Video Designer'):
            overlay=ttk.Frame(workspace,padding=14);self.karaoke_overlays[name]=overlay
            ttk.Label(overlay,text='Authoritative lyrics' if name=='Lyrics' else name,style='Heading.TLabel').pack(anchor='w',pady=(0,8))
            ttk.Label(overlay,textvariable=self.lyric_message,style='Muted.TLabel',wraplength=600).pack(anchor='w',pady=(0,8))
        main=self.karaoke_overlays['Lyrics']
        style=ttk.Style(self.root)
        style.configure('LyricsAction.TButton',background='#7556df',foreground='#ffffff',font=(self.ui_font,10,'bold'))
        style.map('LyricsAction.TButton',background=[('pressed','#6040c8'),('active','#896aef')],foreground=[('disabled','#c3badc')])
        toolbar=ttk.Frame(main);toolbar.pack(fill='x',pady=(0,10))
        self.favorite_sites_button=ttk.Button(toolbar,text='1  Favorite Lyrics Sites',style='LyricsAction.TButton',command=self.show_favorite_sites)
        self.auto_sync_lyrics_button=ttk.Button(toolbar,text='2  Auto-sync pasted lyrics with WhisperX',style='LyricsAction.TButton',command=self.start_alignment)
        def arrange_lyrics_buttons(event):
            stacked=event.width<650
            self.favorite_sites_button.grid(row=0,column=0,sticky='ew',padx=(0,0 if stacked else 6),pady=(0,6 if stacked else 0))
            self.auto_sync_lyrics_button.grid(row=1 if stacked else 0,column=0 if stacked else 1,sticky='ew')
            toolbar.columnconfigure(0,weight=1);toolbar.columnconfigure(1,weight=0 if stacked else 1)
        toolbar.bind('<Configure>',arrange_lyrics_buttons)
        ttk.Label(main,text='Paste or import the complete lyrics, one sung line per row.').pack(anchor='w',pady=(0,8))
        frame=ttk.Frame(main);frame.pack(fill='both',expand=True)
        self.lyrics_editor=tk.Text(frame,wrap='word',undo=True,background='#080e19',foreground='#dbe8fa',insertbackground='white',font=('Segoe UI',12))
        scroll=ttk.Scrollbar(frame,command=self.lyrics_editor.yview);self.lyrics_editor.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');self.lyrics_editor.pack(fill='both',expand=True)
        self.lyrics_editor.bind('<<Modified>>',self.lyrics_text_modified)
        actions=ttk.Frame(main);actions.pack(fill='x',pady=(8,0))
        for label,cmd in [('Apply lyrics',self.apply_lyrics),('Word Sync',lambda:self.show_inspector('Word Sync'))]:ttk.Button(actions,text=label,command=cmd).pack(side='left',padx=(0,6))
        main=self.karaoke_overlays['Word Sync']
        self.line_tree=ttk.Treeview(main,columns=('time','state','text'),show='headings',height=7,selectmode='browse')
        for col,label,width in [('time','Start – end',130),('state','Review',90),('text','Exact lyric line',340)]:
            self.line_tree.heading(col,text=label);self.line_tree.column(col,width=width,stretch=col=='text')
        self.line_tree.pack(fill='x');
        line_scroll=ttk.Scrollbar(main,orient='horizontal',command=self.line_tree.xview);self.line_tree.configure(xscrollcommand=line_scroll.set)
        line_scroll.pack(fill='x');self.line_tree.bind('<<TreeviewSelect>>',self.select_lyric_line)
        self.word_canvas=tk.Canvas(main,height=145,background='#080e19',highlightthickness=0)
        self.word_canvas.pack(fill='x',pady=8);self.word_canvas.bind('<Configure>',lambda e:self.draw_word_timeline())
        self.word_canvas.bind('<Button-1>',self.timeline_word_press);self.word_canvas.bind('<B1-Motion>',self.timeline_word_drag);self.word_canvas.bind('<ButtonRelease-1>',self.timeline_word_release)
        zoom=ttk.Frame(main);zoom.pack(fill='x')
        ttk.Label(zoom,text='Visible seconds').pack(side='left');ttk.Scale(zoom,from_=2,to=60,variable=self.word_zoom,command=lambda v:self.draw_word_timeline()).pack(side='left',fill='x',expand=True,padx=8)
        self.playhead_label=ttk.Label(zoom,text='0.000 s');self.playhead_label.pack(side='right')
        self.word_tree=ttk.Treeview(main,columns=('word','start','end','score'),show='headings',height=7,selectmode='browse')
        for col,label,width in [('word','Exact word',240),('start','Start',95),('end','End',95),('score','Confidence',100)]:self.word_tree.heading(col,text=label);self.word_tree.column(col,width=width,stretch=col=='word')
        self.word_tree.pack(fill='both',expand=True,pady=8);
        self.word_tree.bind('<<TreeviewSelect>>',self.select_lyric_word)
        main=self.karaoke_overlays['Video Designer']
        ttk.Label(main,text='Cinematic visuals with DeRo Sync lyric layouts',style='Section.TLabel').pack(anchor='w',pady=(5,12))
        ttk.Label(main,text='Set the appearance in the sidebar. Exact frames and short video previews use the same subtitle renderer as the final export.',wraplength=570,style='Muted.TLabel').pack(anchor='w',pady=(0,15))
        self.lyric_preview_label=ttk.Label(main,text='Render a frame to inspect the lyric design.',anchor='center');self.lyric_preview_label.pack(fill='both',expand=True)
        row=ttk.Frame(main);row.pack(fill='x',pady=(10,0))
        ttk.Button(row,text='Exact frame at playhead',command=self.preview_exact_lyrics).pack(side='left')
        ttk.Button(row,text='Export 10-second preview...',command=self.export_short_preview).pack(side='left',padx=8)
        out=self.inspector_pages['Output']
        ttk.Label(out,text='Live lyrics are a layout guide. Use Exact lyric preview to check final wrapping, fills, and fades.',wraplength=220,style='Muted.TLabel').pack(anchor='w',pady=8)
        ttk.Separator(out).pack(fill='x',pady=12)
        button(out,'Lyrics and Word Sync',lambda:self.show_inspector('Word Sync'))
        button(out,'Exact lyric preview',self.preview_exact_lyrics)
        button(out,'Export 10-second preview...',self.export_short_preview)
        self.root.after(100,self.poll_karaoke)

    def lyrics_text_modified(self,event=None):
        if self.lyrics_editor.edit_modified():
            self.lyrics_editor.edit_modified(False)
            if self.lyrics_editor.get('1.0','end-1c')!=self.lyric_document.text:self.lyric_message.set('Unapplied lyric edits. Apply them before alignment or export.')

    def reset_karaoke(self):
        self.cancel_alignment();self.set_alignment_running(False);self.lyric_control=None;self.lyric_generation+=1;self.stop_monitor();self.monitor_generation+=1
        self.monitor_player.load(None);self.monitor_path=None;self.waveform=None
        self.lyric_document=LyricDocument();self.lyric_undo=[];self.lyric_redo=[]
        self.alignment_summary={};self.alignment_inspector={}
        self.refresh_lyrics()

    def refresh_lyrics(self):
        if not hasattr(self,'lyrics_editor'):return
        self.alignment_summary=copy.deepcopy(self.lyric_document.data['alignment_summary'])
        self.alignment_inspector=copy.deepcopy(self.lyric_document.data['sync_inspector'])
        if self.lyrics_editor.get('1.0','end-1c')!=self.lyric_document.text:
            self.lyrics_editor.delete('1.0','end');self.lyrics_editor.insert('1.0',self.lyric_document.text);self.lyrics_editor.edit_modified(False)
        for k,v in self.lyric_document.style.items():self.style_vars[k].set(v)
        self.line_tree.delete(*self.line_tree.get_children())
        for i,(a,b,text) in enumerate(self.lyric_document.events):self.line_tree.insert('','end',iid=str(i),values=(f'{a:.3f} – {b:.3f}',self.lyric_document.data['alignment_status'].get(str(i),'estimated'),text))
        self.selected_line=min(self.selected_line,max(0,len(self.lyric_document.events)-1))
        if self.lyric_document.events:self.line_tree.selection_set(str(self.selected_line))
        self.refresh_words()
        warnings=self.lyric_document.warnings()
        self.lyric_message.set(f'{len(self.lyric_document.events)} lyric lines · {len(warnings)} timing items need review' if self.lyric_document.events else 'Paste the exact lyrics, then align and review the timings.')

    def remember_lyrics(self):
        self.lyric_undo.append(self.lyric_document.snapshot());self.lyric_undo=self.lyric_undo[-50:];self.lyric_redo=[]

    def edit_lyrics(self,operation):
        if self.lyric_control is not None:return messagebox.showinfo('Alignment running','Cancel alignment before editing timings.')
        previous=self.lyric_document.snapshot()
        try:operation();self.lyric_document.validate()
        except (ValueError,IndexError,KeyError,tk.TclError) as exc:
            self.lyric_document=LyricDocument(previous);messagebox.showerror('Could not change lyrics',str(exc));return False
        self.lyric_undo.append(previous);self.lyric_undo=self.lyric_undo[-50:];self.lyric_redo=[]
        self.refresh_lyrics();return True

    def import_lyrics(self):
        path=filedialog.askopenfilename(filetypes=[('Lyrics text','*.txt'),('All files','*.*')])
        if not path:return
        try:text=Path(path).read_text(encoding='utf-8-sig')
        except (OSError,UnicodeError) as exc:return messagebox.showerror('Could not import lyrics',str(exc))
        self.lyrics_editor.delete('1.0','end');self.lyrics_editor.insert('1.0',text)
        self.lyric_message.set('Lyrics imported. Apply them to create or replace timings.')

    def apply_lyrics(self):
        text=self.lyrics_editor.get('1.0','end-1c')
        if text==self.lyric_document.text and self.lyric_document.events:return
        if self.length<=0:return messagebox.showinfo('Load song','Open a visualizer preview to analyze the song before applying lyrics.')
        if self.lyric_document.events and not messagebox.askyesno('Replace lyric timings?','Applying changed text resets existing word timings. Continue?'):return
        self.edit_lyrics(lambda:self.lyric_document.set_text(text,self.length))

    def save_lyrics(self):
        path=filedialog.asksaveasfilename(defaultextension='.txt',filetypes=[('Lyrics text','*.txt')])
        if path:
            try:Path(path).write_text(self.lyrics_editor.get('1.0','end-1c'),encoding='utf-8')
            except OSError as exc:messagebox.showerror('Could not save lyrics',str(exc))

    def undo_lyrics(self):
        if self.lyric_control is not None or not self.lyric_undo:return
        self.lyric_redo.append(self.lyric_document.snapshot());self.lyric_document=LyricDocument(self.lyric_undo.pop());self.refresh_lyrics()
    def redo_lyrics(self):
        if self.lyric_control is not None or not self.lyric_redo:return
        self.lyric_undo.append(self.lyric_document.snapshot());self.lyric_document=LyricDocument(self.lyric_redo.pop());self.refresh_lyrics()

    def select_lyric_line(self,event=None):
        selection=self.line_tree.selection()
        if selection:self.selected_line=int(selection[0]);self.selected_word=0;self.refresh_words()
    def refresh_words(self):
        if not hasattr(self,'word_tree'):return
        self.word_tree.delete(*self.word_tree.get_children())
        words=self.lyric_document.words.get(str(self.selected_line),[])
        scores=self.lyric_document.data['word_scores'].get(str(self.selected_line),[])
        for i,(a,b,text) in enumerate(words):
            score=scores[i] if i<len(scores) else None
            self.word_tree.insert('','end',iid=str(i),values=(text,f'{a:.3f}',f'{b:.3f}',f'{score:.2f}' if isinstance(score,(int,float)) else '—'))
        if words:
            self.selected_word=min(self.selected_word,len(words)-1);self.word_tree.selection_set(str(self.selected_word));self.select_lyric_word()
        if self.lyric_document.events:
            a,b,_=self.lyric_document.events[self.selected_line];self.line_start.set(f'{a:.3f}');self.line_end.set(f'{b:.3f}')
        self.draw_word_timeline()
    def select_lyric_word(self,event=None):
        selected=self.word_tree.selection()
        if not selected:return
        self.selected_word=int(selected[0]);a,b,_=self.lyric_document.words[str(self.selected_line)][self.selected_word]
        self.word_start.set(f'{a:.3f}');self.word_end.set(f'{b:.3f}');self.draw_word_timeline()
    def nudge_word(self,amount):
        words=self.lyric_document.words.get(str(self.selected_line),[])
        if words:
            a,b,_=words[self.selected_word];self.edit_lyrics(lambda:self.lyric_document.set_word(self.selected_line,self.selected_word,a+amount,b+amount))
    def apply_word_times(self):self.edit_lyrics(lambda:self.lyric_document.set_word(self.selected_line,self.selected_word,float(self.word_start.get()),float(self.word_end.get())))
    def apply_line_times(self):self.edit_lyrics(lambda:self.lyric_document.set_line_bounds(self.selected_line,float(self.line_start.get()),float(self.line_end.get())))
    def shift_lyrics(self):self.edit_lyrics(lambda:self.lyric_document.shift(float(self.shift_seconds.get())))
    def review_line(self):
        if self.lyric_document.events:self.edit_lyrics(lambda:self.lyric_document.data['alignment_status'].__setitem__(str(self.selected_line),'reviewed'))
    def word_at_playhead(self,end):
        words=self.lyric_document.words.get(str(self.selected_line),[])
        if not words:return
        a,b,_=words[self.selected_word];t=self.position.get()
        self.edit_lyrics(lambda:self.lyric_document.set_word(self.selected_line,self.selected_word,a if end else t,t if end else b))
    def tap_next_word(self):
        words=self.lyric_document.words.get(str(self.selected_line),[])
        if not words:return
        i=self.selected_word;t=self.position.get()
        def change():
            if i>0:
                prev=words[i-1];self.lyric_document.set_word(self.selected_line,i-1,prev[0],t)
            self.lyric_document.set_word(self.selected_line,i,t,max(t+.05,words[i][1]))
        self.edit_lyrics(change);self.selected_word=min(i+1,len(words)-1);self.word_tree.selection_set(str(self.selected_word));self.select_lyric_word()

    def load_monitor(self,play=False):
        key={'Vocals':'vocals','Instrumental':'instrumental','Original mix':'audio'}[self.monitor_choice.get()]
        path=self.project_vars[key].get()
        if not os.path.isfile(path):return messagebox.showinfo('Monitoring audio missing','Choose an available monitoring track. Import stems in Separation or select Original mix.')
        if path==self.monitor_path:
            if play:self.play_word_line()
            return
        self.stop_monitor();self.monitor_generation+=1;generation=self.monitor_generation
        self.lyric_message.set('Loading monitoring audio and waveform…')
        def work():
            try:
                samples=decode_preview(path);mono=np.mean(samples,axis=1) if samples.ndim>1 else samples
                block=max(1,len(mono)//4000);trim=len(mono)//block*block
                peaks=np.max(np.abs(mono[:trim].reshape(-1,block)),axis=1)
                self.lyric_queue.put(('monitor',(generation,path,samples,peaks,play)))
            except Exception as exc:self.lyric_queue.put(('monitor_error',(generation,str(exc))))
        threading.Thread(target=work,daemon=True).start()
    def stop_monitor(self):
        self.monitor_player.stop();self.monitoring=False
    def play_word_line(self):
        if not self.lyric_document.events:return
        key={'Vocals':'vocals','Instrumental':'instrumental','Original mix':'audio'}[self.monitor_choice.get()]
        if self.monitor_path!=self.project_vars[key].get():return self.load_monitor(True)
        self.pause();a,b,_=self.lyric_document.events[self.selected_line]
        try:
            self.monitor_player.play(max(0,a-.25),min(len(self.monitor_samples)/44100,b+.4),loop=self.monitor_loop.get());self.monitoring=True;self.monitor_end=b+.4
        except Exception as exc:self.lyric_message.set('Audio monitoring unavailable: '+str(exc))

    def timeline_window(self):
        center=self.lyric_document.events[self.selected_line][0] if self.lyric_document.events else self.position.get()
        return max(0,center-1),max(2,self.word_zoom.get())
    def draw_word_timeline(self):
        if not hasattr(self,'word_canvas'):return
        c=self.word_canvas;c.delete('all');width=max(1,c.winfo_width());start,span=self.timeline_window()
        if self.waveform is not None and self.wave_duration>0:
            points=[]
            for x in range(0,width,2):
                t=start+x/width*span;idx=int(t/self.wave_duration*len(self.waveform))
                if 0<=idx<len(self.waveform):
                    h=float(self.waveform[idx])*35;c.create_line(x,42-h,x,42+h,fill='#3b779b')
        for i,(a,b,text) in enumerate(self.lyric_document.words.get(str(self.selected_line),[])):
            x1=(a-start)/span*width;x2=(b-start)/span*width
            if x2<0 or x1>width:continue
            color='#67ccbc' if i==self.selected_word else '#345675'
            c.create_rectangle(x1,85,x2,120,fill=color,outline='#91aed0',tags=(f'word{i}',))
            c.create_text((x1+x2)/2,102,text=text,fill='#09121f' if i==self.selected_word else '#eef5ff',width=max(10,x2-x1-4))
        x=(self.position.get()-start)/span*width;c.create_line(x,0,x,145,fill='#ffd578',width=2)
        for n in range(6):c.create_text(n*width/5,134,text=f'{start+n*span/5:.1f}',fill='#a3bad5',anchor='s')
        self.playhead_label.configure(text=f'{self.position.get():.3f} s')
    def timeline_word_press(self,event):
        start,span=self.timeline_window();width=max(1,self.word_canvas.winfo_width());t=start+event.x/width*span
        self.word_drag=None
        for i,(a,b,text) in enumerate(self.lyric_document.words.get(str(self.selected_line),[])):
            if event.y>=80 and a-.08<=t<=b+.08:
                self.selected_word=i;self.word_tree.selection_set(str(i));self.select_lyric_word()
                edge=0 if abs(t-a)<abs(t-b) else 1
                self.word_drag=(i,edge,None);break
        self.position.set(max(0,min(self.length,t)));self.draw_word_timeline()
        if self.monitoring:
            self.stop_monitor()
            try:
                self.monitor_end=min(len(self.monitor_samples)/44100,self.lyric_document.events[self.selected_line][1]+.4)
                if self.position.get()<self.monitor_end:
                    self.monitoring=self.monitor_player.play(self.position.get(),self.monitor_end)
            except Exception as exc:self.lyric_message.set('Monitoring seek failed: '+str(exc))
    def timeline_word_drag(self,event):
        if self.word_drag is None:return
        start,span=self.timeline_window();t=max(0,start+event.x/max(1,self.word_canvas.winfo_width())*span)
        i,edge,_=self.word_drag;self.word_drag=(i,edge,t)
        self.lyric_message.set(f'Release to set word {i+1} '+('start' if edge==0 else 'end')+f' to {t:.3f} s')
    def timeline_word_release(self,event):
        if self.word_drag is None:return
        i,edge,t=self.word_drag;self.word_drag=None
        if t is None:return
        a,b,_=self.lyric_document.words[str(self.selected_line)][i]
        self.edit_lyrics(lambda:self.lyric_document.set_word(self.selected_line,i,t if edge==0 else a,t if edge==1 else b))

    def alignment_setup(self):
        messagebox.showinfo('WhisperX alignment setup','Use the same Python environment as DeRo Sync. Install requirements-alignment.txt after installing a matching PyTorch and torchaudio build for your NVIDIA driver. Run Install_Lyric_Alignment.bat. Model downloads require an internet connection. Existing CUDA packages are preserved by the installer.')
    def set_alignment_running(self,running):
        self.lyrics_editor.configure(state='disabled' if running else 'normal')
        self.auto_sync_lyrics_button.configure(state='disabled' if running else 'normal')

    def alignment_available(self):
        try:return importlib.util.find_spec('whisperx') is not None
        except (ImportError,ValueError):return False

    def start_alignment(self):
        if self.lyric_control is not None:return
        if self.busy:return messagebox.showinfo('Please wait','Finish the current analysis or export before alignment.')
        source=self.vocals.get().strip()
        if not source or not os.path.isfile(source):
            return messagebox.showwarning('Isolated vocals required','Word Sync needs the separated vocal stem. Open Separation and select an existing vocals.wav file, or run Demucs. Your pasted lyrics and existing timings have not been changed.')
        raw=self.lyrics_editor.get('1.0','end-1c')
        lines=[line.strip() for line in raw.splitlines() if line.strip()]
        if not lines:return messagebox.showwarning('Missing lyrics','Paste your correct lyrics first.')
        if not self.alignment_available():return messagebox.showwarning('WhisperX not installed','Install WhisperX in the same Python 3.12 environment using Install_Lyric_Alignment.bat. Check your working PyTorch/CUDA setup before changing it. Existing lyrics and timings have not been changed.')
        if self.lyric_document.words and not messagebox.askyesno('Replace existing word timings?','Automatic alignment will replace existing word timings, including manual edits and review marks. Failed or canceled alignment keeps them. Continue?',default='no'):return
        self.stop_monitor();self.lyric_generation+=1;generation=self.lyric_generation
        snapshot=self.lyric_document.snapshot()
        if raw!=self.lyric_document.text:
            snapshot.update(authoritative_lyrics=raw,events=[],word_timings={},alignment_status={},word_scores={},manual_overrides={})
        snapshot['style']['enabled']=True
        control=ExportControl();self.lyric_control=control
        language={'English':'en','Spanish / Español':'es'}.get(self.song_language.get(),'auto')
        self.set_alignment_running(True)
        self.lyric_message.set('Starting WhisperX alignment…')
        def work():
            try:
                with tempfile.TemporaryDirectory(prefix='dero-align-') as folder:
                    request=Path(folder)/'request.json';result=Path(folder)/'result.json'
                    request.write_text(json.dumps({'source':os.path.abspath(source),'lines':lines,'language':language},ensure_ascii=False),encoding='utf-8')
                    cmd=[sys.executable,'-u',str(Path(__file__).with_name('whisperx_worker.py')),str(request),str(result)]
                    proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',env=dict(os.environ,PYTHONIOENCODING='utf-8'))
                    tail=[]
                    with control.process(proc):
                        for line in proc.stdout:
                            control.check();tail.append(line.strip());tail=tail[-30:]
                            self.lyric_queue.put(('alignment_log',(generation,line.strip())))
                        code=proc.wait();control.check()
                    if code or not result.exists():raise RuntimeError('\n'.join(tail)[-2500:] or 'WhisperX did not return alignment data.')
                    aligned=json.loads(result.read_text(encoding='utf-8'))
                    checked=LyricDocument(snapshot);checked.apply_alignment(aligned)
                    self.lyric_queue.put(('aligned',(generation,checked.snapshot(),aligned[5],aligned[6])))
            except ExportCancelled:self.lyric_queue.put(('alignment_error',(generation,'Alignment canceled. Existing timings kept.')))
            except Exception as exc:self.lyric_queue.put(('alignment_error',(generation,'Alignment failed; existing timings kept. '+str(exc))))
        threading.Thread(target=work,daemon=True).start()
    def cancel_alignment(self):
        if self.lyric_control is not None:self.lyric_control.cancel()

    def lyric_color(self,key):
        color=colorchooser.askcolor(color=self.style_vars[key].get())[1]
        if color:self.style_vars[key].set(color)
    def apply_lyric_style(self):
        def change():
            for key,default in STYLE_DEFAULTS.items():
                value=self.style_vars[key].get()
                self.lyric_document.style[key]=bool(value) if isinstance(default,bool) else int(value) if isinstance(default,int) else float(value) if isinstance(default,float) else value
        return self.edit_lyrics(change)
    def save_ass(self):
        from lyric_ass import ass_file
        if not self.lyric_document.events:return
        path=filedialog.asksaveasfilename(defaultextension='.ass',filetypes=[('ASS subtitles','*.ass')])
        if path:
            try:
                settings=self.settings();ass_file(self.lyric_document.ass_project(),path,settings.width,settings.height)
            except Exception as exc:messagebox.showerror('Could not save subtitles',str(exc))
    def preview_exact_lyrics(self):
        if self.busy:return
        if self.renderer is None:
            self.prepare_preview();return messagebox.showinfo('Preparing preview','Wait for audio analysis, then render the exact frame.')
        if not self.apply_lyric_style():return
        self.pause();settings=self.settings();features=self.features;seconds=self.position.get();snapshot=self.lyric_document.snapshot()
        self.busy=True;self.lyric_message.set('Rendering exact cinematic frame and lyrics…')
        def work():
            try:
                from visualizer_core import Renderer
                frame=exact_frame(Renderer(settings,features),seconds,snapshot)
                self.lyric_queue.put(('exact_frame',frame))
            except Exception as exc:self.lyric_queue.put(('preview_error',str(exc)))
        threading.Thread(target=work,daemon=True).start()
        self.show_inspector('Video Designer')
    def export_short_preview(self):
        if self.length<=0:return self.prepare_preview()
        start=max(0,min(self.position.get(),self.length-.01));end=min(self.length,start+10)
        previous=(self.selection_start.get(),self.selection_end.get())
        try:
            self.selection_start.set(start);self.selection_end.set(end);self.update_selection();self.export_file()
        finally:
            self.selection_start.set(previous[0]);self.selection_end.set(previous[1]);self.update_selection()

    def poll_karaoke(self):
        try:
            while True:
                kind,data=self.lyric_queue.get_nowait()
                if kind=='alignment_log':
                    generation,line=data
                    if generation==self.lyric_generation:self.lyric_message.set(line[-350:])
                elif kind in ('aligned','alignment_error'):
                    if data[0]!=self.lyric_generation:continue
                    self.lyric_control=None;self.set_alignment_running(False)
                    if kind=='aligned':
                        self.remember_lyrics();self.lyric_document=LyricDocument(data[1]);self.alignment_summary=data[2];self.alignment_inspector=data[3];self.refresh_lyrics()
                        self.show_inspector('Word Sync');self.monitor_choice.set('Vocals');self.load_monitor();self.show_alignment_quality()
                    else:self.lyric_message.set(data[1]);messagebox.showerror('Alignment stopped',data[1])
                elif kind=='monitor':
                    generation,path,samples,peaks,play=data
                    if generation!=self.monitor_generation:continue
                    self.monitor_path=path;self.monitor_samples=samples;self.monitor_player.load(samples)
                    self.waveform=peaks;self.wave_duration=len(samples)/44100;self.draw_word_timeline()
                    self.lyric_message.set('Monitoring audio loaded. Choose a line to listen and adjust its words.')
                    if play:self.play_word_line()
                elif kind=='monitor_error':
                    if data[0]==self.monitor_generation:self.lyric_message.set('Monitoring audio failed: '+data[1])
                elif kind=='exact_frame':
                    self.busy=False;self.preview_frame=data;self.fit_preview()
                    shown=data.copy();shown.thumbnail((max(200,self.lyric_preview_label.winfo_width()),max(150,self.lyric_preview_label.winfo_height())))
                    self.lyric_preview_image=ImageTk.PhotoImage(shown);self.lyric_preview_label.configure(image=self.lyric_preview_image,text='')
                    self.lyric_message.set('Exact frame rendered using the final export lyric pipeline.')
                elif kind=='preview_error':self.busy=False;self.lyric_message.set('Exact preview failed: '+data);messagebox.showerror('Preview failed',data)
        except __import__('queue').Empty:pass
        if self.monitoring:
            position=self.monitor_player.position()
            if position is not None:self.position.set(position);self.draw_word_timeline()
            if position is None or (not self.monitor_loop.get() and position>=self.monitor_end):self.stop_monitor()
        self.root.after(100,self.poll_karaoke)

    def show_alignment_quality(self):
        statuses=list(self.lyric_document.data['alignment_status'].values())
        summary='   |   '.join(label+': '+str(statuses.count(key)) for key,label in [('aligned','Timestamp-matched'),('partial','Partial'),('estimated','Estimated'),('failed','Failed')])
        window=tk.Toplevel(self.root);window.title('Synchronization quality');window.transient(self.root)
        frame=ttk.Frame(window,padding=18);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='Synchronization quality',style='Heading.TLabel').pack(anchor='w')
        ttk.Label(frame,text=summary,wraplength=560).pack(anchor='w',pady=12)
        ttk.Label(frame,text='Partial and estimated lines need manual review. Timestamp matches do not guarantee audible accuracy. Your pasted lyrics were preserved.',wraplength=560,style='Muted.TLabel').pack(anchor='w',pady=(0,12))
        row=ttk.Frame(frame);row.pack(fill='x')
        def inspect():window.destroy();self.show_sync_inspector()
        ttk.Button(row,text='Export JSON / Sync Inspector',command=inspect).pack(side='left')
        ttk.Button(row,text='OK',command=window.destroy).pack(side='right');window.grab_set()

    def show_sync_inspector(self):
        if not self.alignment_summary:return messagebox.showinfo('Sync Inspector','Run automatic alignment first to inspect its timestamp matches and quality details.')
        report={'summary':copy.deepcopy(self.alignment_summary),'inspector':copy.deepcopy(self.alignment_inspector)}
        window=tk.Toplevel(self.root);window.title('Sync Inspector');window.geometry('760x520');window.minsize(560,350);window.transient(self.root)
        frame=ttk.Frame(window,padding=14);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='Alignment details',style='Heading.TLabel').pack(anchor='w')
        ttk.Label(frame,text='Includes the recognition transcript and word timing evidence. Export only if you want to save these details.',wraplength=680,style='Muted.TLabel').pack(anchor='w',pady=8)
        box=ttk.Frame(frame);box.pack(fill='both',expand=True)
        text=tk.Text(box,wrap='none',background='#080e19',foreground='#dbe8fa',font=('Consolas',10))
        scroll=ttk.Scrollbar(box,command=text.yview);text.configure(yscrollcommand=scroll.set);scroll.pack(side='right',fill='y');text.pack(fill='both',expand=True)
        encoded=json.dumps(report,ensure_ascii=False,indent=2);text.insert('1.0',encoded);text.configure(state='disabled')
        row=ttk.Frame(frame);row.pack(fill='x',pady=(10,0))
        folder=tk.StringVar(value='')
        def save():
            path=filedialog.asksaveasfilename(parent=window,initialfile=self.filename_stem()+' - Sync Inspector.json',defaultextension='.json',filetypes=[('Sync Inspector JSON','*.json')])
            if not path:return
            try:Path(path).write_text(encoded,encoding='utf-8')
            except OSError as exc:return messagebox.showerror('Could not export Sync Inspector',str(exc),parent=window)
            folder.set(str(Path(path).resolve().parent));open_folder.configure(state='normal')
        ttk.Button(row,text='Export JSON...',command=save).pack(side='left')
        open_folder=ttk.Button(row,text='Open JSON export folder',state='disabled',command=lambda:self._open_path(folder.get()));open_folder.pack(side='left',padx=6)
        ttk.Button(row,text='Close',command=window.destroy).pack(side='right')
