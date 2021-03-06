# SPDX-License-Identifier: BSD-3-Clause

'''
Sends a notification email using twisted.mail.smtp sendmail.
It can be used to send certain recipients an email about a certain event
that happened in the SoftFab (e.g. Job complete or Job failed).
'''

from email.message import Message
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
from typing import Iterable, Iterator, Tuple
import logging
import re

from twisted.internet.defer import Deferred
from twisted.python.failure import Failure

from softfab.projectlib import Project
from softfab.utils import IllegalStateError

# The twisted.mail package wasn't ported to Python 3 until Twisted 17.x.
try:
    # pylint: disable=useless-suppression
    # pylint: disable=ungrouped-imports
    from twisted.mail.smtp import sendmail
except ImportError:
    logging.error(
        "The twisted.mail package is not installed; "
        "sending notifcation e-mails won't work"
        )
    sendmail = None


_reAddressSep = re.compile(r'[\s,;]+')

class NotificationPresenter:
    """Interface for generating notification messages."""

    @property
    def singleLineSummary(self) -> str:
        raise NotImplementedError

    def keyValue(self) -> Iterator[Tuple[str, str]]:
        """Generates key-value pairs which give an overview of the most
        important properties of a job.
        This is used to create easily parseable files for external processes,
        such as mail filters.
        """
        raise NotImplementedError

def sendNotification(locator: str,
                     presenter: NotificationPresenter,
                     project: Project
                     ) -> None:
    '''Sends a notification about some event that happened in the SoftFab.
    The locator specifies how the message should be sent: the protocol and
    the recipient. The presenter is used to create the message body.
    Depending on the protocol, different presenter methods will be called.
    The presentation is constructed before this method returns, to ensure
    the data being presented is from the moment the event happened.
    The notification is sent asynchronously.
    '''
    protocol, path = locator.split(':', 1)
    if protocol == 'mailto':
        # Create message text.
        # TODO: Parse and validate address when it is input.
        recipients = _reAddressSep.split(path)

        def createPlaintextContent() -> Iterator[str]:
            yield 'SoftFab\n'
            for key, value in presenter.keyValue():
                if key is None:
                    yield ''
                else:
                    yield f'{key}:\t{value}'
            yield '\n' # force a new-line at end of file

        def createHTMLContent() -> Iterator[str]:
            yield '<HTML>'
            yield '<HEAD></HEAD>'
            yield '<BODY>'
            yield '<H3>SoftFab notification email</H3>'
            yield f'<B>{presenter.singleLineSummary}</B>'
            for key, value in presenter.keyValue():
                if key is None:
                    yield ''
                elif key == 'URL':
                    yield f'<P>{value}</P>'
            yield '<TABLE border="1" style="margin:4px 10px;" summary="tasks">'
            for key, value in presenter.keyValue():
                if key is None:
                    yield ''
                elif key.endswith('name'):
                    yield f'<TR><TD>{value}</TD>'
                elif key.endswith('result'):
                    yield f'<TD>{value}</TD>'
                elif key.endswith('summary'):
                    yield f'<TD>{value}</TD></TR>'
            yield '</TABLE>'
            yield '</BODY></HTML> '

        messageStr = MIMEMultipart('alternative')
        messageStr["Subject"] = presenter.singleLineSummary
        textpart = MIMEText('\n '.join(createPlaintextContent()), 'plain')
        htmlpart = MIMEText('\n '.join(createHTMLContent()), 'html')
        messageStr.attach(textpart)
        messageStr.attach(htmlpart)
        # Send message asynchronously.
        if not project['mailnotification']:
            logging.debug(
                'Dropping notification e-mail because notifications '
                'by e-mail are disabled'
                )
        elif sendmail is None:
            logging.warning(
                'Dropping notification e-mail because twisted.mail is '
                'not installed'
                )
        else:
            _sendMailLogged(
                project.smtpRelay, project.mailSender, recipients, messageStr
                )
    else:
        logging.error('Unknown notification protocol "%s"', protocol)

def _logMailSendFailure(failure: Failure) -> Failure:
    logging.error('Notification sending failed: %s', failure.getErrorMessage())
    return failure

def _sendMailLogged(smtpRelay: str,
                    mailSender: str,
                    recipients: Iterable[str],
                    message: Message
                    ) -> Deferred:
    if sendmail is None:
        raise IllegalStateError('twisted.mail is not installed')
    message['From'] = mailSender
    message['To'] = ', '.join(recipients)
    message['Date'] = formatdate()
    return sendmail(
        smtpRelay, mailSender, recipients, message.as_string().encode()
        ).addErrback(_logMailSendFailure)

_testMailBody = '''
This is a notification test e-mail sent by SoftFab.
'''

def sendTestMail(smtpRelay: str, mailSender: str, recipient: str) -> Deferred:
    message = MIMEText(_testMailBody)
    message['Subject'] = 'SoftFab notification test'
    recipients = _reAddressSep.split(recipient)
    return _sendMailLogged(smtpRelay, mailSender, recipients, message)
