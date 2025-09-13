# shared code for all compiler modules
import sys
import re
import glob
import datetime
import subprocess
import os.path
import shutil
import traceback
from pathlib import Path
import time
from timeit import default_timer as timer
from enum import Enum, IntEnum

class DebugLevels(IntEnum):
    SILENT = 0
    NOTICE = 1
    INFO = 2
    DEBUG = 3
    TRACE = 4

_loglevel = DebugLevels.INFO

vanilla_inheritance_keywords = [None, 'extends', 'expands']
# text colors
WARNING = '\033[91m'
ENDCOLOR = '\033[0m'
re_error = re.compile(r'((none)|(null)|(warning)|(error[^i])|(fail)|(critical)|(out of bounds)|((^| )time:)|(LoadMap:))', re.IGNORECASE)

def set_loglevel(new_loglevel):
    global _loglevel
    assert isinstance(new_loglevel, DebugLevels), 'loglevel must be of type DebugLevels'
    _loglevel = new_loglevel

def increase_loglevel(new_loglevel):
    global _loglevel
    assert isinstance(new_loglevel, DebugLevels), 'loglevel must be of type DebugLevels'
    assert isinstance(_loglevel, DebugLevels), 'loglevel must be of type DebugLevels'
    if new_loglevel > _loglevel:
        set_loglevel(new_loglevel)

def trace(str):
    global _loglevel
    if _loglevel >= DebugLevels.TRACE:
        print(str)

def debug(str):
    global _loglevel
    if _loglevel >= DebugLevels.DEBUG:
        print(str)

def info(str):
    global _loglevel
    if _loglevel >= DebugLevels.INFO:
        print(str)

def notice(str):
    # this might be useful if we do threading? so we can redirect to a file?
    global _loglevel
    if _loglevel >= DebugLevels.NOTICE:
        print(str)

def prependException(e, msg):
    if not e.args:
        e.args = ("",)
    e.args = (msg + " \n" + e.args[0],) + e.args[1:]

def appendException(e, msg):
    if not e.args:
        e.args = ("",)
    e.args = (str(e.args[0]) + " \n" + str(msg),) + e.args[1:]

def printError(e):
    print(WARNING+e+ENDCOLOR)

def printHeader(text):
    print("")
    print("=====================================================")
    print("            "+text)
    print("=====================================================")
    print("")


def print_colored(msg):
    msg = re_error.sub(WARNING+"\\1"+ENDCOLOR, msg)
    print(msg)

def indent(msg):
    return '\t'+msg.replace('\n', '\n\t')

def read(pipe, outs, errs, verbose):
    o = ''
    if pipe and pipe.readable():
        o += pipe.readline()

    hasWarnings = re_error.search(o)
    if o and (verbose or hasWarnings):
        print_colored(str(datetime.datetime.now().time()) +" "+ o.strip())
    if hasWarnings:
        errs += o
    return outs+o, errs


def call(cmds, verbose=False, stdout=True, stderr=True):
    global _loglevel
    print("\nrunning "+repr(cmds))
    start = timer()
    last_print = start
    if _loglevel >= DebugLevels.TRACE:
        verbose = True

    if stdout:
        stdout = subprocess.PIPE
        if stderr:
            stderr = subprocess.STDOUT
    elif stderr:
        stderr = subprocess.PIPE
        stdout = None
    else:
        stderr = None
        stdout = None

    proc = subprocess.Popen(cmds, stdout=stdout, stderr=stderr, close_fds=True, universal_newlines=True, errors="replace")
    outs = ''
    errs = ''
    pipe = None
    if stdout:
        pipe = proc.stdout
    elif stderr:
        pipe = proc.stderr

    try:
        while proc.returncode is None and timer() - start < 600:
            (outs, errs) = read(pipe, outs, errs, verbose)
            proc.poll()
        if proc.returncode != 0:
            raise Exception("call didn't return 0: "+repr(cmds), outs, errs)
    except Exception as e:
        proc.kill()
        (outs, errs) = read(pipe, outs, errs, verbose)
        proc.poll()
        #print(traceback.format_exc())
        raise
    elapsed_time = timer() - start # in seconds
    print( repr(cmds) + " took " + str(elapsed_time) + " seconds and returned " + str(proc.returncode) + "\n" )
    return (proc.returncode, outs, errs)


def insensitive_glob(pattern):
    return sorted(
        glob.glob(pattern, recursive=True)
        + glob.glob(pattern+'/**', recursive=True)
        + glob.glob(pattern+'/*', recursive=True)
    )


def exists(file):
    exists = os.path.isfile(file)
    # if exists:
    #     print("file already exists: " + file)
    return exists

def exists_dir(path):
    exists = os.path.isdir(path)
    # if exists:
    #     print("dir already exists: " + path)
    return exists

def find_type_dir_path_offset(path):
    typeDirs = ["Classes","Textures","Sounds","Text"]

    lastTypeDirIdx = -1
    found = False

    for idx, pathChunk in enumerate(path):
        if pathChunk in typeDirs:
            found = True
            lastTypeDirIdx = idx

    return found,lastTypeDirIdx



def is_uc_file(file):
    path = list(Path(file).parts)
    if len(path) <3:
        return False

    found,typeIdx = find_type_dir_path_offset(path)

    if not found:
        typeIdx = -2

    namespaceIdx = typeIdx - 1
    parentIdx = typeIdx - 2

    filename = "//".join(path[typeIdx+1:])

    namespace = path[namespaceIdx]
    type = path[typeIdx]
    parent = None
    if not found and len(path) > 3:
        parent = path[-4]
    elif found and parentIdx>=0:
        parent = path[parentIdx]
    if type != 'Classes':
        return False
    if not filename.endswith('.uc'):
        return False

    return True, filename, namespace, parent, type
