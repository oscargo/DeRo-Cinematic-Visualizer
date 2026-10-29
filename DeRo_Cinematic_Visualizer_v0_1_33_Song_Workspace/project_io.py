"""Versioned project documents; media is referenced, never embedded."""
from video_encoder import ENCODER_CHOICES
import json
import math
import os
from pathlib import Path

DEFAULTS = {
    'export_encoder':ENCODER_CHOICES[0],
    'song_language':'Auto Detect','demucs_model':'High quality — HTDemucs Fine-Tuned',
    'instrumental':'','vocals':'','audio_track':'Original mix',
    'spectrum_mapping':'Stepped','spectrum_style':'Classic bars','spectrum_mirrored':True,'spectrum_density':100.0,
    'spectrum_fill':58.0,'spectrum_color_end':'#35a5ff',
    'frequency_min':50.0,'frequency_max':10584.0,'frequency_scale':'Linear',
    'particle_continuous':True,'particles_enabled':True,'particle_reactivity':'Bass','particle_direction':'Out','particle_reactive':True,
    'particle_color':'#ebeef7','spectrum_color':'#f0f6ff',
    'overlay_enabled':False,'overlay_path':'','overlay_size':20.0,'overlay_x':50.0,
    'overlay_y':50.0,'overlay_opacity':100.0,'overlay_shape':'Original',
    'auto_open_export':True, 'completion_sound':True, 'preview_sound':True, 'audio':'', 'background':'', 'title':'', 'dust':130, 'reactive':24,
    'sensitivity':3.0, 'fps':60, 'bands':384, 'res':'1920 x 1080',
    'title_size':12.0, 'title_x':50.0, 'title_y':42.0, 'title_font':'Sans',
    'title_bold':False, 'title_italic':False, 'title_uppercase':False,
    'title_color':'#f8f9fd', 'spectrum_width':80.0, 'spectrum_x':50.0,
    'spectrum_y':90.0, 'spectrum_height':19.8, 'particle_speed':20.0, 'spectrum_gain':1.5,
}
# Artist is a separate text row with its own appearance and position.
for key in ('size','x','y','font','bold','italic','uppercase','color'):
    DEFAULTS['artist_'+key]=DEFAULTS['title_'+key]
DEFAULTS.update(artist='',artist_size=8.0,artist_y=58.5)


RANGES = {'frequency_min':(20,19999),'frequency_max':(21,20000),'spectrum_density':(25,200),'spectrum_fill':(10,100),'bands':(16,2048),'overlay_size':(1,100),'overlay_x':(0,100),'overlay_y':(0,100),'overlay_opacity':(0,100),'spectrum_gain':(.1,3),'particle_speed':(.1,30),'dust':(0,800),'reactive':(0,100),'sensitivity':(.1,3),
          'title_size':(.5,12),'title_x':(0,100),'title_y':(0,100),
          'spectrum_width':(10,100),'spectrum_x':(0,100),'spectrum_y':(0,100),
          'spectrum_height':(1,30)}
CHOICES = {'export_encoder':ENCODER_CHOICES,
           'song_language':('Auto Detect','English','Spanish / Español'),
           'demucs_model':('High quality — HTDemucs Fine-Tuned','Standard — HTDemucs'),
           'audio_track':('Original mix','Instrumental','Vocals'),'spectrum_mapping':('Stepped','Balanced','Smooth'),'particle_reactivity':('Bass','Vocals / Midrange','Treble','Displayed range'),'spectrum_style':('Classic bars','Gradient bars','Glow bars','Reflected bars','Filled spectrum'),'frequency_scale':('Logarithmic','Linear'),'particle_direction':('Out','Left','Right','Up','Down'),'overlay_shape':('Original','Circle'),'fps':(30,60),
           'res':('1920 x 1080','1280 x 720','854 x 480'), 'title_font':('Sans','Serif','Mono')}

for key in ('size','x','y'):
    RANGES['artist_'+key]=RANGES['title_'+key]
CHOICES['artist_font']=CHOICES['title_font']


def validate_settings(values):
    if not isinstance(values,dict):raise ValueError('Project settings must be an object.')
    result=dict(DEFAULTS)
    for key,default in DEFAULTS.items():
        value=values.get(key,values.get('sensitivity',default) if key=='spectrum_gain' else default)
        if isinstance(default,bool):valid=isinstance(value,bool)
        elif isinstance(default,(int,float)):
            valid=isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)
            if isinstance(default,int):valid=valid and int(value)==value
        else:valid=isinstance(value,str)
        if not valid:raise ValueError(f'Invalid project setting: {key}')
        if key in RANGES and not RANGES[key][0]<=value<=RANGES[key][1]:
            raise ValueError(f'Project setting out of range: {key}')
        if key in CHOICES and value not in CHOICES[key]:raise ValueError(f'Unsupported {key}')
        result[key]=value
    for name in ('title_color','artist_color','particle_color','spectrum_color','spectrum_color_end'):
        color=result[name]
        if len(color)!=7 or color[0]!='#' or any(c not in '0123456789abcdefABCDEF' for c in color[1:]):
            raise ValueError('Text color must be a hex color (#RRGGBB).')
    if result['frequency_min']>=result['frequency_max']:
        raise ValueError('Minimum frequency must be lower than maximum frequency.')
    return result


def save_project(path,settings,start=0,end=None):
    path=Path(path).resolve()
    values=validate_settings(settings)
    selection=validate_selection([start,end])
    for key in ('audio','background','overlay_path','instrumental','vocals'):
        if values[key]:
            try:values[key]=os.path.relpath(os.path.abspath(values[key]),path.parent)
            except ValueError:values[key]=os.path.abspath(values[key])
    data={'format':'dero-visualizer-project','version':1,'settings':values,'selection':selection}
    temporary=path.with_name(path.name+'.tmp')
    try:
        temporary.write_text(json.dumps(data,indent=2),encoding='utf-8')
        os.replace(temporary,path)
    finally:
        if temporary.exists():temporary.unlink()


def validate_selection(selection):
    if not isinstance(selection,list) or len(selection)!=2:raise ValueError('Invalid project selection.')
    start,end=selection
    for value in (start,end):
        if value is not None and (isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value)):
            raise ValueError('Invalid selection time.')
    if start is None or start<0 or (end is not None and end<=start):raise ValueError('Invalid selection range.')
    return [start,end]


def load_project(path):
    path=Path(path).resolve()
    data=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data,dict) or data.get('format')!='dero-visualizer-project' or data.get('version')!=1:
        raise ValueError('Not a supported DeRo project.')
    values=validate_settings(data.get('settings'))
    for key in ('audio','background','overlay_path','instrumental','vocals'):
        if values[key]:values[key]=str((path.parent/values[key]).resolve())
    return values,validate_selection(data.get('selection',[0,None]))
