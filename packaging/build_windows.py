"""Build an offline, relocatable Windows x64 folder on Linux or Windows.

Requires Python + pip, a precompiled launcher, and internet on the build machine.
The person receiving the built ZIP needs none of these.
"""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,sys,urllib.request,zipfile

SOURCE=Path(__file__).resolve().parents[1]
PYTHON_VERSION='3.12.10'
PYTHON_URL=f'https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--launcher',type=Path,required=True)
    args=parser.parse_args()
    cache=args.cache.resolve();cache.mkdir(parents=True,exist_ok=True)
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    runtime=output/'runtime';runtime.mkdir(exist_ok=True)
    embed=cache/PYTHON_URL.rsplit('/',1)[1]
    if not embed.exists():urllib.request.urlretrieve(PYTHON_URL,embed)
    subprocess.run([sys.executable,'-m','pip','download','--dest',str(cache),'--only-binary=:all:','--platform','win_amd64','--implementation','cp','--python-version','312','--abi','cp312','-r',str(SOURCE/'requirements-portable.txt')],check=True)
    with zipfile.ZipFile(embed) as z:z.extractall(runtime)
    packages=runtime/'Lib'/'site-packages';packages.mkdir(parents=True,exist_ok=True)
    wanted=('numpy-1.26.4-','opencv_python_headless-4.11.0.86-','pyside6_essentials-6.8.3-','shiboken6-6.8.3-')
    wheels=[p for p in cache.glob('*.whl') if p.name.lower().startswith(wanted)]
    if len(wheels)!=4:raise RuntimeError('Missing or duplicate Windows wheels in cache.')
    for wheel in wheels:
        with zipfile.ZipFile(wheel) as z:z.extractall(packages)
    # Application-local CRTs are already redistributable parts of the Qt wheel.
    for pattern in ('msvcp*.dll','vcruntime*.dll','concrt*.dll'):
        for dll in (packages/'PySide6').glob(pattern):shutil.copy2(dll,runtime/dll.name)
    (runtime/'python312._pth').write_text('python312.zip\n.\n..\nLib/site-packages\nimport site\n',encoding='utf-8')
    for name in ('app.py','ocr.py','paths.py','portable_start.py','portable_check.py','README.md','requirements-portable.txt'):
        shutil.copy2(SOURCE/name,output/name)
    for name in ('assets','examples','packaging','tests'):
        shutil.copytree(SOURCE/name,output/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','.pytest_cache'))
    if (SOURCE/'licenses').exists():shutil.copytree(SOURCE/'licenses',output/'licenses',dirs_exist_ok=True)
    shutil.copy2(args.launcher,output/'Monomoon Translator.exe')
    for folder in ('profiles','exports','logs'):(output/'data'/folder).mkdir(parents=True,exist_ok=True)
    (output/'START HERE.txt').write_text('Monomoon Translator - Windows 10/11, 64-bit\n\n1. Extract the WHOLE ZIP.\n2. Double-click Monomoon Translator.exe.\n3. Paste a screenshot, then click Read screenshot.\n\nNo installation, Python, admin rights, or internet required.\nKeep runtime, examples, assets, and the source files together.\nMove or share this entire folder, including data, to keep your saved profiles and exports.\nAdvanced is optional and contains image controls and alphabet teaching.\nDiagnostics: data/logs/app.log.\n',encoding='utf-8')
    (output/'Check portable runtime.cmd').write_text('@echo off\r\ncd /d "%~dp0"\r\n"%~dp0runtime\\python.exe" -B "%~dp0portable_check.py"\r\necho.\r\necho Results are in data\\logs.\r\npause\r\n',encoding='utf-8')
    (output/'Start with diagnostics.cmd').write_text('@echo off\r\ncd /d "%~dp0"\r\n"%~dp0runtime\\python.exe" -B "%~dp0app.py" %*\r\nif errorlevel 1 pause\r\n',encoding='utf-8')
    manifest={'python':PYTHON_VERSION,'python_url':PYTHON_URL,'inputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [embed,*wheels]}}
    (output/'BUILD-MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(output)
if __name__=='__main__':main()
