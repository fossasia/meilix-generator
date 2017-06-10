from __future__ import with_statement

import contextlib
import itertools
import mock
import os
import pkg_resources
import ssl
import sys
import tempfile
import threading
import traceback
import unittest
import urllib
import urllib3

try:
    import json
except ImportError:
    import simplejson as json

from wsgiref.simple_server import make_server, WSGIServer

try:
    from urlparse import parse_qs
except Exception:
    from cgi import parse_qs

from dropbox.rest import RESTClientObject, RESTResponse, SDK_VERSION, ErrorResponse
from dropbox.six import b

SERVER_CERT_FILE = pkg_resources.resource_filename(__name__, 'server.crt')
SERVER_KEY_FILE = pkg_resources.resource_filename(__name__, 'server.key')

def clean_qs(d):
    return dict((k, v[0] if len(v) == 1 else v) for (k, v) in d.iteritems())

def json_dumpb(data):
    toret = json.dumps(data)
    if sys.version_info >= (3,):
        toret = toret.encode('utf8')
    return toret

class TestHTTPSConnection(unittest.TestCase):
    """
    Test urllib3's HTTPSConnectionPool to make sure it does SSL verification
    """

    @contextlib.contextmanager
    def listen_server(self, routes):
        HOST = "localhost"
        PORT = 8080

        def catch_exception(call):
            def new(*n, **kw):
                try:
                    call()
                except Exception:
                    traceback.print_exc()
            return new

        can_connect = threading.Event()

        @catch_exception
        def run_thread():
            time_to_die = [False]
            def simple_app(environ, start_response):
                path = environ['PATH_INFO']

                if path == '/die':
                    time_to_die[0] = True
                    start_response('200 OK', [('Content-type', 'text/plain')])
                    return [b('dead')]

                try:
                    result = routes[path]
                except KeyError:
                    start_response('404 NOT FOUND', [('Content-type', 'text/plain')])
                    return [b('NOT FOUND')]
                else:
                    start_response('200 OK', [('Content-type', 'text/plain')])
                    return [result]

            class SecureWSGIServer(WSGIServer):
                def get_request(self):
                    socket, client_address = WSGIServer.get_request(self)
                    socket = ssl.wrap_socket(socket,
                                             server_side=True,
                                             certfile=SERVER_CERT_FILE,
                                             keyfile=SERVER_KEY_FILE)
                    return socket, client_address

            server = make_server(HOST, PORT, simple_app, server_class=SecureWSGIServer)
            try:
                can_connect.set()
                while not time_to_die[0]:
                    server.handle_request()
            finally:
                server.server_close()

        t = threading.Thread(target=run_thread)
        t.start()
        a = None
        try:
            a = urllib3.HTTPSConnectionPool(
                host=HOST,
                port=PORT,
                cert_reqs=ssl.CERT_REQUIRED,
                ca_certs=SERVER_CERT_FILE
            )
            can_connect.wait()
            yield a
        finally:
            a and a.close()
            try:
                urllib.urlopen("https://localhost:%d/die" % PORT).close()
            except Exception:
                traceback.print_exc()
            t.join()

    def test_basic(self):
        path = "/"
        result = b("sup")
        with self.listen_server({path : result}) as a:
            response = a.request("GET", path)
            self.assertEqual(response.data, result)

    def test_basic_unicode(self):
        path = u"/\u4545"
        result = b("sup")
        with self.listen_server({path : result}) as a:
            # URLs can't have unicode in them,
            # they have to be quoted by urllib.quote
            self.assertRaises(Exception, a.request, "GET", path)

def setup_response_mock(json_data):
    """
    Sets up a mock to fake the output of the socket returned by urlopen
    It will return the stringified json_data
    """
    response = mock.Mock()
    response.status = 200
    # second call to read should return "" (it is called on close() to clean out socket
    response.read.side_effect = [json_dumpb(json_data), ""]
    response.release_conn.return_value = None
    mock_urlopen = mock.Mock()
    mock_urlopen.return_value = response
    return (response, mock_urlopen)

def check_mock(response, mock_urlopen, method, url, headers, post_params=None, body=None, raw_response=False):
    """
    Ensures that urlopen was called exactly once with the appropriate parameters.
    Also ensures that the urlopen response is read() exactly once to get the
    data off the socket.
    """
    body = urllib.urlencode(post_params) if post_params else body
    mock_urlopen.assert_called_with(
        method=method, url=url, body=body,
        headers=headers, preload_content=False
    )
    # called once to read. Once to make sure it's flushed
    calls = [] if raw_response else [mock.call(None), mock.call(RESTResponse.BLOCKSIZE)]
    response.read.assert_has_calls(calls)

class TestGet(unittest.TestCase):
    def test_basic(self):
        json_data = {'foo' : 'bar', 'baz' : 42}
        url = 'https://api.dropbox.com/metadata'

        # setup mocks
        response, mock_urlopen = setup_response_mock(json_data)

        # invoke code
        ret = RESTClientObject(mock_urlopen=mock_urlopen).GET(url)

        # check code
        check_mock(
            response, mock_urlopen, 'GET', url, 
            headers={'User-Agent' : 'OfficialDropboxPythonSDK/' + SDK_VERSION}
        )

        self.assertEqual(ret, json_data)

    def test_newline_in_header(self):
        json_data = {'foo' : 'bar', 'baz' : 42}
        url = 'https://api.dropbox.com/metadata'

        # setup mocks
        response, mock_urlopen = setup_response_mock(json_data)

        # invoke code
        self.assertRaises(ValueError,
                          RESTClientObject(mock_urlopen=mock_urlopen).GET,
                          url,
                          headers={'X-Foo': 'blah\nblah'})

    def test_non_200(self):
        json_data = {'error' : 'bar', 'user_error' : 42}
        url = 'https://api.dropbox.com/metadata'
        reason = 1
        headers = {'sup' : 'there'}

        # setup mocks
        response, mock_urlopen = setup_response_mock(json_data)

        # invoke code
        try:
            RESTClientObject(mock_urlopen=mock_urlopen).GET(url)
        except ErrorResponse, e:
            self.assertEqual(e.status, 304)
            self.assertEqual(e.error_msg, json_data['error'])
            self.assertEqual(e.user_error_msg, json_data['user_error'])
            self.assertEqual(e.reason, reason)
            self.assertEqual(e.headers, headers)
            self.assertEqual(e.body, json_data)

        # check code
        check_mock(
            response, mock_urlopen, 'GET', url, 
            headers={'User-Agent' : 'OfficialDropboxPythonSDK/' + SDK_VERSION}
        )

    def test_crazy_unicode(self):
        json_data = {'foo' : 'bar', 'baz' : 42}
        url = u'https://api.dropbox.com/metadata\u4545\u6f22/\u8a9e'

        # setup mocks
        response, mock_urlopen = setup_response_mock(json_data)

        # invoke code
        ret = RESTClientObject(mock_urlopen=mock_urlopen).GET(url)

        # check code
        check_mock(
            response, mock_urlopen, 'GET', url, 
            headers={'User-Agent' : 'OfficialDropboxPythonSDK/' + SDK_VERSION}
        )

        self.assertEqual(ret, json_data)

class TestPost(unittest.TestCase):
    def test_basic(self):
        json_data = {'foo' : 'bar', 'baz' : 42}
        url = 'https://api.dropbox.com/metadata'

        # setup mocks
        response, mock_urlopen = setup_response_mock(json_data)

        # invoke code
        ret = RESTClientObject(mock_urlopen=mock_urlopen).POST(url)

        # check code
        check_mock(
            response, mock_urlopen, 'POST', url,
            headers={'User-Agent' : 'OfficialDropboxPythonSDK/' + SDK_VERSION}
        )

        self.assertEqual(ret, json_data)

    def test_newline_in_header(self):
        json_data = {'foo' : 'bar', 'baz' : 42}
        url = 'https://api.dropbox.com/metadata'

        # setup mocks
        response, mock_urlopen = setup_response_mock(json_data)

        # invoke code
        self.assertRaises(ValueError,
                          RESTClientObject(mock_urlopen=mock_urlopen).POST,
                          url,
                          headers={'X-Foo': 'blah\nblah'})

    def _post_params(self, params):
        json_data = {'foo' : 'bar', 'baz' : 42}
        url = 'https://api.dropbox.com/metadata'
        post_params = params

        # setup mocks
        response, mock_urlopen = setup_response_mock(json_data)

        # invoke code
        ret = RESTClientObject(mock_urlopen=mock_urlopen).POST(url, params=post_params)

        # check code
        check_mock(
            response, mock_urlopen, 'POST', url, post_params=post_params,
            headers={'User-Agent' : 'OfficialDropboxPythonSDK/' + SDK_VERSION,
                     'Content-type' : 'application/x-www-form-urlencoded'}
        )

        self.assertEqual(clean_qs(parse_qs(mock_urlopen.call_args[1]['body'])),
                         post_params)
        self.assertEqual(ret, json_data)

    def test_post_params(self):
        self._post_params({'quux' : 'is', 'a' : 'horse'})

    def test_post_params_crazy_unicode_values(self):
        # Python 2 can't handle unicode in the key name
        self._post_params({u'quux' : 'is\u4545', 'a' : 'horse\u4545'})

class TestPut(unittest.TestCase):
    def test_body(self):
        json_data = {'foo' : 'bar', 'baz' : 42}
        url = 'https://api.dropbox.com/metadata'

        # setup mocks
        response, mock_urlopen = setup_response_mock(json_data)

        fd, path = tempfile.mkstemp()
        os.unlink(path)
        with os.fdopen(fd, 'wb+') as f:
            f.writelines(itertools.repeat(b("a5"), int(16 * 1024 / 2)))
            f.seek(0)

            # invoke code
            ret = RESTClientObject(mock_urlopen=mock_urlopen).PUT(url, body=f,
                                                                       raw_response=True)

            # check code
            check_mock(
                response, mock_urlopen, 'PUT', url, body=f, raw_response=True,
                headers={'User-Agent' : 'OfficialDropboxPythonSDK/' + SDK_VERSION}
            )

            assert ret.urllib3_response is response
