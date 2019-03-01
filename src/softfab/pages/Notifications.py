# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum
import re

from twisted import version as twistedVersion

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor, PresentableError, Redirect
from softfab.formlib import actionButtons, makeForm, textInput
from softfab.notification import sendmail
from softfab.pageargs import EnumArg, PageArgs, StrArg
from softfab.projectlib import project
from softfab.xmlgen import xhtml

def presentEmailForm():
    yield xhtml.h3[ 'SMTP relay' ]
    yield xhtml.p[
        textInput(name='smtpRelay', value=project.smtpRelay, size=60)
        ]
    yield xhtml.p[
        'Notification e-mails will be sent via this SMTP server.'
        ]
    yield xhtml.p[
        'Note: Currently SMTP authentication is not supported, '
        'so SMTP is only usable when access to the relay is restricted '
        'by network interface or IP address. '
        'Do not disable authentication on an SMTP relay accessible '
        'from the internet; spammers will find and abuse it.'
        ]

    yield xhtml.h3[ 'Sender address' ]
    yield xhtml.p[
        textInput(name='mailSender', value=project.mailSender, size=60)
        ]
    yield xhtml.p[
        'This address will be used in the "From:" field '
        'of notification e-mails.'
        ]

    yield xhtml.p[ actionButtons(Actions) ]

def presentForm():
    yield xhtml.h2[ 'E-mail' ]
    if sendmail is None:
        yield xhtml.p(class_='notice')[
            'Cannot send e-mail notifications.'
            ]
        yield xhtml.p[
            'Notifications by e-mail require the ', xhtml.code['twisted.mail'],
            ' package, which is not installed.'
            ]
        if (twistedVersion.major, twistedVersion.minor) < (17, 5):
            yield xhtml.p[
                'The Python 3 version of ', xhtml.code['twisted.mail'],
                ' is only available since Twisted 17.5.0, '
                'while this SoftFab is currently running on Twisted ',
                twistedVersion.public(), '.'
                ]
    yield makeForm()[
        presentEmailForm()
        ]

class Notifications_GET(FabPage):
    icon = 'IconNotification'
    description = 'Notifications'

    def checkAccess(self, req):
        pass

    def presentContent(self, proc):
        yield from presentForm()

# This is not an accurate check whether the address complies with the RFC,
# but it should accept real addresses while rejecting most invalid ones.
# Note that even if an e-mail address is syntactically correct, that still
# doesn't guarantee that it's an existing address, so putting much effort
# into syntax checking likely isn't worth it.
reMailAddress = re.compile(r'[^@\s]+@([^@.\s]+\.)*[^@.\s]+$')

Actions = Enum('Actions', 'SAVE CANCEL')

class Notifications_POST(FabPage):
    icon = 'IconNotification'
    description = 'Notifications'

    def checkAccess(self, req):
        req.checkPrivilege('p/m')

    class Arguments(PageArgs):
        action = EnumArg(Actions)
        smtpRelay = StrArg()
        mailSender = StrArg()

    class Processor(PageProcessor):

        def process(self, req):
            args = req.args

            action = args.action
            if action is not Actions.SAVE:
                assert action is Actions.CANCEL, action
                raise Redirect(self.page.getParentURL(req))

            smtpRelay = args.smtpRelay
            mailSender = args.mailSender
            if mailSender and not reMailAddress.match(mailSender):
                raise PresentableError(xhtml.p(class_='notice')[
                    'Mail sender ', xhtml.code[mailSender],
                    ' does not look like an e-mail address.'
                    ])
            project.setMailConfig(smtpRelay, mailSender)

    def presentContent(self, proc):
        yield xhtml.p[ 'Notification settings saved.' ]
        yield self.backToParent(proc.req)

    def presentError(self, proc, message):
        yield super().presentError(proc, message)
        yield from presentForm()
