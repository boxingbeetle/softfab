# SPDX-License-Identifier: BSD-3-Clause

from twisted import version as twistedVersion

from softfab.FabPage import FabPage
from softfab.formlib import makeForm, textInput
from softfab.notification import sendmail
from softfab.projectlib import project
from softfab.xmlgen import xhtml

def presentNoEmail():
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

def presentEmailForm():
    yield xhtml.h3[ 'SMTP relay' ]
    yield xhtml.p[
        textInput(value=project.smtpRelay, size=60)
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
        textInput(value=project.mailSender, size=60)
        ]
    yield xhtml.p[
        'This address will be used in the "From:" field '
        'of notification e-mails.'
        ]

class Notifications(FabPage):
    icon = 'IconNotification'
    description = 'Notifications'

    def checkAccess(self, req):
        pass

    def presentContent(self, proc):
        yield xhtml.h2[ 'E-mail' ]
        if sendmail is None:
            yield from presentNoEmail()
        else:
            yield makeForm()[
                presentEmailForm()
                ]
