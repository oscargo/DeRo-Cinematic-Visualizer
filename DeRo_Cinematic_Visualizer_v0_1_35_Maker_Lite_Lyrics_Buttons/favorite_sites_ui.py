"""Native favorite-site workflow matching Maker Lite's Lyrics tab."""
import tkinter as tk
from tkinter import ttk,messagebox,simpledialog
import webbrowser
from urllib.parse import urlsplit
from lyric_sites import FavoriteSites,checked_site,site_search_url

class FavoriteSitesUI:
    def copy_song_search_to_clipboard(self):
        text=' '.join(value for value in (self.artist.get().strip(),self.title.get().strip()) if value)
        if not text:return ''
        try:
            self.root.clipboard_clear();self.root.clipboard_append(text);self.root.update_idletasks()
            return text if self.root.clipboard_get()==text else ''
        except tk.TclError:return ''

    def show_favorite_sites(self):
        if getattr(self,'favorite_sites_window',None) is not None and self.favorite_sites_window.winfo_exists():
            self.favorite_sites_window.lift();return
        store=FavoriteSites()
        try:sites=store.load()
        except (OSError,ValueError) as exc:
            messagebox.showerror('Could not load favorite sites',str(exc),parent=self.root);return
        copied=self.copy_song_search_to_clipboard()
        window=tk.Toplevel(self.root);self.favorite_sites_window=window
        window.title('Favorite Lyrics Sites');window.geometry('740x380');window.minsize(560,340);window.transient(self.root)
        shell=ttk.Frame(window,padding=16);shell.pack(fill='both',expand=True)
        ttk.Label(shell,text='Favorite lyrics websites',style='Heading.TLabel').pack(anchor='w')
        ttk.Label(shell,text='Saved for all projects. Open a site, copy the lyrics, then paste them into the Lyrics tab.',wraplength=660,style='Muted.TLabel').pack(anchor='w',pady=(5,8))
        status=tk.StringVar(value=('Copied to clipboard: '+copied) if copied else 'Nothing copied. Check Artist and Song on the Song tab.')
        status_label=ttk.Label(shell,textvariable=status,wraplength=660);status_label.pack(anchor='w',pady=(0,8))
        window.bind('<Configure>',lambda e:status_label.configure(wraplength=max(400,window.winfo_width()-40)))
        def recopy():
            value=self.copy_song_search_to_clipboard();status.set('Copied to clipboard: '+value if value else 'Nothing copied. Check Artist and Song on the Song tab.');return value
        ttk.Button(shell,text='Copy artist + song again',command=recopy).pack(anchor='w',pady=(0,8))
        box=ttk.Frame(shell);box.pack(fill='both',expand=True)
        items=tk.Listbox(box,height=6,background='#101c2c',foreground='#dfebfa',selectbackground='#315d86',selectforeground='white',highlightthickness=0,activestyle='none',exportselection=False)
        scroll=ttk.Scrollbar(box,command=items.yview);items.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');items.pack(fill='both',expand=True)
        def refill(index=0):
            items.delete(0,'end')
            for site in sites:
                name=site['name'];host=urlsplit(site['url']).hostname.lower().removeprefix('www.')
                if name.lower().rstrip('/') in (site['url'].lower().rstrip('/'),host,'https://'+host,'http://'+host):
                    name={'azlyrics.com':'AZLyrics','genius.com':'Genius','songlyrics.com':'SongLyrics'}.get(host,host)
                items.insert('end',name+' — '+site['url'])
            if sites:items.selection_set(min(index,len(sites)-1))
        def selected():
            selection=items.curselection();return selection[0] if selection else None
        def persist(proposal,index):
            try:store.save(proposal)
            except (OSError,ValueError) as exc:messagebox.showerror('Could not save favorite sites',str(exc),parent=window);return
            sites[:]=proposal;refill(index)
        def edit(add=False):
            index=selected()
            if not add and index is None:return
            old={} if add else sites[index]
            name=simpledialog.askstring('Site name','Name:',initialvalue=old.get('name',''),parent=window)
            if name is None:return
            url=simpledialog.askstring('Site URL','Website URL (https://...):',initialvalue=old.get('url','https://'),parent=window)
            if url is None:return
            try:entry=checked_site(name,url)
            except ValueError as exc:messagebox.showwarning('Invalid link',str(exc),parent=window);return
            proposal=list(sites)
            if add:proposal.append(entry);index=len(proposal)-1
            else:proposal[index]=entry
            persist(proposal,index)
        def remove():
            index=selected()
            if index is None:return
            if messagebox.askyesno('Remove favorite','Remove this favorite site?',parent=window):
                proposal=list(sites);proposal.pop(index);persist(proposal,max(0,index-1))
        def move(delta):
            index=selected()
            if index is None or not 0<=index+delta<len(sites):return
            proposal=list(sites);proposal[index],proposal[index+delta]=proposal[index+delta],proposal[index];persist(proposal,index+delta)
        def open_selected(search=False):
            index=selected()
            if index is None:return messagebox.showinfo('Select a site','Select a favorite lyrics website first.',parent=window)
            text=recopy();url=sites[index]['url']
            if search:
                if not text:return messagebox.showinfo('Song information needed','Enter the artist and song title on the Song tab before searching.',parent=window)
                url,direct=site_search_url(sites[index],text)
                if not direct:messagebox.showinfo('Manual website search','The artist and song title have been copied. Paste them into the website search box with Ctrl+V.',parent=window)
            try:opened=webbrowser.open(url)
            except Exception as exc:messagebox.showerror('Unable to open link',str(exc),parent=window);return
            if not opened:return messagebox.showwarning('Unable to open link','Could not open the selected website.',parent=window)
            if text:self.root.after(450,self.copy_song_search_to_clipboard)
            window.destroy()
        actions=ttk.Frame(shell);actions.pack(fill='x',pady=(10,6))
        for label,command in [('Search current song',lambda:open_selected(True)),('Open website',open_selected)]:ttk.Button(actions,text=label,command=command).pack(side='left',padx=(0,6))
        manage=ttk.Frame(shell);manage.pack(fill='x')
        for label,command in [('Add',lambda:edit(True)),('Edit',edit),('Remove',remove),('Move up',lambda:move(-1)),('Move down',lambda:move(1))]:ttk.Button(manage,text=label,command=command,padding=(7,5)).pack(side='left',padx=(0,5))
        ttk.Button(manage,text='Close',command=window.destroy).pack(side='right')
        items.bind('<Double-Button-1>',lambda e:open_selected());refill();window.grab_set()
