# SPDX-License-Identifier: BSD-3-Clause

from typing import (
    Dict, Iterator, Mapping, Optional, Sequence, Tuple, Union, cast
)
import re

from softfab.utils import cachedProperty

# Content negotiation is described in:
#   https://tools.ietf.org/html/rfc7231#section-5.3

def parseAcceptValue(
        accepted: Optional[str]
        ) -> Iterator[Tuple[str, Mapping[str, str]]]:
    '''Parses an HTTP content negotiation header.
    Iterates through the things that are accepted; each element is a pair
    consisting of a name and a parameters dictionary.
    If None is passed, the iteration will be empty.
    '''
    if accepted is None:
        return
    # TODO: The HTTP spec allows quoted strings as parameter values, which
    #       could contain characters ",", ";" or "=" and confuse our parser.
    #       In practice, no-one seems to use parameters at all (except "q").
    for elem in accepted.split(','):
        parts = elem.split(';')
        name = parts[0].strip()
        params = {}
        for paramStr in parts[1 : ]:
            try:
                key, value = paramStr.split('=')
            except ValueError:
                # Ignore invalid parameters.
                pass
            else:
                params[key.strip()] = value.strip()
        yield name, params

def parseAcceptQuality(
        accepted: Optional[str]
        ) -> Iterator[Tuple[str, float]]:
    '''Parses an HTTP content negotiation header.
    Iterates through the things that are accepted; each element is a pair
    consisting of a name and a floating point value between 0.0 and 1.0
    that is parsed from the "q" (quality) parameter.
    If None is passed, the iteration will be empty.
    '''
    for name, parameters in parseAcceptValue(accepted):
        qualityStr = parameters.get('q', '1')
        try:
            quality = float(qualityStr)
        except ValueError:
            # Ignore invalid entries.
            pass
        else:
            yield name, min(max(quality, 0.0), 1.0)

class AcceptedEncodings(Dict[str, float]):
    '''Dictionary that stores information about accepted encodings:
    keys are encoding names, values are floating-point weights.
    A lookup of an unspecified encoding will default to the value for "*";
    if no value for "*" is given either, the default will be 0.0, except
    for "identity", where it will be a small positive value.
    '''

    @classmethod
    def parse(cls, accepted: Optional[str]) -> 'AcceptedEncodings':
        '''Parses an HTTP "Accept-Encoding" header, or None presenting
        the absence of such a header.
        '''
        return cls(parseAcceptQuality(accepted))

    def __init__(self, iterable: Iterator[Tuple[str, float]]):
        super().__init__(iterable)
        # Convert deprecated names to preferred ones.
        # Note that "x-deflate" does not occur in RFC 7230, but it is
        # sent by some browsers, such as Konqueror.
        for encoding in 'compress', 'deflate', 'gzip':
            value = self.pop('x-' + encoding, None)
            if value is not None:
                self.setdefault(encoding, value)

    def __missing__(self, key: str) -> float:
        return self.get('*', 0.1 if key == 'identity' else 0.0)

class UserAgent:

    __reUserAgentPart = re.compile(r'\([^\)]*\)|[^ ]+')
    @classmethod
    def __parseUserAgent(cls,
            userAgent: str
            ) -> Iterator[Union[str, Sequence[str]]]:
        matcher = cls.__reUserAgentPart
        i = 0
        while True:
            match = matcher.search(userAgent, i)
            if match is None:
                break
            i = match.end()
            part = match.group()
            if part.startswith('('):
                if not part.endswith(')'):
                    # Broken user agent string, stop parsing.
                    break
                # Comment string.
                yield tuple(s.strip() for s in part[1 : -1].split(';'))
            else:
                # Product string.
                yield part

    def __init__(self, userAgentHeader: str, acceptHeader: str):
        self.__userAgentHeader = userAgentHeader
        self.__acceptHeader = acceptHeader

    @property
    def rawUserAgent(self) -> str:
        '''The User-Agent header that was part of the request, or None
        if the header wasn't present.
        Page generation code should use the various properties of this
        class instead of the raw header, but for debugging it can be
        useful to have access to the raw header.
        '''
        return self.__userAgentHeader

    @cachedProperty
    def client(self) -> Optional[str]:
        '''Best effort to identify the user agent that made this request.
        Contains a string in the form "name/version" if successful,
        "name" if the name could be determined but the version could not,
        or None if it has no clue.
        '''
        userAgent = self.__userAgentHeader
        if userAgent is None:
            return None

        main = None # type: Optional[str]
        compat = None # type: Optional[str]
        for productOrComment in self.__parseUserAgent(userAgent):
            if isinstance(productOrComment, tuple):
                comment = cast(Sequence[str], productOrComment)
                if main is not None and compat is None:
                    if len(comment) >= 2 and comment[0] == 'compatible':
                        # Internet Explorer identifies as "MSIE x.y" instead of
                        # "MSIE/x.y", but Konqueror uses "Konqueror/x.y".
                        compat = '/'.join(comment[1].split(' ')[ : 2])
                        # Note: Outlook identifies as both MSIE and MSOffice.
                        # Since the rendering engine is that of Office, that
                        # is the most relevant for us.
                        if comment[1].startswith('MSIE '):
                            for item in comment[2 : ]:
                                if item.startswith('MSOffice '):
                                    compat = '/'.join(item.split(' ')[ : 2])
            else:
                product = cast(str, productOrComment)
                if main is None:
                    if product.startswith('Mozilla/'):
                        # Several browser families identify as Mozilla, so keep
                        # looking for more clues.
                        main = product
                    else:
                        # Assume we can trust the name of main product.
                        return product
                elif product.startswith('Safari/'):
                    # Note: Chrome identifies as both Chrome and Safari.
                    if not main.startswith('Chrome/'):
                        main = product
                        compat = None
                elif product.startswith('Chrome/'):
                    main = product
                    compat = None
                else:
                    # Second product encountered, so any following "compatible"
                    # comments will likely apply to the second product.
                    if compat is None:
                        compat = ''
        return compat if compat else main

    @cachedProperty
    def family(self) -> Optional[str]:
        '''Best effort to identify the family of the user agent that
        made this request.
        Contains the family name, or None if it has no clue.
        Recognized families are Mozilla, MSIE, Opera, Safari, Chrome and
        Konqueror.
        '''
        client = self.client
        return client.split('/', 1)[0] if client else None

    @cachedProperty
    def version(self) -> Optional[Sequence[int]]:
        '''Best effort to identify the version of the user agent that
        made this request. Contains a tuple of integers, or None if it has
        no clue. For example, Firefox 2.x identifies as Mozilla 5.0, so the
        returned value is (5, 0).
        '''
        client = self.client
        if not client:
            return None
        try:
            name_, versionStr = client.split('/', 1)
        except ValueError:
            return None
        i = 0
        while i < len(versionStr):
            ch = versionStr[i]
            if ch.isdigit() or ch == '.':
                i += 1
            else:
                break
        if i == 0:
            return None
        try:
            return tuple(int(part) for part in versionStr[ : i].split('.'))
        except ValueError:
            # This can happen when versionStr contains "..".
            return None

    @cachedProperty
    def operatingSystem(self) -> Optional[str]:
        '''Best effort to identify the operating system of the user
        agent that made this request.
        Contains a string, or None if it has no clue.
        Be careful when interpreting returned strings, since the exact format
        can differ per user agent. For example Linux is reported as "Linux i686"
        by Firefox 2.0.0.14 and as just "Linux" by Konqueror 3.5.7.
        Windows versions seem to be returned identically by all common browsers,
        but are not what you might expect, for example Windows XP identifies as
        "Windows NT 5.1".
        '''
        userAgent = self.__userAgentHeader
        if userAgent is None:
            return None

        for productOrComment in self.__parseUserAgent(userAgent):
            # OS is always mentioned in a comment.
            if isinstance(productOrComment, tuple):
                # Prefer longer matches over short ones.
                commentParts = sorted(
                    cast(Sequence[str], productOrComment),
                    key=len, reverse=True
                    )
                # Look for known operating system names.
                for osName in (
                    'Windows', 'Linux', 'Macintosh',
                    'FreeBSD', 'OpenBSD', 'NetBSD',
                    'Solaris', 'SunOS', 'IRIX', 'HP-UX',
                    ):
                    for commentPart in commentParts:
                        if commentPart.startswith(osName):
                            return commentPart

        return None

    @cachedProperty
    def acceptedTypes(self) -> Mapping[str, float]:
        '''A parsed version of the HTTP "accept" header, which describes
        the media types that the user agent is capable of handling and
        its preferences for one type over another.
        The value is a mapping of media type to quality value.
        '''
        accepted = self.__acceptHeader
        if accepted is None:
            # Assume that the client accepts all media types, per RFC 7231
            # section 5.3.2.
            return {'*/*': 1.0}
        else:
            return dict(parseAcceptQuality(accepted))

    @cachedProperty
    def acceptsXHTML(self) -> bool:
        '''True iff the user agent is likely to be able to display
        XHTML when it is served as XML.
        '''
        # Follow the W3C guideline for choosing media type:
        #   http://www.w3.org/TR/xhtml-media-types/#media-types
        return self.acceptedTypes.get('application/xhtml+xml', 0.0) > 0.0
