#!/usr/bin/env python3

# milter-addmessageid - Milter to add message-id to mails without it.
#
# Written in 2014 by Pol Van Aubel <dev@polvanaubel.com>
# Updated in 2022 to python3 by Pol Van Aubel <dev@polvanaubel.com>
#
# To the extent possible under law, the author(s) have dedicated all copyright
# and related and neighboring rights to this software to the public domain
# worldwide. This software is distributed without any warranty.
#
# You should have received a copy of the CC0 Public Domain Dedication along
# with this software. If not, see
# <http://creativecommons.org/publicdomain/zero/1.0/>.
# 
# 
# This software is built on the pure-python libmilter implementation by Jay
# Deiman (crustymonkey): https://github.com/crustymonkey/python-libmilter
# which is licensed under the GNU Lesser General Public License v3.0
#

"""Python-based milter to add message-id headers to mails without them.

The Message-ID header is an important piece of dat in today's e-mail
infrastructure. Unfortunately, RFC 5322 does not mandate them in strong enough
terms:
   Though listed as optional in the table in section 3.6, every message
   SHOULD have a "Message-ID:" field.  Furthermore, reply messages
   SHOULD have "In-Reply-To:" and "References:" fields as appropriate
   and as described below.

Because it was not worded as "MUST", there are still broken MUA's out there,
used by ignorant people (android's native mail client is one of them), that do
not add the Message-ID field. Since this screws up duplicate detection in my
mailclient (alot / notmuch), I've created this milter to add a unique
message-id to each e-mail not carrying one. This also enables any client
working with this mail to use the Message-ID as the basis for any thread by
using it in In-Reply-To fields.
"""

import os
import socket
import sys
import time

import libmilter as lm


class MessageIDMilter(lm.ThreadMixin, lm.MilterProtocol):
    """This milter detects messages without a Message-ID header and adds it.

    This milter is designed to receive all headers for each mail from the MTA.
    It does a case-insensitive match on "Message-ID" for each header. If it is
    present, the milter does not modify the message at all. If it is not
    present, the milter generates a (very likely) unique Message-ID and adds
    it to the e-mail.
    """
    has_messageid = False

    def __init__(self, opts=0, protos=lm.SMFIP_ALLPROTOS ^ lm.SMFIP_NOHDRS):
        """Initialize the milter with appropriate flags.

        We only want headers, so set the SMFIP-flags that we don't want or
        respond to anything except headers. We will then get callbacks for the
        headers, end-of-body (which is actually end-of-message?), abort and
        close.
        """
        # inherit parents
        lm.MilterProtocol.__init__(self, opts, protos)
        lm.ThreadMixin.__init__(self)

    def log(self, message):
        """Print the message to stdout."""
        print(message, file=sys.stdout)
        sys.stdout.flush()

    def header(self, key, val, cmdDict):
        """Check whether the header is Message-ID.

        If Message-ID is found, we don't want to add one to this e-mail.
        However, semantics of sending a milter ACCEPT are unclear, so since
        processing is cheap, just CONTINUE.
        """
        # self.log("Header received: {!s} with value {!s}".format(key, val))
        if key.lower() == b"message-id":
            self.has_messageid = True
        return lm.CONTINUE

    def eob(self, cmdDict):
        """Add the Message-ID to the e-mail if it doesn't have one."""
        # self.log("End of message received.")
        if self.has_messageid:
            self.has_messageid = False
            return lm.CONTINUE
        else:
            key = b"Message-ID"
            val = self.create_messageid()
            self.log("Message without Message-ID received. "
                     "Adding header: {!s} with value {!s}".format(key, val))
            self.addHeader(key, val)
            return lm.CONTINUE

    def close(self):
        """Reset state to ensure clean reuse if necessary."""
        # self.log("Close received.")
        self.has_messageid = False

    def abort(self):
        """Reset state to ensure clean reuse if necessary."""
        # self.log("Abort received.")
        self.has_messageid = False

    def create_messageid(self):
        """Create a unique message ID.

        Based on recommendations from <http://www.jwz.org/doc/mid.html>. Since
        we cannot guarantee uniqueness for message ID's using the fqdn of the
        system that actually sent the message, use our own fqdn. The addition
        of a microsecond-precision clock and 8 bytes from urandom should be
        sufficient to guarantee uniqueness. Also, we use BASE16 encoding, not
        BASE36.

        If the system does not return any string for fqdn, we substitute 8
        random bytes.
        """
        microseconds = str(int(time.time() * 1000000))
        random_part = os.urandom(8).hex()
        fqdn = socket.getfqdn()
        if not fqdn:
            fqdn = os.urandom(8).hex()
        message_id = " <" + microseconds + "." + random_part + "@" + fqdn + ">"
        return message_id.encode("utf8")


def run_messageidmilter():
    import signal

    socketpath = "/var/run/milter"
    try:
        os.mkdir(socketpath, 0o755)
    except OSError:
        # directory already exists, continue.
        pass
    socketname = "messageidmilter"

    # We want to be able to add headers, so tell the MTA that.
    opts = lm.SMFIF_ADDHDRS

    # We're assuming that most e-mail, i.e. 99.9% of it, actually does carry
    # the Message-ID header. Since expensive operations (reading /dev/urandom)
    # only happen if a mail does not have the header, the overhead of forking
    # an interpreter for each incoming connection from the MTA is not worth it
    factory = lm.ThreadFactory(socketpath + "/" + socketname,
                               MessageIDMilter, opts)

    def sighandler(signum, frame):
        factory.close()
        sys.exit(1)

    signal.signal(signal.SIGINT, sighandler)
    signal.signal(signal.SIGQUIT, sighandler)
    signal.signal(signal.SIGTERM, sighandler)

    try:
        factory.run()
    except Exception:
        e = sys.exc_info()
        print("EXCEPTION OCCURRED: {!s}".format(e), file=sys.stderr)
        sys.stderr.flush()
        factory.close()
        raise


if __name__ == "__main__":
    run_messageidmilter()
