# SPDX-License-Identifier: BSD-3-Clause

'''Export data in CSV format
'''

from Page import FabResource, Responder
from authentication import LoginAuthPage
from pageargs import EnumArg, PageArgs
from webgui import pageLink
from xmlgen import xhtml

from enum import Enum

class Separator(Enum):
    '''Identifies the separator character to place between values.
    The reason for allowing different separator characters than the comma is
    that Excel only accepts the separator character of the active locale.
    This is an utterly stupid idea, but many people use Excel so we have to
    work around its idiocies.
    '''
    COMMA = ','
    SEMICOLON = ';'
    TAB = '\t'

class CSVPage(FabResource, Responder):
    authenticationWrapper = LoginAuthPage

    class Arguments(PageArgs):
        sep = EnumArg(Separator, Separator.COMMA)

    def respond(self, response, proc):
        response.setHeader('Content-Type', 'text/x-csv; charset=UTF-8')
        response.setFileName(self.getFileName(proc))
        sepChar = proc.args.sep.value
        for row in self.iterRows(proc):
            response.write(sepChar.join(row), '\r\n')

    def getFileName(self, proc):
        raise NotImplementedError

    def iterRows(self, proc):
        raise NotImplementedError

def presentCSVLink(page, args):
    return xhtml.p[
        'Export data in CSV format: ',
        pageLink(page, args.override(sep = Separator.COMMA))[ 'comma' ],
        ' or ',
        pageLink(page, args.override(sep = Separator.SEMICOLON))[ 'semicolon' ],
        ' separated',
        xhtml.br,
        'Note: Excel only accepts the list separator from the OS regional '
        'settings.'
        ]
