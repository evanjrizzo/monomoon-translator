"""All resources and user data are relative to the app, including portable builds."""
from pathlib import Path
import re
import sys

RESOURCE_DIR=Path(__file__).resolve().parent
APP_DIR=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else RESOURCE_DIR

def resource(*parts):
    return RESOURCE_DIR.joinpath(*parts)

def data_folder(name):
    folder=APP_DIR/'data'/name
    folder.mkdir(parents=True,exist_ok=True)
    return folder

def profile_suggestion(name):
    # Windows filenames exclude these characters, device names and trailing dots.
    safe=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',name).strip(' .')[:90] or 'alphabet'
    if safe.upper().split('.')[0] in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}:
        safe='alphabet_'+safe
    return data_folder('profiles')/(safe+'.json')
