"""Shared authoritative lyric/timing model for editing, preview, ASS and export."""
import copy
import math
import re
from lyric_ass import check_word_timing_integrity

STYLE_DEFAULTS={
 'enabled':False,'lyric_display_mode':'single','lyric_font_family':'Arial','lyric_font_size':72,
 'lyric_font_bold':True,'lyric_outline':3,'lyric_vertical_percent':53,
 'lyric_unsung_color':'#EAF3FF','lyric_sung_color':'#31B9FF','lyric_lead_seconds':2.,
 'classic_flow_lines':3,'classic_flow_fade_in':300,'classic_flow_fade_out':400,
 'lyric_exit':'Fade Out','lyric_exit_duration':300,'lyric_exit_delay':150,
 'lyric_final_fade_out':2000,'opening_progress_enabled':True,'opening_progress_duration':5.,
 'opening_progress_before':5.,'silence_progress_enabled':False,'silence_progress_threshold':5.,
 'show_identity':False,'identity_intro_seconds':5.}


def _number(value):
 if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError('Timing must be a finite number.')
 return float(value)


class LyricDocument:
 def __init__(self,data=None):
  self.data={'schema_version':1,'authoritative_lyrics':'','events':[],'word_timings':{},
             'alignment_status':{},'word_scores':{},'manual_overrides':{},'alignment_summary':{},'sync_inspector':{},'style':copy.deepcopy(STYLE_DEFAULTS)}
  if data is not None:
   if not isinstance(data,dict):raise ValueError('Lyrics must be a document object.')
   if data.get('schema_version',1)!=1:raise ValueError('Unsupported lyric document version.')
   for key in self.data:
    if key!='style' and key in data:self.data[key]=copy.deepcopy(data[key])
   if not isinstance(data.get('style',{}),dict):raise ValueError('Lyric style must be an object.')
   self.data['style'].update({k:v for k,v in data.get('style',{}).items() if k in STYLE_DEFAULTS})
  self.validate()

 @property
 def text(self):return self.data['authoritative_lyrics']
 @property
 def events(self):return self.data['events']
 @property
 def words(self):return self.data['word_timings']
 @property
 def style(self):return self.data['style']
 def snapshot(self):return copy.deepcopy(self.data)
 def ass_project(self):return dict(self.snapshot(),**copy.deepcopy(self.style))

 def validate(self):
  if not isinstance(self.text,str):raise ValueError('Authoritative lyrics must be text.')
  if not isinstance(self.events,list) or not isinstance(self.words,dict):raise ValueError('Malformed lyric events or word timings.')
  lines=[line.strip() for line in self.text.splitlines() if line.strip()]
  if self.events and len(self.events)!=len(lines):raise ValueError('Line timings do not match the authoritative lyrics.')
  for i,event in enumerate(self.events):
   if not isinstance(event,(list,tuple)) or len(event)!=3:raise ValueError('Malformed lyric line.')
   a,b,text=event
   if _number(a)<0 or _number(b)<=a or text!=lines[i]:raise ValueError('Invalid line time or changed lyric text.')
   words=self.words.get(str(i),[])
   if not isinstance(words,list) or any(not isinstance(w,(list,tuple)) or len(w)!=3 for w in words):raise ValueError('Malformed timed word.')
   if words and [w[2] for w in words]!=lines[i].split():raise ValueError('Timed words must match the authoritative lyric words exactly.')
   for word in words:
    if not isinstance(word,(list,tuple)) or len(word)!=3:raise ValueError('Malformed timed word.')
    if _number(word[0])<0 or _number(word[1])<=word[0]:raise ValueError('Word end must be after its start.')
  for key in self.words:
   if not isinstance(key,str) or not key.isdigit() or str(int(key))!=key or int(key)>=len(self.events):raise ValueError('Word timings reference an unknown line.')
  for key in ('alignment_status','word_scores','manual_overrides','alignment_summary','sync_inspector'):
   if not isinstance(self.data[key],dict):raise ValueError('Invalid lyric review metadata.')
  for key,default in STYLE_DEFAULTS.items():
   value=self.style[key]
   if isinstance(default,bool):
    if not isinstance(value,bool):raise ValueError('Invalid lyric style: '+key)
   elif isinstance(default,(int,float)):_number(value)
   elif not isinstance(value,str):raise ValueError('Invalid lyric style: '+key)
  if self.style['lyric_display_mode'] not in ('single','preview','alternating','classic_flow'):raise ValueError('Unknown lyric display mode.')
  if self.style['lyric_exit'] not in ('Fade Out','None'):raise ValueError('Unknown lyric exit effect.')
  for key in ('lyric_unsung_color','lyric_sung_color'):
   if not re.fullmatch(r'#[0-9A-Fa-f]{6}',self.style[key]):raise ValueError('Lyric colors must use #RRGGBB.')
  limits={'lyric_font_size':(24,120),'lyric_outline':(0,8),'lyric_vertical_percent':(12,88),
          'lyric_lead_seconds':(0,5),'classic_flow_lines':(2,3),'opening_progress_duration':(.5,20),
          'opening_progress_before':(0,30),'silence_progress_threshold':(1,60),
          'identity_intro_seconds':(0,30),'lyric_exit_duration':(0,5000),'lyric_exit_delay':(0,1000),
          'lyric_final_fade_out':(0,5000),'classic_flow_fade_in':(0,1500),'classic_flow_fade_out':(0,2000)}
  for key,(low,high) in limits.items():
   if not low<=self.style[key]<=high:raise ValueError('Lyric style out of range: '+key)
  return self

 def set_text(self,text,duration,start=0):
  if not isinstance(text,str):raise ValueError('Paste lyric text first.')
  lines=[line.strip() for line in text.splitlines() if line.strip()]
  duration=_number(duration);start=_number(start)
  if not lines or duration<=start:raise ValueError('Load a song and paste at least one lyric line.')
  from lyric_alignment import estimate_line_timings
  result=LyricDocument();result.data['style']=copy.deepcopy(self.style);result.style['enabled']=True
  result.data['authoritative_lyrics']=text
  total=sum(len(line.split()) for line in lines);cursor=start
  for i,line in enumerate(lines):
   end=cursor+(duration-start)*len(line.split())/total
   result.events.append([cursor,end,line]);result.words[str(i)]=estimate_line_timings(line.split(),cursor,end)
   result.data['alignment_status'][str(i)]='estimated';cursor=end
  result.validate();self.data=result.data

 def apply_alignment(self,result):
  events,words,language,statuses,scores,summary,inspector=result
  proposal=self.snapshot();proposal.update(events=events,word_timings=words,alignment_status=statuses,
       word_scores=scores,manual_overrides={},alignment_summary=summary,sync_inspector=inspector)
  checked=LyricDocument(proposal)
  self.data=checked.data
  return language,summary,inspector

 def set_word(self,line,index,start,end):
  start=_number(start);end=_number(end)
  if start<0 or end<=start:raise ValueError('Word end must be after its start.')
  words=self.words[str(line)]
  words[index]=[round(start,3),round(end,3),words[index][2]]
  self.events[line][0]=min(w[0] for w in words);self.events[line][1]=max(w[1] for w in words)
  key=str(line);previous=self.data['alignment_status'].get(key,'estimated')
  edited=self.data['manual_overrides'].get(key,[])
  edited=list(edited) if isinstance(edited,list) else []
  if index not in edited:edited.append(index)
  self.data['manual_overrides'][key]=edited
  self.data['alignment_status'][key]='manual' if previous in ('aligned','manual','reviewed') or len(edited)==len(words) else 'partial'
  self.validate()

 def set_line_bounds(self,line,start,end):
  start=_number(start);end=_number(end)
  if start<0 or end<=start:raise ValueError('Line end must be after its start.')
  old_a,old_b,_=self.events[line];scale=(end-start)/(old_b-old_a)
  for word in self.words[str(line)]:word[0]=start+(word[0]-old_a)*scale;word[1]=start+(word[1]-old_a)*scale
  self.events[line][0:2]=[start,end];self.data['alignment_status'][str(line)]='manual';self.validate()

 def shift(self,seconds):
  seconds=_number(seconds)
  if self.events and min(e[0] for e in self.events)+seconds<0:raise ValueError('The shift would put lyrics before the song starts.')
  for event in self.events:event[0]+=seconds;event[1]+=seconds
  for words in self.words.values():
   for word in words:word[0]+=seconds;word[1]+=seconds
  self.validate()

 def warnings(self):
  result=check_word_timing_integrity(self.data)
  for i,event in enumerate(self.events):
   if i and event[0]<self.events[i-1][1]:result.append(f'Line {i+1}: overlaps the previous lyric line; review its order and bounds')
   if self.data['alignment_status'].get(str(i),'estimated') not in ('aligned','manual','reviewed'):
    result.append(f'Line {i+1}: '+self.data['alignment_status'].get(str(i),'estimated')+' timings need review')
  return result

 def identity_visible(self,seconds):
  return self.style['show_identity'] or not self.style['enabled'] or not self.events or seconds<min(self.events[0][0],self.style['identity_intro_seconds'])
