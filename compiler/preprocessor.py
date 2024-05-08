# handles ifdef so we can exclude/include code depending on compiler flags, like if we want to build on top of another mod
from compiler.base import *

# in (?=(?P<next>#\w+))
# the # symbol is for a lookahead
# because we want to read up until the next preprocessor directive (like the next #elseif, #else, or #endif)
# but we don't want to swallow it yet
re_split_ifdef = re.compile(r'(?P<ifdef>#[^\s]+)( (?P<cond>[^\s]+))?\n(?P<code>.*?)\n(?=(?P<next>#\w+))', flags=re.DOTALL)

re_comment_out = re.compile(r'^', flags=re.MULTILINE) # for a regex substitution with //
re_compileif = re.compile(r'(#dontcompileif|#compileif) (.+)')
re_replace_vars = re.compile(r'#var\((\w+?)\)')
re_replace_defineds = re.compile(r'#defined\((.+?)\)')

# for finding the start and end of an ifdef block:
re_find_ifdefs = re.compile(r'((#ifdef )|(#ifndef ))(.*?)(#endif)', flags=re.DOTALL)

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


def preprocess(content: str, ifdef: str, definitions: dict):
    removed_code_before = ''
    removed_code_after = ''
    replacement = None
    counts = {'#ifdef':0, '#ifndef':0, '#else':0, '#elseif':0, '#elseifn':0}

    for i in re_split_ifdef.finditer(ifdef):
        counts[i.group('ifdef')] += 1

        ifdeftext = i.group('ifdef')
        if i.group('cond'):
            ifdeftext += ' ' + i.group('cond')
        ifdeftext += '\n'
        blocktext = ifdeftext + i.group('code')
        if i.group('next'):
            blocktext += '\n'
        commentedtext = re_comment_out.sub('//', blocktext)

        if replacement is not None:
            removed_code_after += commentedtext

        elif bIfdef(i.group('ifdef'), i.group('cond'), definitions):
            removed_code_before += '//' + ifdeftext
            replacement = i.group('code')
            removed_code_after += '\n'

        elif replacement is None:
            removed_code_before += commentedtext

        if i.group('next') == '#endif':
            removed_code_after += '//#endif'

    # warnings
    num_lines = ifdef.count('\n')
    if num_lines > 200:
        # this is a strong warning to refactor the code
        raise Exception("ifdef is "+str(num_lines)+" lines long!")
    if counts['#ifdef'] + counts['#ifndef'] != 1:
        raise Exception("ifdef has "+str(counts['#ifdef'] + counts['#ifndef'])+" #ifdefs/#ifndefs")
    if counts['#elseif'] + counts['#elseifn'] > 20:
        # this is a strong warning to refactor the code
        raise Exception("ifdef has "+str(counts['#elseif'] + counts['#elseifn'])+" #elseifs/#elseifns")
    if counts['#else'] > 1:
        raise Exception("ifdef has "+str(counts['#else'])+" #elses")

    if replacement is None:
        replacement = ""


    replacement = removed_code_before + replacement + removed_code_after
    return content.replace( ifdef, replacement )


def replace_checkcompile(content, definitions):
    content_out = content
    for i in re_compileif.finditer(content):
        cond = proc_conditions(i.group(2), definitions)
        if i.group(1) == '#dontcompileif' and cond:
            return None
        elif i.group(1) == '#compileif' and not cond:
            return None

        content_out = content_out.replace( i.group(0), '// ' + i.group(0) )
    return content_out


def replace_vars(content, definitions):
    content_out = content
    for i in re_replace_vars.finditer(content):
        if i.group(1) in definitions:
            content_out = content_out.replace( i.group(0), definitions[i.group(1)] )
        else:
            content_out = content_out.replace( i.group(0), "None" )
    return content_out


def replace_defineds(content, definitions):
    content_out = content
    for i in re_replace_defineds.finditer(content):
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
    for i in re_find_ifdefs.finditer(content):
        content_out = preprocess(content_out, i.group(0), definitions)
    assert num_lines == content_out.count('\n')
    return content_out
