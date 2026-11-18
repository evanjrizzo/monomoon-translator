"""Build an application-local Linux x64 bundle using the active Python runtime."""
from pathlib import Path
import argparse,shutil,subprocess,sys
SOURCE=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--work',type=Path,required=True);parser.add_argument('--library',type=Path,action='append',default=[])
    args=parser.parse_args();output=args.output.resolve();work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--name','Monomoon Translator','--distpath',str(output),'--workpath',str(work/'pyinstaller'),'--specpath',str(work),'--add-data',str(SOURCE/'examples')+':examples','--add-data',str(SOURCE/'assets')+':assets','--hidden-import','PySide6.QtSvg','--hidden-import','portable_check','--exclude-module','tkinter','--collect-all','numpy',str(SOURCE/'app.py')],check=True,cwd=SOURCE)
    bundle=output/'Monomoon Translator'
    for library in args.library:shutil.copy2(library,bundle/'_internal'/library.name)
    for folder in ('profiles','exports','logs'):(bundle/'data'/folder).mkdir(parents=True,exist_ok=True)
    shutil.copytree(SOURCE,bundle/'source',ignore=shutil.ignore_patterns('.git','__pycache__','.pytest_cache','data','.venv','build','dist'),dirs_exist_ok=True)
    if (SOURCE/'licenses').exists():shutil.copytree(SOURCE/'licenses',bundle/'licenses',dirs_exist_ok=True)
    (bundle/'Start Monomoon Translator.sh').write_text('#!/usr/bin/env bash\nset -euo pipefail\ncd -- "$(dirname -- "${BASH_SOURCE[0]}")"\nmkdir -p data/logs\nexec "./Monomoon Translator" "$@" >> data/logs/app.log 2>&1\n')
    (bundle/'Start Monomoon Translator.sh').chmod(0o755)
    (bundle/'START HERE.txt').write_text('Monomoon Translator - Linux x64\n\nExtract the entire archive. Open Start Monomoon Translator.sh, or run ./Monomoon\\ Translator in this folder.\nNo Python or package installation required.\nBuilt and tested on Ubuntu/Pop!_OS 24.04 (glibc 2.39). Older distributions may need rebuilding from source.\nKeep _internal and the executable together. Profiles and exports default to data/ beside the executable.\nPortable self-test: ./Monomoon\\ Translator --self-test\n')
    print(bundle)
if __name__=='__main__':main()
