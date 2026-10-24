"""Windows Credential Manager storage for local service secrets (never JSON files)."""
import ctypes as ct
from ctypes import wintypes as wt
import json
import os


class Credential(ct.Structure):
    _fields_ = [('Flags', wt.DWORD), ('Type', wt.DWORD), ('TargetName', wt.LPWSTR),
        ('Comment', wt.LPWSTR), ('LastWritten', wt.FILETIME), ('CredentialBlobSize', wt.DWORD),
        ('CredentialBlob', ct.POINTER(ct.c_ubyte)), ('Persist', wt.DWORD), ('AttributeCount', wt.DWORD),
        ('Attributes', ct.c_void_p), ('TargetAlias', wt.LPWSTR), ('UserName', wt.LPWSTR)]


def api():
    if os.name != 'nt':
        raise RuntimeError('WINDOWS_CREDENTIAL_MANAGER_REQUIRED')
    lib = ct.WinDLL('Advapi32.dll', use_last_error=True)
    lib.CredReadW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ct.POINTER(ct.POINTER(Credential))]
    lib.CredReadW.restype = wt.BOOL
    lib.CredWriteW.argtypes = [ct.POINTER(Credential), wt.DWORD]
    lib.CredWriteW.restype = wt.BOOL
    lib.CredFree.argtypes = [ct.c_void_p]
    return lib


def read(target):
    lib, ptr = api(), ct.POINTER(Credential)()
    if not lib.CredReadW(target, 1, 0, ct.byref(ptr)):
        if ct.get_last_error() == 1168:
            return None
        raise OSError('CREDENTIAL_READ_FAILED')
    try:
        return json.loads(ct.string_at(ptr.contents.CredentialBlob, ptr.contents.CredentialBlobSize).decode('utf-8'))
    finally:
        lib.CredFree(ptr)


def write(target, value):
    lib = api()
    raw = json.dumps(value).encode('utf-8')
    blob = (ct.c_ubyte * len(raw)).from_buffer_copy(raw)
    item = Credential(Type=1, TargetName=target, CredentialBlobSize=len(raw),
                      CredentialBlob=blob, Persist=2, UserName='Hermeneut local services')
    if not lib.CredWriteW(ct.byref(item), 0):
        raise OSError('CREDENTIAL_WRITE_FAILED')
