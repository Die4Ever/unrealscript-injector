# handles ifdef so we can exclude/include code depending on compiler flags, like if we want to build on top of another mod
from compiler.base import *

def proc_conditions(cond, definitions):
    if '&&' in cond:
        if '||' in cond:
            raise RuntimeError("We don't currently support mixed && with || in preprocessor conditions: " + cond)
        ands = True
        vars = cond.split('&&')
    else:
        ands = False
        vars = cond.split('||')

    for var in vars:
        if var.strip() in definitions:
            if not ands:
                return True
        elif ands:
            return False

    return ands


def bIfdef(ifdef, cond, definitions):
    if ifdef == '#else':
        return True
    #var = re.search( r'(#\w+) (.*)$', ifdef )
    if ifdef == '#ifdef' or ifdef == '#elseif':
        return proc_conditions(cond, definitions)
    elif ifdef == '#ifndef' or ifdef == '#elseifn':
        return not proc_conditions(cond, definitions)

    raise RuntimeError("Unknown preprocessor "+ifdef+' '+cond)


def preprocess(content, ifdef, definitions):
    # the ?=(#\w+) is for a lookahead
    # because we want to read up until the next preprocessor directive
    # but we don't want to swallow it yet
    r = re.compile(r'(?P<ifdef>#[^\s]+)( (?P<cond>[^\s]+))?\n(?P<code>.*?)\n(?=(?P<next>#\w+))', flags=re.DOTALL)

    # pad the new lines so the errors coming from the compiler match the lines in the original files
    num_lines_before = 0
    num_lines_after = 1 # 1 for the #endif
    replacement = None
    num_lines = 0
    counts = {'#ifdef':0, '#ifndef':0, '#else':0, '#elseif':0, '#elseifn':0}

    for i in r.finditer(ifdef):
        counts[i.group('ifdef')] += 1

        if replacement is not None:
            num_lines_after += i.group('code').count('\n') + 2

        elif bIfdef(i.group('ifdef'), i.group('cond'), definitions):
            num_lines_before += 1
            replacement = i.group('code')
            num_lines = replacement.count('\n')

        elif replacement is None:
            num_lines_before += i.group('code').count('\n') + 2

    if num_lines_before + num_lines + num_lines_after > 200:
        # this is a strong warning to refactor the code
        raise Exception("ifdef is "+str(num_lines_before + num_lines + num_lines_after)+" lines long!")
    if counts['#ifdef'] + counts['#ifndef'] != 1:
        raise Exception("ifdef has "+str(counts['#ifdef'] + counts['#ifndef'])+" #ifdefs/#ifndefs")
    if counts['#elseif'] + counts['#elseifn'] > 20:
        # this is a strong warning to refactor the code
        raise Exception("ifdef has "+str(counts['#elseif'] + counts['#elseifn'])+" #elseifs/#elseifns")
    if counts['#else'] > 1:
        raise Exception("ifdef has "+str(counts['#else'])+" #elses")

    if replacement is None:
        replacement = ""
        num_lines_before -= 1

    if replacement is not None:
        replacement = ('\n'*num_lines_before) + replacement + ('\n'*num_lines_after)
        return content.replace( ifdef, replacement )
    return content


def replace_checkcompile(content, definitions):
    r = re.compile(r'(#dontcompileif|#compileif) (.+)')
    content_out = content
    for i in r.finditer(content):
        cond = proc_conditions(i.group(2), definitions)
        if i.group(1) == '#dontcompileif' and cond:
            return None
        elif i.group(1) == '#compileif' and not cond:
            return None

        vars = i.group(1).split('||')
        for var in vars:
            if var.strip() in definitions:
                return None
        content_out = content_out.replace( i.group(0), '' )
    return content_out


def replace_vars(content, definitions):
    r = re.compile(r'#var\((\w+?)\)')
    content_out = content
    for i in r.finditer(content):
        if i.group(1) in definitions:
            content_out = content_out.replace( i.group(0), definitions[i.group(1)] )
        else:
            content_out = content_out.replace( i.group(0), "None" )
    return content_out


def replace_defineds(content, definitions):
    r = re.compile(r'#defined\((.+?)\)')
    content_out = content
    for i in r.finditer(content):
        if proc_conditions(i.group(1), definitions):
            content_out = content_out.replace( i.group(0), 'true' )
        else:
            content_out = content_out.replace( i.group(0), 'false' )
    return content_out


def preprocessor(content, definitions):
    # TODO: doesn't yet support nested preprocessor definitions
    num_lines = content.count('\n')
    content = replace_checkcompile(content, definitions)
    if not content:
        return None
    content = replace_vars(content, definitions)
    content = replace_defineds(content, definitions)
    content_out = content
    r = re.compile(r'((#ifdef )|(#ifndef ))(.*?)(#endif)', flags=re.DOTALL)
    for i in r.finditer(content):
        content_out = preprocess(content_out, i.group(0), definitions)
    assert num_lines == content_out.count('\n')
    return content_out
