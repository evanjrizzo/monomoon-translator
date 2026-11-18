"""Entry point used by the Windows launcher. No machine-specific configuration."""
import os
import sys
import traceback
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
os.chdir(ROOT)

def show_error(message):
    if sys.platform=='win32':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,message,'Monomoon Translator could not start',0x10)
    else:print(message,file=sys.__stderr__)

def start():
    try:
        log_dir=ROOT/'data'/'logs'
        log_dir.mkdir(parents=True,exist_ok=True)
        # Keep diagnostics with the portable app; windowed Python has no stdout.
        log=(log_dir/'app.log').open('a',encoding='utf-8',buffering=1)
        sys.stdout=sys.stderr=log
        if sys.platform=='win32':
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('MonomoonTranslator.Portable')
        def report(kind,value,tb):
            traceback.print_exception(kind,value,tb,file=log)
            log.flush()
            show_error(f'{value}\n\nDetails are in:\n{log_dir / "app.log"}')
        sys.excepthook=report
        from app import main
        main()
    except SystemExit:
        raise
    except Exception:
        details=traceback.format_exc()
        try:
            sys.stderr.write(details)
            sys.stderr.flush()
        except Exception:pass
        show_error('Monomoon Translator could not start. Extract the whole ZIP to a writable folder, then try again.\n\n'+details)
        raise SystemExit(1)

if __name__=='__main__':start()
