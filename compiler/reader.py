# read and parse UC files
from compiler.base import *

subclasses = dict()

class OtherFile():
    def __init__(self, mod_name, file, filename, namespace, type):
        self.file = file
        self.mod_name = mod_name
        self.filename = filename
        self.namespace = namespace
        self.type = type
        self.content = None
        with open(self.file, 'rb') as f:
            data = f.read()
            self.binary = False
            if filename.endswith('.txt'):
                if data[:2] == b'\xfe\xff' or data[:2] == b'\xff\xfe': # 'ÿþ'
                    self.content = data.decode('utf-16', 'replace')
                    data = self.content.encode('utf-8', 'replace')
                self.content = data.decode('windows-1252', 'ignore')
                self.content = self.content.replace('\r\n', '\n')
            else:
                self.content = data
                self.binary = True

    @staticmethod
    def ReadOtherFile(mod_name, file):
        path = list(Path(file).parts)
        if len(path) <3:
            return None
        filename = path[-1]
        namespace = path[-3]
        type = path[-2]
        if filename.endswith('.txt') or filename.endswith('.pcx') or filename.endswith('.wav') or filename.endswith('.mp3'):
            return OtherFile(mod_name, file, filename, namespace, type)
        return None


class UnrealScriptFile():
    @staticmethod
    def read_file(mod_name, file, preprocessor, definitions):
        self = UnrealScriptFile()
        self.file = file
        self.mod_name = mod_name
        self.binary = False
        return self._read_file(preprocessor, definitions)


    def _read_file(self, preprocessor, definitions):
        global subclasses
        success, self.filename, self.namespace, self.parentfolder, self.type = is_uc_file(self.file)
        if not success:
            raise RuntimeError( self.file + ' is not an unrealscript file!' )

        self.content = None
        with open(self.file, 'rb') as f:
            data = f.read()
            if data[:2] == b'\xfe\xff' or data[:2] == b'\xff\xfe': # 'ÿþ'
                self.content = data.decode('utf-16', 'replace')
                data = self.content.encode('utf-8', 'replace')
            self.content = data.decode('windows-1252', 'ignore')
            self.content = self.content.replace('\r\n', '\n')
        self.content = preprocessor.preprocessor(self.content, definitions)
        if not self.content:
            info('skipping ' + self.file)
            return None
        self.content_no_comments = self.strip_comments(self.content)
        self.classline = self.get_class_line(self.content_no_comments)
        inheritance = re.search(r'class\s+(?P<classname>\S+)\s+(.*\s+)??((?P<operator>(injects)|(extends)|(expands)|(overwrites)|(merges)|(shims))\s+(?P<baseclass>[^\s;]+))?', self.classline, flags=re.IGNORECASE)
        self.classname = None
        self.operator = None
        self.baseclass = None
        if inheritance is not None:
            self.classname = inheritance.group('classname')
            self.operator = inheritance.group('operator')
            self.baseclass = inheritance.group('baseclass')
            a = subclasses.get(self.baseclass, [])
            a.append(self.classname)
            subclasses[self.baseclass] = a
        else:
            RuntimeError(self.file+" couldn't read class definition")

        # maybe do some assertions on classnames, and verify that classname matches filename?
        self.qualifiedclass = self.namespace+'.'+self.classname
        if self.operator == 'injects' and 'injections' not in definitions:
            self.modify_classline(self.classname, 'extends', self.baseclass)
        return self

    def modify_classline(f, classname, operator, baseclass):
        comment = "// === was "+f.mod_name+'/'
        if f.parentfolder:
            comment += f.parentfolder+'/'
        comment += f.filename+' class '+f.classname+" ===\n"

        oldclassline = f.classline

        re_old = r'class\s+'+f.classname+r'\s+'+f.operator+r'\s+'+f.baseclass
        new_classline = comment + 'class '+classname+' '+operator+' '+baseclass
        f.classline = re.sub(re_old, new_classline, oldclassline, count=1, flags=re.IGNORECASE)
        f.classname = classname
        f.operator = operator
        f.baseclass = baseclass
        #re.sub doesn't match for a multiline classline (like the harry class in HP2), so use a string replace
        f.content = f.content.replace(oldclassline,f.classline)

    def __repr__(self):
        return self.classline

    @staticmethod
    def get_class_line(content):
        classline = re.search( r'(class .+?;)', content, flags=re.IGNORECASE | re.DOTALL)
        if classline is not None:
            classline = classline.group(0)
        else:
            print(content[:5000])
            raise RuntimeError('Could not find classline')
        return classline

    @staticmethod
    def strip_comments(content):
        content_no_comments = re.sub(r'//.*', ' ', content)
        content_no_comments = re.sub(r'/\*.*?\*/', ' ', content_no_comments, flags=re.DOTALL)
        return content_no_comments


def proc_file(file, files, mod_name, injects, preprocessor, definitions):
    debug("Processing "+file+" from "+mod_name)
    if not exists(file):
        return
    if not is_uc_file(file):
        f = OtherFile.ReadOtherFile(mod_name, file)
        if f is None:
            return
        files[file] = f
        return f

    if not hasattr(proc_file,"last_folder"):
        proc_file.last_folder=""
    folder = Path(file).parent
    if folder != proc_file.last_folder:
        info("Processing folder "+str(folder)[-50:]+" from "+mod_name)
    proc_file.last_folder = folder

    f = UnrealScriptFile.read_file(mod_name, file, preprocessor, definitions)
    if f is None:
        return

    if f.operator not in vanilla_inheritance_keywords:
        key = f.namespace+'.'+f.baseclass
        if key not in injects:
            injects[key] = [ ]
        injects[key].append(f)
    files[f.qualifiedclass] = f
    return f


def GetSubclasses(baseclass: str) -> list:
    global subclasses
    ret = []
    for c in subclasses.get(baseclass, []):
        ret.append(c)
        ret.extend(GetSubclasses(c))
    return ret
