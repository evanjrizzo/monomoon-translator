#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#include <windows.h>
#include <shellapi.h>
#include <wchar.h>
#include <stdlib.h>

/* Quote one Windows argument, including trailing slashes and embedded quotes. */
static int quote(wchar_t *out,size_t cap,size_t *at,const wchar_t *arg) {
#define PUT(c) do { if (*at+1>=cap) return 0; out[(*at)++]=(c); } while (0)
    PUT(L'"');
    while (*arg) {
        size_t slashes=0;
        while (*arg==L'\\') {slashes++;arg++;}
        if (*arg==L'"' || !*arg) {
            for(size_t i=0;i<slashes*2;i++) PUT(L'\\');
            if (*arg==L'"') {PUT(L'\\');PUT(*arg++);}
        } else {
            for(size_t i=0;i<slashes;i++) PUT(L'\\');
            PUT(*arg++);
        }
    }
    PUT(L'"');out[*at]=0;return 1;
#undef PUT
}
int WINAPI wWinMain(HINSTANCE instance,HINSTANCE previous,PWSTR line,int show) {
    (void)instance;(void)previous;(void)line;(void)show;
    wchar_t root[32768],python[32768],script[32768],command[32768];
    DWORD length=GetModuleFileNameW(NULL,root,32768);
    if (!length || length>=32768) return 1;
    wchar_t *slash=wcsrchr(root,L'\\');if (!slash) return 1;*slash=0;
    if (wcslen(root)>32000) return 1;
    swprintf(python,32768,L"%ls\\runtime\\pythonw.exe",root);
    swprintf(script,32768,L"%ls\\portable_start.py",root);
    int argc=0;wchar_t **argv=CommandLineToArgvW(GetCommandLineW(),&argc);
    size_t at=0;int okay=quote(command,32768,&at,python);
    if (okay && at+4<32768) {wcscpy(command+at,L" -B ");at+=4;}else okay=0;
    if (okay) okay=quote(command,32768,&at,script);
    for(int i=1;okay && i<argc;i++) {
        if (at+2>=32768) {okay=0;break;}
        command[at++]=L' ';okay=quote(command,32768,&at,argv[i]);
    }
    if(argv) LocalFree(argv);
    if(!okay) {MessageBoxW(NULL,L"The file path is too long.",L"Monomoon Translator",MB_ICONERROR);return 1;}
    STARTUPINFOW startup={0};startup.cb=sizeof(startup);
    PROCESS_INFORMATION process={0};
    if (!CreateProcessW(python,command,NULL,NULL,FALSE,CREATE_NO_WINDOW,NULL,root,&startup,&process)) {
        MessageBoxW(NULL,L"Cannot start Monomoon Translator. Extract the ENTIRE ZIP first. Keep the runtime folder beside Monomoon Translator.exe.",L"Monomoon Translator",MB_ICONERROR);return 1;
    }
    CloseHandle(process.hThread);CloseHandle(process.hProcess);return 0;
}
