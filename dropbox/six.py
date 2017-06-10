import sys

def b(str_):
    if sys.version_info >= (3,):
        str_ = str_.encode('latin1')
    return str_

def u(str_):
    if sys.version_info < (3,):
        str_ = str_.decode('latin1')
    return str_
