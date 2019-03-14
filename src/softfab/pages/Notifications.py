# SPDX-License-Identifier: BSD-3-Clause

from enum import Enum
import re
import time

from twisted import version as twistedVersion
from twisted.internet.defer import inlineCallbacks

from softfab.FabPage import FabPage
from softfab.Page import PageProcessor, PresentableError, Redirect
from softfab.formlib import actionButtons, checkBox, makeForm, textInput
from softfab.notification import sendTestMail, sendmail
from softfab.pageargs import BoolArg, EnumArg, PageArgs, StrArg
from softfab.projectlib import project
from softfab.xmlgen import XMLContent, xhtml

def presentEmailForm():
    yield xhtml.p[
        checkBox(name='mailNotification')['Send notifications via e-mail']
        ]

    yield xhtml.h3[ 'SMTP relay' ]
    yield xhtml.p[textInput(name='smtpRelay', size=60)]
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
    yield xhtml.p[textInput(name='mailSender', size=60)]
    yield xhtml.p[
        'This address will be used in the "From:" field '
        'of notification e-mails.'
        ]

    yield xhtml.p[ actionButtons(Actions.SAVE, Actions.CANCEL) ]

    yield xhtml.h3[ 'Test' ]
    yield xhtml.p[ 'Send a test e-mail to:' ]
    yield xhtml.p[textInput(name='mailRecipient', size=60)]
    yield xhtml.p[ actionButtons(Actions.TEST) ]

def presentForm(args):
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
    yield makeForm(args=args)[ presentEmailForm() ]

class Notifications_GET(FabPage[FabPage.Processor, FabPage.Arguments]):
    icon = 'IconNotification'
    description = 'Notifications'

    def checkAccess(self, req):
        pass

    def presentContent(self, proc: FabPage.Processor) -> XMLContent:
        yield from presentForm(MailConfigArgs(
            mailNotification=project['mailnotification'],
            smtpRelay=project.smtpRelay,
            mailSender=project.mailSender,
            ))

# This is not an accurate check whether the address complies with the RFC,
# but it should accept real addresses while rejecting most invalid ones.
# Note that even if an e-mail address is syntactically correct, that still
# doesn't guarantee that it's an existing address, so putting much effort
# into syntax checking likely isn't worth it.
reMailAddress = re.compile(r'[^@\s]+@([^@.\s]+\.)*[^@.\s]+$')

Actions = Enum('Actions', 'TEST SAVE CANCEL')

class MailConfigArgs(PageArgs):
    mailNotification = BoolArg()
    smtpRelay = StrArg()
    mailSender = StrArg()

class Notifications_POST(FabPage['Notifications_POST.Processor', 'Notifications_POST.Arguments']):
    icon = 'IconNotification'
    description = 'Notifications'

    def checkAccess(self, req):
        req.checkPrivilege('p/m')

    class Arguments(MailConfigArgs):
        action = EnumArg(Actions)
        mailRecipient = StrArg()

    class Processor(PageProcessor):

        @inlineCallbacks
        def process(self, req):
            args = req.args
            action = args.action
            smtpRelay = args.smtpRelay
            mailSender = args.mailSender

            if action is Actions.CANCEL:
                raise Redirect(self.page.getParentURL(req))
            elif action is Actions.TEST:
                # pylint: disable=attribute-defined-outside-init
                recipient = args.mailRecipient
                if not recipient:
                    raise PresentableError(xhtml.p(class_='notice')[
                        'Please enter a recipient address '
                        'to send the test-email to'
                        ])
                self.mailTestTime = time.localtime()
                try:
                    numOk_, addresses = yield sendTestMail(
                        smtpRelay, mailSender, args.mailRecipient
                        )
                except Exception as ex:
                    raise PresentableError(xhtml.p(class_='notice')[
                        'Sending test mail failed: %s' % ex
                        ])
                self.mailTestResult = tuple(
                    ( address.decode(errors='replace'),
                      '%s (%d)' % (resp.decode(errors='replace'), code) )
                    for address, code, resp in addresses
                    )
            elif action is Actions.SAVE:
                if mailSender and not reMailAddress.match(mailSender):
                    raise PresentableError(xhtml.p(class_='notice')[
                        'Mail sender ', xhtml.code[mailSender],
                        ' does not look like an e-mail address.'
                        ])
                project.setMailConfig(
                    args.mailNotification, smtpRelay, mailSender
                    )
            else:
                assert False, action

    def presentContent(self, proc: Processor) -> XMLContent:
        action = proc.args.action
        if action is Actions.TEST:
            yield xhtml.p(class_='notice')[
                'Result for notification test of %s:'
                % time.strftime('%H:%M:%S', proc.mailTestTime)
                ]
            yield xhtml.p[
                xhtml.br.join(
                    (address, ' : ', result)
                    for address, result in proc.mailTestResult
                    )
                ]
            yield from presentForm(proc.args)
        elif action is Actions.SAVE:
            yield xhtml.p[ 'Notification settings saved.' ]
            yield self.backToParent(proc.req)
        else:
            assert False, action

    def presentError(self, proc: Processor, message: str) -> XMLContent:
        yield super().presentError(proc, message)
        yield from presentForm(proc.args)
