import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import paths

def test_profile_names_are_windows_safe_and_local(tmp_path,monkeypatch):
    monkeypatch.setattr(paths,'APP_DIR',tmp_path)
    path=paths.profile_suggestion('CON')
    assert path.name=='alphabet_CON.json'
    path=paths.profile_suggestion('my:fictional/letters?')
    assert path.parent==tmp_path/'data'/'profiles'
    assert path.name=='my_fictional_letters_.json'
    assert paths.data_folder('exports')==tmp_path/'data'/'exports'

def test_resource_paths_ignore_working_directory(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert paths.resource('examples','starter-alphabet.json').is_file()
