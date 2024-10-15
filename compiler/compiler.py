# calls the other modules and runs the UCC make compiler
import hashlib
from compiler.base import *
import json

dryrun = False

def merge_dicts(base, priority):
    merged = base.copy()
    for p in priority:
        if isinstance(priority[p], dict):
            merged[p] = merge_dicts(base.get(p, {}), priority[p])
        else:
            merged[p] = priority[p]
    return merged


def run(args):
    if args.verbose:
        args.base.loglevel = 'debug'

    argprofiles = args.profile
    default_settings = {}
    with open('compiler_settings.default.json') as f:
        default_settings = json.load(f)

    settings = {}
    try:
        with open('compiler_settings.json') as f:
            settings = json.load(f)
    except FileNotFoundError as e:
        appendException(e, '\n\nERROR: You need to copy compiler_settings.example.json to compiler_settings.json and adjust the paths.')
        raise

    merged = merge_dicts(default_settings, settings)

    profiles = []
    if argprofiles == 'all':
        profiles = merged.keys()
    else:
        profiles = argprofiles.split(',')

    for p in profiles:
        profile_name = p.strip()
        profile = merged[profile_name]
        if profile['verbose']:
            increase_loglevel(DebugLevels.DEBUG)
        else:
            increase_loglevel(DebugLevels.INFO)
        printHeader("using profile: "+profile_name+", settings:")
        notice(repr(profile)+"\n")
        if not run_profile(args, profile):
            return


def run_profile(args, settings):
    out = settings['out_dir']
    packages = settings['packages']
    run_tests = settings['run_tests']

    copy_local = settings.get('copy_local')
    changed = False
    if settings.get('copy_if_changed'):
        copy_local = True
        gitstatus = None
        try:
            gitstatus = call(['git', 'status'])[1]
        except Exception as e:
            notice("failed to call git status: " + repr(e))
        if gitstatus and re.search(r'%s' % settings.get('copy_if_changed'), gitstatus):
            changed = True

    (compileResult, compileWarnings) = compile(args, settings)
    if compileResult != 0:
        return False

    testSuccess = True
    if run_tests:
        testSuccess = args.tester.runAutomatedTests(out, packages[0])
        for warning in compileWarnings:
            print_colored(warning)

    if not testSuccess:
        return False

    if settings.get('copy_if_changed') and not changed:
        notice("not copying locally because "+settings.get('copy_if_changed')+" has not changed: "+repr(packages))
    elif copy_local:
        copy_package_files(out, packages)
    else:
        notice("not copying locally due to compiler_settings config file: "+repr(packages))

    return True


def compile(args, settings):
    orig_files = {}
    mods_files = []
    injects = {}
    written = {}

    #source = None
    source = None
    if 'source_path' in settings:
        source = settings['source_path']
    mods = settings['mods_paths']
    out_dir = settings['out_dir']
    definitions = settings['preproc_definitions']
    packages = settings['packages']
    rewrite_packages = {}
    if 'rewrite_packages' in settings:
        rewrite_packages = settings['rewrite_packages']
    reader = args.reader
    preprocessor = args.preprocessor
    writer = args.writer

    if source:
        notice("processing source files from "+source)
        for file in insensitive_glob(source+'/*'):
            try:
                reader.proc_file(file, orig_files, 'source', None, preprocessor, definitions)
            except Exception as e:
                appendException(e, "error processing vanilla file: "+file)
                raise
        assert len(orig_files) > 100, 'found original code files in source_path'
        for hashcheck in settings.get('hash_checks', []):
            c = hashcheck['class']
            hash = MD5(orig_files[c].content)
            expected = hashcheck['expected']
            assert hash == expected, 'MD5 of ' + c + ' is ' + hash + ', expected ' + expected
        # helps with unreal-map-flipper
        # a = reader.GetSubclasses('Decoration')
        # for c in a:
        #     print(c+'=0,')
        # sys.exit(0)

    for mod in mods:
        notice("processing files from mod "+mod)
        mods_files.append({})
        for file in insensitive_glob(mod+'*'):
            try:
                if file_is_blacklisted(file, settings):
                    continue
                f = reader.proc_file(file, mods_files[-1], mod, injects, preprocessor, definitions)
                if f and f.namespace in rewrite_packages:
                    f.namespace = rewrite_packages[f.namespace]
            except Exception as e:
                appendException(e, "error processing mod file: "+file)
                raise
        assert len(mods_files[-1]) > 10, 'found code files in '+mod

    notice("\nwriting source files...")
    writer.before_write(orig_files, injects)
    for file in orig_files.values():
        try:
            debug("Writing file "+str(file.file))
            writer.write_file(out_dir, file, written, injects)
        except Exception as e:
            appendException(e, "error writing vanilla file "+str(file.file))
            raise

    for mod in mods_files:
        notice("writing mod "+repr(mod.keys())[:200])
        try:
            writer.before_write(mod, injects)
        except Exception as e:
            appendException(e, "error before_write mod "+repr(mod.keys()))
            raise
        for file in mod.values():
            debug("Writing mod file "+str(file.file))
            try:
                writer.write_file(out_dir, file, written, injects)
            except Exception as e:
                appendException(e, "error writing mod file "+str(file.file))
                raise

    if dryrun:
        return 1

    writer.cleanup(out_dir, written)

    # now we need to delete DeusEx.u otherwise it won't get recompiled, might want to consider support for other packages too
    for package in packages:
        file = out_dir + '/System/'+package+'.u'
        if exists(file):
            notice("Removing old "+file)
            os.remove(file)

    # can set a custom ini file ucc make INI=ProBob.ini https://www.oldunreal.com/wiki/index.php?title=Working_with_*.uc%27s
    # I can run automated tests like ucc Core.HelloWorld
    if not exists_dir(out_dir + '/DeusEx/Inc'):
        os.makedirs(out_dir + '/DeusEx/Inc', exist_ok=True)
    # also we can check UCC.log for success or just the existence of DeusEx.u
    ret = 1
    try:
        (ret, out, errs) = call([ out_dir + '/System/ucc', 'make', '-h', '-NoBind', '-Silent' ])
        warnings = []
        re_terrorist = re.compile(r'((Parsing)|(Compiling)) (([\w\d_]*Terrorist\w*)|(AmmoNone))')
        for line in errs.splitlines():
            if not re_terrorist.match(line):
                warnings.append(line)
    except Exception as e:
        displayCompileError(e)
        return (1, None)

    # TODO: if ret != 0 we should show the end of UCC.log, we could also keep track of compiler warnings to show at the end after the test results

    for package in packages:
        file = out_dir + '/System/'+package+'.u'
        if not exists(file):
            raise RuntimeError("could not find file after compiling: "+file)

    return (ret, warnings)


def displayCompileError(e):
    errs = e.args[2]
    for line in errs.splitlines():
        m = re.match(r'(.*\.uc)\((\d+)\) : Error,', line)
        if m:
            break
    if not m:
        return
    linenum = int(m.group(2))
    with open(m.group(1)) as f:
        lines = f.readlines()
        printError('Code context around line '+str(linenum)+':')
        text = str(linenum-1) + ':' + lines[linenum-2]
        text+= WARNING + str(linenum) + ':' + ENDCOLOR + lines[linenum-1]
        text+= str(linenum) + ':' + lines[linenum]
        print(text)


def copy_package_files(out_dir, packages):
    for package in packages:
        copyPackageFile(out_dir, package)


def copyPackageFile(out, package):
    file = package+'.u'
    if exists(out + '/System/'+file):
        notice(file+" exists")
        shutil.copy(out + '/System/'+file,'./'+file)
        notice(file+" copied locally")
    else:
        raise RuntimeError("could not find "+file)


def file_is_blacklisted(file, settings):
    for b in settings['blacklist']:
        if b in file:
            return True
    return False

def MD5(data) -> str:
    if isinstance(data, str):
        data = data.encode('utf-8')
    ret = hashlib.md5(data).hexdigest()
    debug("MD5 of " + str(len(data)) + " bytes is " + ret)
    return ret
